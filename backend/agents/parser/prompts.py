"""Prompt text shared by every parser facet.

Facet-specific instructions live next to each facet definition; the rules
here apply to all of them, so citations can be checked against the PDF.
"""

INSTRUCTIONS_SEPARATOR = "\n---\n"

COMMON_EXTRACTION_RULES = (
    "Rules:\n"
    "- Every citation quote must be copied verbatim from the cited page: "
    "at least 15 characters, no paraphrasing, no ellipsis.\n"
    "- Use the page number from the === PAGE n === marker that precedes "
    "the quoted text.\n"
    "- If a fact is not stated in the document, return null for it "
    "(or an empty list). Never invent a value."
)

REPAIR_INSTRUCTIONS = (
    "Your previous answer cited quotes that do not appear on the cited "
    "page. Return the full answer again, replacing each quote below with "
    "text copied exactly from the document and the correct page number. "
    "Drop a fact only if the document does not state it.\n"
    "Quotes that failed verification:"
)
