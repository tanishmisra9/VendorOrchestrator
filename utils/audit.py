import json
import logging
from typing import Any, Optional

from db.connection import session_scope
from db.models import AuditLog, AnalystOverride as AnalystOverrideModel

logger = logging.getLogger(__name__)


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
    except Exception:
        logger.exception("Failed to write audit log for %s", agent_name)


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
    except Exception:
        logger.exception("Failed to write analyst override for vendor %s", vendor_id)
