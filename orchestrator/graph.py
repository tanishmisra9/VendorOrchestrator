from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

from agents.data_quality import DataQualityAgent
from agents.deduplication import DeduplicationAgent
from agents.loader import LoaderAgent
from context.memory import SharedContext

logger = logging.getLogger(__name__)

QUALITY_ISSUE_THRESHOLD = 0.2


class PipelineState(BaseModel):
    """State object flowing through the LangGraph pipeline."""

    raw_records: list[dict] = Field(default_factory=list)
    cleaned_records: list[dict] = Field(default_factory=list)
    quality_report: dict = Field(default_factory=dict)
    clustered_records: list[dict] = Field(default_factory=list)
    load_result: dict = Field(default_factory=dict)
    needs_quality_review: bool = False
    quality_review_approved: bool = False
    context_snapshot: dict = Field(default_factory=dict)


def _make_data_quality_node(ctx: SharedContext):
    agent = DataQualityAgent(ctx)

    def data_quality_node(state: PipelineState) -> dict:
        result = agent.run(state.raw_records)
        return {
            "cleaned_records": result["cleaned_records"],
            "quality_report": result["quality_report"],
            "needs_quality_review": result["quality_report"].get("needs_review", False),
        }

    return data_quality_node


def _make_deduplication_node(ctx: SharedContext):
    agent = DeduplicationAgent(ctx)

    def deduplication_node(state: PipelineState) -> dict:
        result = agent.run(state.cleaned_records)
        return {"clustered_records": result["clustered_records"]}

    return deduplication_node


def _make_loader_node(ctx: SharedContext):
    agent = LoaderAgent(ctx)

    def loader_node(state: PipelineState) -> dict:
        result = agent.run(state.clustered_records)
        return {
            "load_result": result["load_result"],
            "context_snapshot": ctx.get_full_state(),
        }

    return loader_node


def _quality_review_node(state: PipelineState) -> dict:
    """Marks the pipeline as paused for analyst review.

    In the Streamlit UI this state is detected and the user
    is prompted to approve or reject continuation.
    For non-interactive runs we auto-approve.
    """
    logger.warning(
        "Quality review required: %.1f%% of records flagged",
        state.quality_report.get("quality_issue_rate", 0) * 100,
    )
    return {"quality_review_approved": True}


def _route_after_quality(state: PipelineState) -> str:
    if state.needs_quality_review:
        return "quality_review"
    return "deduplication"


def build_pipeline(context: Optional[SharedContext] = None) -> StateGraph:
    """Build and compile the vendor processing LangGraph pipeline."""
    if context is None:
        context = SharedContext()
        context.new_run()

    graph = StateGraph(PipelineState)

    graph.add_node("data_quality", _make_data_quality_node(context))
    graph.add_node("quality_review", _quality_review_node)
    graph.add_node("deduplication", _make_deduplication_node(context))
    graph.add_node("loader", _make_loader_node(context))

    graph.add_edge(START, "data_quality")

    graph.add_conditional_edges(
        "data_quality",
        _route_after_quality,
        {"quality_review": "quality_review", "deduplication": "deduplication"},
    )

    graph.add_edge("quality_review", "deduplication")
    graph.add_edge("deduplication", "loader")
    graph.add_edge("loader", END)

    return graph.compile()


def run_pipeline(
    records: list[dict], context: Optional[SharedContext] = None
) -> PipelineState:
    """Convenience function to run the full pipeline on a list of records."""
    if context is None:
        context = SharedContext()
    context.new_run()

    pipeline = build_pipeline(context)
    initial_state = PipelineState(raw_records=records)
    result = pipeline.invoke(initial_state)
    return result


def run_pipeline_stepwise(
    records: list[dict],
    context: Optional[SharedContext] = None,
    on_step: Optional[Any] = None,
) -> PipelineState:
    """Run the pipeline step-by-step, calling on_step(step_name, progress)
    between each stage so the UI can update a progress bar.

    on_step signature: (step_name: str, step_index: int, total_steps: int) -> None
    """
    if context is None:
        context = SharedContext()
    context.new_run()

    steps = [
        ("Cleaning and standardizing records...", "data_quality"),
        ("Finding and clustering duplicates...", "deduplication"),
        ("Inserting into vendor master database...", "loader"),
    ]
    total = len(steps)

    dq_agent = DataQualityAgent(context)
    dedup_agent = DeduplicationAgent(context)
    loader_agent = LoaderAgent(context)

    state = PipelineState(raw_records=records)

    # Step 1: Data Quality
    if on_step:
        on_step(steps[0][0], 0, total)
    dq_result = dq_agent.run(state.raw_records)
    state.cleaned_records = dq_result["cleaned_records"]
    state.quality_report = dq_result["quality_report"]
    state.needs_quality_review = dq_result["quality_report"].get("needs_review", False)

    if state.needs_quality_review:
        logger.warning(
            "Quality review required: %.1f%% of records flagged",
            state.quality_report.get("quality_issue_rate", 0) * 100,
        )

    # Step 2: Deduplication
    if on_step:
        on_step(steps[1][0], 1, total)
    dedup_result = dedup_agent.run(state.cleaned_records)
    state.clustered_records = dedup_result["clustered_records"]

    # Step 3: Loader
    if on_step:
        on_step(steps[2][0], 2, total)
    load_result = loader_agent.run(state.clustered_records)
    state.load_result = load_result["load_result"]
    state.context_snapshot = context.get_full_state()

    if on_step:
        on_step("Complete", total, total)

    return state
