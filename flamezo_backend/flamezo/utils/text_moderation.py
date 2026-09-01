"""Lightweight text moderation for user-generated content (comments).

Masks a basic profanity list with asterisks rather than rejecting the whole
comment — keeps the conversation flowing while scrubbing slurs/abuse. This is a
deliberately simple word-boundary filter (not an ML classifier); extend the
list as needed.
"""
import re

# Base English + common Hindi/Hinglish abuse. Kept intentionally short and
# obvious; matched case-insensitively on word boundaries (so "class" is safe).
_BAD_WORDS = {
    "fuck", "fucker", "fucking", "shit", "bitch", "bastard", "asshole",
    "dick", "cunt", "slut", "whore", "motherfucker", "bullshit", "wanker",
    "chutiya", "chutiye", "bhosdi", "bhosdike", "madarchod", "behenchod",
    "bhenchod", "gandu", "gaand", "randi", "harami", "kutte", "kamine",
    "lund", "loda", "lauda", "chodu", "bkl", "mc", "bc",
}

# One regex, word-boundaried, longest-first so "motherfucker" masks whole.
_PATTERN = re.compile(
    r"\b(" + "|".join(sorted((re.escape(w) for w in _BAD_WORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Return `text` with any profanity replaced by asterisks of equal length."""
    if not text:
        return text
    return _PATTERN.sub(lambda m: "*" * len(m.group(0)), text)


def demo():
    assert sanitize_text("you are a bitch") == "you are a *****"
    assert sanitize_text("great class today") == "great class today"  # no false hit
    assert sanitize_text("chutiya move") == "******* move"
    assert sanitize_text("") == ""
    print("text_moderation demo OK")


if __name__ == "__main__":
    demo()
