"""Conservative offline content classification for organization folders.

The classifier deliberately prefers the existing file-type folder when evidence is weak.
It does not inspect file contents itself; callers pass bounded text extracted by file_extractor.
"""

from __future__ import annotations

import re


# Distinct phrases are counted once. Requiring multiple signals avoids classifying a
# generic document from a single incidental word.
_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "Invoices": (
        "tax invoice",
        "invoice number",
        "invoice no",
        "invoice date",
        "amount due",
        "bill to",
        "gstin",
        "total invoice",
        "invoice",
    ),
    "Receipts": (
        "payment receipt",
        "receipt number",
        "transaction id",
        "payment received",
        "amount paid",
        "receipt",
    ),
    "Resumes": (
        "curriculum vitae",
        "professional summary",
        "work experience",
        "resume",
        "employment history",
        "technical skills",
    ),
    "Certificates": (
        "certificate of completion",
        "certifies that",
        "certificate number",
        "awarded to",
        "this is to certify",
        "certificate",
    ),
    "Contracts": (
        "employment agreement",
        "terms and conditions",
        "hereby agree",
        "agreement between",
        "effective date",
        "party of the first part",
    ),
    "Reports": (
        "executive summary",
        "methodology",
        "key findings",
        "annual report",
        "quarterly report",
        "conclusion",
    ),
}


def classify_content_subcategory(content: str) -> str | None:
    """Return a semantic subfolder when bounded text contains enough evidence."""
    text = (content or "").casefold()
    if not text.strip():
        return None

    scores: list[tuple[int, str]] = []
    for category, terms in _CATEGORY_TERMS.items():
        matched = 0
        for term in terms:
            pattern = rf"(?<!\\w){re.escape(term)}(?!\\w)"
            if re.search(pattern, text):
                matched += 1
        if matched >= 2:
            scores.append((matched, category))

    if not scores:
        return None

    # Stable ordering makes ties deterministic and independent of set iteration.
    scores.sort(key=lambda item: (-item[0], item[1]))
    if len(scores) > 1 and scores[0][0] == scores[1][0]:
        return None
    return scores[0][1]


def organization_category(base_category: str, content: str) -> str:
    """Combine the broad file-type folder with a confidently detected content folder."""
    base = (base_category or "Other_Files").strip("/\\") or "Other_Files"
    subcategory = classify_content_subcategory(content)
    return f"{base}/{subcategory}" if subcategory else base
