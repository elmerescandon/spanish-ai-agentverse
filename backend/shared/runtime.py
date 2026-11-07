"""Asyncio event loop helper for running uAgents on Python 3.14."""

import asyncio


# [TO REFACTOR:(alex)]: uAgents 0.26.1 calls asyncio.get_event_loop() at
# construction time, which raises on Python 3.14 without an active loop
def create_event_loop() -> asyncio.AbstractEventLoop:
    """Create and register a new asyncio event loop for the current thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop
