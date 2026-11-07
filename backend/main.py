"""Entry point that starts the API and background agents."""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

logger = logging.getLogger(__name__)

app = FastAPI(title="Protocol Gap Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main() -> None:
    """Start API server and background agent listeners."""
    logging.basicConfig(level=logging.INFO)
    logger.info("backend started: host=%s port=%d", DEFAULT_HOST, DEFAULT_PORT)
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    main()
