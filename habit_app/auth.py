from datetime import datetime, timedelta, timezone
import secrets

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def build_session(days):
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    return token, expires_at
