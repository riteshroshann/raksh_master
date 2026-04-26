from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    supabase_url: str = Field(default="http://host.docker.internal:54321")
    supabase_service_role_key: str = Field(default="")
    ingestion_api_key: str = Field(default="local-dev-key-change-in-prod")
    anthropic_api_key: str = Field(default="")
    google_application_credentials: str = Field(default="")
    extraction_backend: str = Field(default="api")
    folder_watch_path: str = Field(default="/watch")
    email_imap_host: str = Field(default="imap.gmail.com")
    email_imap_port: int = Field(default=993)
    email_address: str = Field(default="")
    email_password: str = Field(default="")
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_fax_number: str = Field(default="")
    allowed_origins: str = Field(default="http://localhost:5173")
    max_upload_size_mb: int = Field(default=500)
    confidence_default_threshold: float = Field(default=0.85)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
