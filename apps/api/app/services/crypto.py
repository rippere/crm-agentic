import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """Derive a 32-byte Fernet key from SECRET_KEY using SHA-256."""
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_token(plain: str) -> str:
    """Encrypt a plaintext token string. Returns a base64url-encoded ciphertext string."""
    f = _get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a previously encrypted token string. Returns the original plaintext."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()
