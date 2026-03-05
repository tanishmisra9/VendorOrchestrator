import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock

from context.memory import SharedContext
from agents.loader import LoaderAgent


def _make_agent() -> LoaderAgent:
    ctx = SharedContext()
    ctx.new_run()
    return LoaderAgent(ctx)


class TestCanonicalSelection:
    def test_picks_most_complete_record(self):
        agent = _make_agent()
        members = [
            {"vendor_name": "Acme", "address": "", "city": "", "state": "", "tax_id": ""},
            {"vendor_name": "Acme Corp", "address": "123 Main St", "city": "NYC", "state": "NY", "tax_id": "12-3456789"},
        ]
        canonical = agent._pick_canonical(members)
        assert canonical["vendor_name"] == "Acme Corp"

    def test_single_member_is_canonical(self):
        agent = _make_agent()
        members = [{"vendor_name": "Only One", "address": "1 St", "city": "C", "state": "S", "tax_id": "11-1111111"}]
        canonical = agent._pick_canonical(members)
        assert canonical["vendor_name"] == "Only One"


class TestGroupByClusters:
    def test_groups_correctly(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "A", "cluster_id": 0},
            {"vendor_name": "B", "cluster_id": 0},
            {"vendor_name": "C", "cluster_id": 2},
        ]
        clusters = agent._group_by_cluster(records)
        assert len(clusters) == 2
        assert len(clusters[0]) == 2
        assert len(clusters[2]) == 1

    def test_no_cluster_id_uses_index(self):
        agent = _make_agent()
        records = [
            {"vendor_name": "A"},
            {"vendor_name": "B"},
        ]
        clusters = agent._group_by_cluster(records)
        assert len(clusters) == 2


class TestLoaderRun:
    @patch("agents.loader.log_agent_action")
    @patch("agents.loader.get_engine")
    def test_run_returns_summary(self, mock_engine, mock_log):
        mock_conn = MagicMock()
        mock_engine.return_value.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.begin.return_value.__exit__ = MagicMock(return_value=False)

        agent = _make_agent()
        records = [
            {"vendor_name": "Acme Corp", "address": "123 Main St", "city": "NYC", "state": "NY", "zip": "10001", "country": "US", "tax_id": "12-3456789", "cluster_id": 0},
            {"vendor_name": "ACME Corporation", "address": "123 Main Street", "city": "NYC", "state": "NY", "zip": "10001", "country": "US", "tax_id": "12-3456789", "cluster_id": 0},
            {"vendor_name": "XYZ Logistics", "address": "999 Ocean Rd", "city": "LA", "state": "CA", "zip": "90001", "country": "US", "tax_id": "99-0000000", "cluster_id": 2},
        ]
        result = agent.run(records)
        summary = result["load_result"]
        assert summary["total_processed"] == 3
        assert summary["clusters"] == 2
        assert summary["inserted_canonical"] + summary["duplicates_marked"] == 3
        assert mock_conn.execute.called
