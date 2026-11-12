"""Password checks and anonymous learner identity helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

_STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{2,24}$")


def verify_password(candidate: str, expected: str) -> bool:
    """Constant-time password comparison; an unconfigured password never matches."""

    if not expected or not candidate:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def new_session_token() -> str:
    return secrets.token_urlsafe(24)


def normalize_student_id(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not _STUDENT_ID_RE.fullmatch(value):
        raise ValueError("学号/昵称只能包含中文、字母、数字、下划线或短横线，长度 2-24。")
    return value


def normalize_display_name(raw: str) -> str:
    return (raw or "").strip()[:20]


def student_key(session_token: str, student_id: str = "") -> str:
    """Build a stable quota key.

    A supplied class ID makes the daily quota meaningful across browser
    refreshes. Without one we fall back to the session token. This is a
    classroom courtesy limit, not an authentication boundary.
    """

    identity = f"id:{student_id.strip().lower()}" if student_id.strip() else f"session:{session_token}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def client_fingerprint(headers: object | None) -> str:
    """Hash a few request headers for abuse diagnostics, never store raw IPs."""

    if headers is None:
        return ""
    try:
        getter = headers.get  # type: ignore[attr-defined]
        parts = [
            str(getter("X-Forwarded-For", "") or "")[:200],
            str(getter("User-Agent", "") or "")[:300],
        ]
    except Exception:
        return ""
    if not any(parts):
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class LearnerIdentity:
    session_token: str
    student_id: str
    display_name: str
    quota_key: str
    fingerprint: str = ""
    role: str = "student"

    @property
    def public_label(self) -> str:
        if self.display_name:
            return self.display_name
        if self.student_id:
            return self.student_id
        return f"匿名-{self.session_token[-4:].upper()}"
