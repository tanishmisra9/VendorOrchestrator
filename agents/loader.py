from collections import defaultdict
from typing import Any

from db.connection import get_engine, session_scope
from db.models import VendorMaster, Base
from utils.audit import log_agent_action
from .base import BaseAgent

BATCH_SIZE = 2000


class LoaderAgent(BaseAgent):
    name = "LoaderAgent"

    def run(self, data: list[dict]) -> dict[str, Any]:
        """Load deduplicated records into the vendor master DB.

        For each cluster, the most complete record becomes canonical (active);
        others are marked as duplicates. Uses bulk inserts for performance.
        """
        self.info(f"Loading {len(data):,} records")

        clusters = self._group_by_cluster(data)
        inserted = 0
        duplicates_marked = 0

        rows_to_insert: list[dict] = []
        for cluster_id, members in clusters.items():
            canonical = self._pick_canonical(members)
            for record in members:
                is_canonical = record is canonical
                rows_to_insert.append({
                    "vendor_name": record.get("vendor_name", ""),
                    "address": record.get("address"),
                    "city": record.get("city"),
                    "state": record.get("state"),
                    "zip": record.get("zip"),
                    "country": record.get("country", "US"),
                    "tax_id": record.get("tax_id"),
                    "status": "active" if is_canonical else "duplicate",
                    "cluster_id": cluster_id,
                    "source": record.get("source", "batch_upload"),
                })
                if is_canonical:
                    inserted += 1
                else:
                    duplicates_marked += 1

        engine = get_engine()
        total = len(rows_to_insert)
        for start in range(0, total, BATCH_SIZE):
            batch = rows_to_insert[start:start + BATCH_SIZE]
            with engine.begin() as conn:
                conn.execute(VendorMaster.__table__.insert(), batch)
            if (start + BATCH_SIZE) % 10000 == 0 or start + BATCH_SIZE >= total:
                self.info(f"  Inserted {min(start + BATCH_SIZE, total):,}/{total:,} rows")

        self.info("Writing audit summary...")
        log_agent_action(
            agent_name=self.name,
            action="batch_load_complete",
            details={
                "total_processed": len(data),
                "inserted_canonical": inserted,
                "duplicates_marked": duplicates_marked,
                "clusters": len(clusters),
            },
            confidence=1.0,
        )

        summary = {
            "total_processed": len(data),
            "inserted_canonical": inserted,
            "duplicates_marked": duplicates_marked,
            "clusters": len(clusters),
        }
        self.info(
            f"Done: {inserted:,} canonical, {duplicates_marked:,} duplicates "
            f"across {len(clusters):,} clusters"
        )
        return {"load_result": summary}

    def _group_by_cluster(self, records: list[dict]) -> dict[int, list[dict]]:
        clusters: dict[int, list[dict]] = defaultdict(list)
        for idx, rec in enumerate(records):
            cid = rec.get("cluster_id", idx)
            clusters[cid].append(rec)
        return dict(clusters)

    def _pick_canonical(self, members: list[dict]) -> dict:
        """Choose the record with the most non-empty fields as canonical."""
        def completeness(rec: dict) -> int:
            return sum(
                1 for k, v in rec.items()
                if k not in ("cluster_id", "_index", "source")
                and v is not None
                and (not isinstance(v, str) or v.strip())
            )

        return max(members, key=completeness)
