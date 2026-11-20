"""Hashing of LINE identifiers and LINE webhook signature verification."""
import base64
import hashlib
import hmac

from app.core.config import get_settings


def hash_ref(raw_id: str) -> str:
    """Stable, non-reversible reference for a LINE user/group id. The raw id is never persisted."""
    secret = get_settings().id_hash_secret.encode()
    return hmac.new(secret, raw_id.encode(), hashlib.sha256).hexdigest()


def verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")
