"""stealth-browser: human-like, anti-fingerprint browser automation."""

from .browser import (
    apply_stealth,
    open_browser,
    human_delay,
    human_scroll,
    human_move,
    human_type,
    human_fill_form,
)

__version__ = "0.2.0"
__all__ = [
    "apply_stealth",
    "open_browser",
    "human_delay",
    "human_scroll",
    "human_move",
    "human_type",
    "human_fill_form",
]
