import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.matching import (
    name_similarity,
    address_similarity,
    combined_score,
    compare_two_records,
    fuzzy_match_vendors,
    find_duplicates_for_record,
    HIGH_CONFIDENCE_THRESHOLD,
)


class TestNameSimilarity:
    def test_identical_names(self):
        assert name_similarity("Acme Corp", "Acme Corp") == 100.0

    def test_similar_names(self):
        score = name_similarity("Acme Corporation", "Acme Corp")
        assert score > 70

    def test_different_names(self):
        score = name_similarity("Acme Corporation", "Global Tech Solutions")
        assert score < 50


class TestAddressSimilarity:
    def test_identical(self):
        assert address_similarity("123 Main Street", "123 Main Street") == 100.0

    def test_abbreviation(self):
        score = address_similarity("123 Main St", "123 Main Street")
        assert score > 70

    def test_different(self):
        score = address_similarity("123 Main St", "456 Oak Ave")
        assert score < 60


class TestCombinedScore:
    def test_perfect_match(self):
        score = combined_score(100.0, 100.0, True)
        assert score == 100.0

    def test_name_only(self):
        score = combined_score(100.0, 0.0, False)
        assert 45 < score < 55

    def test_tax_id_boost(self):
        score_without = combined_score(70.0, 70.0, False)
        score_with = combined_score(70.0, 70.0, True)
        assert score_with > score_without


class TestCompareRecords:
    def test_exact_duplicate(self):
        a = {"vendor_name": "Acme Corp", "address": "123 Main St", "tax_id": "12-3456789"}
        b = {"vendor_name": "Acme Corp", "address": "123 Main St", "tax_id": "12-3456789"}
        result = compare_two_records(a, b)
        assert result.combined_score >= HIGH_CONFIDENCE_THRESHOLD
        assert result.tax_id_match is True

    def test_no_match(self):
        a = {"vendor_name": "Acme Corp", "address": "123 Main St", "tax_id": "12-3456789"}
        b = {"vendor_name": "XYZ Logistics", "address": "999 Ocean Rd", "tax_id": "99-0000000"}
        result = compare_two_records(a, b)
        assert result.combined_score < 60
        assert result.tax_id_match is False


class TestFuzzyMatchVendors:
    def test_finds_duplicates(self):
        records = [
            {"vendor_name": "Acme Corporation", "address": "123 Main St", "tax_id": "12-3456789"},
            {"vendor_name": "ACME Corp", "address": "123 Main Street", "tax_id": "12-3456789"},
            {"vendor_name": "XYZ Logistics", "address": "999 Ocean Rd", "tax_id": "99-0000000"},
        ]
        matches = fuzzy_match_vendors(records, threshold=60)
        assert len(matches) >= 1
        pair = matches[0]
        assert {pair.index_a, pair.index_b} == {0, 1}

    def test_no_matches_below_threshold(self):
        records = [
            {"vendor_name": "Alpha Inc", "address": "1 A St", "tax_id": "11-1111111"},
            {"vendor_name": "Beta LLC", "address": "2 B Ave", "tax_id": "22-2222222"},
        ]
        matches = fuzzy_match_vendors(records, threshold=80)
        assert len(matches) == 0


class TestFindDuplicatesForRecord:
    def test_finds_match(self):
        new = {"vendor_name": "Acme Corp", "address": "123 Main St", "tax_id": "12-3456789"}
        existing = [
            {"vendor_name": "Acme Corporation", "address": "123 Main Street", "tax_id": "12-3456789"},
            {"vendor_name": "XYZ Logistics", "address": "999 Ocean Rd", "tax_id": "99-0000000"},
        ]
        matches = find_duplicates_for_record(new, existing, threshold=60)
        assert len(matches) >= 1
        assert matches[0].index_b == 0

    def test_no_match(self):
        new = {"vendor_name": "Brand New Vendor", "address": "000 Nowhere", "tax_id": "00-0000000"}
        existing = [
            {"vendor_name": "Acme Corporation", "address": "123 Main Street", "tax_id": "12-3456789"},
        ]
        matches = find_duplicates_for_record(new, existing, threshold=80)
        assert len(matches) == 0
