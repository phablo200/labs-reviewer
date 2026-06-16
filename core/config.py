import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Agent Language Model"
    LANGUAGE_DB_PATH: str = os.getenv("LANGUAGE_DB_PATH", "public/language_database/ingl_s.json")
    MEBRAIN_SYSTEM_API_URL: str = os.getenv(
        "MEBRAIN_SYSTEM_API_URL", "http://localhost:3005"
    )
    RAG_DECK_REFRESH_HOURS: int = int(os.getenv("RAG_DECK_REFRESH_HOURS", "24"))
    AUTH_TOKEN_VERIFIER: str = os.getenv("AUTH_TOKEN_VERIFIER", "jwt")
    AUTH_JWT_SECRET: str = os.getenv("AUTH_JWT_SECRET", "")
    AUTH_JWT_PUBLIC_KEY: str = os.getenv("AUTH_JWT_PUBLIC_KEY", "")
    AUTH_JWT_ALGORITHM: str = os.getenv("AUTH_JWT_ALGORITHM", "HS256")
    AUTH_JWT_ISSUER: str = os.getenv("AUTH_JWT_ISSUER", "")
    AUTH_JWT_AUDIENCE: str = os.getenv("AUTH_JWT_AUDIENCE", "")
    AUTH_JWKS_URL: str = os.getenv("AUTH_JWKS_URL", "")
    AUTH_EXPECTED_APPLICATION_ID: str = os.getenv(
        "AUTH_EXPECTED_APPLICATION_ID",
        "00000000-0000-0000-0000-000000000002",
    )
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "labs_reviewer")
    TASK_DISPATCHER: str = os.getenv("TASK_DISPATCHER", "background_tasks")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND",
        "redis://localhost:6379/1",
    )


settings = Settings()
