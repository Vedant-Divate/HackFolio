"""Shared domain taxonomy matching for all source clients."""

import re
from typing import List


DOMAIN_PATTERNS = {
    r"\bblockchain\b": "blockchain",
    r"\bweb3\b": "web3",
    r"(?<![\w-])(?:security|cybersecurity)(?![\w-])": "security",
    r"\bcloud\b": "cloud",
    r"\bfull[- ]stack\b": "full_stack",
    r"\b(?:artificial intelligence|machine learning|ai)\b": "ai_ml",
}


def match_domains(text: str) -> List[str]:
    """Return supported domains matched as explicit terms, preserving order."""
    return [
        domain for pattern, domain in DOMAIN_PATTERNS.items()
        if re.search(pattern, text or "", re.IGNORECASE)
    ]