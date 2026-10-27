"""Operator console locale helper (Phase 3, Task 3.5).

Selects console message language via the DEFAULT_LOCALE environment variable.
English is the default; Korean is available. Presentation only: never changes
persisted values, validation reasons, memo fields, status/reason/mode values,
state transitions, or order behavior.
"""
import os

SUPPORTED_LOCALES = ("en", "ko")
DEFAULT_LOCALE = "en"


def get_locale() -> str:
    raw = (os.environ.get("DEFAULT_LOCALE") or "").strip().lower()
    return raw if raw in SUPPORTED_LOCALES else DEFAULT_LOCALE


def t(en: str, ko: str) -> str:
    """Return the console string for the active locale (en default, ko alternate)."""
    return ko if get_locale() == "ko" else en
