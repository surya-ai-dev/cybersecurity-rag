"""Uvicorn ASGI server entrypoint for the Cybersecurity RAG HTTP API."""

import uvicorn

from app.core.config import settings


def main() -> None:
    """Launch the FastAPI application via Uvicorn using Settings configuration."""
    uvicorn.run(
        "app.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
