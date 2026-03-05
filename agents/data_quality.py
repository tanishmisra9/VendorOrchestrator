import re
from typing import Any

from context.schema import QualitySuggestion
from .base import BaseAgent

REQUIRED_FIELDS = ["vendor_name", "address", "city", "state", "tax_id"]

ADDRESS_ABBREVIATIONS = {
    r"\bSt\b\.?": "Street",
    r"\bAve\b\.?": "Avenue",
    r"\bBlvd\b\.?": "Boulevard",
    r"\bDr\b\.?": "Drive",
    r"\bLn\b\.?": "Lane",
    r"\bRd\b\.?": "Road",
    r"\bCt\b\.?": "Court",
    r"\bPl\b\.?": "Place",
    r"\bPkwy\b\.?": "Parkway",
    r"\bHwy\b\.?": "Highway",
    r"\bSte\b\.?": "Suite",
    r"\bApt\b\.?": "Apartment",
}

EIN_PATTERN = re.compile(r"^\d{2}-?\d{7}$")


class DataQualityAgent(BaseAgent):
    name = "DataQualityAgent"

    def run(self, data: list[dict]) -> dict[str, Any]:
        """Clean and standardize raw vendor records.

        Returns a dict with 'cleaned_records' and 'quality_report'.
        """
        self.info(f"Processing {len(data)} records")
        cleaned: list[dict] = []
        suggestions: list[QualitySuggestion] = []
        flagged_count = 0

        for idx, record in enumerate(data):
            clean_rec, rec_suggestions = self._clean_record(idx, record)
            cleaned.append(clean_rec)
            suggestions.extend(rec_suggestions)
            if rec_suggestions:
                flagged_count += 1

        for s in suggestions:
            self.log_to_context("quality_suggestions", s)

        quality_rate = flagged_count / len(data) if data else 0
        report = {
            "total_records": len(data),
            "flagged_records": flagged_count,
            "quality_issue_rate": round(quality_rate, 3),
            "total_issues": len(suggestions),
            "needs_review": quality_rate > 0.2,
        }

        self.info(
            f"Done: {flagged_count}/{len(data)} records flagged "
            f"({len(suggestions)} issues)"
        )

        return {"cleaned_records": cleaned, "quality_report": report}

    def _clean_record(
        self, idx: int, record: dict
    ) -> tuple[dict, list[QualitySuggestion]]:
        suggestions: list[QualitySuggestion] = []
        cleaned = dict(record)

        for field in REQUIRED_FIELDS:
            val = cleaned.get(field)
            if not val or (isinstance(val, str) and not val.strip()):
                suggestions.append(
                    QualitySuggestion(
                        record_index=idx,
                        field=field,
                        original_value=val,
                        issue=f"Missing required field: {field}",
                        severity="error",
                    )
                )

        cleaned["vendor_name"], name_suggs = self._standardize_name(
            idx, cleaned.get("vendor_name", "")
        )
        suggestions.extend(name_suggs)

        cleaned["address"], addr_suggs = self._normalize_address(
            idx, cleaned.get("address", "")
        )
        suggestions.extend(addr_suggs)

        cleaned["tax_id"], tax_suggs = self._validate_tax_id(
            idx, cleaned.get("tax_id", "")
        )
        suggestions.extend(tax_suggs)

        for field in ["city", "state", "country"]:
            if cleaned.get(field) and isinstance(cleaned[field], str):
                cleaned[field] = cleaned[field].strip().title()

        if cleaned.get("zip") and isinstance(cleaned["zip"], str):
            cleaned["zip"] = cleaned["zip"].strip()

        return cleaned, suggestions

    def _standardize_name(
        self, idx: int, name: str
    ) -> tuple[str, list[QualitySuggestion]]:
        suggestions: list[QualitySuggestion] = []
        if not name:
            return name, suggestions

        original = name
        name = name.strip()
        name = re.sub(r"[^\w\s&.,'-]", "", name)
        name = re.sub(r"\s+", " ", name)
        name = name.title()

        if name != original.strip():
            suggestions.append(
                QualitySuggestion(
                    record_index=idx,
                    field="vendor_name",
                    original_value=original,
                    suggested_value=name,
                    issue="Name standardized (whitespace/casing/special chars)",
                )
            )
        return name, suggestions

    def _normalize_address(
        self, idx: int, address: str
    ) -> tuple[str, list[QualitySuggestion]]:
        suggestions: list[QualitySuggestion] = []
        if not address:
            return address, suggestions

        original = address
        address = address.strip()
        address = re.sub(r"\s+", " ", address)

        for abbr, full in ADDRESS_ABBREVIATIONS.items():
            address = re.sub(abbr, full, address, flags=re.IGNORECASE)

        if address != original.strip():
            suggestions.append(
                QualitySuggestion(
                    record_index=idx,
                    field="address",
                    original_value=original,
                    suggested_value=address,
                    issue="Address normalized (abbreviations expanded)",
                )
            )
        return address, suggestions

    def _validate_tax_id(
        self, idx: int, tax_id: str
    ) -> tuple[str, list[QualitySuggestion]]:
        suggestions: list[QualitySuggestion] = []
        if not tax_id:
            return tax_id, suggestions

        original = tax_id
        tax_id = tax_id.strip()

        digits = re.sub(r"[^0-9]", "", tax_id)
        if len(digits) == 9:
            formatted = f"{digits[:2]}-{digits[2:]}"
            if formatted != original.strip():
                suggestions.append(
                    QualitySuggestion(
                        record_index=idx,
                        field="tax_id",
                        original_value=original,
                        suggested_value=formatted,
                        issue="Tax ID reformatted to EIN standard (XX-XXXXXXX)",
                    )
                )
            return formatted, suggestions

        if not EIN_PATTERN.match(tax_id):
            suggestions.append(
                QualitySuggestion(
                    record_index=idx,
                    field="tax_id",
                    original_value=original,
                    issue="Tax ID does not match EIN format (XX-XXXXXXX)",
                    severity="error",
                )
            )
        return tax_id, suggestions
