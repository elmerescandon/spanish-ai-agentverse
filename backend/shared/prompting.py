"""Prompt building blocks shared by every agent that sends pages to Gemini.

Citations are verified against the page numbers in PAGE_MARKER_TEMPLATE,
so every agent must render pages the same way.
"""

from collections.abc import Sequence
from enum import StrEnum

from backend.shared.messages import PageText

PAGE_MARKER_TEMPLATE = "=== PAGE {page_number} ==="
INSTRUCTIONS_SEPARATOR = "\n---\n"


def format_pages_for_prompt(pages: Sequence[PageText]) -> str:
    """Render pages with the 1-based markers citations refer to."""
    return "\n".join(
        f"{PAGE_MARKER_TEMPLATE.format(page_number=page.page_number)}\n"
        f"{page.text}"
        for page in pages
    )


def quoted_values(enum_class: type[StrEnum]) -> str:
    """List an enum's values as the JSON strings Gemini must return."""
    return ", ".join(f'"{member.value}"' for member in enum_class)
