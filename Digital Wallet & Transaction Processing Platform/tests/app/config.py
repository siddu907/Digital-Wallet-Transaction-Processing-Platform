from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str 
    jwt_secret_key: str 
    jwt_algorithm: str 
    access_token_minutes: int
    refresh_token_days: int
    max_transaction_amount: str 
    daily_transfer_limit: str
    daily_withdrawal_limit: str
    max_transactions_per_day: int 
    suspicious_amount_threshold: str 
    celery_broker_url: str 
    celery_result_backend: str 
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=20, ge=0)

    model_config = SettingsConfigDict(env_file=(".env.example", ".env"), extra="ignore")


settings = Settings()
