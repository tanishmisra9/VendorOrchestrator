import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from context.memory import SharedContext
from agents.data_quality import DataQualityAgent


def _make_agent() -> DataQualityAgent:
    ctx = SharedContext()
    ctx.new_run()
    return DataQualityAgent(ctx)


class TestNameStandardization:
    def test_strips_whitespace_and_titlecases(self):
        agent = _make_agent()
        records = [{"vendor_name": "  acme  corp  ", "address": "", "city": "", "state": "", "tax_id": ""}]
        result = agent.run(records)
        assert result["cleaned_records"][0]["vendor_name"] == "Acme Corp"

    def test_removes_special_characters(self):
        agent = _make_agent()
        records = [{"vendor_name": "Acme@Corp#Inc", "address": "", "city": "", "state": "", "tax_id": ""}]
        result = agent.run(records)
        cleaned_name = result["cleaned_records"][0]["vendor_name"]
        assert "@" not in cleaned_name
        assert "#" not in cleaned_name


class TestAddressNormalization:
    def test_expands_abbreviations(self):
        agent = _make_agent()
        records = [{"vendor_name": "Test", "address": "123 Main St", "city": "NYC", "state": "NY", "tax_id": "12-3456789"}]
        result = agent.run(records)
        assert "Street" in result["cleaned_records"][0]["address"]

    def test_expands_multiple_abbreviations(self):
        agent = _make_agent()
        records = [{"vendor_name": "Test", "address": "456 Oak Ave Ste 100", "city": "LA", "state": "CA", "tax_id": "12-3456789"}]
        result = agent.run(records)
        addr = result["cleaned_records"][0]["address"]
        assert "Avenue" in addr
        assert "Suite" in addr


class TestTaxIdValidation:
    def test_formats_raw_digits(self):
        agent = _make_agent()
        records = [{"vendor_name": "Test", "address": "1 St", "city": "C", "state": "S", "tax_id": "123456789"}]
        result = agent.run(records)
        assert result["cleaned_records"][0]["tax_id"] == "12-3456789"

    def test_already_formatted(self):
        agent = _make_agent()
        records = [{"vendor_name": "Test", "address": "1 St", "city": "C", "state": "S", "tax_id": "12-3456789"}]
        result = agent.run(records)
        assert result["cleaned_records"][0]["tax_id"] == "12-3456789"

    def test_invalid_tax_id_flagged(self):
        agent = _make_agent()
        records = [{"vendor_name": "Test", "address": "1 St", "city": "C", "state": "S", "tax_id": "ABC"}]
        result = agent.run(records)
        assert result["quality_report"]["total_issues"] > 0


class TestMissingFields:
    def test_flags_missing_required(self):
        agent = _make_agent()
        records = [{"vendor_name": "", "address": "", "city": "", "state": "", "tax_id": ""}]
        result = agent.run(records)
        assert result["quality_report"]["flagged_records"] == 1

    def test_quality_issue_rate(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "Good Vendor", "address": "123 St", "city": "NYC", "state": "NY", "tax_id": "12-3456789"},
            {"vendor_name": "", "address": "", "city": "", "state": "", "tax_id": ""},
        ]
        result = agent.run(records)
        assert result["quality_report"]["quality_issue_rate"] > 0
