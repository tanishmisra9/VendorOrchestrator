import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock, patch
import json

from context.memory import SharedContext
from agents.deduplication import DeduplicationAgent


def _make_agent(mock_llm_response=None) -> DeduplicationAgent:
    ctx = SharedContext()
    ctx.new_run()

    mock_client = MagicMock()
    if mock_llm_response:
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(mock_llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

    return DeduplicationAgent(ctx, openai_client=mock_client)


class TestHighConfidenceDuplicates:
    def test_exact_tax_id_match_clusters(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "Acme Corporation", "address": "123 Main Street", "tax_id": "12-3456789"},
            {"vendor_name": "ACME Corp", "address": "123 Main St", "tax_id": "12-3456789"},
            {"vendor_name": "XYZ Logistics", "address": "999 Ocean Rd", "tax_id": "99-0000000"},
        ]
        result = agent.run(records)
        clustered = result["clustered_records"]
        assert clustered[0]["cluster_id"] == clustered[1]["cluster_id"]
        assert clustered[2]["cluster_id"] != clustered[0]["cluster_id"]


class TestLLMFallback:
    def test_medium_confidence_uses_llm(self):
        llm_response = {
            "judgment": "duplicate",
            "confidence": 0.75,
            "rationale": "Similar names and addresses suggest same entity",
        }
        agent = _make_agent(mock_llm_response=llm_response)

        records = [
            {"vendor_name": "Horizon Healthcare Ltd", "address": "444 Medical Dr", "tax_id": "11-9988776"},
            {"vendor_name": "Horizon Health Care Limited", "address": "444 Medical Drive", "tax_id": "11-9988776"},
        ]
        result = agent.run(records)
        clustered = result["clustered_records"]
        assert clustered[0]["cluster_id"] == clustered[1]["cluster_id"]

    def test_llm_says_not_duplicate(self):
        llm_response = {
            "judgment": "not_duplicate",
            "confidence": 0.3,
            "rationale": "Different entities despite similar names",
        }
        agent = _make_agent(mock_llm_response=llm_response)

        records = [
            {"vendor_name": "Delta Corp", "address": "100 River Rd", "tax_id": "88-1111111"},
            {"vendor_name": "Delta Inc", "address": "200 Lake Ave", "tax_id": "88-2222222"},
        ]
        result = agent.run(records)
        clustered = result["clustered_records"]
        assert clustered[0]["cluster_id"] != clustered[1]["cluster_id"]


class TestClusterAssignment:
    def test_all_unique_records_get_separate_clusters(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "Alpha Inc", "address": "1 A St", "tax_id": "11-1111111"},
            {"vendor_name": "Beta LLC", "address": "2 B Ave", "tax_id": "22-2222222"},
            {"vendor_name": "Gamma Co", "address": "3 C Rd", "tax_id": "33-3333333"},
        ]
        result = agent.run(records)
        cluster_ids = [r["cluster_id"] for r in result["clustered_records"]]
        assert len(set(cluster_ids)) == 3

    def test_context_updated(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "Acme Corp", "address": "123 Main St", "tax_id": "12-3456789"},
            {"vendor_name": "ACME Corporation", "address": "123 Main Street", "tax_id": "12-3456789"},
        ]
        agent.run(records)
        history = agent.context.read("matching_history")
        assert len(history) > 0
