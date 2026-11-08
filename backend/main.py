"""Entry point that starts the API and background agents."""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.shared.config import load_settings

logger = logging.getLogger(__name__)
settings = load_settings()

app = FastAPI(title="Protocol Gap Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main() -> None:
    """Start API server and background agent listeners."""
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "backend started: host=%s port=%d origins=%s",
        settings.backend_host,
        settings.backend_port,
        settings.allowed_origins,
    )
    uvicorn.run(app, host=settings.backend_host, port=settings.backend_port)


if __name__ == "__main__":
    main()
