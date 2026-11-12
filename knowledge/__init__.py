"""Offline course content bundled with the assistant."""

from __future__ import annotations

from knowledge.dsp_entries import ENTRIES
from knowledge.dsp_quiz_bank import QUIZ_BANK

ENTRY_BY_ID = {entry["id"]: entry for entry in ENTRIES}

__all__ = ["ENTRIES", "ENTRY_BY_ID", "QUIZ_BANK"]
