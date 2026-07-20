import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEV_DEFAULT_SALT = b"lianghua-dev-config-key"


def _derive_dev_key() -> bytes:
    digest = hashlib.sha256(_DEV_DEFAULT_SALT + settings.database_url.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    raw = settings.config_key.strip()
    if raw:
        key = raw.encode() if isinstance(raw, str) else raw
    else:
        logger.warning("LIANGHUA_CONFIG_KEY 未配置，使用开发环境派生密钥（不可用于生产）")
        key = _derive_dev_key()
    return Fernet(key)


def encrypt_str(plain: str) -> bytes:
    if not plain:
        return b""
    return _get_fernet().encrypt(plain.encode("utf-8"))


def decrypt_str(cipher: bytes | None) -> str:
    if not cipher:
        return ""
    return _get_fernet().decrypt(cipher).decode("utf-8")
