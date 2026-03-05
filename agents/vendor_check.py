import json
import logging
from typing import Any, Optional

from openai import OpenAI

from db.connection import session_scope
from db.models import VendorMaster
from utils.matching import (
    find_duplicates_for_record,
    MatchCandidate,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
)
from utils.audit import log_agent_action
from .base import BaseAgent

logger = logging.getLogger(__name__)

CHECK_PROMPT = """You are a vendor data expert. A user wants to add a new vendor. Compare it against this potential duplicate from our database and determine if they are the same vendor.

New vendor:
{new_vendor}

Existing vendor:
{existing_vendor}

Respond in JSON with:
- "judgment": "duplicate" or "not_duplicate"
- "confidence": float between 0 and 1
- "rationale": brief explanation
"""


class VendorCheckAgent(BaseAgent):
    name = "VendorCheckAgent"

    def __init__(self, context, openai_client: Optional[OpenAI] = None) -> None:
        super().__init__(context)
        self._llm = openai_client

    @property
    def llm(self) -> OpenAI:
        if self._llm is None:
            self._llm = OpenAI(max_retries=1, timeout=10)
        return self._llm

    def run(self, data: dict) -> dict[str, Any]:
        """Check a new vendor record against the existing database.

        Returns a recommendation: 'allow', 'warn', or 'block',
        along with any matching vendors found.
        """
        self.info(f"Checking vendor: {data.get('vendor_name', 'unknown')}")

        existing = self._fetch_active_vendors()
        if not existing:
            self.info("No existing vendors in database — allowing insert")
            return {
                "recommendation": "allow",
                "matches": [],
                "message": "No existing vendors found. Safe to add.",
            }

        candidates = find_duplicates_for_record(
            data, existing, threshold=MEDIUM_CONFIDENCE_THRESHOLD
        )

        if not candidates:
            self.info("No duplicates found")
            return {
                "recommendation": "allow",
                "matches": [],
                "message": "No potential duplicates found. Safe to add.",
            }

        top = candidates[0]

        if top.combined_score >= HIGH_CONFIDENCE_THRESHOLD or top.tax_id_match:
            match_info = self._build_match_info(top, existing)
            log_agent_action(
                agent_name=self.name,
                action="block_duplicate",
                details={"new_vendor": data, "match": match_info},
                confidence=top.combined_score / 100.0,
            )
            return {
                "recommendation": "warn",
                "matches": [match_info for c in candidates[:5]],
                "message": f"High-confidence duplicate found (score: {top.combined_score:.1f}%). Review before adding.",
            }

        llm_result = self._llm_check(data, existing[top.index_b])
        if llm_result and llm_result.get("judgment") == "duplicate":
            match_info = self._build_match_info(top, existing)
            return {
                "recommendation": "warn",
                "matches": [match_info],
                "message": f"LLM flagged as potential duplicate: {llm_result.get('rationale', '')}",
            }

        return {
            "recommendation": "allow",
            "matches": [
                self._build_match_info(c, existing) for c in candidates[:3]
            ],
            "message": "Low-confidence matches found. Likely safe to add, but review listed matches.",
        }

    def _fetch_active_vendors(self) -> list[dict]:
        with session_scope() as session:
            vendors = (
                session.query(VendorMaster)
                .filter(VendorMaster.status == "active")
                .all()
            )
            return [v.to_dict() for v in vendors]

    def _build_match_info(
        self, candidate: MatchCandidate, existing: list[dict]
    ) -> dict:
        matched_vendor = existing[candidate.index_b]
        return {
            "vendor_id": matched_vendor.get("id"),
            "vendor_name": matched_vendor.get("vendor_name"),
            "address": matched_vendor.get("address"),
            "tax_id": matched_vendor.get("tax_id"),
            "score": candidate.combined_score,
            "tax_id_match": candidate.tax_id_match,
        }

    def _llm_check(self, new_vendor: dict, existing_vendor: dict) -> Optional[dict]:
        try:
            prompt = CHECK_PROMPT.format(
                new_vendor=json.dumps(new_vendor, indent=2),
                existing_vendor=json.dumps(existing_vendor, indent=2, default=str),
            )
            response = self.llm.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            logger.exception("LLM vendor check failed")
            return None
