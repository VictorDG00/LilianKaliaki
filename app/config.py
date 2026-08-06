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
    DB_PASSWORD: str = ""
    APP_PORT: str = ""

    # Loga todo SQL (com os parametros) no stdout. So para debug local:
    # em producao o Promtail manda o stdout pro Loki, e os parametros
    # incluem nome/email/telefone dos contatos.
    SQL_ECHO: bool = False

    # Cookie de sessao so trafega em HTTPS. Desligar apenas em teste local.
    SESSION_HTTPS_ONLY: bool = True

    class Config:
        env_file = ".env"

settings = Settings()