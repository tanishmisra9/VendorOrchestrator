import os
import re
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from context.memory import SharedContext
from db.connection import init_db, session_scope
from db.models import VendorMaster, AuditLog, AnalystOverride as OverrideModel
from agents.vendor_check import VendorCheckAgent
from orchestrator.graph import run_pipeline, run_pipeline_stepwise
from utils.audit import log_analyst_override
from utils.errors import safe_message
from utils.matching import sanitize_like

load_dotenv()
logging.basicConfig(level=logging.INFO)

MAX_UPLOAD_SIZE_MB = 200

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
TAX_ID_PATTERN = re.compile(r"^\d{2}-\d{7}$")
ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")

st.set_page_config(
    page_title="Vendor Master Assistant",
    page_icon="📋",
    layout="wide",
)

st.markdown("""
<style>
/* Page title */
h1, h1 span { font-size: 3rem !important; font-weight: 700 !important; }
/* Section headers (st.header) */
h2, h2 span { font-size: 2.2rem !important; font-weight: 600 !important; }
/* Sub-headers (st.subheader) */
h3, h3 span { font-size: 1.8rem !important; font-weight: 600 !important; }
/* Caption under title — slightly larger */
div[data-testid="stCaptionContainer"] p { font-size: 17px !important; }
/* Body text — one consistent size, scoped to avoid headings */
div[data-testid="stMarkdownContainer"] > p { font-size: 15px !important; }
label, div[data-testid="stMetricLabel"] p { font-size: 15px !important; }
/* Warning alert text — smaller */
div.stWarning p { font-size: 14px !important; }
/* Metric values — tighten gap to label and size down 15% from 3.6rem */
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] div,
div[data-testid="stMetricValue"] p,
div[data-testid="stMetricValue"] span,
[data-testid="stMetricValue"] { font-size: 3rem !important; font-weight: 700 !important; margin-top: -8px !important; }
/* Tab labels — match section header size */
button[data-baseweb="tab"] { font-size: 1.4rem !important; }
/* Hide the default file uploader label */
div[data-testid="stFileUploader"] > label { display: none !important; }
/* Smaller caption for "* required column" */
.stCaption, div[data-testid="stCaptionContainer"] { font-size: 6px !important; }
</style>
""", unsafe_allow_html=True)


def _get_session_context() -> SharedContext:
    """Return a per-session SharedContext stored in st.session_state."""
    if "shared_context" not in st.session_state:
        st.session_state["shared_context"] = SharedContext()
    return st.session_state["shared_context"]


def _check_auth() -> bool:
    """Gate access behind a password if REQUIRE_AUTH is set."""
    if not REQUIRE_AUTH:
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("Vendor master assistant")
    password = st.text_input("Enter password to continue", type="password")
    if st.button("Login", type="primary"):
        if password == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def ensure_db():
    try:
        init_db()
        return True
    except Exception as e:
        st.error(f"Database connection failed: {safe_message(e)}")
        return False


def main():
    if not _check_auth():
        return

    st.title("Agentic vendor master assistant")
    st.caption("AI-powered vendor data management, deduplication, and enrichment")

    db_ok = ensure_db()

    tab_batch, tab_add, tab_search, tab_audit = st.tabs(
        ["Batch pipeline", "Add vendor", "Search vendors", "Audit log"]
    )

    with tab_batch:
        render_batch_tab(db_ok)

    with tab_add:
        render_add_vendor_tab(db_ok)

    with tab_search:
        render_search_tab(db_ok)

    with tab_audit:
        render_audit_tab(db_ok)


# ---------------------------------------------------------------------------
# Batch Pipeline
# ---------------------------------------------------------------------------

def render_batch_tab(db_ok: bool):
    st.header("Batch vendor processing")

    REQUIRED_COLUMNS = {"vendor_name"}
    EXPECTED_COLUMNS = {"vendor_name", "address", "city", "state", "zip", "country", "tax_id", "source"}
    EXPECTED_ORDERED = ["vendor_name", "address", "city", "state", "zip", "country", "tax_id", "source"]

    uploaded = st.file_uploader(
        "Drag and drop vendor file here", type=["csv", "xlsx", "xls"], key="batch_upload"
    )

    if uploaded is not None:
        st.markdown("""
        <style>
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {
            display: none !important;
        }
        </style>
        """, unsafe_allow_html=True)

        file_size_mb = uploaded.size / (1024 * 1024)
        if file_size_mb > MAX_UPLOAD_SIZE_MB:
            st.error(
                f"File too large ({file_size_mb:.1f} MB). "
                f"Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB."
            )
            return

        try:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded)
        except Exception as e:
            st.error(f"Failed to read file: {safe_message(e)}")
            return

        file_cols = set(df.columns.str.strip().str.lower())
        df.columns = df.columns.str.strip().str.lower()

        matched_cols = EXPECTED_COLUMNS & file_cols
        missing_required = REQUIRED_COLUMNS - file_cols
        missing_optional = EXPECTED_COLUMNS - REQUIRED_COLUMNS - file_cols
        extra_cols = file_cols - EXPECTED_COLUMNS

        st.markdown(
            f'<div style="background-color:#0e3a1e;border-radius:8px;padding:16px 20px;margin:8px 0;">'
            f'<span style="color:#4ade80;font-size:18px;font-weight:600;">{len(df):,} records</span>'
            f'<span style="color:#4ade80;font-size:18px;"> found in </span>'
            f'<code style="color:#4ade80;font-size:16px;">{uploaded.name}</code>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.subheader("Column validation")

        pills_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px 0;">'
        for col_name in EXPECTED_ORDERED:
            required_tag = " *" if col_name in REQUIRED_COLUMNS else ""
            if col_name in file_cols:
                pills_html += (
                    f'<span style="display:inline-block;padding:8px 18px;'
                    f'border-radius:8px;background-color:#0e3a1e;color:#4ade80;'
                    f'font-size:16px;font-family:monospace;font-weight:500;">'
                    f'{col_name}{required_tag}</span>'
                )
            else:
                label_extra = " (required, missing)" if col_name in REQUIRED_COLUMNS else " (missing)"
                pills_html += (
                    f'<span style="display:inline-block;padding:8px 18px;'
                    f'border-radius:8px;background-color:#3b1114;color:#f87171;'
                    f'font-size:16px;font-family:monospace;font-weight:500;">'
                    f'{col_name}{label_extra}</span>'
                )

        for col_name in sorted(extra_cols):
            pills_html += (
                f'<span style="display:inline-block;padding:8px 18px;'
                f'border-radius:8px;background-color:#3b1114;color:#f87171;'
                f'font-size:16px;font-family:monospace;font-weight:500;">'
                f'{col_name} (extra, ignored)</span>'
            )
        pills_html += '</div>'

        st.markdown(pills_html, unsafe_allow_html=True)
        st.caption("\\* required column")

        if missing_required:
            st.error(
                f"**Cannot proceed** — missing required column(s): "
                f"{', '.join(f'`{c}`' for c in sorted(missing_required))}. "
                f"Please fix your file and re-upload."
            )
            return

        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = ""

        if st.button("Run pipeline", type="primary", disabled=not db_ok):
            records = df.fillna("").to_dict(orient="records")
            ctx = _get_session_context()

            import time
            import random

            bar_el = st.empty()
            status_el = st.empty()

            def _render_bar(pct: float, color: str = "#3b82f6"):
                bar_el.markdown(
                    f'<div style="width:100%;height:8px;border-radius:4px;'
                    f'background-color:#1e293b;overflow:hidden;">'
                    f'<div style="width:{pct*100:.1f}%;height:100%;border-radius:4px;'
                    f'background-color:{color};'
                    f'transition:width 0.6s ease,background-color 1.2s ease;"></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            def _typewriter(element, text: str):
                displayed = ""
                i = 0
                while i < len(text):
                    burst = random.randint(2, 5)
                    chunk = text[i:i + burst]
                    displayed += chunk
                    i += burst
                    element.markdown(
                        f'<p style="font-size:16px;margin:0;">{displayed}'
                        f'<span style="animation:blink 1s step-end infinite;">|</span></p>'
                        f'<style>@keyframes blink {{50%{{opacity:0}}}}</style>',
                        unsafe_allow_html=True,
                    )
                    time.sleep(random.uniform(0.01, 0.06))
                element.markdown(
                    f'<p style="font-size:16px;margin:0;">{text}</p>',
                    unsafe_allow_html=True,
                )

            _render_bar(0)

            def on_step(step_name: str, step_index: int, total_steps: int):
                pct = step_index / total_steps if total_steps else 0
                _render_bar(pct)
                _typewriter(status_el, step_name)

            try:
                result = run_pipeline_stepwise(records, ctx, on_step=on_step)
            except Exception as e:
                status_el.empty()
                bar_el.empty()
                st.error(f"Pipeline failed: {safe_message(e)}")
                return

            _render_bar(1.0, "#22c55e")
            _typewriter(status_el, "Done.")
            time.sleep(0.8)
            status_el.empty()
            bar_el.markdown(
                '<div style="width:100%;height:8px;border-radius:4px;'
                'background-color:#1e293b;overflow:hidden;margin-bottom:32px;">'
                '<div style="width:100%;height:100%;border-radius:4px;'
                'background-color:#22c55e;"></div></div>',
                unsafe_allow_html=True,
            )

            col1, col2, col3, col4 = st.columns(4)
            lr = getattr(result, "load_result", {})
            if isinstance(lr, dict):
                col1.metric(
                    "Total processed",
                    f"{lr.get('total_processed', 0):,}",
                    help="Total number of vendor records read from the uploaded file.",
                )
                col2.metric(
                    "Canonical vendors",
                    f"{lr.get('inserted_canonical', 0):,}",
                    help="Unique vendors kept in the master. One representative record per duplicate group.",
                )
                col3.metric(
                    "Duplicates marked",
                    f"{lr.get('duplicates_marked', 0):,}",
                    help="Records identified as duplicates of a canonical vendor and suppressed from the active master.",
                )
                col4.metric(
                    "Clusters",
                    f"{lr.get('clusters', 0):,}",
                    help="Number of groups where two or more records were found to refer to the same vendor.",
                )

            qr = getattr(result, "quality_report", {})
            if isinstance(qr, dict) and qr:
                _render_quality_report(qr)


def _render_quality_report(qr: dict):
    total = qr.get("total_records", 0)
    flagged = qr.get("flagged_records", 0)
    clean = total - flagged
    issue_rate = qr.get("quality_issue_rate", 0)
    total_issues = qr.get("total_issues", 0)
    needs_review = qr.get("needs_review", False)

    if needs_review:
        st.warning(
            f"**Review recommended** — {issue_rate:.0%} of records had quality issues "
            f"(threshold: 20%)"
        )
    else:
        st.success(
            f"Quality looks good — only {issue_rate:.0%} of records had issues."
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Clean records", f"{clean:,}")
    col2.metric("Flagged records", f"{flagged:,}")
    col3.metric("Total issues found", f"{total_issues:,}")

    with st.expander("Raw report details", expanded=False):
        st.json(qr)


# ---------------------------------------------------------------------------
# Add Vendor
# ---------------------------------------------------------------------------

def render_add_vendor_tab(db_ok: bool):
    st.header("Add new vendor")

    with st.form("add_vendor_form"):
        col1, col2 = st.columns(2)
        with col1:
            vendor_name = st.text_input("Vendor name *")
            address = st.text_input("Address")
            city = st.text_input("City")
        with col2:
            state = st.text_input("State (2-letter code)")
            zip_code = st.text_input("ZIP code")
            country = st.text_input("Country", value="US")
        tax_id = st.text_input("Tax ID (EIN format: XX-XXXXXXX)")
        submitted = st.form_submit_button("Check & submit", type="primary", disabled=not db_ok)

    if submitted:
        errors = _validate_vendor_form(vendor_name, tax_id, zip_code, state)
        if errors:
            for err in errors:
                st.error(err)
            return

        new_vendor = {
            "vendor_name": vendor_name.strip(),
            "address": address.strip(),
            "city": city.strip(),
            "state": state.strip().upper(),
            "zip": zip_code.strip(),
            "country": country.strip() or "US",
            "tax_id": tax_id.strip(),
        }

        ctx = _get_session_context()
        ctx.new_run()
        agent = VendorCheckAgent(ctx)

        with st.spinner("Checking for duplicates..."):
            result = agent.run(new_vendor)

        st.session_state["vendor_check_result"] = result
        st.session_state["pending_vendor"] = new_vendor

    check_result = st.session_state.get("vendor_check_result")
    pending_vendor = st.session_state.get("pending_vendor")

    if check_result and pending_vendor:
        recommendation = check_result["recommendation"]
        matches = check_result["matches"]

        if recommendation == "allow":
            st.success(check_result["message"])
            _insert_vendor(pending_vendor)
            st.session_state.pop("vendor_check_result", None)
            st.session_state.pop("pending_vendor", None)
            st.balloons()

        elif recommendation == "warn":
            st.warning(check_result["message"])
            st.subheader("Potential duplicates")
            if matches:
                st.dataframe(pd.DataFrame(matches), use_container_width=True)

            col_accept, col_override = st.columns(2)
            with col_accept:
                if st.button("Accept as duplicate (don't add)", key="accept_dup"):
                    st.info("Vendor not added. Marked as known duplicate.")
                    st.session_state.pop("vendor_check_result", None)
                    st.session_state.pop("pending_vendor", None)
            with col_override:
                reason = st.text_input("Override reason", key="override_reason")
                if st.button("Override: add anyway", key="override_add"):
                    vendor_id = _insert_vendor(pending_vendor)
                    if vendor_id and matches:
                        log_analyst_override(
                            vendor_id=vendor_id,
                            original_action="block_duplicate",
                            override_action="force_insert",
                            reason=reason or "Analyst override",
                            analyst_name="analyst",
                        )
                    st.success("Vendor added with analyst override.")
                    st.session_state.pop("vendor_check_result", None)
                    st.session_state.pop("pending_vendor", None)


def _validate_vendor_form(
    vendor_name: str, tax_id: str, zip_code: str, state: str
) -> list[str]:
    errors = []
    if not vendor_name or not vendor_name.strip():
        errors.append("Vendor name is required.")
    if tax_id and tax_id.strip() and not TAX_ID_PATTERN.match(tax_id.strip()):
        errors.append("Tax ID must be in EIN format: XX-XXXXXXX (e.g. 12-3456789).")
    if zip_code and zip_code.strip() and not ZIP_PATTERN.match(zip_code.strip()):
        errors.append("ZIP code must be 5 digits or 5+4 format (e.g. 12345 or 12345-6789).")
    if state and state.strip() and state.strip().upper() not in US_STATES:
        errors.append(f"State '{state.strip()}' is not a valid 2-letter US state code.")
    return errors


def _insert_vendor(record: dict) -> int | None:
    try:
        with session_scope() as session:
            vendor = VendorMaster(
                vendor_name=record["vendor_name"],
                address=record.get("address"),
                city=record.get("city"),
                state=record.get("state"),
                zip=record.get("zip"),
                country=record.get("country", "US"),
                tax_id=record.get("tax_id"),
                status="active",
                source="manual_entry",
            )
            session.add(vendor)
            session.flush()
            return vendor.id
    except Exception as e:
        st.error(f"Failed to insert vendor: {safe_message(e)}")
        return None


# ---------------------------------------------------------------------------
# Search Vendors
# ---------------------------------------------------------------------------

def render_search_tab(db_ok: bool):
    st.header("Search vendor master")
    st.caption("Shows canonical (active) vendors by default. Expand a row to see its duplicate cluster.")

    if not db_ok:
        st.warning("Database not connected.")
        return

    col1, col2 = st.columns(2)
    with col1:
        search_name = st.text_input("Search by vendor name", key="search_name")
    with col2:
        search_tax = st.text_input("Search by tax ID", key="search_tax")

    show_dupes = st.toggle("Include duplicate records in results", value=False, key="show_dupes")

    has_filter = bool(search_name or search_tax)
    if has_filter:
        st.button("Search", key="search_btn", type="primary")

    with session_scope() as session:
        total_active = session.query(VendorMaster).filter(VendorMaster.status == "active").count()
        total_all = session.query(VendorMaster).count()

        if total_all == 0:
            st.info("No vendors in the database yet. Upload a file in the Batch pipeline tab to get started.")
            return

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Active vendors", f"{total_active:,}")
        col_m2.metric("Total records", f"{total_all:,}")
        col_m3.metric("Duplicates", f"{total_all - total_active:,}")

        st.divider()

        query = session.query(VendorMaster)

        if not show_dupes:
            query = query.filter(VendorMaster.status == "active")

        if search_name:
            safe_name = sanitize_like(search_name)
            query = query.filter(
                VendorMaster.vendor_name.ilike(f"%{safe_name}%")
            )
        if search_tax:
            safe_tax = sanitize_like(search_tax)
            query = query.filter(VendorMaster.tax_id.ilike(f"%{safe_tax}%"))

        results = query.order_by(VendorMaster.vendor_name).limit(200).all()

        if not results:
            st.info("No vendors found matching your criteria.")
            return

        if has_filter:
            st.subheader("Search results")
        else:
            st.subheader("All vendors")

        display_cols = ["id", "vendor_name", "address", "city", "state",
                       "zip", "country", "tax_id", "source"]
        if show_dupes:
            display_cols.insert(5, "status")
            display_cols.append("cluster_id")

        df = pd.DataFrame([v.to_dict() for v in results])
        df = df[[c for c in display_cols if c in df.columns]]
        st.dataframe(df, use_container_width=True)

        showing = len(results)
        if not show_dupes:
            st.caption(f"Showing {showing:,} of {total_active:,} active vendors"
                       + (" (filtered)" if has_filter else "") + " — max 200 rows")
        else:
            st.caption(f"Showing {showing:,} records (including duplicates)"
                       + (" (filtered)" if has_filter else "") + " — max 200 rows")

        cluster_ids = [
            v.cluster_id for v in results
            if v.cluster_id is not None
        ]

        if cluster_ids and not show_dupes:
            st.subheader("Duplicate clusters")
            st.caption("Expand a vendor below to see all records that were grouped as duplicates of it.")

            clusters_with_dupes = (
                session.query(VendorMaster)
                .filter(
                    VendorMaster.cluster_id.in_(cluster_ids),
                    VendorMaster.status == "duplicate",
                )
                .all()
            )
            dupes_by_cluster: dict[int, list[dict]] = {}
            for d in clusters_with_dupes:
                dupes_by_cluster.setdefault(d.cluster_id, []).append(d.to_dict())

            for vendor in results:
                cid = vendor.cluster_id
                dupes = dupes_by_cluster.get(cid, [])
                if not dupes:
                    continue
                with st.expander(
                    f"**{vendor.vendor_name}** — {len(dupes)} duplicate(s) in cluster #{cid}"
                ):
                    dupe_df = pd.DataFrame(dupes)
                    dupe_display = [c for c in ["id", "vendor_name", "address", "city",
                                                 "state", "tax_id", "source", "status"]
                                    if c in dupe_df.columns]
                    st.dataframe(dupe_df[dupe_display], use_container_width=True)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

def render_audit_tab(db_ok: bool):
    st.header("Audit log")

    audit_type = st.radio(
        "View", ["Agent actions", "Analyst overrides"], horizontal=True
    )

    if not db_ok:
        st.warning("Database not connected.")
        return

    if audit_type == "Agent actions":
        agent_filter = st.selectbox(
            "Filter by agent",
            ["All", "DataQualityAgent", "DeduplicationAgent", "LoaderAgent", "VendorCheckAgent"],
        )

        with session_scope() as session:
            query = session.query(AuditLog).order_by(AuditLog.timestamp.desc())
            if agent_filter != "All":
                query = query.filter(AuditLog.agent_name == agent_filter)
            logs = query.limit(200).all()

            if logs:
                data = [
                    {
                        "ID": l.id,
                        "Agent": l.agent_name,
                        "Action": l.action,
                        "Vendor ID": l.vendor_id,
                        "Confidence": l.confidence,
                        "Timestamp": l.timestamp,
                        "Details": str(l.details_json) if l.details_json else "",
                    }
                    for l in logs
                ]
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                st.info("No audit log entries found.")

    else:
        with session_scope() as session:
            overrides = (
                session.query(OverrideModel)
                .order_by(OverrideModel.timestamp.desc())
                .limit(200)
                .all()
            )
            if overrides:
                data = [
                    {
                        "ID": o.id,
                        "Vendor ID": o.vendor_id,
                        "Original Action": o.original_action,
                        "Override Action": o.override_action,
                        "Reason": o.reason,
                        "Analyst": o.analyst_name,
                        "Timestamp": o.timestamp,
                    }
                    for o in overrides
                ]
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                st.info("No analyst overrides recorded.")


if __name__ == "__main__":
    main()
