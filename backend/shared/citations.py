"""Deterministic citation grounding and symbol-font cleanup helpers.

Known trade-off: compact matching removes all hyphens and dashes, so a minus
sign is not distinguished (`-5` matches `5`), which is acceptable given the
15-character minimum quote length (`MIN_QUOTE_CHARACTERS`).
"""

import re
import unicodedata

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


def verify_citation(citation: Citation, pages: list[PageText]) -> Citation:
    """Return a copy of citation with is_verified set by checking pages."""
    compact_quote = normalize_for_matching(citation.quote)
    if len(compact_quote) < MIN_QUOTE_CHARACTERS:
        return citation.model_copy(update={"is_verified": False})

    page_by_number = {page.page_number: page.text for page in pages}
    cited_page_text = page_by_number.get(citation.page_number)
    if cited_page_text is None:
        return citation.model_copy(update={"is_verified": False})

    compact_page = normalize_for_matching(cited_page_text)
    if compact_quote in compact_page:
        return citation.model_copy(update={"is_verified": True})

    next_page_text = page_by_number.get(citation.page_number + 1)
    if next_page_text is not None:
        compact_next = normalize_for_matching(next_page_text)
        compact_span = compact_page + compact_next
        if compact_quote in compact_span and compact_quote not in compact_next:
            return citation.model_copy(update={"is_verified": True})

    return citation.model_copy(update={"is_verified": False})


def verify_citations(
    citations: list[Citation],
    pages: list[PageText],
) -> list[Citation]:
    """Return verified copies for every citation in citations."""
    return [verify_citation(citation, pages) for citation in citations]
