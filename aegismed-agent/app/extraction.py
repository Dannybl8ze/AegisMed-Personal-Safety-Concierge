"""Parse a free-text medication request into structured fields.

Deterministic on purpose: the result feeds the rule checks, so it must not
depend on a model. Example: "Add Warfarin 6mg twice daily for patient-101".
"""
import re

UNKNOWN = "unknown"

_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mg\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")
_REQUEST_VERB_RE = re.compile(
    r"\b(?:add|start|prescribe|schedule|give|order)\b", re.IGNORECASE
)
_PATIENT_RE = re.compile(
    r"\bpatient[-_ ]+(?!patient\b)([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)", re.IGNORECASE
)

# Words that surround a drug name but are never part of it.
_NOT_A_DRUG = frozenset(
    """
    a add adding also an and at bid can change could daily day dose drug every for
    four give giving her his i in increase is like medication mg my need new now of
    on once order ordering patient per please prescribe prescribing prescription
    qid request schedule scheduling set some start starting take taking the their
    then three thrice tid time times to twice up want we with would you
    """.split()
)

_MAX_NAME_WORDS = 3


def _name_from(words: list[str]) -> str:
    return " ".join(w.capitalize() for w in words)


def _words_before(text: str) -> list[str]:
    """Drug-name words that sit directly before a position (reading backwards)."""
    tail = re.search(r"((?:[A-Za-z][A-Za-z\-]*\s+)+)$", text)
    if not tail:
        return []
    name: list[str] = []
    for word in reversed(tail.group(1).split()):
        if word.lower() in _NOT_A_DRUG or len(name) == _MAX_NAME_WORDS:
            break
        name.insert(0, word)
    return name


def _words_after(text: str) -> list[str]:
    """Drug-name words that sit directly after a position (reading forwards)."""
    name: list[str] = []
    position = 0
    while len(name) < _MAX_NAME_WORDS:
        match = re.match(r"\s*(?:of\s+)?([A-Za-z][A-Za-z\-]*)", text[position:], re.IGNORECASE)
        if not match or match.group(1).lower() in _NOT_A_DRUG:
            break
        name.append(match.group(1))
        position += match.end()
    return name


def extract_drug_name(text: str) -> str:
    """Best-effort drug name: the words next to the dose, else after the request verb."""
    dose = _DOSE_RE.search(text)
    if dose:
        words = _words_before(text[: dose.start()]) or _words_after(text[dose.end():])
        if words:
            return _name_from(words)
    verb = _REQUEST_VERB_RE.search(text)
    if verb:
        words = _words_after(text[verb.end():])
        if words:
            return _name_from(words)
    return UNKNOWN


def extract_frequency(text: str) -> int:
    lowered = text.lower()
    if re.search(r"\b(?:twice|2 times|bid)\b", lowered):
        return 2
    if re.search(r"\b(?:three|3 times|tid)\b", lowered):
        return 3
    if re.search(r"\b(?:four|4 times|qid)\b", lowered):
        return 4
    return 1


def extract_patient_id(text: str) -> str:
    """The id that follows "patient", without its prefix (e.g. "104")."""
    match = _PATIENT_RE.search(text)
    return match.group(1) if match else UNKNOWN


def parse_medication_text(text: str) -> dict:
    dose = _DOSE_RE.search(text)
    return {
        "drug_name": extract_drug_name(text),
        "dose_mg": float(dose.group(1)) if dose else 0.0,
        "frequency_per_day": extract_frequency(text),
        "patient_id": extract_patient_id(text),
        "notes": text,
    }
