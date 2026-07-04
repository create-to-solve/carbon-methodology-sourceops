import pandas as pd
import streamlit as st

try:
    import requests
except ImportError:  # pragma: no cover - handled in the Streamlit page.
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - handled in the Streamlit page.
    BeautifulSoup = None

from pipeline import (
    CANDIDATE_SCHEMA,
    EXTRACTION_ERROR_SCHEMA,
    FILES,
    SOURCE_RESOLUTION_AUDIT_FILE,
    SOURCE_RESOLUTION_AUDIT_SCHEMA,
    SOURCE_RESOLUTION_SCHEMA,
    SUPPORTED_EXTRACTORS,
    add_record_readiness,
    apply_output_safeguards,
    as_csv_download,
    clean_url,
    count_contains,
    count_value,
    current_extracted_links,
    current_extraction_errors,
    current_live_source_failures,
    current_methodunit_candidates,
    current_source_resolution_results,
    derive_onboarding_plan,
    ensure_columns,
    load_data,
    normalize_columns,
    normalize_text,
    pretty_label,
    run_candidate_extractors,
    save_timestamped_outputs,
    select_existing,
    session_or_output,
    text_blob,
    value_counts_df,
)
from extractors import (
    ARTISAN_C_SINK_FALLBACK_SOURCE_URL,
    SOURCE_CHECK_MAX_PROGRAMMES,
    extract_cfc_candidates,
    extract_climate_action_reserve_candidates,
    resolve_artisan_c_sink_source,
    run_source_check,
)


APP_TITLE = "Carbon Methodology Intelligence Platform"

RECOMMENDED_SOURCE_CHECK_PRESETS = [
    "Climate Action Reserve",
    "International Carbon Registry (ICR)",
    "Asia Carbon Institute",
    "City Forest Credits",
    "Clean Development Mechanism (CDM)",
    "American Carbon Registry (ACR)",
]

PAGE_SUMMARIES = {
    "home": "A board-level view of source coverage, automation readiness, and review risk across programmes.",
    "coverage": "Use this page to understand which programmes already have rows, where source status is unresolved, and how confident the source profile is.",
    "profiles": "Searchable source intelligence for each programme: official source locations, connector type, extraction strategy, confidence, and notes.",
    "connectors": "Extraction archetypes grouped by source pattern, with reusability and maintenance implications.",
    "waves": "A pragmatic ingestion roadmap: automate stable catalogues first, then handle semi-automated, manual, and unresolved sources.",
    "qa": "Open source-quality concerns that should be resolved before or during ingestion.",
    "actions": "The operating queue for what to do next by programme, priority, wave, and confidence.",
    "live_check": "Small-batch reachability and link-discovery checks for selected methodology source pages.",
    "candidate_extraction": "Controlled extraction of candidate MethodUnits from the first supported public source pages.",
    "about": "Definitions and rationale behind the SourceOps layer.",
}


st.set_page_config(page_title=APP_TITLE, layout="wide")


def page_summary(text: str) -> None:
    st.caption(text)


def section_note(text: str) -> None:
    st.caption(text)


def require_rows(df: pd.DataFrame, dataset_name: str) -> bool:
    if not df.empty:
        return True
    st.warning(f"No rows are loaded for {dataset_name}. Check that the expected CSV exists and has data.")
    return False


def dataframe_config(df: pd.DataFrame) -> dict:
    config = {}
    for column in df.columns:
        if column.endswith("_url") or column in {"official_website", "evidence_urls"}:
            label = "Current Source URL" if column == "current_source_url" else pretty_label(column)
            config[column] = st.column_config.LinkColumn(label, display_text=None, width="large")
        else:
            config[column] = st.column_config.TextColumn(pretty_label(column))
    return config


def show_dataframe(df: pd.DataFrame, key: str, height: int = 420) -> None:
    if df.empty:
        st.info("No rows match the current view. Clear one or more filters to broaden the result.")
        return
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=dataframe_config(df),
    )
    st.download_button(
        "Download filtered CSV",
        data=as_csv_download(df),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"download_{key}",
    )


def metric_row(metrics: list[tuple[str, str | int | float]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)


def show_bar_chart(df: pd.DataFrame, x: str, y: str, empty_message: str) -> None:
    if df.empty or x not in df.columns or y not in df.columns or df[y].sum() == 0:
        st.info(empty_message)
        return
    st.bar_chart(df, x=x, y=y)


def current_session_timestamp() -> str:
    summary = st.session_state.get("source_exploration_summary", {})
    if summary.get("Run timestamp"):
        return summary["Run timestamp"]
    extracted = current_extracted_links()
    if not extracted.empty and "extracted_at" in extracted.columns:
        latest = extracted["extracted_at"].astype(str).str.strip()
        latest = latest[latest.ne("")]
        if not latest.empty:
            return latest.max()
    return "Not run this session"


def sidebar_workspace_status(data: dict[str, pd.DataFrame]) -> None:
    profiles = data.get("source_profiles", pd.DataFrame())
    qa = data.get("qa_flags", pd.DataFrame())
    st.sidebar.caption("Workspace Status")
    st.sidebar.metric("Programmes", len(profiles))
    st.sidebar.metric("Operational connectors", len(SUPPORTED_EXTRACTORS))
    st.sidebar.metric("Candidate methods", len(current_methodunit_candidates()))
    st.sidebar.metric("Evidence links", len(current_extracted_links()))
    st.sidebar.metric("QA rules", len(qa))
    st.sidebar.caption(f"Last refresh: {current_session_timestamp()}")


def inline_filters(df: pd.DataFrame, filter_columns: list[str], key_prefix: str, defaults: dict[str, list[str]] | None = None) -> pd.DataFrame:
    filtered = df.copy()
    if filtered.empty:
        return filtered
    columns = st.columns(min(len(filter_columns), 5) or 1)
    defaults = defaults or {}
    for index, filter_column in enumerate(filter_columns):
        if filter_column not in filtered.columns:
            continue
        options = sorted([value for value in filtered[filter_column].dropna().unique() if str(value).strip()])
        with columns[index % len(columns)]:
            selected = st.multiselect(
                pretty_label(filter_column),
                options,
                default=[value for value in defaults.get(filter_column, []) if value in options],
                key=f"{key_prefix}_{filter_column}",
            )
        if selected:
            filtered = filtered[filtered[filter_column].isin(selected)]
    return filtered


def source_resolution_audit_warnings(data: dict[str, pd.DataFrame]) -> None:
    for warning in data.get("source_resolution_audit_warnings", []):
        st.warning(warning)


def audit_project_count(audit: pd.DataFrame) -> int:
    if audit.empty or "project_count" not in audit.columns:
        return 0
    values = audit["project_count"].astype(str).str.replace(",", "", regex=False).str.strip()
    return int(pd.to_numeric(values, errors="coerce").fillna(0).sum())


def count_yes_or_partial(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    normalized = df[column].astype(str).str.strip().str.lower()
    return int(normalized.isin(["yes", "partial"]).sum())


def count_yes(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int(df[column].astype(str).str.strip().str.lower().eq("yes").sum())


def source_resolution_audit_issue_rows(audit: pd.DataFrame) -> pd.DataFrame:
    if audit.empty:
        return audit.copy()
    issue = audit.get("creates_issue_record", pd.Series("", index=audit.index)).astype(str).str.strip().str.lower().eq("yes")
    review_status = audit.get("review_status", pd.Series("", index=audit.index)).astype(str).str.strip().str.lower()
    review_issue = review_status.isin(["needs_research", "access_request", "unresolved", "parked"])
    return audit[issue | review_issue].copy()


def programme_status_counts(profiles: pd.DataFrame, plan: pd.DataFrame) -> dict[str, int]:
    if profiles.empty:
        return {
            "total_programmes": 0,
            "programmes_mapped": 0,
            "programmes_requiring_investigation": 0,
            "operational_connectors": 0,
        }
    method_source = profiles.get("method_source_url", pd.Series("", index=profiles.index)).astype(str).str.strip()
    official_site = profiles.get("official_website", pd.Series("", index=profiles.index)).astype(str).str.strip()
    mapped = method_source.ne("") | official_site.ne("")
    investigation_categories = [
        "Needs manual investigation",
        "Needs URL repair",
        "Needs browser automation later",
        "Needs document/PDF parsing",
    ]
    investigation = int(plan.get("onboarding_category", pd.Series("", index=plan.index)).isin(investigation_categories).sum())
    return {
        "total_programmes": len(profiles),
        "programmes_mapped": int(mapped.sum()),
        "programmes_requiring_investigation": investigation,
        "operational_connectors": count_value(plan, "onboarding_category", "Working extractor"),
    }


def source_pattern_label(row: pd.Series) -> str:
    text = text_blob(row, ["connector_type", "source_type", "extraction_strategy", "notes", "populated_source_status"])
    if any(term in text for term in ["js-heavy", "portal", "dynamic", "headless"]):
        return "JS-heavy portals"
    if any(term in text for term in ["adopted", "external", "cdm"]):
        return "Adopted external methods"
    if any(term in text for term in ["api", "registry"]):
        return "API/registry sources"
    if any(term in text for term in ["pdf", "document", "guideline"]):
        return "PDF/document-first"
    if any(term in text for term in ["catalog", "catalogue", "html", "table", "list"]):
        return "HTML/catalogue-first"
    return "Unknown/manual investigation"


def source_pattern_counts(profiles: pd.DataFrame) -> pd.DataFrame:
    labels = [
        "HTML/catalogue-first",
        "PDF/document-first",
        "JS-heavy portals",
        "Adopted external methods",
        "API/registry sources",
        "Unknown/manual investigation",
    ]
    if profiles.empty:
        return pd.DataFrame({"Source pattern": labels, "Programmes": [0] * len(labels)})
    pattern_series = profiles.apply(source_pattern_label, axis=1)
    counts = pattern_series.value_counts().reindex(labels, fill_value=0).reset_index()
    counts.columns = ["Source pattern", "Programmes"]
    return counts


def maturity_counts(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty or "onboarding_category" not in plan.columns:
        return pd.DataFrame(columns=["Coverage maturity", "Programmes"])
    label_map = {
        "Working extractor": "Operational / partial connector",
        "Ready for extraction": "Ready for connector build",
        "Needs URL repair": "Access issue or URL repair",
        "Needs document/PDF parsing": "Documents found / parsing later",
        "Needs browser automation later": "Portal source / not attempted yet",
        "Needs adopted-method handling": "Adopted-method handling needed",
        "Needs manual investigation": "Source resolution needed",
    }
    maturity = plan["onboarding_category"].map(label_map).fillna(plan["onboarding_category"])
    counts = maturity.value_counts().reset_index()
    counts.columns = ["Coverage maturity", "Programmes"]
    return counts


def connector_priority_rows(data: dict[str, pd.DataFrame], plan: pd.DataFrame) -> pd.DataFrame:
    priorities = []
    if not plan.empty and "program_name" in plan.columns:
        for target in ["American Carbon Registry", "Climate Forward", "Plan Vivo", "City Forest Credits"]:
            matches = plan[plan["program_name"].astype(str).str.contains(target, case=False, na=False)]
            if matches.empty:
                continue
            row = matches.iloc[0]
            priorities.append(
                {
                    "Rank": len(priorities) + 1,
                    "Programme": row.get("program_name", target),
                    "Why it matters": "High-priority catalogue-first HTML source." if "American Carbon Registry" in target else row.get("recommended_next_action", ""),
                    "Current status": row.get("current_extraction_status", "not attempted yet"),
                }
            )
    if not any("American Carbon Registry" in str(row.get("Programme", "")) for row in priorities):
        priorities.insert(
            0,
            {
                "Rank": 1,
                "Programme": "American Carbon Registry",
                "Why it matters": "American Carbon Registry - high-priority catalogue-first HTML source.",
                "Current status": "not attempted yet",
            },
        )
    for index, row in enumerate(priorities, start=1):
        row["Rank"] = index
    return pd.DataFrame(priorities[:5])


def render_audit_summary(audit: pd.DataFrame, key_prefix: str) -> None:
    metric_row(
        [
            ("Total audited sources", len(audit)),
            ("Project count covered", audit_project_count(audit)),
            ("Creates method record", count_yes_or_partial(audit, "creates_methodology_record")),
            ("Creates issue record", count_yes(audit, "creates_issue_record")),
        ]
    )
    left, right = st.columns(2)
    with left:
        st.caption("Recommended catalogue action")
        show_dataframe(
            value_counts_df(audit, "recommended_catalogue_action", "recommended_catalogue_action"),
            f"{key_prefix}_action_counts",
            height=220,
        )
    with right:
        st.caption("Review status")
        show_dataframe(
            value_counts_df(audit, "review_status", "review_status"),
            f"{key_prefix}_review_counts",
            height=220,
        )


def render_source_resolution_audit_table(data: dict[str, pd.DataFrame], key_prefix: str) -> pd.DataFrame:
    source_resolution_audit_warnings(data)
    audit = data.get("source_resolution_audit", pd.DataFrame(columns=SOURCE_RESOLUTION_AUDIT_SCHEMA))
    audit = audit.copy()
    if audit.empty:
        st.info("No mid-activity source-resolution audit rows are loaded.")
        return audit

    st.info(
        "This audit does not mean all sources can be extracted. It classifies each source into an action: "
        "automate, capture document family, store pointer, request access, derive from projects, or mark unresolved."
    )
    render_audit_summary(audit, f"{key_prefix}_summary")
    filtered = inline_filters(
        audit,
        [
            "recommended_catalogue_action",
            "recommended_ingestion_mode",
            "review_status",
            "source_access_issue",
            "confidence",
        ],
        key_prefix,
    )
    display_columns = [
        "activity_tier",
        "project_count",
        "programme",
        "official_website",
        "source_resolves",
        "dedicated_methodology_page",
        "where_methodology_info_lives",
        "methodology_model",
        "approximate_count",
        "recommended_catalogue_action",
        "recommended_ingestion_mode",
        "confidence",
        "assessment_basis",
        "source_access_issue",
        "creates_methodology_record",
        "creates_supporting_links",
        "creates_issue_record",
        "review_status",
        "notes",
        "last_verified",
        "evidence_urls",
    ]
    show_dataframe(select_existing(filtered, display_columns), f"{key_prefix}_filtered", height=520)
    return filtered


def normalize_demo_extraction_result(result: tuple) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    candidates = result[0] if len(result) > 0 else []
    error = result[1] if len(result) > 1 else ""
    metrics = result[2] if len(result) > 2 else {}
    errors = []
    if error:
        if isinstance(error, list):
            errors.extend(error)
        else:
            errors.append(error)
    return (
        apply_output_safeguards(
            pd.DataFrame(
                [{column: candidate.get(column, "") for column in CANDIDATE_SCHEMA} for candidate in candidates],
                columns=CANDIDATE_SCHEMA,
            )
        ),
        pd.DataFrame(
            [{column: row.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for row in errors],
            columns=EXTRACTION_ERROR_SCHEMA,
        ),
        metrics,
    )


def render_result_interpretation(candidates: pd.DataFrame, errors: pd.DataFrame) -> None:
    if candidates.empty and errors.empty:
        return
    extracted_records = candidates[
        candidates.get("candidate_type", pd.Series(dtype=str)).eq("methodunit_candidate")
    ].copy()
    supporting_links = candidates[
        ~candidates.get("candidate_type", pd.Series(dtype=str)).eq("methodunit_candidate")
    ].copy()
    extracted_with_readiness = add_record_readiness(extracted_records)
    issues_attention = (
        len(errors)
        + count_value(extracted_with_readiness, "record_readiness", "needs_research")
        + count_value(extracted_with_readiness, "record_readiness", "source_issue")
    )

    metric_row(
        [
            ("Extracted methodology/protocol records", len(extracted_records)),
            ("Supporting links separated", len(supporting_links)),
            ("Issues requiring attention", issues_attention),
            ("Errors logged", len(errors)),
        ]
    )

    st.markdown("**What worked**")
    ready_records = extracted_with_readiness[extracted_with_readiness["record_readiness"].eq("ready_for_review")]
    if ready_records.empty:
        st.info("No ready-for-review methodology/protocol records were produced in the current output.")
    else:
        worked_rows = []
        for source_name, group in ready_records.groupby("program_name", dropna=False):
            source_text = normalize_text(source_name)
            if "Climate Action Reserve" in source_text:
                interpretation = "structured-table extraction working"
                action = "ready for review/export"
            elif "City Forest Credits" in source_text:
                interpretation = "document/protocol-family discovery working"
                action = "review document titles and versions"
            else:
                interpretation = "source-specific extraction produced usable records"
                action = "review and prepare for catalogue export"
            worked_rows.append(
                {
                    "Source": source_text or "Unknown source",
                    "Extracted records": len(group),
                    "Interpretation": interpretation,
                    "Recommended next action": action,
                }
            )
        st.dataframe(pd.DataFrame(worked_rows), hide_index=True, use_container_width=True)

    st.markdown("**What needs review**")
    needs_review_rows = []
    icr_records = extracted_with_readiness[
        extracted_with_readiness.get("program_name", pd.Series("", index=extracted_with_readiness.index)).astype(str).str.contains(
            "International Carbon Registry|ICR", case=False, na=False,
        )
    ]
    if not icr_records.empty:
        needs_review_rows.append(
            {
                "Source": "International Carbon Registry / ICR",
                "Records": len(icr_records),
                "Interpretation": "M-ICR codes and detail URLs discovered, but titles may require manual review.",
                "Recommended next action": "Treat as discovery records until titles are verified.",
            }
        )
    other_needs = extracted_with_readiness[
        extracted_with_readiness["record_readiness"].eq("needs_research")
        & ~extracted_with_readiness.index.isin(icr_records.index)
    ]
    for source_name, group in other_needs.groupby("program_name", dropna=False):
        needs_review_rows.append(
            {
                "Source": normalize_text(source_name) or "Unknown source",
                "Records": len(group),
                "Interpretation": "Partial or uncertain extracted records.",
                "Recommended next action": "Review titles, status, version, and source evidence before export.",
            }
        )
    if needs_review_rows:
        st.dataframe(pd.DataFrame(needs_review_rows), hide_index=True, use_container_width=True)
    else:
        st.info("No partial or uncertain extracted records are visible in the current output.")

    st.markdown("**What could not be accessed**")
    if errors.empty:
        st.info("No source-access or extraction errors were logged in the current output.")
    else:
        access_rows = []
        for source_name, group in errors.groupby("program_name", dropna=False):
            source_text = normalize_text(source_name)
            if "Asia Carbon Institute" in source_text:
                interpretation = "SSL/source-access issue logged; not treated as methodology extraction failure."
                action = "Open manually in browser or retry later; do not bypass SSL by default."
            else:
                interpretation = "Source fetch or extraction issue logged."
                action = "Review the source URL and retry when appropriate."
            access_rows.append(
                {
                    "Source": source_text or "Unknown source",
                    "Issues": len(group),
                    "Interpretation": interpretation,
                    "Recommended next action": action,
                }
            )
        st.dataframe(pd.DataFrame(access_rows), hide_index=True, use_container_width=True)

    st.markdown("**What was separated out**")
    separated_rows = pd.DataFrame(
        [
            {"Separated type": "Supporting documents", "Rows": count_value(candidates, "candidate_type", "supporting_document")},
            {"Separated type": "Development pages", "Rows": count_value(candidates, "candidate_type", "development_page")},
            {"Separated type": "Navigation links", "Rows": count_value(candidates, "candidate_type", "navigation_link")},
            {"Separated type": "Excluded rows", "Rows": count_value(candidates, "candidate_type", "exclude")},
        ]
    )
    st.dataframe(separated_rows, hide_index=True, use_container_width=True)


def interpreting_outputs_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("How to Read the Outputs")
    page_summary("Use this page before reviewing exported CSVs. It explains what each output means and what it does not mean.")

    rows = [
        {
            "Term": "Candidate MethodUnit",
            "Meaning": "A possible methodology/protocol record found by the app.",
            "How to Interpret": "It is not approved for catalogue ingestion until reviewed.",
        },
        {
            "Term": "Supporting Link",
            "Meaning": "A source URL captured during extraction, including PDFs, FAQs, templates, guidance pages, development pages, navigation links, and excluded links.",
            "How to Interpret": "Useful links are preserved even when they are not treated as methodology records.",
        },
        {
            "Term": "Issue to Resolve",
            "Meaning": "A data-quality issue, source-access failure, extraction error, or review-needed record.",
            "How to Interpret": "Resolve or document before Export for Catalogue when material.",
        },
        {
            "Term": "Review Queue",
            "Meaning": "The set of extracted methodology records awaiting human review.",
            "How to Interpret": "`pending_review` means the row still needs reviewer judgment.",
        },
        {
            "Term": "Export for Catalogue",
            "Meaning": "A downloadable or timestamp-saved CSV package for downstream catalogue work.",
            "How to Interpret": "Export is a handoff artifact, not an automatic catalogue import.",
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.subheader("Important Reading Rules")
    st.write("- Extracted records are not approved methodologies.")
    st.write("- `review_status = pending_review` means human review is still required.")
    st.write("- High confidence means extraction confidence, not business, legal, or carbon-market approval.")
    st.write("- Supporting documents are preserved as Supporting Links but separated from extracted methodology records.")


def live_source_check_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Step 1: Check source access")
    page_summary(PAGE_SUMMARIES["live_check"])
    if not require_rows(data["source_profiles"], "source profiles"):
        return

    st.write(
        "This check does not ingest methodologies yet. It verifies whether source pages are reachable "
        "and whether methodology/protocol/document links can be discovered for review."
    )
    st.caption(
        "It fetches only the selected source page, follows redirects, and lists candidate links. "
        "It does not fetch linked PDFs, bypass access controls, create accounts, or run at scale."
    )

    if requests is None or BeautifulSoup is None:
        st.error("Live checks require `requests` and `beautifulsoup4`. Install dependencies from requirements.txt.")
        return

    profiles = data["source_profiles"].copy()
    for column in ["program_name", "method_source_url", "official_website", "connector_type", "confidence"]:
        if column not in profiles.columns:
            profiles[column] = ""

    profiles["method_source_url"] = profiles["method_source_url"].astype(str).map(clean_url)
    profiles["official_website"] = profiles["official_website"].astype(str).map(clean_url)
    profiles["has_method_source_url"] = profiles["method_source_url"].astype(str).str.len() > 0

    st.subheader("Select Sources")
    left, right = st.columns(2)
    with left:
        only_method_sources = st.checkbox("Only show rows with Method Source URL", value=True)
    with right:
        allow_website_fallback = st.checkbox(
            "Use Official Website when Method Source URL is missing",
            value=False,
            help="Fallback is useful for reconnaissance, but the default stays focused on method source pages.",
        )

    candidates = profiles.copy()
    if only_method_sources:
        candidates = candidates[candidates["has_method_source_url"]]

    candidates["source_check_url"] = candidates["method_source_url"]
    if allow_website_fallback:
        candidates.loc[candidates["source_check_url"].eq(""), "source_check_url"] = candidates["official_website"]
    candidates = candidates[candidates["source_check_url"].astype(str).str.len() > 0]

    connector_options = sorted(
        [value for value in candidates["connector_type"].dropna().unique() if str(value).strip()]
    )
    selected_connectors = st.multiselect("Source Pattern", connector_options, help="Optional filter before selecting programmes.")
    if selected_connectors:
        candidates = candidates[candidates["connector_type"].isin(selected_connectors)]

    programme_options = sorted(candidates["program_name"].dropna().unique())
    preset_default = [name for name in RECOMMENDED_SOURCE_CHECK_PRESETS if name in programme_options]
    use_presets = st.checkbox("Start with recommended quick-check preset", value=True)
    default_selection = preset_default if use_presets else []

    selected_programmes = st.multiselect(
        "Programmes to check",
        programme_options,
        default=default_selection,
        help=f"Small-batch guard: maximum {SOURCE_CHECK_MAX_PROGRAMMES} programmes per run.",
    )

    selected_rows = candidates[candidates["program_name"].isin(selected_programmes)].drop_duplicates("program_name")
    st.caption(f"{len(selected_rows)} programmes selected. Maximum per run: {SOURCE_CHECK_MAX_PROGRAMMES}.")

    preview_columns = [
        "program_name",
        "source_check_url",
        "method_source_url",
        "official_website",
        "connector_type",
        "confidence",
    ]
    with st.expander("Selected source preview", expanded=False):
        show_dataframe(select_existing(selected_rows, preview_columns), "live_source_check_selection", height=240)

    run_check = st.button("Run live source check", type="primary", disabled=selected_rows.empty)
    if run_check:
        if len(selected_rows) > SOURCE_CHECK_MAX_PROGRAMMES:
            st.error(f"Select {SOURCE_CHECK_MAX_PROGRAMMES} or fewer programmes for a single reconnaissance run.")
        else:
            results = []
            progress = st.progress(0, text="Starting source checks...")
            for index, (_, row) in enumerate(selected_rows.iterrows(), start=1):
                progress.progress(
                    index / len(selected_rows),
                    text=f"Checking {row.get('program_name', 'selected programme')} ({index}/{len(selected_rows)})",
                )
                results.append(run_source_check(row))
            progress.empty()
            st.session_state["live_source_check_results"] = pd.DataFrame(results)

    results_df = st.session_state.get("live_source_check_results", pd.DataFrame())
    if not results_df.empty:
        st.subheader("Source Check Results")
        status_counts = value_counts_df(results_df, "check_status", "check_status")
        show_bar_chart(status_counts, "check_status", "count", "No source-check statuses are available.")
        display_columns = [
            "checked_at",
            "program_name",
            "check_status",
            "status_code",
            "source_url",
            "final_url",
            "content_type",
            "response_size_bytes",
            "page_title",
            "total_links",
            "pdf_links",
            "likely_link_count",
            "likely_links",
            "content_hash",
            "error",
        ]
        show_dataframe(select_existing(results_df, display_columns), "live_source_check_results", height=460)
    else:
        st.info("Select programmes and run a check to see results here.")


def candidate_extraction_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Step 2: Extract or resolve records")
    page_summary(PAGE_SUMMARIES["candidate_extraction"])
    if not require_rows(data["source_profiles"], "source profiles"):
        return

    st.write(
        "This page extracts possible methodology/protocol records from selected public source pages. "
        "The outputs are not automatically approved; they enter a human review queue."
    )
    st.caption(
        "Supported in this prototype: Climate Action Reserve, International Carbon Registry / ICR, "
        "Asia Carbon Institute, and City Forest Credits. These source-specific extractors fetch only the selected public listing pages and "
        "collect candidate links or table rows; linked PDFs are not fetched."
    )

    if requests is None or BeautifulSoup is None:
        st.error("Candidate extraction requires `requests` and `beautifulsoup4`. Install dependencies from requirements.txt.")
        return

    selected_extractors = st.multiselect(
        "Supported source-specific extractors",
        SUPPORTED_EXTRACTORS,
        default=SUPPORTED_EXTRACTORS,
        help="Only these controlled public-source extractors are enabled.",
    )
    allow_insecure_ssl = st.checkbox(
        "Allow insecure SSL for analyst testing",
        value=False,
        help="Use only for a selected manual run when a public source has a certificate verification issue.",
    )
    if allow_insecure_ssl:
        st.warning("Insecure SSL verification disabled for analyst testing. Do not use this for production ingestion.")
    run_extraction = st.button("Run extraction", type="primary", disabled=not selected_extractors)

    if run_extraction:
        with st.spinner("Extracting candidate MethodUnits from selected public source pages..."):
            candidates_df, errors_df, enrichment_metrics = run_candidate_extractors(
                selected_extractors,
                data["source_profiles"],
                allow_insecure_ssl=allow_insecure_ssl,
            )
        st.session_state["candidate_extraction_results"] = candidates_df
        st.session_state["candidate_extraction_errors"] = errors_df
        st.session_state["candidate_extraction_enrichment_metrics"] = enrichment_metrics
        st.session_state["candidate_extraction_sources_attempted"] = len(selected_extractors)
        st.session_state["demo_source_last_run"] = "Source-specific extraction"
        st.session_state["source_resolution_last_run"] = ""

    candidates = apply_output_safeguards(
        st.session_state.get("candidate_extraction_results", pd.DataFrame(columns=CANDIDATE_SCHEMA))
    )
    errors = st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    enrichment_metrics = st.session_state.get("candidate_extraction_enrichment_metrics", {})
    sources_attempted = st.session_state.get("candidate_extraction_sources_attempted", 0)

    methodunit_count = count_value(candidates, "candidate_type", "methodunit_candidate")
    supporting_count = count_value(candidates, "candidate_type", "supporting_document")
    development_count = count_value(candidates, "candidate_type", "development_page")
    navigation_count = count_value(candidates, "candidate_type", "navigation_link")
    excluded_count = count_value(candidates, "candidate_type", "exclude")
    pending_review = count_value(candidates, "review_status", "pending_review")

    if sources_attempted or not candidates.empty or not errors.empty:
        st.subheader("Output Routing")
        routing_rows = [
            {
                "Output": "Extracted records",
                "Count": methodunit_count,
                "Next tab": "Review Extracted Records",
                "Purpose": "Review possible methodology/protocol records before catalogue export.",
            },
            {
                "Output": "Supporting links",
                "Count": len(candidates) - methodunit_count,
                "Next tab": "Supporting Links",
                "Purpose": "Audit useful links that were not treated as methodology records.",
            },
            {
                "Output": "Errors / issues",
                "Count": len(errors),
                "Next tab": "Issues to Resolve",
                "Purpose": "Resolve source-access or extraction issues.",
            },
            {
                "Output": "Downloads / saved files",
                "Count": methodunit_count + len(candidates) + len(errors),
                "Next tab": "Export for Catalogue",
                "Purpose": "Download or save review-ready CSV handoff files.",
            },
        ]
        st.dataframe(pd.DataFrame(routing_rows), hide_index=True, use_container_width=True)

    metric_row(
        [
            ("Sources attempted", sources_attempted),
            ("Total extracted rows", len(candidates)),
            ("Extracted methodology records", methodunit_count),
            ("Supporting documents", supporting_count),
        ]
    )
    metric_row(
        [
            ("Development pages", development_count),
            ("Navigation links", navigation_count),
            ("Excluded rows", excluded_count),
            ("Pending review", pending_review),
        ]
    )
    methodunit_rows = candidates[candidates.get("candidate_type", pd.Series("", index=candidates.index)).eq("methodunit_candidate")]
    missing_title = methodunit_rows[
        methodunit_rows.get("methodunit_name", pd.Series("", index=methodunit_rows.index)).astype(str).str.strip().isin(["", "Title requires review"])
    ]
    missing_status = methodunit_rows[
        methodunit_rows.get("status", pd.Series("", index=methodunit_rows.index)).astype(str).str.strip().eq("")
    ]
    needs_review = methodunit_rows[
        methodunit_rows.get("review_status", pd.Series("", index=methodunit_rows.index)).astype(str).str.lower().eq("pending_review")
    ]
    st.subheader("Quality Summary")
    metric_row(
        [
            ("Table-derived records", count_value(methodunit_rows, "extraction_method", "table_parse")),
            ("Link-derived records", count_value(methodunit_rows, "extraction_method", "link_parse")),
            ("Records missing title", len(missing_title)),
            ("Records missing status", len(missing_status)),
            ("Records needing review", len(needs_review)),
        ]
    )
    st.caption("ICR detail-page enrichment")
    metric_row(
        [
            ("ICR candidates found", int(enrichment_metrics.get("icr_candidates_found", 0) or 0)),
            ("ICR detail pages fetched", int(enrichment_metrics.get("icr_detail_pages_fetched", 0) or 0)),
            ("ICR titles extracted", int(enrichment_metrics.get("icr_titles_extracted", 0) or 0)),
            ("ICR titles still requiring review", int(enrichment_metrics.get("icr_titles_still_requiring_review", 0) or 0)),
            ("ICR fetch failures", int(enrichment_metrics.get("icr_fetch_failures", 0) or 0)),
            ("ICR suspicious titles rejected", int(enrichment_metrics.get("icr_suspicious_titles_rejected", 0) or 0)),
        ]
    )
    st.caption("City Forest Credits document/protocol-family extraction")
    metric_row(
        [
            ("CFC records found", int(enrichment_metrics.get("cfc_records_found", 0) or 0)),
            ("CFC document links found", int(enrichment_metrics.get("cfc_document_links_found", 0) or 0)),
            ("CFC supporting links found", int(enrichment_metrics.get("cfc_supporting_links_found", 0) or 0)),
            ("CFC records missing version", int(enrichment_metrics.get("cfc_records_missing_version", 0) or 0)),
            ("CFC fetch failures", int(enrichment_metrics.get("cfc_fetch_failures", 0) or 0)),
        ]
    )

    if not errors.empty:
        st.subheader("Extraction Errors")
        section_note("Failed source checks are separated from extracted rows so reviewers can decide whether to retry or inspect manually.")
        show_dataframe(select_existing(errors, EXTRACTION_ERROR_SCHEMA), "extraction_errors", height=220)

    if candidates.empty:
        st.info("Run candidate extraction to populate the candidate MethodUnit table.")
        return

    st.subheader("Review Filters")
    filter_col_0, filter_col_1, filter_col_2, filter_col_3, filter_col_4, filter_col_5 = st.columns(6)
    filtered = candidates.copy()
    filter_specs = [
        (filter_col_0, "candidate_type"),
        (filter_col_1, "program_name"),
        (filter_col_2, "unit_type"),
        (filter_col_3, "confidence"),
        (filter_col_4, "status"),
        (filter_col_5, "review_status"),
    ]
    for container, column in filter_specs:
        if column not in filtered.columns:
            continue
        options = sorted([value for value in filtered[column].dropna().unique() if str(value).strip()])
        with container:
            default = ["methodunit_candidate"] if column == "candidate_type" and "methodunit_candidate" in options else []
            selected = st.multiselect(pretty_label(column), options, default=default, key=f"candidate_filter_{column}")
        if selected:
            filtered = filtered[filtered[column].isin(selected)]

    st.subheader("Classified Extracted Rows")
    section_note(
        f"{len(filtered)} rows shown after filters. The default view shows extracted methodology records only; include other types to audit supporting links."
    )
    display_df = select_existing(filtered, CANDIDATE_SCHEMA)
    if display_df.empty:
        st.info("No rows match the current candidate filters.")
    else:
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=480,
            column_config=dataframe_config(display_df),
        )

    methodunit_review = candidates[candidates["candidate_type"].eq("methodunit_candidate")]
    download_left, download_right = st.columns(2)
    with download_left:
        st.download_button(
            "Download extracted records review CSV",
            data=as_csv_download(select_existing(methodunit_review, CANDIDATE_SCHEMA)),
            file_name="methodunit_candidates_review.csv",
            mime="text/csv",
            key="download_methodunit_candidates_review",
            disabled=methodunit_review.empty,
        )
    with download_right:
        st.download_button(
            "Download full extracted links CSV",
            data=as_csv_download(select_existing(candidates, CANDIDATE_SCHEMA)),
            file_name="extracted_source_links_full.csv",
            mime="text/csv",
            key="download_extracted_source_links_full",
            disabled=candidates.empty,
        )


def source_registry_workflow_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Source Registry")
    page_summary("Official source map for each programme, including source URLs, extraction strategy, confidence, and review status.")
    st.info(
        "Purpose: inspect the official source map before extracting from sources. Interpret this as source intelligence, not methodology approval. "
        "Action: filter for low confidence, high priority, or unresolved sources and decide what needs checking."
    )
    profiles = data["source_profiles"]
    if not require_rows(profiles, "source registry"):
        return

    filtered = inline_filters(
        profiles,
        ["connector_type", "confidence", "automation_priority", "populated_source_status"],
        "source_registry",
    )
    metric_row(
        [
            ("Visible programmes", len(filtered)),
            ("High automation priority", count_contains(filtered, "automation_priority", "High")),
            ("Manual review required", count_value(filtered, "human_review_required", "Yes")),
            ("Low confidence", count_contains(filtered, "confidence", "Low")),
        ]
    )

    display_columns = [
        "program_name",
        "current_methodology_row_count",
        "official_organization",
        "official_website",
        "registry_url",
        "method_source_url",
        "connector_type",
        "extraction_strategy",
        "automation_priority",
        "populated_source_status",
        "confidence",
        "human_review_required",
        "evidence_urls",
        "notes",
    ]
    st.subheader("Source Registry Table")
    show_dataframe(select_existing(filtered, display_columns), "source_registry", height=460)

    st.subheader("Live Source Check Summary")
    checks = st.session_state.get("live_source_check_results", pd.DataFrame())
    if checks.empty:
        st.info("No live source check results in the current session. Use Extract from Sources to perform a pre-check.")
    else:
        chart = value_counts_df(checks, "check_status", "check_status")
        show_bar_chart(chart, "check_status", "count", "Live source check status summary is unavailable.")
        show_dataframe(select_existing(checks, ["checked_at", "program_name", "check_status", "status_code", "source_url", "final_url", "content_type", "likely_link_count", "error"]), "source_registry_live_check_summary", height=260)


def source_resolution_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Source Resolution")
    page_summary("Resolve where methodology information lives when a standard does not publish a clean methodology table or catalogue.")
    st.info(
        "Some standards do not have a dedicated methodologies section. Source Resolution decides where methodology information lives before extraction is designed. "
        "Valid outcomes include automated extraction, document-family capture, adopted-method pointer, access request, unresolved, or park."
    )
    st.write(
        "Use this when a source appears to have one or a few methods, no clean methodology index, or access constraints. "
        "A resolution run can still create review records, supporting links, and issues for the downstream Workbench tabs."
    )

    st.subheader("High-Activity Source Comparison")
    comparison = pd.DataFrame(
        [
            {
                "Source": "Climate Action Reserve",
                "Resolution": "Clean protocols page",
                "Current handling": "Automated extraction from clean protocols table.",
                "Catalogue action": "Review/export extracted protocol records.",
            },
            {
                "Source": "Artisan C-sink",
                "Resolution": "No separate methodology index",
                "Current handling": "Document-family capture from standard page/PDF plus clarification documents.",
                "Catalogue action": "Capture as one Standard / Document family record with supporting evidence.",
            },
            {
                "Source": "Open Forest Protocol (OFP)",
                "Resolution": "Access-gated methodology",
                "Current handling": "Request access; do not bypass DocSend or access controls.",
                "Catalogue action": "Track as access request until official materials are available.",
            },
            {
                "Source": "Taiwan VER",
                "Resolution": "Official platform inaccessible / unresolved",
                "Current handling": "Project-derived or unresolved until platform access improves.",
                "Catalogue action": "Keep in investigation queue; avoid overclaiming methodology coverage.",
            },
        ]
    )
    st.dataframe(comparison, hide_index=True, use_container_width=True)

    st.subheader("Mid-Activity Source Resolution Audit")
    st.write(
        "This CSV is an evidence-backed decision layer for source resolution. It guides catalogue action, "
        "but it is not approved catalogue truth and does not automatically create methodology records."
    )
    render_source_resolution_audit_table(data, "source_resolution_audit")

    st.subheader("Supported Source-Resolution Case")
    st.write(
        "Artisan C-sink is handled as a document-family case, not a normal table extractor. "
        "The resolver fetches only the public source page, does not parse full PDFs, and keeps all outputs pending review."
    )
    st.caption(f"Fallback public source page if no clean registry page is available: {ARTISAN_C_SINK_FALLBACK_SOURCE_URL}")
    if st.button("Resolve Artisan C-sink source", type="primary"):
        with st.spinner("Resolving Artisan C-sink source page..."):
            resolution_df, candidates_df, errors_df = resolve_artisan_c_sink_source(data.get("source_profiles", pd.DataFrame()))
        st.session_state["source_resolution_results"] = resolution_df
        st.session_state["source_resolution_candidates"] = candidates_df
        st.session_state["source_resolution_errors"] = errors_df
        st.session_state["candidate_extraction_results"] = candidates_df
        st.session_state["candidate_extraction_errors"] = errors_df
        st.session_state["candidate_extraction_enrichment_metrics"] = {}
        st.session_state["candidate_extraction_sources_attempted"] = 1
        st.session_state["source_resolution_last_run"] = "Artisan C-sink"
        st.session_state["demo_source_last_run"] = ""

    resolution = st.session_state.get("source_resolution_results", pd.DataFrame(columns=SOURCE_RESOLUTION_SCHEMA))
    candidates = apply_output_safeguards(st.session_state.get("source_resolution_candidates", pd.DataFrame(columns=CANDIDATE_SCHEMA)))
    errors = st.session_state.get("source_resolution_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    if resolution.empty:
        st.info("Run Artisan C-sink source resolution to create a document-family record and supporting-link audit.")
        return

    st.subheader("Resolution Result")
    show_dataframe(select_existing(resolution, SOURCE_RESOLUTION_SCHEMA), "source_resolution_results", height=180)
    methodunit_records = candidates[candidates.get("candidate_type", pd.Series("", index=candidates.index)).eq("methodunit_candidate")]
    supporting_links = candidates[candidates.get("candidate_type", pd.Series("", index=candidates.index)).eq("supporting_document")]
    metric_row(
        [
            ("Document-family records", len(methodunit_records)),
            ("Supporting links", len(supporting_links)),
            ("Issues logged", len(errors)),
        ]
    )

    st.subheader("Created Record")
    if methodunit_records.empty:
        st.warning("No document-family record was created. Review source-access issues below.")
    else:
        show_dataframe(
            select_existing(
                methodunit_records,
                ["program_name", "methodunit_name", "unit_type", "source_url", "document_url", "confidence", "review_status", "notes"],
            ),
            "source_resolution_methodunit",
            height=180,
        )

    st.subheader("Supporting Documents")
    if supporting_links.empty:
        st.info("No clarification/supporting documents were detected on this source page.")
    else:
        show_dataframe(
            select_existing(supporting_links, ["program_name", "methodunit_name", "candidate_type", "document_url", "classification_reason", "notes"]),
            "source_resolution_supporting",
            height=260,
        )

    st.subheader("Issues to Resolve")
    if errors.empty:
        st.info("No source-resolution issues were logged.")
    else:
        st.write("If the standard PDF link is missing, broken, redirected, or returns an error, preserve it here as a source issue rather than an app failure.")
        show_dataframe(select_existing(errors, EXTRACTION_ERROR_SCHEMA), "source_resolution_errors", height=220)


def candidate_review_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Review Extracted Records")
    page_summary("Review possible methodology/protocol records before they are exported to a catalogue.")
    st.info(
        "Purpose: check extracted records before catalogue handoff. Extracted records are not automatically approved methodologies. "
        "Interpret rows as possible methodology/protocol records that still need human judgment. "
        "Action: filter candidates and assign a review decision for display/download."
    )
    st.write(
        "Records are grouped into usable records and review-needed records. High confidence means extraction quality, not final approval. "
        "ICR records should be treated as discovery records unless the title is clean."
    )
    session_candidates = current_methodunit_candidates()
    candidates, source_label = session_or_output(
        session_candidates,
        "methodunit_candidates_review.csv",
        "methodunit_candidates_review",
        CANDIDATE_SCHEMA,
    )

    with st.expander("Advanced: load records from CSV", expanded=False):
        st.write("Use this only when manually reviewing an exported candidate CSV outside the latest extraction run.")
        uploaded = st.file_uploader("Upload extracted records CSV", type=["csv"], key="candidate_review_upload")
        if uploaded is not None:
            try:
                candidates = ensure_columns(normalize_columns(pd.read_csv(uploaded, dtype=str).fillna("")), CANDIDATE_SCHEMA)
                source_label = "uploaded CSV"
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not read uploaded CSV: {exc}")
    candidates = add_record_readiness(candidates)

    st.caption(f"Review queue source: {source_label}")
    if candidates.empty:
        st.info("No extracted records are loaded yet. Go to Extract from Sources and run Climate Action Reserve or City Forest Credits, or use Source Resolution for Artisan C-sink.")
        return

    if "candidate_type" in candidates.columns:
        candidates = candidates[candidates["candidate_type"].eq("methodunit_candidate") | candidates["candidate_type"].eq("")]
    filtered = inline_filters(
        candidates,
        ["program_name", "record_readiness", "confidence", "status", "review_status"],
        "candidate_review",
    )
    decision = st.selectbox(
        "Review decision for displayed rows",
        ["pending_review", "needs_research", "approved", "rejected"],
        key="candidate_review_decision",
        help="This decision is added for display/download only and is not written to disk automatically.",
    )
    filtered = filtered.copy()
    filtered["review_decision"] = decision
    display_columns = [
        "program_name",
        "methodunit_code",
        "methodunit_name",
        "unit_type",
        "sector",
        "version",
        "status",
        "source_url",
        "document_url",
        "record_readiness",
        "confidence",
        "review_status",
        "review_decision",
        "notes",
    ]
    show_dataframe(select_existing(filtered, display_columns), "candidate_review_queue", height=500)


def evidence_links_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Supporting Links")
    page_summary("Useful links found during extraction that are preserved separately from extracted methodology records.")
    st.info(
        "These links are produced by Extract from Sources. They are useful context, but they are not treated as methodology records. "
        "Examples include PDFs, FAQs, templates, guidance pages, development pages, navigation links, and excluded links."
    )
    links, source_label = session_or_output(
        current_extracted_links(),
        "extracted_source_links_full.csv",
        "extracted_source_links_full",
        CANDIDATE_SCHEMA,
    )
    with st.expander("Advanced: load supporting links from CSV", expanded=False):
        st.write("Use this only when manually reviewing an exported full links CSV outside the latest extraction run.")
        uploaded = st.file_uploader("Upload supporting links CSV", type=["csv"], key="supporting_links_upload")
        if uploaded is not None:
            try:
                links = apply_output_safeguards(
                    ensure_columns(normalize_columns(pd.read_csv(uploaded, dtype=str).fillna("")), CANDIDATE_SCHEMA)
                )
                source_label = "uploaded CSV"
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not read uploaded CSV: {exc}")
    st.caption(f"Current data source: {source_label}")
    if links.empty:
        st.info("No supporting links are loaded yet. Run extraction or source resolution first.")
        return
    filtered = inline_filters(
        links,
        ["candidate_type", "program_name", "unit_type", "confidence", "status", "review_status"],
        "evidence_links",
    )
    show_dataframe(select_existing(filtered, CANDIDATE_SCHEMA), "evidence_links", height=520)


def qa_exceptions_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Issues to Resolve")
    page_summary("Broken URLs, SSL problems, stale links, duplicate risks, missing titles, and other review issues.")
    st.info(
        "These issues are produced by source checks and extraction runs. Source-access failures are useful findings, not just app errors. "
        "Use this tab to resolve, retry, or document issues before Export for Catalogue."
    )

    st.subheader("Data-Quality Issues")
    qa = data.get("qa_flags", pd.DataFrame())
    if qa.empty:
        st.info("No QA flags are loaded.")
    else:
        qa = qa.copy()
        if "issue_type" not in qa.columns and "issue" in qa.columns:
            qa["issue_type"] = qa["issue"].str.extract(
                r"(duplicate|variant|ambiguous|external|malformed|incomplete|low-confidence|methodology)",
                expand=False,
                flags=2,
            ).fillna("review").str.lower()
        if "severity" not in qa.columns:
            qa["severity"] = qa["issue_type"].map(
                {
                    "duplicate": "Medium",
                    "variant": "Medium",
                    "ambiguous": "High",
                    "external": "Medium",
                    "malformed": "Medium",
                    "incomplete": "Medium",
                    "low-confidence": "High",
                }
            ).fillna("Review") if "issue_type" in qa.columns else "Review"

        section_note("Highlighted issue classes (keyword-based counts across the QA source text).")
        highlight_terms = {
            "Duplicate or variant names": "duplicate|variant",
            "Ambiguous standards": "ambiguous",
            "Adopted external methods": "external|accepted external|adopted",
            "Malformed or incomplete evidence URLs": "malformed|incomplete|url|source",
            "Low-confidence sources": "low-confidence|low confidence|manual investigation",
        }
        highlight_cols = st.columns(len(highlight_terms))
        for column, (label, pattern) in zip(highlight_cols, highlight_terms.items()):
            issue_text = qa.get("issue", pd.Series("", index=qa.index)).astype(str)
            column.metric(label, int(issue_text.str.contains(pattern, case=False, regex=True).sum()))

        show_dataframe(qa, "qa_exceptions_data_quality", height=260)

    st.subheader("Source-Access Errors")
    failures = current_live_source_failures()
    if failures.empty:
        st.info("No failed Live Source Check rows in the current session.")
    else:
        show_dataframe(select_existing(failures, ["checked_at", "program_name", "source_url", "status_code", "check_status", "error"]), "qa_exceptions_source_access", height=240)

    st.subheader("Extraction Errors")
    errors, source_label = session_or_output(
        current_extraction_errors(),
        "extraction_errors.csv",
        "extraction_errors",
        EXTRACTION_ERROR_SCHEMA,
    )
    st.caption(f"Extraction error source: {source_label}")
    if errors.empty:
        st.info("No extraction errors are available.")
    else:
        st.write("These errors come from the latest extraction run or the latest saved extraction error output.")
        show_dataframe(errors, "qa_exceptions_extraction_errors", height=240)

    st.subheader("Review-Needed Records")
    review_needed = current_methodunit_candidates()
    if not review_needed.empty:
        review_needed = review_needed[
            review_needed.get("review_status", pd.Series("", index=review_needed.index)).astype(str).str.lower().eq("pending_review")
            | review_needed.get("review_status", pd.Series("", index=review_needed.index)).astype(str).str.lower().eq("needs_research")
            | review_needed.get("methodunit_name", pd.Series("", index=review_needed.index)).astype(str).eq("Title requires review")
        ]
    if review_needed.empty:
        st.info("No current extracted records needing review are loaded.")
    else:
        show_dataframe(select_existing(review_needed, ["program_name", "methodunit_code", "methodunit_name", "confidence", "review_status", "notes"]), "qa_exceptions_review_needed", height=240)

    st.subheader("Source-Resolution Audit Next Actions")
    source_resolution_audit_warnings(data)
    audit = data.get("source_resolution_audit", pd.DataFrame(columns=SOURCE_RESOLUTION_AUDIT_SCHEMA))
    audit_issues = source_resolution_audit_issue_rows(audit)
    if audit_issues.empty:
        st.info("No source-resolution audit rows require issue records or special review status.")
    else:
        st.write(
            "These rows come from the mid-activity source-resolution audit. Treat them as review issues or next-action items, "
            "not approved methodology records."
        )
        display_columns = [
            "programme",
            "project_count",
            "recommended_catalogue_action",
            "recommended_ingestion_mode",
            "review_status",
            "source_access_issue",
            "creates_issue_record",
            "confidence",
            "notes",
            "evidence_urls",
        ]
        show_dataframe(select_existing(audit_issues, display_columns), "source_resolution_audit_next_actions", height=360)


def export_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Export for Catalogue")
    page_summary("Download review-ready outputs that could feed a methodology catalogue after human review.")
    st.info(
        "Purpose: download review-ready outputs that could feed a methodology catalogue after human review. "
        "Do not treat all extracted records as already approved. Interpret exports as review handoff files. "
        "Action: download individual CSVs or save timestamped outputs locally."
    )

    methodunits, methodunit_source = session_or_output(
        current_methodunit_candidates(),
        "methodunit_candidates_review.csv",
        "methodunit_candidates_review",
        CANDIDATE_SCHEMA,
    )
    links, links_source = session_or_output(
        current_extracted_links(),
        "extracted_source_links_full.csv",
        "extracted_source_links_full",
        CANDIDATE_SCHEMA,
    )
    errors, errors_source = session_or_output(
        current_extraction_errors(),
        "extraction_errors.csv",
        "extraction_errors",
        EXTRACTION_ERROR_SCHEMA,
    )
    source_resolution, source_resolution_source = session_or_output(
        current_source_resolution_results(),
        "source_resolution_results.csv",
        "source_resolution_results",
        SOURCE_RESOLUTION_SCHEMA,
    )
    source_registry = data.get("source_profiles", pd.DataFrame())
    qa = data.get("qa_flags", pd.DataFrame())
    st.caption(
        f"Export sources: records = {methodunit_source}; supporting links = {links_source}; "
        f"extraction errors = {errors_source}; source resolution = {source_resolution_source}."
    )

    if methodunits.empty and links.empty and errors.empty and source_resolution.empty:
        st.info(
            "No extraction or source-resolution output is available yet. Run a quick demo extraction or resolve Artisan C-sink before returning here to export."
        )

    downloads = [
        ("Current extracted methodology records", methodunits, "methodunit_candidates_review.csv"),
        ("Full Supporting Links", links, "extracted_source_links_full.csv"),
        ("Extraction errors", errors, "extraction_errors.csv"),
        ("Source-resolution results", source_resolution, "source_resolution_results.csv"),
        ("Source Registry table", source_registry, "source_registry.csv"),
        ("QA flags", qa, "qa_flags.csv"),
    ]
    for label, df, file_name in downloads:
        st.download_button(
            label,
            data=as_csv_download(df),
            file_name=file_name,
            mime="text/csv",
            key=f"export_{file_name}",
            disabled=df.empty,
        )

    st.subheader("Save Timestamped Outputs")
    st.caption("Writes available current outputs into the local outputs/ folder using timestamped filenames.")
    if st.button("Save current outputs to outputs/", type="primary"):
        saved = save_timestamped_outputs(data)
        if saved:
            st.success("Saved timestamped output files:")
            for path in saved:
                st.write(str(path))
        else:
            st.warning("No non-empty outputs were available to save.")


def overview_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Carbon Methodology Intelligence Platform")
    st.subheader("Understanding how methodology information is published, discovered, and operationalized across global carbon programmes.")

    profiles = data.get("source_profiles", pd.DataFrame())
    if not require_rows(profiles, "source registry"):
        return
    plan = derive_onboarding_plan(profiles)
    status = programme_status_counts(profiles, plan)

    st.subheader("Executive Snapshot")
    metric_row(
        [
            ("Total programmes", status["total_programmes"]),
            ("Programmes mapped", status["programmes_mapped"]),
            ("Programmes requiring investigation", status["programmes_requiring_investigation"]),
            ("Operational / partial connectors", status["operational_connectors"]),
        ]
    )

    st.subheader("Source Landscape")
    pattern_counts = source_pattern_counts(profiles)
    show_bar_chart(pattern_counts, "Source pattern", "Programmes", "No source pattern counts are available.")
    st.dataframe(pattern_counts, hide_index=True, use_container_width=True)

    st.subheader("Coverage Maturity")
    maturity = maturity_counts(plan)
    show_bar_chart(maturity, "Coverage maturity", "Programmes", "No coverage maturity counts are available.")
    st.dataframe(maturity, hide_index=True, use_container_width=True)

    st.subheader("Current Priorities")
    priorities = connector_priority_rows(data, plan)
    st.dataframe(priorities, hide_index=True, use_container_width=True)

    st.subheader("Platform Workflow")
    st.markdown(
        "**Source Universe -> Source Classification -> Connector Selection -> Candidate Extraction -> "
        "Evidence Review -> Methodology Intelligence**"
    )

    with st.expander("Detailed registry preview", expanded=False):
        section_note("Detailed programme rows remain available here and on the Source Registry page.")
        display_columns = [
            "program_name",
            "current_source_url",
            "connector_type",
            "current_extraction_status",
            "onboarding_category",
            "recommended_next_action",
            "confidence",
        ]
        show_dataframe(select_existing(plan, display_columns), "overview_registry_preview", height=360)


def source_registry_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Source Registry")
    page_summary("Detailed source intelligence for each programme, including official source URLs, source patterns, confidence, and next actions.")
    profiles = data.get("source_profiles", pd.DataFrame())
    if not require_rows(profiles, "source registry"):
        return

    plan = derive_onboarding_plan(profiles)
    filtered = inline_filters(
        plan,
        ["onboarding_category", "connector_type", "confidence", "populated_source_status", "suggested_wave"],
        "source_registry_platform",
    )
    display_columns = [
        "program_name",
        "current_source_url",
        "method_source_url",
        "official_website",
        "registry_url",
        "connector_type",
        "current_extraction_status",
        "onboarding_category",
        "suggested_wave",
        "recommended_next_action",
        "confidence",
        "notes",
    ]
    show_dataframe(select_existing(filtered, display_columns), "source_registry_platform", height=560)

    with st.expander("Source archetype reference", expanded=False):
        archetype_rows = [
            {"Source archetype": "Structured HTML table", "What it means": "Official methodology or protocol table on a public page.", "Example programmes": "Climate Action Reserve", "Current status": "Implemented for CAR"},
            {"Source archetype": "Methodology catalogue with detail pages", "What it means": "Index page of methodology codes linking to detail pages.", "Example programmes": "International Carbon Registry / ICR", "Current status": "Discovery-only; titles need review"},
            {"Source archetype": "PDF / document family", "What it means": "Methodologies published as document / protocol families with links.", "Example programmes": "City Forest Credits, ART/TREES, C-Capsule", "Current status": "Implemented for CFC at document-link level"},
            {"Source archetype": "Adopted external methods", "What it means": "Programmes that adopt CDM or other external methodologies.", "Example programmes": "Asia Carbon Institute, Social Carbon", "Current status": "Partially implemented for ACI; source access can fail"},
            {"Source archetype": "JS-heavy portal", "What it means": "Registries or portals that render content client-side.", "Example programmes": "Verra, Gold Standard, Isometric, Riverse", "Current status": "Not attempted yet"},
            {"Source archetype": "No clear methodology page", "What it means": "Programmes without a public methodology index.", "Example programmes": "Artisan C-sink, OFP, Taiwan VER", "Current status": "Implemented for Artisan C-sink as source resolution"},
        ]
        st.dataframe(pd.DataFrame(archetype_rows), hide_index=True, use_container_width=True)


def source_landscape_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Source Landscape")
    page_summary("Map of the carbon methodology source universe — the programmes in the registry and the extraction archetype each one needs.")
    st.write(
        "Carbon methodology information is not published in one consistent format. "
        "This page maps the source universe and groups standards by the type of extraction strategy they require."
    )

    profiles = data.get("source_profiles", pd.DataFrame())
    if not require_rows(profiles, "source registry"):
        return

    plan = derive_onboarding_plan(profiles)

    has_method_rows = profiles.get("currently_has_methodology_rows", pd.Series("", index=profiles.index)).astype(str).str.strip().str.lower().eq("yes")
    needs_resolution = count_value(plan, "onboarding_category", "Needs manual investigation") + count_value(
        plan,
        "onboarding_category",
        "Needs document/PDF parsing",
    )

    st.subheader("Programme Status")
    metric_row(
        [
            ("Total programmes", len(plan)),
            ("Programmes with methodology rows", int(has_method_rows.sum())),
            ("Programmes without methodology rows", int((~has_method_rows).sum())),
        ]
    )
    metric_row(
        [
            ("Working/partial extractor", count_value(plan, "onboarding_category", "Working extractor")),
            ("Ready for extraction", count_value(plan, "onboarding_category", "Ready for extraction")),
            ("Needs investigation or source resolution", needs_resolution),
        ]
    )

    st.subheader("Source Archetypes")
    section_note("Each archetype needs a different extraction strategy. One generic scraper is not enough.")
    archetype_rows = [
        {"Source archetype": "Structured HTML table", "What it means": "Official methodology or protocol table on a public page.", "Example programmes": "Climate Action Reserve", "Extraction strategy": "Parse the official table, preserve source/detail links, classify rows.", "Current status": "Implemented for CAR"},
        {"Source archetype": "Methodology catalogue with detail pages", "What it means": "Index page of methodology codes linking to per-methodology detail pages.", "Example programmes": "International Carbon Registry / ICR", "Extraction strategy": "Discover codes and detail URLs, then cautiously enrich from detail-page text.", "Current status": "Discovery-only; titles need review"},
        {"Source archetype": "PDF / document family", "What it means": "Methodologies published as document / protocol families with links.", "Example programmes": "City Forest Credits, ART/TREES, C-Capsule", "Extraction strategy": "List document links first; parse PDFs later in a controlled workflow.", "Current status": "Implemented for CFC at document-link level"},
        {"Source archetype": "Adopted external methods", "What it means": "Programmes that adopt CDM or other external methodologies.", "Example programmes": "Asia Carbon Institute, Social Carbon", "Extraction strategy": "Detect native vs adopted methods and preserve source references.", "Current status": "Partially implemented for ACI; source access can fail"},
        {"Source archetype": "JS-heavy portal", "What it means": "Registries or portals that render content client-side.", "Example programmes": "Verra, Gold Standard, Isometric, Riverse", "Extraction strategy": "Use source-specific analysis later; not simple HTML scraping.", "Current status": "Not implemented"},
        {"Source archetype": "No clear methodology page", "What it means": "Small or unresolved programmes without a public methodology index.", "Example programmes": "Artisan C-sink, OFP, Taiwan VER, small or unresolved programmes", "Extraction strategy": "Resolve where methodology information lives; capture document family, request access, mark unresolved, or park.", "Current status": "Implemented for Artisan C-sink as source resolution"},
    ]
    st.dataframe(pd.DataFrame(archetype_rows), hide_index=True, use_container_width=True)

    st.subheader("Source Registry")
    section_note("Filter to see the current onboarding category, extraction status, and source pattern for each programme.")
    filtered = inline_filters(
        plan,
        ["onboarding_category", "connector_type", "confidence", "populated_source_status", "suggested_wave"],
        "landscape_registry",
    )
    display_columns = [
        "program_name",
        "current_source_url",
        "connector_type",
        "current_extraction_status",
        "onboarding_category",
        "suggested_wave",
        "confidence",
        "populated_source_status",
        "notes",
    ]
    show_dataframe(select_existing(filtered, display_columns), "landscape_registry", height=460)

    with st.expander("Advanced: Source Registry details", expanded=False):
        source_registry_workflow_page(data)


def ingestion_workflow_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Ingestion Workflow")
    page_summary("The assembly line from official source to catalogue export — with the operational controls to run it.")
    st.write(
        "Source information moves through source access checks, source-specific extraction, "
        "source resolution for no-index standards, record classification, evidence capture, human review, and catalogue export. "
        "This page shows the pipeline and lets you run each operational step."
    )

    st.subheader("Pipeline")
    st.markdown(
        "**Official source → source access check → source-specific extraction → "
        "extracted methodology records → supporting links separated → issues logged → "
        "human review → catalogue export**"
    )

    st.subheader("Stage Status")
    st.caption("When a standard has no clean methodology index, Source Resolution decides whether to capture a document family, request access, keep an adopted-method pointer, mark unresolved, or park the source.")
    section_note("Each stage has its own inputs, outputs, and current implementation state.")
    stage_rows = [
        {"Stage": "Source Registry", "What happens": "Maintain the official source map for each programme.", "Current implementation status": "Loaded from CSV", "Outputs produced": "Programme profiles, source URLs, extraction strategy notes"},
        {"Stage": "Source Access Check", "What happens": "Verify whether official source pages are reachable and list candidate document links.", "Current implementation status": "Working", "Outputs produced": "Live source check results with status, links, and errors"},
        {"Stage": "Source-Specific Extraction", "What happens": "Run source-specific ingestion logic for supported public sources.", "Current implementation status": "Working for CAR, CFC, ICR (discovery), ACI (source exception)", "Outputs produced": "Candidate MethodUnit rows and supporting links"},
        {"Stage": "Source Resolution", "What happens": "Resolve where methodology information lives when there is no clean methodology index.", "Current implementation status": "Implemented for Artisan C-sink", "Outputs produced": "Document-family record, supporting clarification links, source-resolution issues"},
        {"Stage": "Record Classification", "What happens": "Classify each row as extracted record, supporting document, development page, navigation link, or excluded.", "Current implementation status": "Working", "Outputs produced": "candidate_type and classification_reason"},
        {"Stage": "Evidence Capture", "What happens": "Preserve source URLs, detail URLs, and notes behind every extracted record.", "Current implementation status": "Working", "Outputs produced": "source_url, document_url, notes"},
        {"Stage": "Human Review", "What happens": "Reviewer inspects extracted records, marks readiness, and decides next action.", "Current implementation status": "In-app review filters and decisions; not persisted", "Outputs produced": "record_readiness and review decision"},
        {"Stage": "Catalogue Export", "What happens": "Download or timestamp-save review-ready CSV outputs.", "Current implementation status": "Working", "Outputs produced": "methodunit_candidates_review, extracted_source_links_full, extraction_errors"},
        {"Stage": "Freshness Monitoring", "What happens": "Re-check source pages over time and detect changes.", "Current implementation status": "Roadmap", "Outputs produced": "Content hash and change tracking (planned)"},
    ]
    st.dataframe(pd.DataFrame(stage_rows), hide_index=True, use_container_width=True)

    st.subheader("Run the Workflow")
    st.caption(
        "Quick Demo runs a one-source end-to-end extraction. Step 1 checks source access. "
        "Step 2 covers structured extraction from clean methodology/protocol pages and source resolution/document-family capture for sources like Artisan C-sink."
    )
    st.info(
        "Extraction is used when a source has a structured methodology/protocol page. "
        "Source Resolution is used when a source lacks a clean methodology page and must be classified before catalogue ingestion."
    )
    st.info(
        "**Recommended demo path**\n\n"
        "- Climate Action Reserve: clean table extraction.\n"
        "- City Forest Credits: document/protocol-family extraction.\n"
        "- Artisan C-sink: no clean methodology page, so use the Source Resolution case."
    )
    demo_tab, step1_tab, step2_tab, resolution_tab = st.tabs(
        ["Quick Demo", "Step 1: Source access check", "Step 2: Extract or resolve records", "Source Resolution"]
    )
    with demo_tab:
        st.write(
            "Run a small end-to-end extraction on a single source. "
            "The outputs populate Evidence & Review just like a full extraction run."
        )
        demo_source = st.selectbox(
            "Demo source",
            ["Climate Action Reserve", "City Forest Credits"],
            key="ingestion_quick_demo_source",
        )
        extractor_map = {
            "Climate Action Reserve": extract_climate_action_reserve_candidates,
            "City Forest Credits": extract_cfc_candidates,
        }
        if st.button("Run quick demo extraction", type="primary", key="ingestion_quick_demo_run"):
            extractor = extractor_map[demo_source]
            with st.spinner(f"Running {demo_source} extraction..."):
                q_candidates, q_errors, q_metrics = normalize_demo_extraction_result(
                    extractor(data.get("source_profiles", pd.DataFrame()))
                )
            st.session_state["candidate_extraction_results"] = q_candidates
            st.session_state["candidate_extraction_errors"] = q_errors
            st.session_state["candidate_extraction_enrichment_metrics"] = q_metrics
            st.session_state["candidate_extraction_sources_attempted"] = 1
            st.session_state["demo_source_last_run"] = demo_source
            st.session_state["source_resolution_last_run"] = ""
            st.success(
                f"Quick demo for {demo_source} finished. Open **Evidence & Review** to inspect the results."
            )
    with step1_tab:
        live_source_check_page(data)
    with step2_tab:
        candidate_extraction_page(data)
    with resolution_tab:
        source_resolution_page(data)


def explore_source_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Connector Pipeline")
    page_summary("Choose a source and see what the platform found: records, documents, issues, and the recommended next action.")
    st.write("Pick a source, run exploration, and review what happened.")

    st.info(
        "**Recommended demo path**\n\n"
        "- CAR: clean methodology/protocol table.\n"
        "- City Forest Credits: document/protocol-family source.\n"
        "- Artisan C-sink: no clean methodology page; source-resolution case."
    )

    source_context = {
        "Climate Action Reserve": {
            "mode": "clean table extraction",
            "next_action": "Review the records found from the public protocol table, then export if they look right.",
            "spinner": "Exploring Climate Action Reserve...",
        },
        "City Forest Credits": {
            "mode": "document/protocol-family extraction",
            "next_action": "Review document titles, versions, and supporting links before catalogue handoff.",
            "spinner": "Exploring City Forest Credits...",
        },
        "Artisan C-sink": {
            "mode": "source resolution",
            "next_action": "Review the document-family record and supporting clarification links before catalogue handoff.",
            "spinner": "Resolving Artisan C-sink source...",
        },
    }
    source = st.selectbox("Source to explore", list(source_context.keys()), key="explore_source_select")

    if st.button("Explore source", type="primary", key="explore_source_run"):
        context = source_context[source]
        with st.spinner(context["spinner"]):
            if source == "Artisan C-sink":
                resolution_df, candidates_df, errors_df = resolve_artisan_c_sink_source(data.get("source_profiles", pd.DataFrame()))
                enrichment_metrics = {}
                st.session_state["source_resolution_results"] = resolution_df
                st.session_state["source_resolution_candidates"] = candidates_df
                st.session_state["source_resolution_errors"] = errors_df
                st.session_state["source_resolution_last_run"] = "Artisan C-sink"
                st.session_state["demo_source_last_run"] = ""
            else:
                extractor = {
                    "Climate Action Reserve": extract_climate_action_reserve_candidates,
                    "City Forest Credits": extract_cfc_candidates,
                }[source]
                candidates_df, errors_df, enrichment_metrics = normalize_demo_extraction_result(
                    extractor(data.get("source_profiles", pd.DataFrame()))
                )
                st.session_state["source_resolution_last_run"] = ""
                st.session_state["demo_source_last_run"] = source
                st.session_state["source_resolution_results"] = pd.DataFrame(columns=SOURCE_RESOLUTION_SCHEMA)
                st.session_state["source_resolution_candidates"] = pd.DataFrame(columns=CANDIDATE_SCHEMA)
                st.session_state["source_resolution_errors"] = pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA)

            st.session_state["candidate_extraction_results"] = candidates_df
            st.session_state["candidate_extraction_errors"] = errors_df
            st.session_state["candidate_extraction_enrichment_metrics"] = enrichment_metrics
            st.session_state["candidate_extraction_sources_attempted"] = 1

            methodunit_count = count_value(candidates_df, "candidate_type", "methodunit_candidate")
            supporting_count = len(candidates_df) - methodunit_count
            if not candidates_df.empty:
                source_status = "reached"
            elif not errors_df.empty:
                source_status = "not reached / access issue"
            else:
                source_status = "no records found"
            st.session_state["source_exploration_summary"] = {
                "Source": source,
                "Source status": source_status,
                "MethodUnit records found": methodunit_count,
                "Supporting links found": supporting_count,
                "Issues logged": len(errors_df),
                "Mode used": context["mode"],
                "Recommended next action": context["next_action"],
            }

    summary = st.session_state.get("source_exploration_summary", {})
    if not summary:
        st.info("Choose a source and click **Explore source** to create review-ready records and evidence.")
        return

    st.subheader("Run Summary")
    metric_row(
        [
            ("Source status", summary.get("Source status", "")),
            ("MethodUnit records found", summary.get("MethodUnit records found", 0)),
            ("Supporting links found", summary.get("Supporting links found", 0)),
            ("Issues logged", summary.get("Issues logged", 0)),
        ]
    )
    st.dataframe(
        pd.DataFrame(
            [
                {"Result": "Source", "Value": summary.get("Source", "")},
                {"Result": "Mode used", "Value": summary.get("Mode used", "")},
                {"Result": "Recommended next action", "Value": summary.get("Recommended next action", "")},
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    errors = st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    if errors.empty:
        st.success("No access or extraction issues were logged for this run.")
    else:
        st.warning("Issues were logged. Review them before using the output package.")
        show_dataframe(select_existing(errors, EXTRACTION_ERROR_SCHEMA), "explore_source_errors", height=180)

    st.info("Review extracted records and evidence on the **Evidence & Review** page.")

    with st.expander("Advanced connector controls", expanded=False):
        st.caption("Operational controls remain available for source checks, multi-source extraction, and source-resolution review.")
        step1_tab, step2_tab, resolution_tab = st.tabs(
            ["Source access checks", "Multi-source extraction", "Source resolution"]
        )
        with step1_tab:
            live_source_check_page(data)
        with step2_tab:
            candidate_extraction_page(data)
        with resolution_tab:
            source_resolution_page(data)


def coverage_progress_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Coverage Progress")
    page_summary("Source-by-source implementation progress and onboarding waves.")
    profiles = data.get("source_profiles", pd.DataFrame())
    if not require_rows(profiles, "source registry"):
        return

    st.write(
        "This page tracks source-by-source implementation progress. "
        "The goal is not to scrape all standards blindly, but to onboard sources in waves based on readiness and extraction strategy."
    )

    plan = derive_onboarding_plan(profiles)

    metric_row(
        [
            ("Working or partial extractors", count_value(plan, "onboarding_category", "Working extractor")),
            ("Ready for extraction", count_value(plan, "onboarding_category", "Ready for extraction")),
            ("Access issue or URL repair", count_value(plan, "onboarding_category", "Needs URL repair")),
            ("Recommended next sources", 2),
        ]
    )
    metric_row(
        [
            ("Documents found / parsing later", count_value(plan, "onboarding_category", "Needs document/PDF parsing")),
            ("Portal source / not attempted yet", count_value(plan, "onboarding_category", "Needs browser automation later")),
            ("Source resolution needed", count_value(plan, "onboarding_category", "Needs manual investigation")),
        ]
    )

    st.subheader("Progress Tracker")
    section_note("Focused view of sources with a known status today.")
    tracker_rows = [
        {"Programme / source": "Climate Action Reserve", "Current status": "working", "Extractor / source type": "structured HTML protocol table", "Current output": "extracted protocol records", "Issue / risk": "none material", "Recommended next action": "keep stable; use as reference pattern", "Suggested wave": "Wave 1"},
        {"Programme / source": "City Forest Credits", "Current status": "working / partial", "Extractor / source type": "document / protocol-family links", "Current output": "protocol / standard document links", "Issue / risk": "PDF metadata not parsed", "Recommended next action": "review titles and versions; consider PDF parsing later", "Suggested wave": "Wave 2"},
        {"Programme / source": "Artisan C-sink", "Current status": "source resolution implemented", "Extractor / source type": "no methodology index / document-family standard", "Current output": "one document-family record plus clarification links", "Issue / risk": "stable standard PDF link should be reviewed", "Recommended next action": "capture as document-family; review standard and clarification documents", "Suggested wave": "Wave 3"},
        {"Programme / source": "International Carbon Registry / ICR", "Current status": "partial / discovery", "Extractor / source type": "M-ICR codes and detail URLs", "Current output": "discovery records", "Issue / risk": "titles require manual review", "Recommended next action": "treat as discovery records; verify titles", "Suggested wave": "Wave 1"},
        {"Programme / source": "Asia Carbon Institute", "Current status": "blocked / source access", "Extractor / source type": "adopted external methods", "Current output": "source-access error logged", "Issue / risk": "SSL / certificate issue", "Recommended next action": "manual check or retry; do not bypass SSL by default", "Suggested wave": "Wave 4"},
        {"Programme / source": "Plan Vivo", "Current status": "recommended next", "Extractor / source type": "document / protocol-family", "Current output": "n/a", "Issue / risk": "document-first source", "Recommended next action": "extend the CFC pattern for document listing", "Suggested wave": "Wave 2"},
        {"Programme / source": "Climate Forward", "Current status": "recommended next", "Extractor / source type": "catalogue-style HTML", "Current output": "n/a", "Issue / risk": "verify URL first", "Recommended next action": "build a small controlled extractor after URL check", "Suggested wave": "Wave 3"},
        {"Programme / source": "American Carbon Registry (ACR)", "Current status": "URL repair first", "Extractor / source type": "catalogue-style HTML", "Current output": "n/a", "Issue / risk": "current URL not confirmed", "Recommended next action": "confirm or repair the source URL before building the extractor", "Suggested wave": "Wave 3"},
    ]
    st.dataframe(pd.DataFrame(tracker_rows), hide_index=True, use_container_width=True)

    st.subheader("Mid-Activity Audit Coverage")
    source_resolution_audit_warnings(data)
    audit = data.get("source_resolution_audit", pd.DataFrame(columns=SOURCE_RESOLUTION_AUDIT_SCHEMA))
    if audit.empty:
        st.info("No mid-activity source-resolution audit rows are loaded.")
    else:
        st.write(
            "This summarizes the audit decision layer for mid-activity standards. "
            "It guides onboarding actions and issue triage; it does not approve catalogue records."
        )
        render_audit_summary(audit, "coverage_mid_activity_audit")

    st.subheader("Onboarding Waves")
    section_note("Waves group sources by readiness and extraction strategy.")
    waves = pd.DataFrame(
        [
            {"Wave": "Wave 1: Stabilize working extractors", "Goal": "Make CAR solid, keep ICR discovery-only unless titles improve, keep ACI as source exception.", "Source archetype": "Currently supported sources", "Example sources": "CAR, ICR, ACI", "Recommended next action": "Stabilize outputs, review edge cases, keep exports reliable.", "Expected output": "Reliable review queue and export."},
            {"Wave": "Wave 2: Add reachable document-family sources", "Goal": "Add City Forest Credits or Nori-style sources.", "Source archetype": "PDF / document family", "Example sources": "City Forest Credits, Nori, ART/TREES, Peatland Code, Plan Vivo", "Recommended next action": "List document / protocol families first; defer PDF content parsing.", "Expected output": "Document / protocol family candidates."},
            {"Wave": "Wave 3: Add more catalogue-style sources", "Goal": "ACR, Climate Forward, BioCarbon Registry, Cercarbono where URLs are valid.", "Source archetype": "Catalogue-first HTML", "Example sources": "ACR, Climate Forward, BioCarbon Registry, Cercarbono", "Recommended next action": "Repair stale URLs, then parse code / title / status / detail URLs.", "Expected output": "Code / title / status / detail URL candidates."},
            {"Wave": "Wave 4: Handle adopted-method sources", "Goal": "Distinguish native methodologies from adopted CDM / Verra / GS methods.", "Source archetype": "Adopted external methods", "Example sources": "Asia Carbon Institute, BioCarbon Registry, Cercarbono, Social Carbon, GCC", "Recommended next action": "Model native records separately from adopted-method references.", "Expected output": "Native method records plus adopted-method references."},
            {"Wave": "Wave 5: Complex / high-value sources", "Goal": "CDM, JCM, Verra, Gold Standard, Isometric, Puro Earth.", "Source archetype": "Large catalogues, JS-heavy portals, complex registries", "Example sources": "CDM, JCM, Verra, Gold Standard, Isometric, Puro Earth", "Recommended next action": "Design source-specific extractors and freshness monitoring.", "Expected output": "Larger-scale source-specific extractors and freshness monitoring."},
            {"Wave": "Wave 6: Long-tail unresolved sources", "Goal": "Manual investigation and periodic checks.", "Source archetype": "Unclear / no methodology page", "Example sources": "Low-confidence and unresolved source registry entries", "Recommended next action": "Confirm source status and decide monitor, manual, or skip.", "Expected output": "Source status decisions and manual review notes."},
        ]
    )
    st.dataframe(waves, hide_index=True, use_container_width=True)

    with st.expander("Advanced: Full source-level plan", expanded=False):
        section_note("Every programme in the registry with its derived onboarding category and suggested wave.")
        filtered = inline_filters(
            plan,
            ["onboarding_category", "suggested_wave", "connector_type", "confidence", "populated_source_status"],
            "coverage_progress_full",
        )
        display_columns = [
            "program_name",
            "current_source_url",
            "connector_type",
            "current_extraction_status",
            "onboarding_category",
            "suggested_wave",
            "recommended_next_action",
            "confidence",
            "notes",
        ]
        show_dataframe(select_existing(filtered, display_columns), "coverage_progress_full", height=520)

    st.info(
        "Coverage expansion should follow this wave order. Classify the source, check URL readiness, "
        "choose an extraction strategy, then route outputs through review before catalogue export."
    )


def evidence_and_review_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Evidence & Review")
    page_summary("Extracted records, supporting material, issues, and export — all read from the latest extraction outputs.")
    st.write(
        "This page shows what extraction produced and how records should be reviewed before catalogue export. "
        "Extracted records are not automatically approved methodologies."
    )

    candidates = apply_output_safeguards(
        st.session_state.get("candidate_extraction_results", pd.DataFrame(columns=CANDIDATE_SCHEMA))
    )
    errors = st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    source_resolution_run = st.session_state.get("source_resolution_last_run", "")
    demo_run = st.session_state.get("demo_source_last_run", "")
    last_run = f"{source_resolution_run} source resolution" if source_resolution_run else demo_run

    if candidates.empty and errors.empty:
        st.info(
            "No extraction outputs are loaded in this session. "
            "Open **Connector Pipeline**, choose a source, and run exploration to produce records, then return here."
        )
    else:
        with st.expander("Result interpretation summary", expanded=True):
            if last_run:
                st.caption(f"Latest session run: {last_run}")
            render_result_interpretation(candidates, errors)

    tabs = st.tabs(["Extracted Records", "Supporting Material", "Issues", "Export", "How to Read Outputs"])
    with tabs[0]:
        candidate_review_page(data)
    with tabs[1]:
        evidence_links_page(data)
    with tabs[2]:
        qa_exceptions_page(data)
    with tabs[3]:
        export_page(data)
    with tabs[4]:
        interpreting_outputs_page(data)


def exports_page(data: dict[str, pd.DataFrame]) -> None:
    export_page(data)


def ai_assisted_scaling_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Strategy")
    profiles = data.get("source_profiles", pd.DataFrame())
    if not profiles.empty:
        st.subheader("Connector Priorities")
        st.dataframe(connector_priority_rows(data, derive_onboarding_plan(profiles)), hide_index=True, use_container_width=True)

    st.subheader("AI-Assisted Scaling")
    page_summary("How AI can assist review responsibly — bounded to evidence, not blindly scraping.")
    st.info(
        "No AI API is called yet. This page describes a roadmap for how AI can assist review tasks with clear evidence and human control."
    )

    st.write(
        "Deterministic source checks and source-specific extractors remain the first layer. "
        "AI is useful for ambiguous or messy cases where deterministic rules alone cannot decide."
    )

    st.subheader("Messy Cases and AI Assist Roles")
    ai_rows = [
        {"Messy case": "Messy PDF title / version", "Deterministic layer": "fetch / document metadata", "AI assist role": "extract title, version, and status from bounded text", "Required evidence": "text snippet with page reference", "Human review decision": "approve, edit, or reject"},
        {"Messy case": "Ambiguous link classification", "Deterministic layer": "link text, URL, and surrounding context", "AI assist role": "classify methodology vs supporting doc vs exclude", "Required evidence": "link text and surrounding context", "Human review decision": "confirm category"},
        {"Messy case": "ICR title problem", "Deterministic layer": "M-ICR code and detail URL", "AI assist role": "propose title only if supported by page text", "Required evidence": "exact text snippet from detail page", "Human review decision": "manual approval"},
        {"Messy case": "Adopted CDM methods", "Deterministic layer": "detect references to CDM / Verra / GS", "AI assist role": "classify native vs adopted", "Required evidence": "source text reference", "Human review decision": "approve mapping"},
        {"Messy case": "Duplicate / alias detection", "Deterministic layer": "fuzzy match and codes", "AI assist role": "suggest possible duplicate or alias", "Required evidence": "matching fields", "Human review decision": "merge or keep separate"},
    ]
    st.dataframe(pd.DataFrame(ai_rows), hide_index=True, use_container_width=True)

    st.subheader("Future AI Workflow")
    st.markdown(
        "**Raw source text → AI suggestion with evidence → human approve / edit / reject → catalogue export**"
    )
    st.caption(
        "The AI layer never replaces reviewer judgment; it surfaces a bounded suggestion with the evidence a reviewer needs to decide."
    )

    st.subheader("Future AI Task Output Schema")
    schema_rows = [
        {"Field": "task_id", "Description": "Unique identifier for the AI-assisted review task."},
        {"Field": "program_name", "Description": "Programme the task belongs to."},
        {"Field": "problem_type", "Description": "Which messy case this task addresses."},
        {"Field": "raw_text_context", "Description": "Bounded text snippet the suggestion is derived from."},
        {"Field": "current_extracted_fields", "Description": "Fields already extracted deterministically."},
        {"Field": "ai_suggestion", "Description": "AI-proposed value or classification."},
        {"Field": "evidence_text", "Description": "Exact text supporting the AI suggestion."},
        {"Field": "confidence", "Description": "AI confidence for the suggestion."},
        {"Field": "reviewer_decision", "Description": "Human reviewer approve / edit / reject outcome."},
    ]
    st.dataframe(pd.DataFrame(schema_rows), hide_index=True, use_container_width=True)

    st.caption("This is a roadmap. No AI calls are made yet.")

    st.subheader("Guardrails")
    st.write("- AI assists bounded extraction and review, not blind scraping.")
    st.write("- Every suggestion must carry its evidence snippet.")
    st.write("- A human reviewer approves, edits, or rejects each suggestion before it reaches the catalogue.")
    st.write("- Source-specific deterministic extractors remain the first layer.")


def main() -> None:
    data = load_data()
    st.title(APP_TITLE)

    st.sidebar.title(APP_TITLE)
    sidebar_workspace_status(data)
    page = st.sidebar.radio(
        "Pages",
        [
            "Overview",
            "Source Registry",
            "Coverage Explorer",
            "Evidence & Review",
            "Connector Pipeline",
            "Exports",
            "Strategy",
        ],
    )

    if page == "Overview":
        overview_page(data)
    elif page == "Source Registry":
        source_registry_page(data)
    elif page == "Coverage Explorer":
        coverage_progress_page(data)
    elif page == "Evidence & Review":
        evidence_and_review_page(data)
    elif page == "Connector Pipeline":
        explore_source_page(data)
    elif page == "Exports":
        exports_page(data)
    elif page == "Strategy":
        ai_assisted_scaling_page(data)


if __name__ == "__main__":
    main()
