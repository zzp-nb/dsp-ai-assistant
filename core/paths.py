"""Filesystem layout and environment bootstrap for the DSP teaching assistant."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load a local .env once, without overriding variables supplied by the host.
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _as_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def data_dir() -> Path:
    """Return the writable data root.

    On Streamlit Community Cloud this defaults to the ephemeral app checkout.
    A host with a persistent volume can point DSP_DATA_DIR at it.
    """

    path = _as_path(os.getenv("DSP_DATA_DIR")) or (PROJECT_ROOT / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def materials_dir() -> Path:
    path = _as_path(os.getenv("DSP_MATERIALS_DIR")) or (data_dir() / "course_materials")
    path.mkdir(parents=True, exist_ok=True)
    return path


def vector_store_dir() -> Path:
    path = _as_path(os.getenv("DSP_VECTOR_DIR")) or (data_dir() / "vector_store")
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    path = _as_path(os.getenv("DSP_DATABASE_PATH")) or (data_dir() / "database" / "dsp.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_data_dirs() -> None:
    for path in (data_dir(), materials_dir(), vector_store_dir(), database_path().parent):
        path.mkdir(parents=True, exist_ok=True)
