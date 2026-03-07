import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class AuditLogEntry:
    ts: str
    level: str
    audit_id: str
    message: str
    context: Optional[Dict[str, Any]] = None


class AuditLogger:
    def __init__(self, audit_id: Optional[str], log_path: str):
        self.audit_id = audit_id or "unknown"
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, message: str, **context: Any) -> AuditLogEntry:
        entry = AuditLogEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            level=level,
            audit_id=self.audit_id,
            message=message,
            context=context or None,
        )
        payload = json.dumps(entry.__dict__, ensure_ascii=False, default=str)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(payload + "\n")
        return entry

    def info(self, message: str, **context: Any) -> AuditLogEntry:
        return self._write("info", message, **context)

    def warning(self, message: str, **context: Any) -> AuditLogEntry:
        return self._write("warning", message, **context)

    def error(self, message: str, **context: Any) -> AuditLogEntry:
        return self._write("error", message, **context)

    def exception(self, message: str, exc: Exception, **context: Any) -> AuditLogEntry:
        context = {
            **context,
            "exception_type": exc.__class__.__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        return self._write("error", message, **context)


class NullAuditLogger:
    def info(self, message: str, **context: Any) -> None:
        return None

    def warning(self, message: str, **context: Any) -> None:
        return None

    def error(self, message: str, **context: Any) -> None:
        return None

    def exception(self, message: str, exc: Exception, **context: Any) -> None:
        return None


def build_audit_logger(audit_id: Optional[str], log_path: Optional[str]) -> AuditLogger | NullAuditLogger:
    if not log_path:
        return NullAuditLogger()
    return AuditLogger(audit_id, log_path)
