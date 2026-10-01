import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Application Configuration
    app_name: str = "Warehouse Inventory AI API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server / Security
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]
    
    # Database Configuration (SQL Server / SQLAlchemy)
    database_url: Optional[str] = None
    sql_server: str = "localhost"
    sql_database: str = "WarehouseDB"
    sql_username: str = "wms_chatbot_readonly"
    sql_password: str = "ChangeThisStrongPassword123!"
    sql_driver: str = "ODBC Driver 18 for SQL Server"
    sql_pool_size: int = 10
    sql_max_overflow: int = 20
    sql_query_timeout_sec: int = 30
    sql_max_result_rows: int = 1000
    
    # LLM Configuration
    llm_provider: str = "gemini"  # "gemini", "openai", or "generic_http"
    llm_api_key: str = ""
    llm_model: str = "gemini-1.5-pro"  # or gpt-4o / gpt-3.5-turbo
    llm_base_url: Optional[str] = None
    llm_temperature: float = 0.0
    llm_max_retries: int = 1
    
    # Admin / Debug Authentication
    admin_api_key: str = "admin-secret-key"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
