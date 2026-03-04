"""Shared runtime state for cross-process feature flags."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

_STATE_FILE = Path(__file__).resolve().parent.parent / "env" / "runtime_state.json"


def _ensure_state_dir() -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_state() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(data: dict) -> None:
    _ensure_state_dir()
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=_STATE_FILE.parent) as tmp:
        json.dump(data, tmp)
        temp_path = Path(tmp.name)
    temp_path.replace(_STATE_FILE)


def initialize_speech_enabled(default_enabled: bool = False) -> bool:
    """Initialize runtime speech flag if absent and return current value."""
    state = _read_state()
    if "speech_enabled" not in state:
        state["speech_enabled"] = bool(default_enabled)
        _write_state(state)
    return bool(state.get("speech_enabled", default_enabled))


def set_speech_enabled(enabled: bool) -> bool:
    """Set runtime speech enabled flag and return current value."""
    state = _read_state()
    state["speech_enabled"] = bool(enabled)
    _write_state(state)
    return bool(state["speech_enabled"])


def get_speech_enabled(default_enabled: bool = False) -> bool:
    """Get runtime speech enabled flag."""
    state = _read_state()
    if "speech_enabled" not in state:
        return bool(default_enabled)
    return bool(state["speech_enabled"])
