import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz, process


HIGH_CONFIDENCE_THRESHOLD = 85.0
MEDIUM_CONFIDENCE_THRESHOLD = 60.0
NAME_MATCH_OVERRIDE_THRESHOLD = 90.0


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


def _normalize_name(name: str) -> str:
    name = (name or "").lower().strip()
    return re.sub(r"[^\w\s]", "", name)


def _blocking_keys(record: dict) -> list[str]:
    """Generate multiple blocking keys per record to reduce missed duplicates.

    Strategies:
      1. First 12 chars of sorted name tokens (catches reordered names)
      2. First token alone (catches "Deloitte Consulting" vs "Deloitte Touche")
      3. Normalized tax_id (catches exact tax matches in different name blocks)
    """
    keys = []
    name = _normalize_name(record.get("vendor_name", ""))
    tokens = sorted(name.split())

    if tokens:
        keys.append("st:" + " ".join(tokens)[:12])
        keys.append("ft:" + tokens[0][:8])

    tid = _normalize_tax_id(record.get("tax_id", ""))
    if tid and len(tid) >= 7:
        keys.append("tx:" + tid)

    return keys


def _normalize_tax_id(tid: str) -> str:
    return re.sub(r"[^0-9]", "", (tid or "").strip())


_NAME_PREFILTER = 50.0


def fuzzy_match_vendors(
    records: list[dict],
    threshold: float = MEDIUM_CONFIDENCE_THRESHOLD,
) -> list[MatchCandidate]:
    """Find duplicate pairs using multiple blocking strategies.

    Strategy:
      1. Group records by each blocking key (sorted tokens, first token, tax_id).
      2. Within each block, use rapidfuzz.process.extract for a fast name
         pre-filter, then do full comparison only for promising pairs.
    """
    matches: list[MatchCandidate] = []
    seen_pairs: set[tuple[int, int]] = set()

    blocks: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        for key in _blocking_keys(rec):
            blocks[key].append(i)

    MAX_BLOCK_SIZE = 200
    for key, indices in blocks.items():
        if len(indices) < 2:
            continue
        block = indices[:MAX_BLOCK_SIZE]

        is_tax_block = key.startswith("tx:")
        if is_tax_block:
            anchor = block[0]
            for other in block[1:]:
                pair = (min(anchor, other), max(anchor, other))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                rec_a = {**records[anchor], "_index": anchor}
                rec_b = {**records[other], "_index": other}
                matches.append(compare_two_records(rec_a, rec_b))
            continue

        names = [records[idx].get("vendor_name", "") for idx in block]

        for i_pos in range(len(block)):
            query_name = names[i_pos]
            results = process.extract(
                query_name, names, scorer=fuzz.token_sort_ratio,
                score_cutoff=_NAME_PREFILTER, limit=len(names),
            )
            for match_name, score, j_pos in results:
                if j_pos <= i_pos:
                    continue
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


def sanitize_like(value: str) -> str:
    """Escape LIKE special characters in user input to prevent pattern injection."""
    value = value.replace("\\", "\\\\")
    value = value.replace("%", "\\%")
    value = value.replace("_", "\\_")
    return value
