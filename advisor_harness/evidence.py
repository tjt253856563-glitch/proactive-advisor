"""Conservative redaction for material sent to providers or written to the journal."""

import os
import re


_PATTERNS = (
    re.compile(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"(?i)\b(?:bearer\s+[\w./+=-]+|(?:sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|github_pat_[\w]+|AKIA[A-Z0-9]{16}))"),
    re.compile(r"""(?ix)\b(?:[\w.-]*?(?:api[ _-]?key|auth[ _-]?token|access[ _-]?token|token|secret|password|passwd))[\x22\x27]?\s*[:=]\s*["']?[^\s"',;}]{4,}"""),
    re.compile(r"(?i)(?:https?://)[^\s/@]+:[^\s/@]+@"),
)


def redact(text):
    for key, value in os.environ.items():
        if len(value) >= 8 and re.search(r"key|token|secret|password|credential|proxy", key, re.I):
            if value in text:
                text = text.replace(value, "[redacted]")
    for pattern in _PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def contains_secret(data):
    if data is None:
        return False
    text = data.decode("utf-8")
    return redact(text) != text


def clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value
