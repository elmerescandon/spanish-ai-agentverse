"""Deterministic citation grounding and symbol-font cleanup helpers.

Known trade-off: compact matching removes all hyphens and dashes, so a minus
sign is not distinguished (`-5` matches `5`), which is acceptable given the
15-character minimum quote length (`MIN_QUOTE_CHARACTERS`).
"""

import re
import unicodedata
from collections.abc import Callable
from functools import cache

from backend.shared.messages import Citation, PageText

MIN_QUOTE_CHARACTERS = 15

# pypdf maps Symbol-font glyphs to U+F000 + their Symbol code; these are
# the ones seen in real protocols (thresholds, visit windows, statistics).
SYMBOL_FONT_CHARACTERS: dict[str, str] = {
    "\uf0b3": "≥",
    "\uf0a3": "≤",
    "\uf02d": "-",
    "\uf0b7": "•",
    "\uf0b1": "±",
    "\uf061": "α",
    "\uf062": "β",
    "\uf067": "γ",
    "\uf0a5": "∞",
}
SYMBOL_FONT_TRANSLATION = str.maketrans(SYMBOL_FONT_CHARACTERS)

CURLY_QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)

WHITESPACE_AND_DASH_PATTERN = re.compile(
    r"[\s\-\u2010\u2011\u2012\u2013\u2014\u2212\u00ad]+"
)


def replace_symbol_font_characters(text: str) -> str:
    """Replace Symbol-font private-use characters with standard glyphs."""
    return text.translate(SYMBOL_FONT_TRANSLATION)


def normalize_for_matching(text: str) -> str:
    """Produce the compact normalized string used for substring matching."""
    cleaned = replace_symbol_font_characters(text)
    normalized = unicodedata.normalize("NFKC", cleaned).lower()
    straight_quotes = normalized.translate(CURLY_QUOTE_TRANSLATION)
    return WHITESPACE_AND_DASH_PATTERN.sub("", straight_quotes)


def make_citation_verifier(
    pages: list[PageText],
) -> Callable[[Citation], Citation]:
    """Return a function that verifies citations against these pages.

    Each page is normalized at most once, and only if a citation needs it,
    so verifying a whole facet result doesn't re-clean the same pages.
    """
    text_by_number = {page.page_number: page.text for page in pages}

    @cache
    def compact_page(page_number: int) -> str | None:
        text = text_by_number.get(page_number)
        return None if text is None else normalize_for_matching(text)

    def verify(citation: Citation) -> Citation:
        is_verified = _is_quote_on_cited_page(citation, compact_page)
        return citation.model_copy(update={"is_verified": is_verified})

    return verify


def _is_quote_on_cited_page(
    citation: Citation, compact_page: Callable[[int], str | None]
) -> bool:
    compact_quote = normalize_for_matching(citation.quote)
    if len(compact_quote) < MIN_QUOTE_CHARACTERS:
        return False
    cited = compact_page(citation.page_number)
    if cited is None:
        return False
    if compact_quote in cited:
        return True
    # A quote may run onto the next page, but one found entirely on the next
    # page doesn't count: the citation must name the page it starts on.
    following = compact_page(citation.page_number + 1)
    return (
        following is not None
        and compact_quote in cited + following
        and compact_quote not in following
    )


def verify_citation(citation: Citation, pages: list[PageText]) -> Citation:
    """Return a copy of citation with is_verified set by checking pages."""
    return make_citation_verifier(pages)(citation)


def verify_citations(
    citations: list[Citation],
    pages: list[PageText],
) -> list[Citation]:
    """Return verified copies for every citation in citations."""
    verify = make_citation_verifier(pages)
    return [verify(citation) for citation in citations]
