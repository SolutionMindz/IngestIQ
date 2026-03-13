import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://sanjeev@127.0.0.1/Textract"
    upload_dir: str = "uploads"
    parser_version: str = "1.0.0"
    screenshot_dpi: int = 150

    # Section 7: PP-Structure layout and specialized OCR (plan paddleocr_integration_plan)
    use_pp_structure: bool = False  # PPStructureV3 unavailable — use heuristic OCR classifier instead
    use_formula_ocr: bool = False  # Formula regions → LaTeX (requires formula model)
    use_code_ocr: bool = False     # Code regions → code-specific OCR
    use_pix2tex: bool = False      # Tier-1: send small inline image blocks to pix2tex for LaTeX
    use_nougat_ocr: bool = False   # Tier-2: full-page formula OCR via Nougat (requires nougat-ocr; ~60s CPU)
    use_surya_ocr: bool = False    # Tier-2: image/diagram OCR via Surya (requires surya-ocr; ~3-5s CPU)

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
