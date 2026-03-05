import json
import logging
import os
from typing import Any, Optional

from db.connection import session_scope
from db.models import AuditLog, AnalystOverride as AnalystOverrideModel

logger = logging.getLogger(__name__)

STRICT_AUDIT = os.getenv("STRICT_AUDIT", "true").lower() in ("true", "1", "yes")


class AuditWriteError(RuntimeError):
    """Raised when an audit log write fails in strict mode."""


def log_agent_action(
    agent_name: str,
    action: str,
    vendor_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    confidence: Optional[float] = None,
) -> None:
    try:
        with session_scope() as session:
            entry = AuditLog(
                agent_name=agent_name,
                action=action,
                vendor_id=vendor_id,
                details_json=details,
                confidence=confidence,
            )
            session.add(entry)
    except Exception as exc:
        logger.exception("Failed to write audit log for %s", agent_name)
        if STRICT_AUDIT:
            raise AuditWriteError(
                f"Audit log write failed for {agent_name}/{action}"
            ) from exc


def log_analyst_override(
    vendor_id: int,
    original_action: str,
    override_action: str,
    reason: str,
    analyst_name: str,
) -> None:
    try:
        with session_scope() as session:
            entry = AnalystOverrideModel(
                vendor_id=vendor_id,
                original_action=original_action,
                override_action=override_action,
                reason=reason,
                analyst_name=analyst_name,
            )
            session.add(entry)
    except Exception as exc:
        logger.exception("Failed to write analyst override for vendor %s", vendor_id)
        if STRICT_AUDIT:
            raise AuditWriteError(
                f"Analyst override write failed for vendor {vendor_id}"
            ) from exc
