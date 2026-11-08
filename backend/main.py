"""Entry point that starts the API and background agents."""

import logging

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.protocol_pipeline import AnalysisFailedError
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


@app.exception_handler(AnalysisFailedError)
async def answer_analysis_failure(
    _request: Request, error: AnalysisFailedError
) -> JSONResponse:
    """Turn a failed parse or check into a 503 the UI can show."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": f"protocol analysis failed: {error}"},
    )


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
