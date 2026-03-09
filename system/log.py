from __future__ import annotations
from pathlib import Path
import threading

# log file is located in workspace root (parent of system folder)
LOG_PATH = Path(__file__).resolve().parent.parent / "agent_output.log"

_lock = threading.Lock()

def clear() -> None:
    """Clear the contents of the log file."""
    with _lock:
        try:
            LOG_PATH.write_text("")
        except Exception:
            # ensure file exists
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.write_text("")


def add(msg: str) -> None:
    """Append a message with newline to the log file."""
    with _lock:
        try:
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            # if path doesn't exist, create and write again
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
