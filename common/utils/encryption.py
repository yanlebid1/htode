# common/utils/encryption.py
"""
PII encryption utilities for at-rest encryption of sensitive user data.

Uses Fernet (AES-128-CBC) for reversible encryption and HMAC-SHA256
for deterministic search tokens that enable exact-match queries.
"""

import hashlib
import hmac
import os
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Inline secret reader to avoid circular imports with common.utils.secrets
def _read_secret(name: str, fallback_env: str) -> Optional[str]:
    secret_path = f"/run/secrets/{name}"
    try:
        with open(secret_path) as f:
            value = f.read().strip()
            if value:
                return value
    except (FileNotFoundError, PermissionError):
        pass
    return os.getenv(fallback_env)

_ENCRYPTION_KEY: Optional[str] = _read_secret("encryption_master_key", "ENCRYPTION_MASTER_KEY")
_HMAC_KEY: Optional[str] = _read_secret("encryption_hmac_key", "ENCRYPTION_HMAC_KEY")

_fernet: Optional[Fernet] = None


def _get_fernet() -> Optional[Fernet]:
    """Lazy-init Fernet instance from the master key."""
    global _fernet, _ENCRYPTION_KEY
    if _fernet is not None:
        return _fernet
    # Re-read in case env was set after module import
    _ENCRYPTION_KEY = _read_secret("encryption_master_key", "ENCRYPTION_MASTER_KEY") or _ENCRYPTION_KEY
    if not _ENCRYPTION_KEY:
        return None
    try:
        _fernet = Fernet(_ENCRYPTION_KEY.encode() if isinstance(_ENCRYPTION_KEY, str) else _ENCRYPTION_KEY)
        return _fernet
    except Exception:
        logger.error("Invalid ENCRYPTION_MASTER_KEY — cannot initialise Fernet")
        return None


def _get_hmac_key() -> Optional[bytes]:
    """Return HMAC key as bytes, or None if not configured."""
    global _HMAC_KEY
    _HMAC_KEY = _read_secret("encryption_hmac_key", "ENCRYPTION_HMAC_KEY") or _HMAC_KEY
    if not _HMAC_KEY:
        return None
    return _HMAC_KEY.encode() if isinstance(_HMAC_KEY, str) else _HMAC_KEY


def is_encryption_configured() -> bool:
    """Check whether both encryption keys are available."""
    return bool(_read_secret("encryption_master_key", "ENCRYPTION_MASTER_KEY")) and bool(_read_secret("encryption_hmac_key", "ENCRYPTION_HMAC_KEY"))


def encrypt(plaintext: str) -> Optional[str]:
    """
    AES-128-CBC via Fernet — reversible encryption for storage.

    Returns base64-encoded ciphertext, or None if encryption is not configured.
    """
    if not plaintext:
        return None
    f = _get_fernet()
    if f is None:
        return None
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> Optional[str]:
    """
    Decrypt Fernet-encrypted value.

    Returns plaintext, or None if decryption fails or encryption is not configured.
    """
    if not ciphertext:
        return None
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or wrong key")
        return None


def make_search_token(plaintext: str) -> Optional[str]:
    """
    HMAC-SHA256 deterministic token — enables exact-match queries
    without exposing plaintext.

    Returns hex-encoded 64-char token, or None if not configured.
    """
    if not plaintext:
        return None
    key = _get_hmac_key()
    if key is None:
        return None
    return hmac.new(key, plaintext.lower().encode(), hashlib.sha256).hexdigest()


def generate_fernet_key() -> str:
    """Generate a new Fernet key (for initial setup)."""
    return Fernet.generate_key().decode()


def generate_hmac_key() -> str:
    """Generate a new HMAC key (for initial setup)."""
    return os.urandom(32).hex()
