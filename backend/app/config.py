import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://sanjeev@127.0.0.1/Textract"
    upload_dir: str = "uploads"
    parser_version: str = "1.0.0"
    screenshot_dpi: int = 300

    # AWS (optional for Textract)
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None  # Required for temporary/federated credentials (e.g. aws login)
    aws_region: str = "us-east-1"
    # S3 bucket for multi-page Textract (async API requires S3)
    aws_s3_bucket: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"

    def get_upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        path.mkdir(parents=True, exist_ok=True)
        return path


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
