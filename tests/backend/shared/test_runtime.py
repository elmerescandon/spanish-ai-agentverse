"""Unit tests for the uAgents asyncio event loop runtime helper."""

from uagents import Agent

from backend.shared.runtime import create_event_loop

TEST_AGENT_NAME = "t"
TEST_AGENT_SEED = "test seed phrase runtime 0001"


def test_create_event_loop_allows_agent_construction() -> None:
    loop = create_event_loop()
    agent = Agent(name=TEST_AGENT_NAME, seed=TEST_AGENT_SEED, loop=loop)

    assert agent.name == TEST_AGENT_NAME
