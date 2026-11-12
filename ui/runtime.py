"""Per-session runtime wiring for Streamlit pages."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import streamlit as st

from core.ai_service import AIService
from core.auth import (
    LearnerIdentity,
    client_fingerprint,
    new_session_token,
    normalize_student_id,
    student_key,
)
from core.config import AppConfig, load_config
from core.database import Database
from core.paths import ensure_data_dirs
from core.rag_engine import RAGEngine, get_rag_engine


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    rag: RAGEngine
    ai: AIService


@st.cache_resource(show_spinner=False)
def _database(path: str) -> Database:
    database = Database(path)
    database.init_db()
    return database


def bootstrap() -> tuple[AppConfig, Database]:
    ensure_data_dirs()
    config = load_config()
    db = _database(str(config.db_path))
    db.seed_default_settings(
        {
            "daily_student_limit": config.default_daily_student_limit,
            "daily_global_limit": config.default_daily_global_limit,
            "max_input_chars": config.max_input_chars,
            "max_output_tokens": config.max_output_tokens,
        }
    )
    return config, db


def services() -> AppContext:
    config, db = bootstrap()
    rag = get_rag_engine(config.vector_dir, min_score=config.min_retrieval_score)
    return AppContext(config=config, db=db, rag=rag, ai=AIService(config, db, rag=rag))


def _fingerprint() -> str:
    try:
        headers = st.context.headers
    except Exception:
        headers = None
    return client_fingerprint(headers)


def establish_session(role: str, student_id: str = "", display_name: str = "") -> LearnerIdentity:
    token = st.session_state.get("session_token") or new_session_token()
    st.session_state["session_token"] = token
    normalized_id = normalize_student_id(student_id) if student_id else ""
    name = (display_name or "").strip()[:20]
    st.session_state["student_id"] = normalized_id
    st.session_state["display_name"] = name
    st.session_state["role"] = role
    st.session_state["authenticated"] = True
    identity = LearnerIdentity(
        session_token=token,
        student_id=normalized_id,
        display_name=name,
        quota_key=student_key(token, normalized_id),
        fingerprint=_fingerprint(),
        role=role,
    )
    st.session_state["quota_key"] = identity.quota_key
    return identity


def current_identity() -> LearnerIdentity:
    token = st.session_state.get("session_token") or new_session_token()
    st.session_state["session_token"] = token
    student_id = str(st.session_state.get("student_id", ""))
    role = str(st.session_state.get("role", "student"))
    return LearnerIdentity(
        session_token=token,
        student_id=student_id,
        display_name=str(st.session_state.get("display_name", "")),
        quota_key=st.session_state.get("quota_key") or student_key(token, student_id),
        fingerprint=_fingerprint(),
        role=role,
    )


def session_code(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:6].upper()
    return f"#{digest}"


def throttle_login() -> tuple[bool, str]:
    """Small in-session brake; not a substitute for a real auth gateway."""

    now = time.time()
    locked_until = float(st.session_state.get("login_locked_until", 0))
    if locked_until > now:
        return False, f"尝试次数过多，请等待 {int(locked_until - now) + 1} 秒后再试。"
    return True, ""


def record_login_failure() -> None:
    attempts = int(st.session_state.get("login_attempts", 0)) + 1
    st.session_state["login_attempts"] = attempts
    if attempts >= 5:
        st.session_state["login_locked_until"] = time.time() + 30
        st.session_state["login_attempts"] = 0


def reset_login_failures() -> None:
    st.session_state.pop("login_attempts", None)
    st.session_state.pop("login_locked_until", None)
