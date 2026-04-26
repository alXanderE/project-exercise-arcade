from datetime import datetime, timezone

from flask import current_app

try:
    from pymongo import ASCENDING, MongoClient
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    ASCENDING = 1
    MongoClient = None


_mongo_client = None


def mongo_auth_enabled():
    return bool(current_app.config.get("MONGODB_URI")) and MongoClient is not None


def mongo_auth_unavailable_reason():
    if not current_app.config.get("MONGODB_URI"):
        return "MONGODB_URI is not configured."
    if MongoClient is None:
        return "PyMongo is not installed."
    return None


def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(current_app.config["MONGODB_URI"])
    return _mongo_client


def get_auth_collection():
    database = get_mongo_client()[current_app.config["MONGODB_DB"]]
    return database[current_app.config["MONGODB_USERS_COLLECTION"]]


def ensure_mongo_auth_indexes():
    if not mongo_auth_enabled():
        return

    users = get_auth_collection()
    users.create_index([("email", ASCENDING)], unique=True)
    users.create_index([("display_name_lower", ASCENDING)], unique=True)
    users.create_index([("sql_user_id", ASCENDING)], unique=True, sparse=True)
    users.create_index([("session_token", ASCENDING)], unique=True, sparse=True)


def current_timestamp():
    return datetime.now(timezone.utc)


def normalize_auth_document(document):
    if not document:
        return None

    return {
        **document,
        "email": str(document.get("email") or "").strip().lower(),
        "display_name": str(document.get("display_name") or "").strip(),
        "display_name_lower": str(
            document.get("display_name_lower") or document.get("display_name") or ""
        )
        .strip()
        .lower(),
    }


def find_auth_user_by_email(email):
    if not mongo_auth_enabled():
        return None

    return normalize_auth_document(
        get_auth_collection().find_one({"email": str(email or "").strip().lower()})
    )


def find_auth_user_by_display_name(display_name):
    if not mongo_auth_enabled():
        return None

    return normalize_auth_document(
        get_auth_collection().find_one(
            {"display_name_lower": str(display_name or "").strip().lower()}
        )
    )


def find_auth_user_by_identifier(identifier):
    normalized = str(identifier or "").strip().lower()
    if not mongo_auth_enabled() or not normalized:
        return None

    return normalize_auth_document(
        get_auth_collection().find_one(
            {
                "$or": [
                    {"email": normalized},
                    {"display_name_lower": normalized},
                ]
            }
        )
    )


def find_auth_user_by_session_token(session_token):
    if not mongo_auth_enabled() or not session_token:
        return None

    document = get_auth_collection().find_one(
        {
            "session_token": session_token,
            "session_expires_at": {"$gt": current_timestamp()},
        }
    )
    return normalize_auth_document(document)


def create_auth_user(email, display_name, password_hash, sql_user_id):
    users = get_auth_collection()
    timestamp = current_timestamp()
    document = {
        "email": str(email).strip().lower(),
        "display_name": str(display_name).strip(),
        "display_name_lower": str(display_name).strip().lower(),
        "password_hash": password_hash,
        "sql_user_id": sql_user_id,
        "points": 0,
        "level": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    users.insert_one(document)
    return normalize_auth_document(document)


def update_auth_user(email, **updates):
    if not mongo_auth_enabled():
        return None

    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return None

    update_fields = dict(updates)
    if "display_name" in update_fields:
        update_fields["display_name"] = str(update_fields["display_name"]).strip()
        update_fields["display_name_lower"] = update_fields["display_name"].lower()
    if "email" in update_fields:
        update_fields["email"] = str(update_fields["email"]).strip().lower()
    update_fields["updated_at"] = current_timestamp()

    get_auth_collection().update_one(
        {"email": normalized_email},
        {"$set": update_fields},
    )
    return find_auth_user_by_email(update_fields.get("email", normalized_email))


def set_auth_session(email, session_token, expires_at):
    return update_auth_user(
        email,
        session_token=session_token,
        session_expires_at=expires_at,
    )


def clear_auth_session(email):
    if not mongo_auth_enabled():
        return None

    normalized_email = str(email or "").strip().lower()
    get_auth_collection().update_one(
        {"email": normalized_email},
        {
            "$unset": {
                "session_token": "",
                "session_expires_at": "",
            },
            "$set": {"updated_at": current_timestamp()},
        },
    )
    return find_auth_user_by_email(normalized_email)
