"""Entry point that starts the API and agents."""

import logging

logger = logging.getLogger(__name__)


# [TO REFACTOR:(theo)]: placeholder until the brief decides which agents
# and API routes we need
def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("backend started: agent_count=%d", 0)


if __name__ == "__main__":
    main()
