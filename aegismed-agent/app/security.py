"""Security gate helpers: PII redaction and prompt-injection detection."""
import re

SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
# e.g. +1 555-555-5555 or 555-555-5555
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b")

SSN_PLACEHOLDER = "[REDACTED_SSN]"
PHONE_PLACEHOLDER = "[REDACTED_PHONE]"

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"bypass safety",
    r"override system",
    r"force auto-approval",
    r"approve without check",
    r"override caregiver",
    r"ignore safety rules",
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Replace SSNs and phone numbers with placeholders.

    Returns the scrubbed text and the categories it contains redactions for,
    including text that was already scrubbed by an earlier pass.
    """
    text = SSN_PATTERN.sub(SSN_PLACEHOLDER, text)
    text = PHONE_PATTERN.sub(PHONE_PLACEHOLDER, text)
    categories = []
    if SSN_PLACEHOLDER in text:
        categories.append("SSN")
    if PHONE_PLACEHOLDER in text:
        categories.append("Phone")
    return text, categories


def is_prompt_injection(text: str) -> bool:
    """True when the text contains a known instruction-override phrase."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in INJECTION_PATTERNS)
