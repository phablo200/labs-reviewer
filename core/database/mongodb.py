"""MongoDB client lifecycle for the FastAPI application."""

from inspect import isawaitable

from beanie import init_beanie
from pymongo import AsyncMongoClient

from core.config import settings
from labs.process_status.models import ProcessStatus

_client: AsyncMongoClient | None = None


async def init_mongodb() -> None:
    """Initialize MongoDB and Beanie document models."""
    global _client
    _client = AsyncMongoClient(settings.MONGODB_URI)
    await init_beanie(
        database=_client[settings.MONGODB_DATABASE],
        document_models=[ProcessStatus],
    )


async def close_mongodb() -> None:
    """Close the MongoDB client when the app shuts down."""
    global _client
    if _client is None:
        return

    close_result = _client.close()
    if isawaitable(close_result):
        await close_result
    _client = None
