import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://sanjeev@127.0.0.1/Textract"
    upload_dir: str = "uploads"
    parser_version: str = "1.0.0"
    screenshot_dpi: int = 400

    # AWS (optional for Textract)
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None  # Required for temporary/federated credentials (e.g. aws login)
    aws_region: str = "us-east-1"
    # S3 bucket for multi-page Textract (async API requires S3)
    aws_s3_bucket: str | None = None

    # Amazon A2I (Augmented AI) — optional human-in-the-loop review
    a2i_flow_definition_arn: str | None = None   # If unset, tasks are created in 'pending' (manual) mode
    a2i_s3_output_bucket: str = "ingestiq-human-review"
    a2i_confidence_threshold: float = 97.0       # Textract confidence % below which A2I triggers
    a2i_accuracy_threshold: float = 98.0         # Page accuracy % below which A2I triggers

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
