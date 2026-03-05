import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock
import json

from context.memory import SharedContext
from agents.vendor_check import VendorCheckAgent


def _make_agent(mock_llm_response=None) -> VendorCheckAgent:
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

    return VendorCheckAgent(ctx, openai_client=mock_client)


def _make_session_mock(vendors):
    """Create a session mock where all query chains return the given vendor list."""
    session_mock = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.limit.return_value.all.return_value = vendors
    filter_mock.all.return_value = vendors
    query_mock.filter.return_value = filter_mock
    session_mock.query.return_value = query_mock
    return session_mock


class TestVendorCheckNoExisting:
    @patch("agents.vendor_check.session_scope")
    @patch("agents.vendor_check.log_agent_action")
    def test_allows_when_no_existing(self, mock_log, mock_session):
        session_mock = _make_session_mock([])
        mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        agent = _make_agent()
        result = agent.run({"vendor_name": "New Vendor", "address": "1 St", "tax_id": "11-1111111"})
        assert result["recommendation"] == "allow"


class TestVendorCheckWithDuplicates:
    @patch("agents.vendor_check.session_scope")
    @patch("agents.vendor_check.log_agent_action")
    def test_warns_on_high_confidence_match(self, mock_log, mock_session):
        existing_vendor = MagicMock()
        existing_vendor.id = 1
        existing_vendor.to_dict.return_value = {
            "id": 1,
            "vendor_name": "Acme Corporation",
            "address": "123 Main Street",
            "tax_id": "12-3456789",
            "city": "NYC",
            "state": "NY",
            "zip": "10001",
            "country": "US",
            "status": "active",
            "cluster_id": None,
            "source": "batch",
            "created_at": None,
            "updated_at": None,
        }
        existing_vendor.status = "active"

        session_mock = _make_session_mock([existing_vendor])
        mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        agent = _make_agent()
        result = agent.run({
            "vendor_name": "Acme Corp",
            "address": "123 Main St",
            "tax_id": "12-3456789",
        })
        assert result["recommendation"] == "warn"
        assert len(result["matches"]) > 0
