import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz, process


HIGH_CONFIDENCE_THRESHOLD = 85.0
MEDIUM_CONFIDENCE_THRESHOLD = 60.0


@dataclass
class MatchCandidate:
    index_a: int
    index_b: int
    name_score: float
    address_score: float
    combined_score: float
    tax_id_match: bool


def name_similarity(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(a, b)


def address_similarity(a: str, b: str) -> float:
    return fuzz.partial_ratio(a, b)


def combined_score(
    name_score: float,
    address_score: float,
    tax_id_match: bool,
    name_weight: float = 0.5,
    address_weight: float = 0.3,
    tax_weight: float = 0.2,
) -> float:
    tax_score = 100.0 if tax_id_match else 0.0
    return (
        name_score * name_weight
        + address_score * address_weight
        + tax_score * tax_weight
    )


def compare_two_records(rec_a: dict, rec_b: dict) -> MatchCandidate:
    n_score = name_similarity(
        rec_a.get("vendor_name", ""), rec_b.get("vendor_name", "")
    )
    a_score = address_similarity(
        rec_a.get("address", ""), rec_b.get("address", "")
    )

    tax_a = (rec_a.get("tax_id") or "").strip()
    tax_b = (rec_b.get("tax_id") or "").strip()
    tax_match = bool(tax_a and tax_b and tax_a == tax_b)

    return MatchCandidate(
        index_a=rec_a.get("_index", 0),
        index_b=rec_b.get("_index", 0),
        name_score=n_score,
        address_score=a_score,
        combined_score=combined_score(n_score, a_score, tax_match),
        tax_id_match=tax_match,
    )


NAME_MATCH_OVERRIDE_THRESHOLD = 90.0


def _blocking_key(record: dict) -> str:
    """Generate a blocking key from the first 12 chars of sorted name tokens.

    Records that don't share a blocking key are assumed to be non-duplicates,
    avoiding the O(n^2) all-pairs comparison.
    """
    name = (record.get("vendor_name") or "").lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    tokens = sorted(name.split())
    return " ".join(tokens)[:12] if tokens else ""


def _normalize_tax_id(tid: str) -> str:
    return re.sub(r"[^0-9]", "", (tid or "").strip())


def fuzzy_match_vendors(
    records: list[dict],
    threshold: float = MEDIUM_CONFIDENCE_THRESHOLD,
) -> list[MatchCandidate]:
    """Find duplicate pairs using blocking to avoid O(n^2) comparisons.

    Strategy:
      1. Group records by exact normalized tax_id (immediate duplicates).
      2. Group remaining records by name blocking key, then compare
         only within each block.
    """
    matches: list[MatchCandidate] = []
    seen_pairs: set[tuple[int, int]] = set()

    tax_groups: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        norm_tid = _normalize_tax_id(rec.get("tax_id", ""))
        if norm_tid and len(norm_tid) >= 7:
            tax_groups[norm_tid].append(i)

    for tid, indices in tax_groups.items():
        if len(indices) < 2:
            continue
        anchor = indices[0]
        for other in indices[1:]:
            pair = (min(anchor, other), max(anchor, other))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rec_a = {**records[anchor], "_index": anchor}
            rec_b = {**records[other], "_index": other}
            matches.append(compare_two_records(rec_a, rec_b))

    name_blocks: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        key = _blocking_key(rec)
        if key:
            name_blocks[key].append(i)

    MAX_BLOCK_SIZE = 200
    for key, indices in name_blocks.items():
        if len(indices) < 2:
            continue
        block = indices[:MAX_BLOCK_SIZE]
        for i_pos in range(len(block)):
            for j_pos in range(i_pos + 1, len(block)):
                a_idx, b_idx = block[i_pos], block[j_pos]
                pair = (min(a_idx, b_idx), max(a_idx, b_idx))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                rec_a = {**records[a_idx], "_index": a_idx}
                rec_b = {**records[b_idx], "_index": b_idx}
                candidate = compare_two_records(rec_a, rec_b)
                if (candidate.combined_score >= threshold
                        or candidate.name_score >= NAME_MATCH_OVERRIDE_THRESHOLD):
                    matches.append(candidate)

    return matches


def find_duplicates_for_record(
    new_record: dict,
    existing_records: list[dict],
    threshold: float = MEDIUM_CONFIDENCE_THRESHOLD,
) -> list[MatchCandidate]:
    """Check a single new record against a list of existing records."""
    new_rec = {**new_record, "_index": -1}
    matches: list[MatchCandidate] = []
    for idx, existing in enumerate(existing_records):
        existing_rec = {**existing, "_index": idx}
        candidate = compare_two_records(new_rec, existing_rec)
        if candidate.combined_score >= threshold or candidate.tax_id_match:
            matches.append(candidate)
    return sorted(matches, key=lambda m: m.combined_score, reverse=True)
