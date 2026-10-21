"""
Audit logging
Structured json lines logger for an audit run
"""
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
    """Audit Logger class

    Logger allowing muli-severity logging

    @Args:
        audit_id (Optional[str]) -- audit id so Logger references the audit its logging
        log_path (Optional[str]) -- path to the log file, entries are printed to the console if not provided

    """
    def __init__(self, audit_id: Optional[str], log_path: Optional[str]):
        self.audit_id = audit_id or "unknown"
        self.log_path: Optional[Path] = None

        if log_path:
            self.log_path = Path(log_path)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, message: str, **context: Any) -> AuditLogEntry:
        """Writes log entry to the log file in the audit dir or prints to console if no log path 

        @Args: 
            level (str) -- severity level of log entry, info | warning | error | exception
            message (str) -- log message 
            context (Any) -- companing log context 
        
        @Returns:
            entry (AuditLogEntry) -- entry object
        """
        entry = AuditLogEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            level=level,
            audit_id=self.audit_id,
            message=message,
            context=context or None,
        )

        if self.log_path:
            payload = json.dumps(entry.__dict__, ensure_ascii=False, default=str)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(payload + "\n")
        else: 
            print(entry)
        
        return entry

    def info(self, message: str, **context: Any) -> AuditLogEntry:
        """Logs info severity level entry

        @Args: 
            message (str) -- log message 
            context (Any) -- companing log context 
        
        @Returns:
            entry (AuditLogEntry) -- entry object
        """
        return self._write("info", message, **context)

    def warning(self, message: str, **context: Any) -> AuditLogEntry:
        """Logs warning severity level entry

        @Args: 
            message (str) -- log message 
            context (Any) -- companing log context 
        
        @Returns:
            entry (AuditLogEntry) -- entry object
        """
        return self._write("warning", message, **context)

    def error(self, message: str, **context: Any) -> AuditLogEntry:
        """Logs error severity level entry

        @Args: 
            message (str) -- log message 
            context (Any) -- companing log context 
        
        @Returns:
            entry (AuditLogEntry) -- entry object
        """
        return self._write("error", message, **context)

    def exception(self, message: str, exc: Exception, **context: Any) -> AuditLogEntry:
        """Logs exception severity level entry with the exception type, message and traceback

        @Args:
            message (str) -- log message
            exc (Exception) -- exception being logged
            context (Any) -- companing log context
        
        @Returns:
            entry (AuditLogEntry) -- entry object
        """
        context = {
            **context,
            "exception_type": exc.__class__.__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        return self._write("error", message, **context)


def build_audit_logger(audit_id: Optional[str], log_path: Optional[str]) -> AuditLogger:
    """Builds the logger for an audit

    @Args:
        audit_id (Optional[str]) -- audit id the logger references
        log_path (Optional[str]) -- path to the log file

    @Returns:
        audit logger (AuditLogger)
    """
    return AuditLogger(audit_id, log_path)
