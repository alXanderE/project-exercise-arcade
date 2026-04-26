from datetime import datetime, timedelta, timezone
import secrets

from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import BadRequest


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(password, password_hash):
    try:
        return check_password_hash(password_hash, password)
    except (ValueError, BadRequest):
        return False


def build_session(days):
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    return token, expires_at
