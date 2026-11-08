"""CLI entry point for parsing a protocol PDF and printing JSON to stdout."""

import asyncio
import logging
import sys
from pathlib import Path

from backend.agents.parser.agent import AGENT_NAME, parse_protocol
from backend.agents.parser.logic import collect_citations, count_verified
from backend.clients.gemini import GeminiClient
from backend.shared.config import load_settings

logger = logging.getLogger(__name__)


async def _run_cli(pdf_path: Path) -> str:
    settings = load_settings()
    llm = GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
    )
    document = await parse_protocol(pdf_path, llm)
    citations = collect_citations(document)
    verified = count_verified(document)
    verified_share = verified / len(citations) if citations else 0.0
    logger.info(
        "cli parse complete: agent=%s review_id=%s protocol_id=%s "
        "verified=%d/%d (%.1f%%) warnings=%d",
        AGENT_NAME,
        document.protocol_id,
        document.protocol_id,
        verified,
        len(citations),
        verified_share * 100.0,
        len(document.extraction_warnings),
    )
    for warning in document.extraction_warnings:
        logger.warning(
            "extraction warning: agent=%s review_id=%s facet=%s message=%s",
            AGENT_NAME,
            document.protocol_id,
            warning.facet,
            warning.message,
        )
    return document.model_dump_json(exclude={"pages"}, indent=2)


def main() -> None:
    """Parse the PDF path given on the command line and write JSON output."""
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: python -m backend.agents.parser <pdf_path>\n")
        sys.exit(2)
    output_json = asyncio.run(_run_cli(Path(sys.argv[1])))
    sys.stdout.write(f"{output_json}\n")


if __name__ == "__main__":
    main()
