"""stealth-browser: human-like, anti-fingerprint browser automation."""

from .browser import (
    open_browser,
    human_delay,
    human_scroll,
    human_move,
    human_type,
)

__version__ = "0.1.0"
__all__ = [
    "open_browser",
    "human_delay",
    "human_scroll",
    "human_move",
    "human_type",
]
