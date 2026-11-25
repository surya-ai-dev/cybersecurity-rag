"""FastAPI application factory with CORS and clean lifespan resource handling."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import RAGService
from app.api.routes import api_router
from app.core.config import settings
from app.pipeline.engine import RAGEngine


def create_app(engine: Optional[RAGEngine] = None) -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    service = RAGService(engine=engine)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        app_instance.state.rag_service = service
        service.startup()
        try:
            yield
        finally:
            service.shutdown()

    application = FastAPI(
        title="Cybersecurity RAG API",
        version="0.1.0",
        description="HTTP & SSE backend exposing hybrid NIST retrieval and 3-tier conversational memory.",
        lifespan=lifespan,
    )
    application.state.rag_service = service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.api_cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router)
    return application


# Default ASGI app instance for Uvicorn (e.g., uvicorn app.api.app:app)
app = create_app()
