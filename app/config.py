# Configurações e Variáveis de ambiente (.env)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    MERCADO_PAGO_ACCESS_TOKEN: str
    MERCADO_PAGO_WEBHOOK_SECRET: str
    MERCADO_PAGO_PUBLIC_KEY: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
    DB_PASSWORD: str
    APP_PORT: str

    class Config:
        env_file = ".env"

settings = Settings()