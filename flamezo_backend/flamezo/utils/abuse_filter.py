"""Abusive-language check for support requests from customers and merchants.

Used by api/support.py before a requester's subject or message is saved; staff
replies are not checked. English plus Hindi/Hinglish (romanised and Devanagari).
Matches whole words so ordinary words that merely contain one ("class",
"scunthorpe") pass, and normalises common disguises — leetspeak (f*ck -> fuck
needs the letters, but 5h1t -> shit) and stretched letters (fuuuck).

ponytail: a fixed word list; swap in a moderation API if abuse slips through.
"""

import re

_WORDS = {
	# English
	"fuck", "fucking", "fucker", "fucked", "motherfucker", "fck", "fuk", "fuq", "wtf", "stfu",
	"shit", "bullshit", "bitch", "bitches", "bastard", "asshole", "arsehole", "dick", "dickhead",
	"pussy", "cunt", "slut", "whore", "retard", "dumbass", "jackass", "prick", "douche", "douchebag",
	# Hindi / Hinglish (romanised)
	"madarchod", "maderchod", "madarchodd", "behenchod", "bhenchod", "benchod", "bhencho",
	"bhosdike", "bhosdi", "bhosda", "bhosadi", "chutiya", "chutiye", "chutia", "chootiya",
	"chodu", "chod", "chodna", "gaandu", "gandu", "gaand", "lund", "lauda", "lavda", "loda", "lode",
	"randi", "raand", "harami", "haramkhor", "kamina", "kamine", "kutta", "kutte", "kutiya",
	"bsdk", "bkl", "mkc", "jhaat", "jhatu", "chinal", "tatti",
}

# Devanagari: matched as substrings — vowel signs break regex word boundaries.
_DEVANAGARI = (
	"मादरचोद", "बहनचोद", "बहेनचोद", "भोसड़ी", "भोसडी", "चूतिया", "चुतिया", "गांडू", "गाँडू",
	"लंड", "लौड़ा", "रंडी", "हरामी", "हरामखोर", "कमीना", "कमीने", "कुत्ते", "कुतिया",
)

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})


def _squash(s):
	"""fuuuck -> fuck, asshole -> ashole: compare with repeated letters folded."""
	return re.sub(r"(.)\1+", r"\1", s)


def _pattern(words):
	return re.compile(r"\b(" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")\b")


_PLAIN = _pattern(_WORDS)
_SQUASHED = _pattern({_squash(w) for w in _WORDS})


def contains_abuse(text):
	"""True if `text` contains an abusive word."""
	if not text:
		return False
	if any(w in text for w in _DEVANAGARI):
		return True
	t = str(text).lower().translate(_LEET)
	return bool(_PLAIN.search(t) or _SQUASHED.search(_squash(t)))


if __name__ == "__main__":
	# Runnable self-check: python abuse_filter.py
	for bad in ("what the fuck", "FUUUCK this", "5h1t app", "tu chutiya hai", "bhenchod", "BSDK", "ye kya hai madarchod",
	            "भोसड़ीके", "asshole"):
		assert contains_abuse(bad), bad
	for ok in ("My payment failed", "class starts at 5", "Scunthorpe outlet", "the bill is 760",
	           "please check kutch branch", "", None, "hello, bill not paid", "assessment pending"):
		assert not contains_abuse(ok), ok
	print("abuse_filter self-check: OK")
