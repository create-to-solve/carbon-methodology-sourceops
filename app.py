import re
from pathlib import Path

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
    CONNECTOR_MANIFEST_SCHEMA,
    EXTRACTION_ERROR_SCHEMA,
    FILES,
    REVIEW_DECISION_SCHEMA,
    SOURCE_DOCUMENT_SCHEMA,
    SOURCE_RESOLUTION_AUDIT_FILE,
    SOURCE_RESOLUTION_AUDIT_SCHEMA,
    SOURCE_RESOLUTION_SCHEMA,
    SOURCE_RESOLUTION_SOURCES,
    SOURCE_VERIFICATION_SCHEMA,
    SUPPORTED_EXTRACTORS,
    add_record_readiness,
    apply_output_safeguards,
    as_csv_download,
    build_connector_manifest,
    build_programme_intelligence,
    build_source_documents,
    clean_url,
    count_contains,
    count_value,
    current_extracted_links,
    current_extraction_errors,
    current_live_source_failures,
    current_methodunit_candidates,
    current_review_decisions,
    current_source_documents,
    current_source_resolution_results,
    current_source_verification_results,
    derive_onboarding_plan,
    ensure_columns,
    load_data,
    normalize_source_verification_results,
    normalize_columns,
    normalize_text,
    pretty_label,
    programme_key,
    run_candidate_extractors,
    save_timestamped_outputs,
    save_review_decisions,
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


APP_TITLE = "Carbon Methodology Extraction Workbench"

STABLE_EXTRACTORS = [
    "Climate Action Reserve",
    "City Forest Credits",
    "Climate Forward",
    "American Carbon Registry / ACR",
    "Social Carbon",
    "Plan Vivo",
    "BioCarbon Registry / BCR",
    "Cercarbono",
    "Puro Earth",
    "ART/TREES",
]

EXPERIMENTAL_EXTRACTORS = [
    "International Carbon Registry / ICR",
    "Asia Carbon Institute",
]

PUBLIC_EXTRACTORS = STABLE_EXTRACTORS + EXPERIMENTAL_EXTRACTORS

LATEST_SAVED_OUTPUT_DIR = "outputs/demo_latest"

DEMO_METRICS = {
    "stable_extractors": 10,
    "experimental_checks": 2,
    "methodology_records": 145,
    "source_links": 704,
    "source_documents": 677,
    "errors": 0,
}

SOURCE_PROFILES = {
    "Climate Action Reserve": {
        "pattern": "Catalogue + protocol pages",
        "extracts": "Protocol records with version/status and protocol/detail links.",
        "url": "https://www.climateactionreserve.org/how/protocols/",
    },
    "International Carbon Registry / ICR": {
        "pattern": "Catalogue + detail pages",
        "extracts": "M-ICR methodology records with detail-page source links.",
        "url": "https://carbonregistry.com/explore?category=methodologies",
    },
    "Asia Carbon Institute": {
        "pattern": "Public methodology source with access handling",
        "extracts": "Visible methodology records where the public source is reachable.",
        "url": "https://www.asiacarboninstitute.org/",
    },
    "City Forest Credits": {
        "pattern": "Forest/document library",
        "extracts": "Protocol/document-family records and supporting source documents.",
        "url": "https://www.cityforestcredits.org/carbon-credits/carbon-protocols/",
    },
    "Climate Forward": {
        "pattern": "Static table",
        "extracts": "Forecast methodology rows plus primary PDFs from detail pages.",
        "url": "https://www.climateforward.org/program/methodologies/",
    },
    "American Carbon Registry / ACR": {
        "pattern": "Catalogue + detail pages",
        "extracts": "Approved methodology records and current primary methodology PDFs.",
        "url": "https://acrcarbon.org/methodology/",
    },
    "Social Carbon": {
        "pattern": "Coded methodology pages",
        "extracts": "SCM-coded methodology records, statuses, modules, and document links.",
        "url": "https://www.socialcarbon.org/methodologies",
    },
    "Plan Vivo": {
        "pattern": "Approved-methodology cards",
        "extracts": "Approved methodology card records and linked methodology documents.",
        "url": "https://www.planvivo.org/pv-climate-methodologies",
    },
    "BioCarbon Registry / BCR": {
        "pattern": "Elementor methodology cards",
        "extracts": "BCR methodology card records and linked methodological documents.",
        "url": "https://biocarbonregistry.com/en/methodologies/",
    },
    "Cercarbono": {
        "pattern": "Elementor methodology cards",
        "extracts": "Programme-grouped methodology cards and primary document links.",
        "url": "https://www.cercarbono.com/methodologies/",
    },
    "Puro Earth": {
        "pattern": "Document library",
        "extracts": "Methodology records matched to current PDFs and supporting documents.",
        "url": "https://puro.earth/carbon-removal-methods/",
    },
    "ART/TREES": {
        "pattern": "Document family / standard versions",
        "extracts": "TREES standard-version records and validation/verification documents.",
        "url": "https://www.artredd.org/trees/",
    },
}

PUBLIC_EXTRACTOR_ALIASES = {
    "Climate Action Reserve": ["Climate Action Reserve"],
    "International Carbon Registry / ICR": [
        "International Carbon Registry / ICR",
        "International Carbon Registry (ICR)",
        "International Carbon Registry",
        "ICR",
    ],
    "Asia Carbon Institute": ["Asia Carbon Institute"],
    "City Forest Credits": ["City Forest Credits"],
    "Climate Forward": ["Climate Forward"],
    "American Carbon Registry / ACR": [
        "American Carbon Registry / ACR",
        "American Carbon Registry (ACR)",
        "American Carbon Registry",
        "ACR",
    ],
    "Social Carbon": ["Social Carbon"],
    "Plan Vivo": ["Plan Vivo"],
    "BioCarbon Registry / BCR": [
        "BioCarbon Registry / BCR",
        "BioCarbon Registry",
        "BCR",
    ],
    "Cercarbono": ["Cercarbono"],
    "Puro Earth": ["Puro Earth"],
    "ART/TREES": ["ART/TREES"],
}

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
        if column.endswith("_url") or "url" in column or column in {"official_website", "evidence_urls"}:
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


def load_saved_csv(file_name: str, columns: list[str]) -> pd.DataFrame:
    path = Path(__file__).parent / LATEST_SAVED_OUTPUT_DIR / file_name
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return ensure_columns(normalize_columns(pd.read_csv(path, dtype=str).fillna("")), columns)
    except Exception as exc:  # noqa: BLE001 - visible app warning is more useful than failing the page.
        st.warning(f"Could not load latest saved extraction file {path}: {exc}")
        return pd.DataFrame(columns=columns)


def source_alias_keys(source: str) -> set[str]:
    aliases = PUBLIC_EXTRACTOR_ALIASES.get(source, [source])
    return {programme_key(alias) for alias in aliases if normalize_text(alias)}


def source_matches(row_source: str, selected_source: str) -> bool:
    return programme_key(row_source) in source_alias_keys(selected_source)


def records_for_source(records: pd.DataFrame, source: str) -> pd.DataFrame:
    if records.empty or "program_name" not in records.columns:
        return pd.DataFrame(columns=records.columns)
    return records[records["program_name"].astype(str).apply(lambda value: source_matches(value, source))].copy()


def store_update_check_results(
    candidates: pd.DataFrame,
    errors: pd.DataFrame,
    enrichment_metrics: dict,
    source: str,
) -> None:
    prepared_candidates = apply_output_safeguards(ensure_columns(candidates, CANDIDATE_SCHEMA))
    prepared_errors = ensure_columns(errors, EXTRACTION_ERROR_SCHEMA)
    selected_records = records_for_source(current_methodunit_rows(prepared_candidates), source)
    update_succeeded = not selected_records.empty or prepared_errors.empty
    st.session_state["update_check_results"] = prepared_candidates
    st.session_state["update_check_errors"] = prepared_errors
    st.session_state["update_check_enrichment_metrics"] = enrichment_metrics
    st.session_state["update_check_source"] = source
    st.session_state["update_check_status"] = "success" if update_succeeded else "failed"
    st.session_state["candidate_extraction_results"] = prepared_candidates if update_succeeded else pd.DataFrame(columns=CANDIDATE_SCHEMA)
    st.session_state["candidate_extraction_errors"] = prepared_errors
    st.session_state["candidate_extraction_enrichment_metrics"] = enrichment_metrics
    st.session_state["candidate_extraction_sources_attempted"] = 1
    st.session_state["source_resolution_last_run"] = ""
    st.session_state["demo_source_last_run"] = source


def current_methodunit_rows(rows: pd.DataFrame) -> pd.DataFrame:
    prepared = apply_output_safeguards(ensure_columns(rows, CANDIDATE_SCHEMA))
    if prepared.empty or "candidate_type" not in prepared.columns:
        return pd.DataFrame(columns=CANDIDATE_SCHEMA)
    return prepared[prepared["candidate_type"].eq("methodunit_candidate")].copy()


def latest_saved_records() -> pd.DataFrame:
    return add_record_readiness(apply_output_safeguards(load_saved_csv("methodunit_candidates_review.csv", CANDIDATE_SCHEMA)))


def latest_saved_links() -> pd.DataFrame:
    links = load_saved_csv("extracted_source_links_full.csv", CANDIDATE_SCHEMA)
    records = load_saved_csv("methodunit_candidates_review.csv", CANDIDATE_SCHEMA)
    return apply_output_safeguards(links if not links.empty else records)


def latest_saved_errors() -> pd.DataFrame:
    return load_saved_csv("extraction_errors.csv", EXTRACTION_ERROR_SCHEMA)


def update_check_records() -> pd.DataFrame:
    return add_record_readiness(current_methodunit_rows(st.session_state.get("update_check_results", pd.DataFrame(columns=CANDIDATE_SCHEMA))))


def update_check_links() -> pd.DataFrame:
    return apply_output_safeguards(
        ensure_columns(st.session_state.get("update_check_results", pd.DataFrame(columns=CANDIDATE_SCHEMA)), CANDIDATE_SCHEMA)
    )


def update_check_errors() -> pd.DataFrame:
    return ensure_columns(st.session_state.get("update_check_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA)), EXTRACTION_ERROR_SCHEMA)


def records_for_workbench() -> tuple[pd.DataFrame, str]:
    saved = latest_saved_records()
    if st.session_state.get("update_check_status") == "success":
        updated = update_check_records()
        update_source = st.session_state.get("update_check_source", "")
        if not updated.empty:
            if not saved.empty and update_source:
                saved = saved[~saved["program_name"].astype(str).apply(lambda value: source_matches(value, update_source))]
            combined = pd.concat([saved, updated], ignore_index=True)
            return add_record_readiness(combined), "latest saved extraction package plus update-check results"
    if not saved.empty:
        return saved, "latest saved extraction package"
    records, source_label = session_or_output(
        pd.DataFrame(columns=CANDIDATE_SCHEMA),
        "methodunit_candidates_review.csv",
        "methodunit_candidates_review",
        CANDIDATE_SCHEMA,
    )
    return add_record_readiness(records), source_label


def links_for_workbench() -> tuple[pd.DataFrame, str]:
    saved = latest_saved_links()
    if st.session_state.get("update_check_status") == "success":
        updated = update_check_links()
        update_source = st.session_state.get("update_check_source", "")
        if not updated.empty:
            if not saved.empty and update_source:
                saved = saved[~saved["program_name"].astype(str).apply(lambda value: source_matches(value, update_source))]
            return pd.concat([saved, updated], ignore_index=True), "latest saved extraction package plus update-check results"
    if not saved.empty:
        return saved, "latest saved extraction package"
    return session_or_output(
        pd.DataFrame(columns=CANDIDATE_SCHEMA),
        "extracted_source_links_full.csv",
        "extracted_source_links_full",
        CANDIDATE_SCHEMA,
    )


def errors_for_workbench() -> tuple[pd.DataFrame, str]:
    update_errors = update_check_errors()
    if not update_errors.empty:
        return update_errors, "latest update check"
    saved = latest_saved_errors()
    if not saved.empty:
        return saved, "latest saved extraction package"
    return session_or_output(
        pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA),
        "extraction_errors.csv",
        "extraction_errors",
        EXTRACTION_ERROR_SCHEMA,
    )


def workbench_record_table(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(
            columns=[
                "Source/programme",
                "Methodology / document title",
                "Version",
                "Status",
                "Unit type",
                "Primary document",
                "Review status",
            ]
        )
    table = records.copy()
    return pd.DataFrame(
        {
            "Source/programme": table.get("program_name", ""),
            "Methodology / document title": table.get("methodunit_name", ""),
            "Version": table.get("version", ""),
            "Status": table.get("status", ""),
            "Unit type": table.get("unit_type", ""),
            "Primary document": table.get("document_url", ""),
            "Review status": table.get("review_status", ""),
        }
    )


def has_ssl_or_access_issue(errors: pd.DataFrame) -> bool:
    if errors.empty:
        return False
    issue_text = " ".join(
        errors.get(column, pd.Series("", index=errors.index)).astype(str).str.lower().str.cat(sep=" ")
        for column in ["error_type", "error_message", "suggested_action"]
    )
    return any(term in issue_text for term in ["ssl", "certificate", "access", "connection"])


def review_record_key(row: pd.Series | dict) -> str:
    getter = row.get
    parts = [
        normalize_text(getter("program_name", "")),
        normalize_text(getter("methodunit_code", "")),
        normalize_text(getter("methodunit_name", "")),
        clean_url(getter("document_url", "") or getter("source_url", "")),
    ]
    return "|".join(parts)


def apply_saved_review_status(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return records.copy()
    reviewed = current_review_decisions()
    if reviewed.empty:
        return records.copy()
    latest_decisions = {}
    for _, decision in reviewed.iterrows():
        latest_decisions[review_record_key(decision)] = normalize_text(decision.get("review_decision", ""))
    updated = records.copy()
    for index, row in updated.iterrows():
        decision = latest_decisions.get(review_record_key(row))
        if decision:
            updated.at[index, "review_status"] = decision
    return updated


def review_table(records: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Source/programme",
        "Methodology / document title",
        "Version",
        "Status",
        "Unit type",
        "Review status",
        "Primary document link",
    ]
    if records.empty:
        return pd.DataFrame(columns=columns)
    table = records.copy()
    return pd.DataFrame(
        {
            "Source/programme": table.get("program_name", ""),
            "Methodology / document title": table.get("methodunit_name", ""),
            "Version": table.get("version", ""),
            "Status": table.get("status", ""),
            "Unit type": table.get("unit_type", ""),
            "Review status": table.get("review_status", ""),
            "Primary document link": table.get("document_url", ""),
        }
    )


def review_source_options(records: pd.DataFrame) -> list[str]:
    stable_with_records = [source for source in STABLE_EXTRACTORS if not records_for_source(records, source).empty]
    experimental_with_records = [
        source for source in EXPERIMENTAL_EXTRACTORS if not records_for_source(records, source).empty
    ]
    return stable_with_records + experimental_with_records


def default_review_source_index(options: list[str]) -> int:
    preferred = ["American Carbon Registry / ACR", "Cercarbono"]
    for source in preferred:
        if source in options:
            return options.index(source)
    for index, source in enumerate(options):
        if source in STABLE_EXTRACTORS:
            return index
    return 0


def supporting_documents_for_record(record: pd.Series, links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return pd.DataFrame(columns=CANDIDATE_SCHEMA)
    prepared = ensure_columns(links, CANDIDATE_SCHEMA)
    programme = normalize_text(record.get("program_name", ""))
    code = normalize_text(record.get("methodunit_code", ""))
    title = normalize_text(record.get("methodunit_name", ""))
    subset = prepared[prepared["program_name"].astype(str).eq(programme)].copy()
    if code:
        subset = subset[subset["methodunit_code"].astype(str).eq(code)]
    elif title:
        subset = subset[subset["methodunit_name"].astype(str).eq(title)]
    supporting = subset[subset["candidate_type"].astype(str).ne("methodunit_candidate")].copy()
    return supporting


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


def platform_metric_values(data: dict[str, pd.DataFrame]) -> dict[str, int]:
    profiles = data.get("source_profiles", pd.DataFrame())
    plan = derive_onboarding_plan(profiles) if not profiles.empty else pd.DataFrame()
    matrix = connector_matrix_view(data.get("connector_source_matrix", pd.DataFrame()))
    priority_text = combined_text(matrix, ["recommended_priority", "priority_stage", "next_action"]) if not matrix.empty else pd.Series(dtype=str)
    recommended_next = int(text_contains_any(priority_text, ["stage 1", "implement now", "implement or run", "high-priority"]).sum()) if not priority_text.empty else 0
    if recommended_next == 0 and not matrix.empty:
        recommended_next = min(len(matrix), 5)
    return {
        "programmes_tracked": len(profiles),
        "working_partial_connectors": len(SUPPORTED_EXTRACTORS) + len(SOURCE_RESOLUTION_SOURCES),
        "researched_next_sources": len(matrix),
        "recommended_next_builds": recommended_next,
        "loaded_candidates": len(current_methodunit_candidates()),
        "loaded_evidence_links": len(current_extracted_links()),
    }


def sidebar_workspace_status(data: dict[str, pd.DataFrame]) -> None:
    metrics = platform_metric_values(data)
    st.sidebar.caption("Workspace Status")
    st.sidebar.markdown("**Global**")
    st.sidebar.metric("Programmes tracked", metrics["programmes_tracked"])
    st.sidebar.metric("Working / partial connectors", metrics["working_partial_connectors"])
    st.sidebar.metric("Researched next sources", metrics["researched_next_sources"])
    st.sidebar.metric("Recommended next builds", metrics["recommended_next_builds"])
    st.sidebar.markdown("**Current session**")
    st.sidebar.metric("Loaded candidates", metrics["loaded_candidates"])
    st.sidebar.metric("Loaded evidence links", metrics["loaded_evidence_links"])
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


def source_intelligence_warnings(data: dict[str, pd.DataFrame]) -> None:
    for warning in data.get("source_intelligence_warnings", []):
        st.warning(warning)


def text_contains_any(series: pd.Series, terms: list[str]) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=bool)
    pattern = "|".join(re.escape(term) for term in terms)
    return series.astype(str).str.contains(pattern, case=False, regex=True, na=False)


def combined_text(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)
    available = [column for column in columns if column in df.columns]
    if not available:
        return pd.Series("", index=df.index)
    return df[available].astype(str).agg(" ".join, axis=1)


def connector_matrix_view(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return matrix.copy()
    view = matrix.copy()
    if "recommended_priority" not in view.columns:
        view["recommended_priority"] = view.get("priority_stage", "")
    if "recommended_connector" not in view.columns:
        view["recommended_connector"] = view.get("extractor_type", "")
    if "expected_records" not in view.columns:
        view["expected_records"] = view.get("records_expected", view.get("approximate_methodology_count", ""))
    if "fields_available" not in view.columns:
        view["fields_available"] = view.get("fields_visible", "")
    if "disagreement_level" not in view.columns:
        view["disagreement_level"] = view.get("known_disagreement", "")
    if "verification_needed" not in view.columns:
        verification_text = combined_text(view, ["next_action", "known_disagreement", "implementation_note"])
        view["verification_needed"] = text_contains_any(verification_text, ["verify", "verification", "fetch", "check"]).map({True: "Yes", False: "No"})
    if "implementation_difficulty" not in view.columns:
        difficulty = pd.Series("Low", index=view.index)
        js_text = combined_text(view, ["js_required", "source_archetype", "extractor_type"])
        pdf_text = combined_text(view, ["pdf_strategy", "source_archetype"])
        difficulty.loc[text_contains_any(pdf_text, ["pdf"])] = "Medium"
        difficulty.loc[text_contains_any(js_text, ["yes", "js", "playwright", "browser"])] = "High"
        view["implementation_difficulty"] = difficulty
    return view


def connector_roadmap_metrics(matrix: pd.DataFrame) -> list[tuple[str, int]]:
    if matrix.empty:
        return [
            ("Total researched sources", 0),
            ("Implement now", 0),
            ("Needs verification", 0),
            ("Requires PDF parsing", 0),
            ("Requires JS / Playwright", 0),
            ("Disputed / contradictory", 0),
        ]
    view = connector_matrix_view(matrix)
    priority_text = combined_text(view, ["recommended_priority", "priority_stage", "next_action"])
    implement_now = text_contains_any(priority_text, ["stage 1", "implement now", "implement or run", "high-priority"])
    verification_needed = view.get("verification_needed", pd.Series("", index=view.index)).astype(str).str.lower().isin(["yes", "true", "1"])
    pdf_text = combined_text(view, ["pdf_strategy", "source_archetype", "extractor_type"])
    js_text = combined_text(view, ["js_required", "source_archetype", "extractor_type", "recommended_connector"])
    disagreement = view.get("disagreement_level", pd.Series("", index=view.index)).astype(str)
    disputed = disagreement.str.contains("high|medium|contradict|disput|differ", case=False, regex=True, na=False)
    return [
        ("Total researched sources", len(view)),
        ("Implement now", int(implement_now.sum())),
        ("Needs verification", int(verification_needed.sum())),
        ("Requires PDF parsing", int(text_contains_any(pdf_text, ["pdf"]).sum())),
        ("Requires JS / Playwright", int(text_contains_any(js_text, ["yes", "js", "playwright", "browser"]).sum())),
        ("Disputed / contradictory", int(disputed.sum())),
    ]


def connector_roadmap_page(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Connector Roadmap")
    st.info(
        "This section converts the research audits into an implementation roadmap. "
        "It does not mean the sources have already been extracted. It identifies where methodology information appears to live "
        "and what connector pattern should be tested."
    )
    source_intelligence_warnings(data)

    matrix = data.get("connector_source_matrix", pd.DataFrame())
    verification_plan = data.get("source_verification_plan", pd.DataFrame())
    metadata = data.get("connector_source_matrix_metadata", {})
    if isinstance(metadata, dict) and metadata.get("generated_at"):
        st.caption(f"Research matrix generated at: {metadata.get('generated_at')}")

    if matrix.empty:
        st.info("No connector source matrix is loaded yet.")
    else:
        metric_row(connector_roadmap_metrics(matrix))
        view = connector_matrix_view(matrix)
        filter_columns = [
            column
            for column in ["source_archetype", "recommended_priority", "extractor_type", "verification_needed", "disagreement_level"]
            if column in view.columns
        ]
        filtered = inline_filters(view, filter_columns, "connector_roadmap")
        display_columns = [
            "programme_name",
            "recommended_priority",
            "recommended_connector",
            "source_archetype",
            "methodology_source_url",
            "registry_url",
            "document_library_url",
            "expected_records",
            "fields_available",
            "extractor_type",
            "implementation_difficulty",
            "next_action",
            "disagreement_level",
            "verification_needed",
        ]
        st.subheader("Prioritized Connector Table")
        show_dataframe(select_existing(filtered, display_columns), "connector_roadmap", height=520)

    st.subheader("Verification Plan")
    if verification_plan.empty:
        st.info("No source verification plan is loaded yet.")
    else:
        st.write("URLs and assumptions to verify before coding new connectors.")
        verification_filters = [
            column
            for column in ["verification_priority", "recommended_connector_if_verified", "programme_name"]
            if column in verification_plan.columns
        ]
        filtered_plan = inline_filters(verification_plan, verification_filters, "source_verification_plan")
        verification_columns = [
            "programme_name",
            "url_to_verify",
            "secondary_url_to_verify",
            "verification_priority",
            "what_to_check",
            "expected_result_from_reports",
            "disagreement_to_resolve",
            "recommended_connector_if_verified",
            "status",
            "verified_at",
            "notes",
        ]
        show_dataframe(select_existing(filtered_plan, verification_columns), "source_verification_plan", height=420)


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


def connector_manifest_panel(data: dict[str, pd.DataFrame], key: str = "connector_manifest") -> None:
    manifest = build_connector_manifest(data)
    st.subheader("Connector Capability Matrix")
    st.write(
        "This matrix describes how each programme should be handled operationally. "
        "It is connector metadata, not evidence that a source has already been extracted."
    )
    if manifest.empty:
        st.info("No connector manifest rows are available because the Source Registry is not loaded.")
        return
    metric_row(
        [
            ("Manifest rows", len(manifest)),
            ("Operational / partial", count_contains(manifest, "connector_status", "operational")),
            ("Verification needed", count_contains(manifest, "connector_status", "verification")),
            ("Document-family candidates", count_contains(manifest, "connector_status", "document")),
        ]
    )
    filtered = inline_filters(
        manifest,
        ["connector_status", "source_archetype", "run_mode"],
        key,
    )
    show_dataframe(select_existing(filtered, CONNECTOR_MANIFEST_SCHEMA), key, height=380)


def programme_name_options(data: dict[str, pd.DataFrame]) -> list[str]:
    intelligence = build_programme_intelligence(data)
    if intelligence.empty or "programme_name" not in intelligence.columns:
        return []
    return sorted(value for value in intelligence["programme_name"].astype(str).str.strip().unique() if value)


def programme_rows(df: pd.DataFrame, selected_programme: str, column: str) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    selected_l = normalize_text(selected_programme).lower()
    values = df[column].astype(str).str.strip().str.lower()
    exact = df[values.eq(selected_l)].copy()
    if not exact.empty:
        return exact
    return df[values.str.contains(re.escape(selected_l), na=False)].copy()


def first_value(*values: object) -> str:
    for value in values:
        text = normalize_text(str(value or ""))
        if text:
            return text
    return ""


def selected_field_rows(field_text: str) -> pd.DataFrame:
    fields = [
        ("title", "Title"),
        ("code", "Code"),
        ("version", "Version"),
        ("status", "Status"),
        ("sector", "Sector"),
        ("pdf", "PDF URL"),
        ("detail", "Detail URL"),
    ]
    text_l = normalize_text(field_text).lower()
    rows = [{"Field": label, "Available": "Yes"} for token, label in fields if token in text_l]
    if not rows and text_l:
        rows = [{"Field": "Reported fields", "Available": field_text}]
    return pd.DataFrame(rows)


def built_programme_keys() -> set[str]:
    """Return normalized keys for every programme that has a working extractor or source-resolution routine."""
    return {programme_key(name) for name in list(SUPPORTED_EXTRACTORS) + list(SOURCE_RESOLUTION_SOURCES)}


def split_roadmap_by_built(matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (built, next_to_build) DataFrames derived from the connector-source matrix.

    Rows are matched to built connectors by ``programme_key`` so subtle name
    differences ("American Carbon Registry / ACR" vs "American Carbon Registry
    (ACR)") still collapse to the same key.
    """
    empty = pd.DataFrame(columns=["Programme", "Priority", "Source pattern", "Connector approach", "Next action"])
    if matrix.empty:
        return empty, empty
    view = connector_matrix_view(matrix)
    if "recommended_order" in view.columns:
        order = pd.to_numeric(view["recommended_order"], errors="coerce")
        view = view.assign(_order=order).sort_values(["_order", "programme_name"], na_position="last")
    columns = {
        "programme_name": "Programme",
        "recommended_priority": "Priority",
        "source_archetype": "Source pattern",
        "recommended_connector": "Connector approach",
        "next_action": "Next action",
    }
    compact = select_existing(view, list(columns.keys())).rename(columns=columns)
    if compact.empty or "Programme" not in compact.columns:
        return empty, compact
    built_keys = built_programme_keys()
    is_built = compact["Programme"].astype(str).map(lambda name: programme_key(name) in built_keys)
    return compact[is_built].copy(), compact[~is_built].copy()


def compact_roadmap_table(matrix: pd.DataFrame) -> pd.DataFrame:
    """Return the top of the roadmap. Kept for callers that still expect a single table."""
    _built, next_to_build = split_roadmap_by_built(matrix)
    return next_to_build.head(12)


def methodunit_dossier_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("MethodUnit Dossier")
    page_summary("A compact view of one programme or MethodUnit across records, evidence, issues, and source-resolution context.")

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
    resolution, resolution_source = session_or_output(
        current_source_resolution_results(),
        "source_resolution_results.csv",
        "source_resolution_results",
        SOURCE_RESOLUTION_SCHEMA,
    )
    documents = build_source_documents(links)
    manifest = build_connector_manifest(data)

    if links.empty and errors.empty and resolution.empty:
        st.info("No extracted records or source-resolution outputs are loaded yet.")
        return

    programme_values = []
    for frame, column in [(links, "program_name"), (errors, "program_name"), (resolution, "programme")]:
        if not frame.empty and column in frame.columns:
            programme_values.extend(
                value for value in frame[column].astype(str).str.strip().unique() if value
            )
    programmes = sorted(set(programme_values))
    if not programmes:
        st.info("Loaded outputs do not include programme names to build a dossier.")
        return

    selected_programme = st.selectbox("Programme", programmes, key="methodunit_dossier_programme")
    st.caption(
        f"Dossier sources: extracted links = {links_source}; extraction errors = {errors_source}; "
        f"source resolution = {resolution_source}."
    )

    programme_links = links[links.get("program_name", pd.Series("", index=links.index)).astype(str).eq(selected_programme)].copy()
    programme_documents = documents[documents.get("program_name", pd.Series("", index=documents.index)).astype(str).eq(selected_programme)].copy()
    programme_errors = errors[errors.get("program_name", pd.Series("", index=errors.index)).astype(str).eq(selected_programme)].copy()
    programme_resolution = resolution[
        resolution.get("programme", pd.Series("", index=resolution.index)).astype(str).eq(selected_programme)
    ].copy()
    programme_manifest = manifest[
        manifest.get("programme_name", pd.Series("", index=manifest.index)).astype(str).eq(selected_programme)
    ].copy()
    methodunits = programme_links[
        programme_links.get("candidate_type", pd.Series("", index=programme_links.index)).astype(str).eq("methodunit_candidate")
    ].copy()

    metric_row(
        [
            ("Candidate MethodUnits", len(methodunits)),
            ("Evidence documents / links", len(programme_documents)),
            ("Issues logged", len(programme_errors)),
            ("Source-resolution rows", len(programme_resolution)),
        ]
    )

    if not programme_manifest.empty:
        st.subheader("Connector Context")
        show_dataframe(select_existing(programme_manifest, CONNECTOR_MANIFEST_SCHEMA), "dossier_connector_context", height=160)

    if methodunits.empty:
        st.info("No candidate MethodUnit records are loaded for this programme.")
    else:
        st.subheader("Candidate MethodUnits")
        show_dataframe(
            select_existing(
                add_record_readiness(methodunits),
                [
                    "methodunit_code",
                    "methodunit_name",
                    "unit_type",
                    "status",
                    "record_readiness",
                    "confidence",
                    "review_status",
                    "source_url",
                    "document_url",
                    "notes",
                ],
            ),
            "dossier_methodunits",
            height=260,
        )

    st.subheader("Evidence Documents and Links")
    if programme_documents.empty:
        st.info("No normalized document/evidence rows are loaded for this programme.")
    else:
        show_dataframe(select_existing(programme_documents, SOURCE_DOCUMENT_SCHEMA), "dossier_source_documents", height=320)

    st.subheader("Issues and Resolution Context")
    if programme_errors.empty and programme_resolution.empty:
        st.info("No extraction issues or source-resolution context are loaded for this programme.")
    if not programme_errors.empty:
        show_dataframe(select_existing(programme_errors, EXTRACTION_ERROR_SCHEMA), "dossier_errors", height=180)
    if not programme_resolution.empty:
        show_dataframe(select_existing(programme_resolution, SOURCE_RESOLUTION_SCHEMA), "dossier_source_resolution", height=180)


def programme_intelligence_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Programme Intelligence")
    page_summary("Understand what is known about one programme: source location, connector approach, verification needs, and loaded evidence.")
    st.caption(
        "The platform tracks all programmes at baseline level. Only some have extracted MethodUnits, "
        "and the latest source-intelligence matrix covers researched next connectors rather than the full universe."
    )

    programme_intelligence = build_programme_intelligence(data)
    programmes = programme_name_options(data)
    if not programmes:
        st.info("No programme registry or source-intelligence rows are loaded yet.")
        return

    default_index = 0
    for preferred in ("American Carbon Registry (ACR)", "Climate Forward", "Climate Action Reserve"):
        if preferred in programmes:
            default_index = programmes.index(preferred)
            break
    selected_programme = st.selectbox("Programme", programmes, index=default_index, key="programme_intelligence_select")
    st.caption(
        "Try these examples: **American Carbon Registry (ACR)**, **Climate Forward**, **Social Carbon**, **Plan Vivo**, **BioCarbon Registry**, **Puro Earth**, **Artisan C-sink**."
    )

    profiles = data.get("source_profiles", pd.DataFrame())
    matrix = connector_matrix_view(data.get("connector_source_matrix", pd.DataFrame()))
    verification_plan = data.get("source_verification_plan", pd.DataFrame())
    manifest = build_connector_manifest(data)
    links, _links_source = session_or_output(
        current_extracted_links(),
        "extracted_source_links_full.csv",
        "extracted_source_links_full",
        CANDIDATE_SCHEMA,
    )
    source_documents, _documents_source = session_or_output(
        current_source_documents(),
        "source_documents.csv",
        "source_documents",
        SOURCE_DOCUMENT_SCHEMA,
    )
    resolution, _resolution_source = session_or_output(
        current_source_resolution_results(),
        "source_resolution_results.csv",
        "source_resolution_results",
        SOURCE_RESOLUTION_SCHEMA,
    )

    intelligence_rows = programme_rows(programme_intelligence, selected_programme, "programme_name")
    profile_rows = programme_rows(profiles, selected_programme, "program_name")
    matrix_rows = programme_rows(matrix, selected_programme, "programme_name")
    verification_rows = programme_rows(verification_plan, selected_programme, "programme_name")
    manifest_rows = programme_rows(manifest, selected_programme, "programme_name")
    link_rows = programme_rows(links, selected_programme, "program_name")
    document_rows = programme_rows(source_documents, selected_programme, "program_name")
    resolution_rows = programme_rows(resolution, selected_programme, "programme")

    intelligence_row = intelligence_rows.iloc[0] if not intelligence_rows.empty else pd.Series(dtype=object)
    profile = profile_rows.iloc[0] if not profile_rows.empty else pd.Series(dtype=object)
    matrix_row = matrix_rows.iloc[0] if not matrix_rows.empty else pd.Series(dtype=object)
    manifest_row = manifest_rows.iloc[0] if not manifest_rows.empty else pd.Series(dtype=object)

    st.subheader("Status Summary")
    summary_rows = pd.DataFrame(
        [
            {"Signal": "Data coverage", "Current state": first_value(intelligence_row.get("data_coverage_level", "")) or "unknown"},
            {"Signal": "Connector status", "Current state": first_value(intelligence_row.get("connector_status", ""), manifest_row.get("connector_status", ""), intelligence_row.get("populated_source_status", "")) or "No connector implemented yet"},
            {"Signal": "Source pattern", "Current state": first_value(intelligence_row.get("source_pattern", ""), matrix_row.get("source_archetype", ""), profile.get("connector_type", ""), profile.get("source_type", "")) or "Unknown"},
            {"Signal": "Current extraction status", "Current state": first_value(intelligence_row.get("extraction_strategy", ""), manifest_row.get("run_mode", "")) or "Not attempted yet"},
            {"Signal": "Next action", "Current state": first_value(intelligence_row.get("next_action", ""), manifest_row.get("next_action", ""), matrix_row.get("next_action", ""), profile.get("notes", "")) or "Review source registry and verification plan."},
        ]
    )
    st.dataframe(summary_rows, hide_index=True, use_container_width=True)

    st.subheader("Where Methodology Information Lives")
    location_summary = first_value(
        intelligence_row.get("notes", ""),
        intelligence_row.get("extraction_strategy", ""),
        matrix_row.get("implementation_note", ""),
        profile.get("notes", ""),
        profile.get("extraction_strategy", ""),
        resolution_rows.iloc[0].get("where_methodology_info_lives", "") if not resolution_rows.empty else "",
    )
    st.write(location_summary or "No plain-language source-location summary is available for this programme yet.")

    st.subheader("Known Source URLs")
    url_rows = []
    for label, value in [
        ("Official website", first_value(intelligence_row.get("official_website", ""), profile.get("official_website", ""))),
        ("Methodology source URL", first_value(intelligence_row.get("methodology_source_url", ""), matrix_row.get("methodology_source_url", ""), profile.get("method_source_url", ""))),
        ("Registry URL", first_value(intelligence_row.get("registry_url", ""), matrix_row.get("registry_url", ""), profile.get("registry_url", ""))),
        ("Document library URL", first_value(intelligence_row.get("document_library_url", ""), matrix_row.get("document_library_url", ""), profile.get("evidence_urls", ""))),
    ]:
        if value:
            url_rows.append({"Source": label, "url": value})
    if url_rows:
        show_dataframe(pd.DataFrame(url_rows), "programme_known_urls", height=180)
    else:
        st.info("No source URLs are recorded for this programme yet.")

    st.subheader("Expected Fields")
    field_text = first_value(matrix_row.get("fields_available", ""), matrix_row.get("fields_visible", ""))
    fields = selected_field_rows(field_text)
    if fields.empty:
        st.info("No expected field inventory is recorded for this programme yet. Use the source pattern and baseline notes to verify fields before connector work.")
    else:
        st.dataframe(fields, hide_index=True, use_container_width=True)

    st.subheader("Recommended Connector Approach")
    approach_rows = pd.DataFrame(
        [
            {"Question": "Extractor type", "Answer": first_value(intelligence_row.get("recommended_connector", ""), intelligence_row.get("connector_type", ""), matrix_row.get("extractor_type", ""), matrix_row.get("recommended_connector", ""), manifest_row.get("run_mode", "")) or "Not specified"},
            {"Question": "Parsing plan", "Answer": first_value(intelligence_row.get("extraction_strategy", ""), matrix_row.get("implementation_note", ""), profile.get("extraction_strategy", "")) or "Verify source structure before coding."},
            {"Question": "PDF plan", "Answer": first_value(matrix_row.get("pdf_strategy", "")) or "No PDF parsing plan recorded."},
            {"Question": "Dedupe key", "Answer": first_value(matrix_row.get("dedupe_key", "")) or "Not specified yet."},
            {"Question": "Confidence logic", "Answer": first_value(intelligence_row.get("confidence", ""), matrix_row.get("consensus_confidence", ""), profile.get("confidence", "")) or "Review required."},
            {"Question": "Human review", "Answer": first_value(intelligence_row.get("human_review_required", ""), profile.get("human_review_required", "")) or "Review required before catalogue use."},
        ]
    )
    st.dataframe(approach_rows, hide_index=True, use_container_width=True)

    st.subheader("Verification Checklist")
    if verification_rows.empty:
        st.info("No verification checklist rows are recorded for this programme.")
    else:
        show_dataframe(
            select_existing(
                verification_rows,
                [
                    "programme_name",
                    "url_to_verify",
                    "secondary_url_to_verify",
                    "verification_priority",
                    "what_to_check",
                    "expected_result_from_reports",
                    "disagreement_to_resolve",
                    "recommended_connector_if_verified",
                ],
            ),
            "programme_verification_checklist",
            height=260,
        )

    st.subheader("Verified Source Checks")
    verification_results = data.get("plan_verification_results", pd.DataFrame())
    programme_verification = programme_rows(verification_results, selected_programme, "programme_name")
    if programme_verification.empty:
        st.info(
            "No verification runner results recorded for this programme yet. "
            "Run `python scripts/verify_source_intelligence.py` to populate."
        )
    else:
        latest = programme_verification.sort_values("checked_at", ascending=False).iloc[0]
        summary_cols = [
            {"Signal": "Last checked", "Value": latest.get("checked_at", "")},
            {"Signal": "Verification status", "Value": latest.get("verification_status", "")},
            {"Signal": "Records detected", "Value": latest.get("records_detected", "")},
            {"Signal": "PDF links detected", "Value": latest.get("pdf_links", "")},
            {"Signal": "JS likely required", "Value": latest.get("js_likely_required", "")},
            {"Signal": "Notes", "Value": latest.get("notes", "")},
        ]
        st.dataframe(pd.DataFrame(summary_cols), hide_index=True, use_container_width=True)
        show_dataframe(
            select_existing(
                programme_verification,
                [
                    "url_checked",
                    "url_role",
                    "http_status",
                    "final_url",
                    "content_type",
                    "records_detected",
                    "pdf_links",
                    "verification_status",
                    "checked_at",
                ],
            ),
            "programme_verification_results",
            height=200,
        )

    st.subheader("Current Evidence")
    method_rows = link_rows[
        link_rows.get("candidate_type", pd.Series("", index=link_rows.index)).astype(str).eq("methodunit_candidate")
    ].copy() if not link_rows.empty else pd.DataFrame(columns=CANDIDATE_SCHEMA)
    metric_row(
        [
            ("Loaded candidate records", len(method_rows)),
            ("Loaded evidence documents", len(document_rows)),
            ("Source-resolution rows", len(resolution_rows)),
        ]
    )
    if method_rows.empty and document_rows.empty and resolution_rows.empty:
        st.info("No candidate MethodUnits loaded yet. This programme is currently represented by source intelligence / baseline profile data.")
    else:
        if not method_rows.empty:
            with st.expander("Candidate records", expanded=True):
                show_dataframe(select_existing(add_record_readiness(method_rows), CANDIDATE_SCHEMA + ["record_readiness"]), "programme_candidate_records", height=260)
        if not document_rows.empty:
            with st.expander("Evidence documents", expanded=True):
                show_dataframe(select_existing(document_rows, SOURCE_DOCUMENT_SCHEMA), "programme_evidence_documents", height=260)
        if not resolution_rows.empty:
            with st.expander("Source-resolution context", expanded=False):
                show_dataframe(select_existing(resolution_rows, SOURCE_RESOLUTION_SCHEMA), "programme_resolution_context", height=180)

    with st.expander("Advanced details", expanded=False):
        st.subheader("Dossier Sources")
        source_files = first_value(intelligence_row.get("dossier_source_files", ""))
        st.info(f"Dossier built from: {source_files or 'No source files contributed rows for this selection.'}")
        st.subheader("Unified Programme Intelligence Row")
        show_dataframe(intelligence_rows, "programme_unified_intelligence", height=220)
        st.subheader("Raw Source Registry Rows")
        show_dataframe(profile_rows, "programme_raw_source_profile", height=220)
        st.subheader("Raw Connector Matrix Rows")
        show_dataframe(matrix_rows, "programme_raw_connector_matrix", height=220)
        st.subheader("Raw Connector Manifest Rows")
        show_dataframe(manifest_rows, "programme_raw_connector_manifest", height=220)


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
            "Term": "Source Document",
            "Meaning": "A normalized evidence/document row derived from extracted source links.",
            "How to Interpret": "Use it as a review inventory; it does not replace the original extracted links CSV.",
        },
        {
            "Term": "Source Verification Result",
            "Meaning": "A reachability and source-behavior check for an official source URL.",
            "How to Interpret": "Use it before connector coding to decide whether a source is reachable, document-first, or requires URL repair.",
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
    st.write("- Source documents and connector manifest rows are derived review aids; they preserve the original extraction outputs.")


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
            st.session_state["source_verification_results"] = normalize_source_verification_results(
                st.session_state["live_source_check_results"]
            )

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
        st.caption("These source checks are also available as `source_verification_results.csv` in the Export page.")
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
                "Next tab": "Candidate Methods",
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
        st.info("No live source check results in the current session. Use Source Explorer to perform a pre-check.")
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
    st.header("Candidate Methods")
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
        st.info("Run Source Explorer or load exported CSVs to review records.")
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
        help="This decision is added to the displayed rows and is written only when you click Save review decisions.",
    )
    reviewer_note = st.text_area(
        "Reviewer note for displayed rows",
        value="",
        key="candidate_review_note",
        help="Optional note saved with the review decision for the currently displayed rows.",
    )
    filtered = filtered.copy()
    filtered["review_decision"] = decision
    filtered["reviewer_note"] = reviewer_note
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
        "reviewer_note",
        "notes",
    ]
    show_dataframe(select_existing(filtered, display_columns), "candidate_review_queue", height=500)

    st.subheader("Persist Review Decisions")
    st.caption("Saves a local review-decision CSV in outputs/. Existing extraction records are not overwritten.")
    if st.button("Save review decisions for displayed rows", disabled=filtered.empty):
        now = pd.Timestamp.now().isoformat(timespec="seconds")
        decisions = filtered.copy()
        decisions["reviewed_at"] = now
        decisions["previous_review_status"] = decisions.get("review_status", "")
        decision_rows = select_existing(ensure_columns(decisions, REVIEW_DECISION_SCHEMA), REVIEW_DECISION_SCHEMA)
        path = save_review_decisions(decision_rows)
        if path is None:
            st.warning("No review decision rows were available to save.")
        else:
            st.success(f"Saved review decisions to {path}")

    saved_decisions = current_review_decisions()
    if saved_decisions.empty:
        st.info("No persisted review decisions are loaded yet.")
    else:
        with st.expander("Saved review decisions", expanded=False):
            show_dataframe(select_existing(saved_decisions, REVIEW_DECISION_SCHEMA), "saved_review_decisions", height=260)


def evidence_links_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Evidence Documents")
    page_summary("Useful links and normalized document rows preserved separately from candidate methodology records.")
    st.info(
        "These links are produced by Source Explorer and advanced extraction controls. They are useful context, but they are not treated as methodology records. "
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

    st.subheader("Normalized Source Documents")
    st.write(
        "This derived table converts extracted links into a document/evidence inventory. "
        "It preserves the original supporting-link output while making evidence easier to review and export."
    )
    documents = build_source_documents(filtered)
    if documents.empty:
        st.info("No document/evidence rows are available for the current filters.")
    else:
        document_filters = inline_filters(
            documents,
            ["document_category", "evidence_stage", "program_name", "review_status"],
            "source_documents",
        )
        show_dataframe(select_existing(document_filters, SOURCE_DOCUMENT_SCHEMA), "source_documents", height=420)


def review_decisions_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Review Decisions")
    page_summary("Persisted human review decisions for candidate records and evidence handoff.")
    st.write("Review decisions are saved separately from extracted records so the original extraction output remains unchanged.")
    decisions = current_review_decisions()
    if decisions.empty:
        st.info("No persisted review decisions are loaded yet. Use Candidate Methods to save decisions for displayed rows.")
        return
    filtered = inline_filters(
        decisions,
        ["program_name", "review_decision", "record_readiness", "confidence", "previous_review_status"],
        "review_decisions",
    )
    show_dataframe(select_existing(filtered, REVIEW_DECISION_SCHEMA), "review_decisions", height=460)


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

    st.subheader("Source Verification Results")
    verification, verification_source = session_or_output(
        current_source_verification_results(),
        "source_verification_results.csv",
        "source_verification_results",
        SOURCE_VERIFICATION_SCHEMA,
    )
    st.caption(f"Source verification data source: {verification_source}")
    if verification.empty:
        st.info("No source verification rows are loaded. Run a source access check from Source Explorer to create them.")
    else:
        show_dataframe(select_existing(verification, SOURCE_VERIFICATION_SCHEMA), "qa_source_verification_results", height=280)

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
    source_documents, source_documents_source = session_or_output(
        current_source_documents(),
        "source_documents.csv",
        "source_documents",
        SOURCE_DOCUMENT_SCHEMA,
    )
    source_verification, source_verification_source = session_or_output(
        current_source_verification_results(),
        "source_verification_results.csv",
        "source_verification_results",
        SOURCE_VERIFICATION_SCHEMA,
    )
    review_decisions, review_decisions_source = session_or_output(
        current_review_decisions(),
        "review_decisions.csv",
        "review_decisions",
        REVIEW_DECISION_SCHEMA,
    )
    connector_manifest = build_connector_manifest(data)
    source_registry = data.get("source_profiles", pd.DataFrame())
    qa = data.get("qa_flags", pd.DataFrame())
    st.caption(
        f"Export sources: records = {methodunit_source}; supporting links = {links_source}; "
        f"source documents = {source_documents_source}; extraction errors = {errors_source}; "
        f"source resolution = {source_resolution_source}; source verification = {source_verification_source}; "
        f"review decisions = {review_decisions_source}."
    )

    if methodunits.empty and links.empty and errors.empty and source_resolution.empty and source_documents.empty and source_verification.empty:
        st.info(
            "No extraction or source-resolution output is available yet. Run a quick demo extraction or resolve Artisan C-sink before returning here to export."
        )

    downloads = [
        ("Current extracted methodology records", methodunits, "methodunit_candidates_review.csv"),
        ("Full Supporting Links", links, "extracted_source_links_full.csv"),
        ("Normalized source documents", source_documents, "source_documents.csv"),
        ("Extraction errors", errors, "extraction_errors.csv"),
        ("Source-resolution results", source_resolution, "source_resolution_results.csv"),
        ("Source-verification results", source_verification, "source_verification_results.csv"),
        ("Review decisions", review_decisions, "review_decisions.csv"),
        ("Connector manifest", connector_manifest, "connector_manifest.csv"),
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

    st.subheader("Export Data Dictionary")
    dictionary_rows = [
        {"CSV": "methodunit_candidates_review.csv", "Purpose": "Candidate methodology/protocol records requiring human review before catalogue use."},
        {"CSV": "extracted_source_links_full.csv", "Purpose": "Full classified extraction output, including supporting, navigation, development, and excluded links."},
        {"CSV": "source_documents.csv", "Purpose": "Normalized document/evidence inventory derived from extracted source links."},
        {"CSV": "extraction_errors.csv", "Purpose": "Access, fetch, parsing, or classification issues from extraction runs."},
        {"CSV": "source_resolution_results.csv", "Purpose": "Where methodology information lives for no-index or document-family sources."},
        {"CSV": "source_verification_results.csv", "Purpose": "Reachability and source behavior checks performed before connector implementation."},
        {"CSV": "review_decisions.csv", "Purpose": "Persisted local reviewer decisions; does not overwrite extracted records."},
        {"CSV": "connector_manifest.csv", "Purpose": "Operational connector metadata and current implementation posture by programme."},
    ]
    st.dataframe(pd.DataFrame(dictionary_rows), hide_index=True, use_container_width=True)

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
    st.header("Carbon Methodology Extraction Workbench")
    st.write(
        "This app demonstrates how methodology and standards information can be extracted from public carbon registries "
        "and standards bodies, even when each source publishes information differently."
    )

    metric_row(
        [
            ("Stable extractors", DEMO_METRICS["stable_extractors"]),
            ("Experimental checks", DEMO_METRICS["experimental_checks"]),
            ("Extracted records", DEMO_METRICS["methodology_records"]),
            ("Evidence/source links", DEMO_METRICS["source_links"]),
            ("Extraction errors", DEMO_METRICS["errors"]),
        ]
    )

    st.subheader("Supported Sources")
    stable_rows = [{"Stable extractor": source} for source in STABLE_EXTRACTORS]
    st.dataframe(pd.DataFrame(stable_rows), hide_index=True, use_container_width=True, height=360)
    st.subheader("Experimental Source Checks")
    st.caption("These are included for source-access testing and may not have saved records in the current package.")
    experimental_rows = [{"Experimental source check": source} for source in EXPERIMENTAL_EXTRACTORS]
    st.dataframe(pd.DataFrame(experimental_rows), hide_index=True, use_container_width=True, height=110)

    st.subheader("What the App Does")
    st.write("- Finds public methodology/standards pages")
    st.write("- Extracts methodology or document records")
    st.write("- Captures primary and supporting source documents")
    st.write("- Routes records for human review")
    st.write("- Exports reviewed outputs")


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
    st.header("Source Explorer")
    page_summary("Choose a source and see what the platform found: records, documents, issues, and the recommended next action.")
    st.write("Pick a source, run exploration, and review what happened.")

    with st.expander("Recommended demo path", expanded=False):
        st.write("- **Climate Forward** — simple static table.")
        st.write("- **American Carbon Registry / ACR** — catalogue + detail pages + PDFs.")
        st.write("- **Social Carbon** — coded detail pages + version history.")
        st.write("- **Plan Vivo** — compact approved-methodology cards (PM001/PM002).")
        st.write("- **BioCarbon Registry / BCR** — AFOLU card scanner with native + adopted-external (CDM) methodologies.")
        st.write("- **Puro Earth** — landing page + document library with HubSpot-hosted PDFs and evidence-stage tagging.")
        st.write("- **Artisan C-sink** — source-resolution case (no clean methodology page).")

    default_source_context = {
        "Climate Action Reserve": {
            "mode": "clean methodology/protocol table",
            "next_action": "Review the records found from the public protocol table, then export if they look right.",
        },
        "International Carbon Registry / ICR": {
            "mode": "discovery-only (M-ICR codes + detail URLs; titles need manual review)",
            "next_action": "Review discovery records; expect several to be marked needs_research on the title.",
        },
        "Asia Carbon Institute": {
            "mode": "SSL exception surface (source access issue by default)",
            "next_action": "Review the source-access error; retry only with insecure SSL for analyst testing if needed.",
        },
        "City Forest Credits": {
            "mode": "document/protocol-family extraction",
            "next_action": "Review document titles, versions, and supporting links before catalogue handoff.",
        },
        "Climate Forward": {
            "mode": "forecast methodology index + detail-page follow-through",
            "next_action": "Review the 7 forecast methodologies plus their per-methodology PDFs and program document set.",
        },
        "American Carbon Registry / ACR": {
            "mode": "approved methodology catalogue + detail-page follow-through with evidence stages",
            "next_action": "Review the 13 approved methodologies; historical PDFs are captured but never attached as primary.",
        },
        "Social Carbon": {
            "mode": "coded card index + detail-page follow-through with version history",
            "next_action": "Review SCM-coded methodologies; inactive methodologies (e.g. SCM0001) are ingested with status = Inactive.",
        },
        "Artisan C-sink": {
            "mode": "source resolution (document-family capture)",
            "next_action": "Review the document-family record and supporting clarification links before catalogue handoff.",
        },
    }

    explorer_sources = list(SUPPORTED_EXTRACTORS) + list(SOURCE_RESOLUTION_SOURCES)
    source_context = {
        source: default_source_context.get(
            source,
            {
                "mode": "source-specific extraction",
                "next_action": f"Review the records returned for {source} before catalogue handoff.",
            },
        )
        for source in explorer_sources
    }
    source = st.selectbox("Source to explore", explorer_sources, key="explore_source_select")

    if st.button("Explore source", type="primary", key="explore_source_run"):
        context = source_context[source]
        spinner_message = f"Exploring {source}..." if source not in SOURCE_RESOLUTION_SOURCES else f"Resolving {source} source..."
        with st.spinner(spinner_message):
            if source in SOURCE_RESOLUTION_SOURCES:
                resolution_df, candidates_df, errors_df = resolve_artisan_c_sink_source(data.get("source_profiles", pd.DataFrame()))
                enrichment_metrics = {}
                st.session_state["source_resolution_results"] = resolution_df
                st.session_state["source_resolution_candidates"] = candidates_df
                st.session_state["source_resolution_errors"] = errors_df
                st.session_state["source_resolution_last_run"] = source
                st.session_state["demo_source_last_run"] = ""
            else:
                candidates_df, errors_df, enrichment_metrics = run_candidate_extractors(
                    [source],
                    data.get("source_profiles", pd.DataFrame()),
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

    with st.expander("Advanced run details", expanded=False):
        st.write(f"Internal mode used: {summary.get('Mode used', '')}")

    st.info("Review extracted records and evidence on the **Review Desk** page.")

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
    st.header("Review Desk")
    page_summary("Review candidate methods, evidence documents, issues, decisions, and export packages.")
    st.write(
        "Candidate records are not approved methodologies until reviewed. "
        "Use this desk to inspect records, preserve evidence, record decisions, and export handoff files."
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
            "Run Source Explorer or load exported CSVs to review records."
        )
    else:
        with st.expander("Result interpretation summary", expanded=True):
            if last_run:
                st.caption(f"Latest session run: {last_run}")
            render_result_interpretation(candidates, errors)

    tabs = st.tabs(["Candidate Methods", "Evidence Documents", "Issues", "Review Decisions", "Exports"])
    with tabs[0]:
        candidate_review_page(data)
    with tabs[1]:
        evidence_links_page(data)
    with tabs[2]:
        qa_exceptions_page(data)
    with tabs[3]:
        review_decisions_page(data)
    with tabs[4]:
        export_page(data)

    with st.expander("Advanced details", expanded=False):
        interpreting_outputs_page(data)
        methodunit_dossier_page(data)


def exports_page(data: dict[str, pd.DataFrame]) -> None:
    export_page(data)


def connector_roadmap_platform_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Connector Roadmap")
    page_summary("Future source integration planning from research audits and verification plans.")
    st.info(
        "This roadmap identifies where methodology information appears to live and what connector pattern should be tested. "
        "It does not mean these sources have already been extracted."
    )
    source_intelligence_warnings(data)

    matrix = data.get("connector_source_matrix", pd.DataFrame())
    verification_plan = data.get("source_verification_plan", pd.DataFrame())
    view = connector_matrix_view(matrix)

    metric_values = dict(connector_roadmap_metrics(matrix))
    metric_row(
        [
            ("Researched sources", metric_values.get("Total researched sources", 0)),
            ("Ready for verification", metric_values.get("Needs verification", 0)),
            ("PDF-first sources", metric_values.get("Requires PDF parsing", 0)),
            ("JS / API sources", metric_values.get("Requires JS / Playwright", 0)),
        ]
    )

    built_matrix, next_to_build = split_roadmap_by_built(matrix)
    st.subheader("Already Built")
    built_now = list(SUPPORTED_EXTRACTORS) + list(SOURCE_RESOLUTION_SOURCES)
    st.caption(
        f"{len(built_now)} programme(s) have a working extractor or source-resolution routine: "
        + ", ".join(built_now)
    )
    if not built_matrix.empty:
        st.caption("Of those, the following are also present in the researched connector matrix:")
        st.dataframe(built_matrix, hide_index=True, use_container_width=True)

    st.subheader("Next to Build")
    if next_to_build.empty:
        if matrix.empty:
            st.info("No source-intelligence matrix is loaded yet.")
        else:
            st.info("Every researched connector in the matrix has been built.")
    else:
        st.caption("Researched connector candidates that do not yet have an extractor in this app.")
        st.dataframe(next_to_build, hide_index=True, use_container_width=True)

    if not view.empty:
        readiness_text = combined_text(view, ["verification_needed", "next_action", "implementation_note"])
        pdf_text = combined_text(view, ["pdf_strategy", "source_archetype", "extractor_type"])
        js_text = combined_text(view, ["js_required", "api_visible", "source_archetype", "extractor_type", "recommended_connector"])
        disagreement_text = combined_text(view, ["disagreement_level", "known_disagreement"])

        sections = [
            ("Sources Ready for Verification", view[text_contains_any(readiness_text, ["yes", "verify", "verification", "fetch", "check"])]),
            ("PDF-First Sources", view[text_contains_any(pdf_text, ["pdf", "document"])]),
            ("JS / API Sources", view[text_contains_any(js_text, ["yes", "js", "api", "playwright", "browser"])]),
            ("Disputed or Contradictory Sources", view[text_contains_any(disagreement_text, ["high", "medium", "contradict", "disput", "differ"])]),
        ]
        for title, section_df in sections:
            st.subheader(title)
            if section_df.empty:
                st.info(f"No {title.lower()} are identified in the loaded roadmap.")
            else:
                show_dataframe(
                    select_existing(
                        section_df,
                        [
                            "programme_name",
                            "recommended_priority",
                            "source_archetype",
                            "extractor_type",
                            "methodology_source_url",
                            "records_expected",
                            "fields_available",
                            "next_action",
                            "known_disagreement",
                        ],
                    ),
                    re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
                    height=240,
                )

    st.subheader("Verified Source Checks")
    verification_results = data.get("plan_verification_results", pd.DataFrame())
    if verification_results.empty:
        st.info(
            "No verification results loaded. Run `python scripts/verify_source_intelligence.py` "
            "to fetch the plan and matrix URLs and populate `outputs/source_verification_results.csv`."
        )
    else:
        status_counts = (
            verification_results["verification_status"].fillna("").replace("", "unknown").value_counts()
        )
        st.dataframe(
            pd.DataFrame({"verification_status": status_counts.index, "count": status_counts.values}),
            hide_index=True,
            use_container_width=True,
        )
        show_dataframe(
            select_existing(
                verification_results,
                [
                    "programme_name",
                    "url_role",
                    "verification_status",
                    "records_detected",
                    "pdf_links",
                    "js_likely_required",
                    "http_status",
                    "checked_at",
                ],
            ),
            "roadmap_verification_results",
            height=280,
        )

    with st.expander("Advanced details", expanded=False):
        connector_roadmap_page(data)
        st.subheader("Full Connector Manifest")
        connector_manifest_panel(data, "roadmap_connector_manifest")
        if verification_plan.empty:
            st.info("No verification plan CSV is loaded.")
        else:
            st.subheader("Full Verification Plan")
            show_dataframe(verification_plan, "roadmap_full_verification_plan", height=360)


def ai_assisted_scaling_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Strategy")
    profiles = data.get("source_profiles", pd.DataFrame())
    if not profiles.empty:
        st.subheader("Connector Priorities")
        st.dataframe(connector_priority_rows(data, derive_onboarding_plan(profiles)), hide_index=True, use_container_width=True)

    connector_manifest_panel(data, "strategy_connector_manifest")

    connector_roadmap_page(data)

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


def method_about_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Method / About")
    page_summary("How the platform thinks about methodology sources, connectors, evidence, and review.")

    st.subheader("Why Universal Methodology Extraction Is Hard")
    st.write(
        "Carbon programmes publish methodology information in many forms: clean HTML tables, document libraries, "
        "PDF families, adopted external methods, registry portals, and sometimes no dedicated methodology page at all. "
        "A single generic scraper would miss too much context and overstate confidence."
    )

    st.subheader("How Source Intelligence Works")
    st.write(
        "Source intelligence maps where methodology information appears to live, what fields seem visible, "
        "which URLs need verification, and what connector pattern should be tested before implementation."
    )

    st.subheader("What a Connector Does")
    st.write(
        "A connector is a small source-specific routine. It fetches only bounded public source pages, extracts visible "
        "candidate records or document links, preserves source URLs, and logs issues separately."
    )

    st.subheader("What Candidate Records Mean")
    st.write(
        "Candidate records are possible methodology, protocol, or document-family records. "
        "They are not approved methodologies until a human reviewer checks the source evidence."
    )

    st.subheader("Why Evidence Links Are Preserved Separately")
    st.write(
        "Supporting documents, PDFs, guidance pages, development pages, and excluded links help reviewers understand the source. "
        "They are kept separate from candidate methodology records so catalogue exports stay reviewable."
    )

    st.subheader("Why Human Review Is Required")
    st.write(
        "Extraction confidence means the source structure looked readable, not that the record is commercially, legally, "
        "or carbon-market approved. Human review decides whether a candidate should be accepted, edited, rejected, or researched further."
    )

    st.subheader("How Verification-Before-Implementation Works")
    st.write(
        "Before building a new connector, the platform verifies whether the source URL is reachable, whether content is static or dynamic, "
        "which documents are visible, whether PDFs are involved, and whether reports disagree about the source."
    )

    with st.expander("Advanced details", expanded=False):
        interpreting_outputs_page(data)
        connector_manifest_panel(data, "method_about_connector_manifest")


def extract_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Extract")
    st.write("Choose a source to view the latest saved extraction, then optionally check the public source for updates.")

    default_source = "American Carbon Registry / ACR"
    default_index = PUBLIC_EXTRACTORS.index(default_source) if default_source in PUBLIC_EXTRACTORS else 0
    source = st.selectbox(
        "Carbon standard / registry",
        PUBLIC_EXTRACTORS,
        index=default_index,
        key="extract_source_select",
    )
    profile = SOURCE_PROFILES.get(source, {})
    is_experimental = source in EXPERIMENTAL_EXTRACTORS
    if is_experimental:
        st.caption(
            "Experimental source check: this source may not have saved records and live checks may depend on source access."
        )

    st.subheader("Source Profile")
    profile_rows = [
        {"Field": "Source pattern", "Value": profile.get("pattern", "Source-specific extraction")},
        {"Field": "What is extracted", "Value": profile.get("extracts", "Methodology/document records and source links.")},
        {"Field": "Primary source URL", "Value": profile.get("url", "")},
    ]
    st.dataframe(
        pd.DataFrame(profile_rows),
        hide_index=True,
        use_container_width=True,
    )
    if profile.get("url"):
        st.link_button("Open primary source", profile["url"])

    if st.button("Check for updates", key="extract_check_updates"):
        with st.spinner(f"Checking {source} for updates..."):
            candidates_df, errors_df, enrichment_metrics = run_candidate_extractors(
                [source],
                data.get("source_profiles", pd.DataFrame()),
            )
        store_update_check_results(candidates_df, errors_df, enrichment_metrics, source)

    saved_records = records_for_source(latest_saved_records(), source)
    saved_links = records_for_source(latest_saved_links(), source)
    saved_errors = records_for_source(latest_saved_errors(), source)
    update_source = st.session_state.get("update_check_source", "")
    update_status = st.session_state.get("update_check_status", "")
    update_is_for_source = bool(update_source) and source_matches(update_source, source)
    update_records = records_for_source(update_check_records(), source) if update_is_for_source else pd.DataFrame(columns=CANDIDATE_SCHEMA)
    update_links = records_for_source(update_check_links(), source) if update_is_for_source else pd.DataFrame(columns=CANDIDATE_SCHEMA)
    update_errors = records_for_source(update_check_errors(), source) if update_is_for_source else pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA)
    update_succeeded = update_is_for_source and update_status == "success"
    update_failed = update_is_for_source and update_status == "failed"
    display_records = update_records if update_succeeded else saved_records
    display_links = update_links if update_succeeded else saved_links
    display_errors = update_errors if update_is_for_source and not update_errors.empty else saved_errors

    st.subheader("Extracted Records")
    if update_succeeded:
        st.success(f"Update check completed for {source}.")
        if update_records.empty:
            st.info("Update check completed, but no methodology/document records were found for this source.")
        else:
            st.caption("Displaying updated results from this session.")
    elif update_failed:
        if saved_records.empty:
            if is_experimental:
                st.info(f"No saved extraction is available for this experimental source.")
            else:
                st.info(f"No saved extraction is available for {source}.")
            st.warning("Update check could not complete.")
            if has_ssl_or_access_issue(update_errors):
                if source == "Asia Carbon Institute":
                    st.warning(
                        "This appears to be a source-access or SSL certificate issue. "
                        "The source may require manual verification or connector configuration."
                    )
                else:
                    st.warning("This appears to be a source access or SSL certificate issue.")
        else:
            st.warning("Update check could not complete. Showing latest saved records instead.")
            if has_ssl_or_access_issue(update_errors):
                if source == "Asia Carbon Institute":
                    st.warning(
                        "This appears to be a source-access or SSL certificate issue. "
                        "The source may require manual verification or connector configuration."
                    )
                else:
                    st.warning("This appears to be a source access or SSL certificate issue.")
    elif saved_records.empty:
        if is_experimental:
            st.info("No saved extraction is available for this experimental source. Use Check for updates to test the live source.")
        else:
            st.info(f"No saved extraction is available for {source}.")
            st.caption("Use Check for updates to test the live source.")
    else:
        st.success(f"Showing latest extracted records for {source}.")

    if display_records.empty:
        pass
    else:
        st.dataframe(
            workbench_record_table(display_records),
            hide_index=True,
            use_container_width=True,
            height=440,
            column_config={
                "Source/programme": st.column_config.TextColumn("Source/programme", width="medium"),
                "Methodology / document title": st.column_config.TextColumn(
                    "Methodology / document title",
                    width="large",
                ),
                "Version": st.column_config.TextColumn("Version", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Unit type": st.column_config.TextColumn("Unit type", width="small"),
                "Primary document": st.column_config.LinkColumn(
                    "Primary document",
                    display_text="Open",
                    width="small",
                ),
                "Review status": st.column_config.TextColumn("Review status", width="small"),
            },
        )

    with st.expander("Advanced extraction details", expanded=False):
        metric_row(
            [
                ("Saved record count", len(saved_records)),
                ("Update-check record count", len(update_records) if update_is_for_source else 0),
                ("Evidence/source-link count", len(display_links)),
                ("Extraction issue count", len(display_errors)),
            ]
        )
        if not display_errors.empty:
            show_dataframe(
                select_existing(display_errors, EXTRACTION_ERROR_SCHEMA),
                "extract_advanced_errors",
                height=220,
            )


def review_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Review")
    st.write("Select an extracted record, inspect its evidence, save a review decision, and export reviewed records.")

    records, records_source = records_for_workbench()
    links, _links_source = links_for_workbench()
    if records.empty:
        st.info("No extracted records are available for review. Go to Extract to load records or check a source for updates.")
        return

    records = apply_saved_review_status(records)
    source_options = review_source_options(records)
    if not source_options:
        st.info("No extracted records are available for review. Go to Extract to load records or check a source for updates.")
        return

    filter_col_0, filter_col_1 = st.columns([2, 1], gap="small")
    with filter_col_0:
        selected_source = st.selectbox(
            "Source",
            source_options,
            index=default_review_source_index(source_options),
            key="review_source_filter",
        )
    filtered = records_for_source(records, selected_source)
    review_status_options = sorted(
        {
            normalize_text(value) or "pending_review"
            for value in filtered.get("review_status", pd.Series("", index=filtered.index)).astype(str)
        }
    )
    with filter_col_1:
        selected_review_status = st.selectbox(
            "Review status",
            ["All"] + review_status_options,
            key="review_status_filter",
        )
    if selected_review_status != "All":
        status_values = filtered.get("review_status", pd.Series("", index=filtered.index)).astype(str).apply(
            lambda value: normalize_text(value) or "pending_review"
        )
        filtered = filtered[status_values.eq(selected_review_status)].copy()

    if filtered.empty:
        st.info("No records are available for this source in the current extraction package.")
        return

    st.subheader("Records")
    st.dataframe(
        review_table(filtered),
        hide_index=True,
        use_container_width=True,
        height=300,
        column_config={
            "Source/programme": st.column_config.TextColumn("Source/programme", width="medium"),
            "Methodology / document title": st.column_config.TextColumn("Methodology / document title", width="large"),
            "Version": st.column_config.TextColumn("Version", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Unit type": st.column_config.TextColumn("Unit type", width="small"),
            "Review status": st.column_config.TextColumn("Review status", width="small"),
            "Primary document link": st.column_config.LinkColumn(
                "Primary document link",
                display_text="Open",
                width="small",
            ),
        },
    )

    labels = []
    for idx, row in filtered.reset_index().iterrows():
        title = normalize_text(row.get("methodunit_name", "")) or "(untitled record)"
        version = normalize_text(row.get("version", ""))
        labels.append(f"{idx + 1}. {title}" + (f" ({version})" if version else ""))
    selected_label = st.selectbox("Selected record", labels, key="review_record_select")
    selected_position = labels.index(selected_label)
    selected_record = filtered.reset_index(drop=True).iloc[selected_position]

    st.subheader("Selected Record Detail")
    primary_url = clean_url(selected_record.get("document_url") or selected_record.get("source_url"))
    supporting = supporting_documents_for_record(selected_record, links)
    title = normalize_text(selected_record.get("methodunit_name", "")) or "(untitled record)"
    detail_rows = [
        {"Field": "Title", "Value": title},
        {"Field": "Source/programme", "Value": selected_record.get("program_name", "")},
        {"Field": "Version", "Value": selected_record.get("version", "")},
        {"Field": "Status", "Value": selected_record.get("status", "")},
        {"Field": "Unit type", "Value": selected_record.get("unit_type", "")},
        {"Field": "Supporting document count", "Value": len(supporting)},
    ]
    st.dataframe(
        pd.DataFrame(detail_rows),
        hide_index=True,
        use_container_width=True,
    )
    if primary_url:
        st.link_button("Open primary document", primary_url)

    if not supporting.empty:
        with st.expander("Supporting document links", expanded=False):
            show_dataframe(
                select_existing(supporting, ["methodunit_name", "candidate_type", "document_url", "source_url", "notes"]),
                "review_supporting_links",
                height=220,
            )
    else:
        st.caption("No supporting document links were captured for this record.")

    notes = normalize_text(selected_record.get("notes", ""))
    if notes:
        st.caption("Extracted notes")
        st.write(notes)

    decision = st.radio(
        "Review decision",
        ["Approve", "Needs correction", "Reject"],
        horizontal=True,
        key="review_decision_choice",
    )
    reviewer_note = st.text_area("Reviewer note", key="reviewer_note")
    decision_map = {
        "Approve": "approved",
        "Needs correction": "needs_correction",
        "Reject": "rejected",
    }
    if st.button("Save review decision", type="primary", key="save_single_review"):
        now = pd.Timestamp.now().isoformat(timespec="seconds")
        decision_row = selected_record.to_dict()
        decision_row["reviewed_at"] = now
        decision_row["review_decision"] = decision_map[decision]
        decision_row["reviewer_note"] = reviewer_note
        decision_row["previous_review_status"] = decision_row.get("review_status", "")
        decision_row["record_readiness"] = decision_row.get("record_readiness", "")
        decision_df = ensure_columns(pd.DataFrame([decision_row]), REVIEW_DECISION_SCHEMA)
        path = save_review_decisions(decision_df)
        if path is None:
            st.warning("No review decision was available to save.")
        else:
            st.success("Review decision saved.")
            st.rerun()

    reviewed = current_review_decisions()
    st.subheader("Export Reviewed Records")
    if reviewed.empty:
        st.info("No reviewed records have been saved yet.")
    else:
        st.download_button(
            "Export reviewed records",
            data=as_csv_download(reviewed),
            file_name="reviewed_records.csv",
            mime="text/csv",
            key="export_reviewed_records",
        )


def about_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("About")

    st.write(
        "The app currently includes 10 stable extractors and 2 experimental source checks. "
        "Experimental checks are useful for testing access patterns, but they are not part of the stable saved package."
    )

    st.subheader("Why This Is Difficult")
    st.write(
        "Carbon standards publish methodology information in different shapes: catalogue pages, static tables, "
        "document libraries, methodology cards, and standard-version document families. The workbench keeps those "
        "source patterns visible without treating every source as the same scraping problem."
    )

    st.subheader("Source Patterns Handled")
    pattern_rows = [
        {"Source pattern": "Catalogue + detail pages", "Example": "ACR"},
        {"Source pattern": "Static table", "Example": "Climate Forward"},
        {"Source pattern": "Coded methodology pages", "Example": "Social Carbon"},
        {"Source pattern": "Approved-methodology cards", "Example": "Plan Vivo"},
        {"Source pattern": "Elementor methodology cards", "Example": "BioCarbon Registry, Cercarbono"},
        {"Source pattern": "Document library", "Example": "Puro Earth"},
        {"Source pattern": "Document family / standard versions", "Example": "ART/TREES"},
        {"Source pattern": "Forest/document library", "Example": "City Forest Credits"},
    ]
    st.dataframe(pd.DataFrame(pattern_rows), hide_index=True, use_container_width=True)

    st.subheader("Human Review Model")
    st.write(
        "Extracted rows are review candidates. A reviewer opens the primary and supporting source links, then marks each "
        "record approved, needing correction, or rejected. Saved review decisions are exported separately from raw extraction output."
    )

    st.subheader("What Is Not Automated")
    st.write(
        "The app does not decide final market eligibility, interpret legal terms, approve methodologies, or guarantee that "
        "a source has not changed since extraction. Ambiguous records stay in the review workflow."
    )

    with st.expander("Advanced diagnostics", expanded=False):
        connector_manifest_panel(data, "about_connector_manifest")
        verification_results = data.get("plan_verification_results", pd.DataFrame())
        if not verification_results.empty:
            show_dataframe(verification_results, "about_source_verification_results", height=260)


def main() -> None:
    data = load_data()
    st.title(APP_TITLE)

    st.sidebar.title(APP_TITLE)
    page = st.sidebar.radio(
        "Pages",
        [
            "Home",
            "Extract",
            "Review",
            "About",
        ],
    )

    if page == "Home":
        overview_page(data)
    elif page == "Extract":
        extract_page(data)
    elif page == "Review":
        review_page(data)
    elif page == "About":
        about_page(data)


if __name__ == "__main__":
    main()
