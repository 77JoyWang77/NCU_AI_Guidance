"""PDF 問答功能設定（與目標系統共用 Azure OpenAI 和 Qdrant 環境變數）。"""
import pathlib

from pydantic import SecretStr
from pydantic_settings import BaseSettings

# .env lives at the repo root (two levels above this file: backend/app/ → backend/ → repo root).
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


class PdfChatSettings(BaseSettings):
    # Azure OpenAI
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_chat_deployment: str = "gpt-4o"
    azure_mini_deployment: str = "gpt-4o-mini"
    azure_embedding_deployment: str = "text-embedding-3-large"

    # Qdrant（與目標系統共用同一個 server）
    qdrant_url: str = ""
    qdrant_api_key: SecretStr = SecretStr("")
    pdf_qdrant_collection: str = "reports"

    # Database
    database_url: str = ""

    class Config:
        # Look in repo root first, then CWD as fallback.
        env_file = [str(_REPO_ROOT / ".env"), ".env"]
        extra = "ignore"


pdf_settings = PdfChatSettings()
