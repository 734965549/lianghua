from sqlalchemy.orm import Session

from app.core.security import decrypt_str, encrypt_str
from app.db.models.system_config import SystemConfig
from app.repositories.base import BaseRepository


class SystemConfigRepository(BaseRepository[SystemConfig]):
    model = SystemConfig

    def get_all(self) -> list[SystemConfig]:
        return self.db.query(SystemConfig).order_by(SystemConfig.config_key).all()

    def get_by_key(self, config_key: str) -> SystemConfig | None:
        return self.db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()

    def upsert(
        self,
        *,
        config_key: str,
        value: str,
        is_sensitive: bool = False,
        description: str = "",
    ) -> SystemConfig:
        row = self.get_by_key(config_key)
        if row is None:
            row = SystemConfig(config_key=config_key, description=description)
            self.db.add(row)

        if is_sensitive:
            row.is_sensitive = True
            row.encrypted_value = encrypt_str(value) if value else None
            row.config_value = ""
        else:
            row.is_sensitive = False
            row.config_value = value
            row.encrypted_value = None

        if description:
            row.description = description
        self.db.flush()
        return row

    def get_value(self, config_key: str, default: str = "") -> str:
        row = self.get_by_key(config_key)
        if row is None:
            return default
        if row.is_sensitive:
            return decrypt_str(row.encrypted_value) if row.encrypted_value else default
        return row.config_value or default

    def is_configured(self, config_key: str) -> bool:
        row = self.get_by_key(config_key)
        if row is None:
            return False
        if row.is_sensitive:
            return bool(row.encrypted_value)
        return bool(row.config_value)
