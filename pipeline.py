import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).parent / "data"
OUTPUTS_DIR = Path(__file__).parent / "outputs"


FILES = {
    "source_profiles": "source_profiles_final_fixed.csv",
    "connector_strategy": "connector_strategy_fixed.csv",
    "extraction_waves": "extraction_waves_fixed.csv",
    "qa_flags": "qa_flags_fixed.csv",
    "next_actions": "next_actions_fixed.csv",
}
SOURCE_RESOLUTION_AUDIT_FILE = "source_resolution_audit_mid_activity.csv"


CANDIDATE_SCHEMA = [
    "program_id",
    "program_name",
    "methodunit_code",
    "methodunit_name",
    "unit_type",
    "candidate_type",
    "classification_reason",
    "sector",
    "version",
    "status",
    "source_url",
    "document_url",
    "extraction_method",
    "confidence",
    "review_status",
    "extracted_at",
    "notes",
]
EXTRACTION_ERROR_SCHEMA = [
    "program_name",
    "source_url",
    "error_type",
    "error_message",
    "suggested_action",
    "extracted_at",
]
SOURCE_RESOLUTION_SCHEMA = [
    "programme",
    "dedicated_methodology_page",
    "where_methodology_info_lives",
    "methodology_model",
    "recommended_catalogue_action",
    "recommended_ingestion_mode",
    "review_status",
    "evidence_url",
    "resolved_at",
]
SOURCE_RESOLUTION_AUDIT_SCHEMA = [
    "activity_tier",
    "project_count",
    "programme",
    "official_website",
    "source_resolves",
    "dedicated_methodology_page",
    "where_methodology_info_lives",
    "methodology_model",
    "approximate_count",
    "evidence_urls",
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
]
ALLOWED_CANDIDATE_TYPES = [
    "methodunit_candidate",
    "supporting_document",
    "development_page",
    "navigation_link",
    "exclude",
]
SUPPORTED_EXTRACTORS = [
    "Climate Action Reserve",
    "International Carbon Registry / ICR",
    "Asia Carbon Institute",
    "City Forest Credits",
]

LIKELY_LINK_TERMS = (
    "methodology",
    "methodologies",
    "protocol",
    "protocols",
    "standard",
    "standards",
    "method",
    "methods",
    "module",
    "tool",
    "guidance",
    "guideline",
    "pdf",
    "document",
    "library",
    "consultation",
)
CODE_PATTERNS = {
    "icr": re.compile(r"\bM-ICR\s*\d{3,}\b", re.IGNORECASE),
    "cdm": re.compile(r"\b(?:ACM\d{4}|AM\d{4}|AMS[-\s][A-Z0-9.]+)\b", re.IGNORECASE),
    "aci": re.compile(r"\bA\d{2,}(?:-\d{3,})?\b", re.IGNORECASE),
}
CAR_METHODUNIT_TERMS = (
    "protocol",
    "grassland",
    "forest",
    "biochar",
    "rice cultivation",
    "soil enrichment",
    "landfill",
    "livestock",
    "coal mine methane",
    "nitric acid",
    "halocarbon",
    "boiler",
    "ods",
    "refrigeration",
    "composting",
    "digestion",
    "organic waste",
)
SUPPORTING_DOCUMENT_TERMS = (
    "faq",
    "faqs",
    "template",
    "templates",
    "guidance",
    "guideline",
    "manual",
    "procedure",
    "approval process",
    "version history",
    "document",
    "tool",
    "form",
    "equation",
    "equations",
    "data",
    "worksheet",
    "workbook",
)
DEVELOPMENT_PAGE_TERMS = (
    "development",
    "consultation",
    "under-development",
    "public-consultation",
    "public consultation",
    "concept submission",
    "concept",
    "adaptation",
    "issue paper",
    "issue papers",
    "workgroup",
    "meeting",
    "meetings",
    "revision",
)
NAVIGATION_LINK_TERMS = (
    "next",
    "previous",
    "methodology development",
    "procedural",
    "icr methodologies",
    "approved methodologies",
    "under development",
    "sector",
)
GENERIC_NAV_TERMS = {
    "about",
    "account",
    "contact",
    "cookies",
    "events",
    "facebook",
    "home",
    "instagram",
    "linkedin",
    "login",
    "menu",
    "news",
    "privacy",
    "search",
    "sign in",
    "terms",
    "twitter",
    "x",
    "youtube",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize CSV headers while keeping source values unchanged."""
    normalized = df.copy()
    normalized.columns = (
        normalized.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return normalized


@st.cache_data(show_spinner=False)
def load_csv(file_name: str) -> pd.DataFrame:
    path = DATA_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(f"Missing expected file: {path}")
    return normalize_columns(pd.read_csv(path, dtype=str).fillna(""))


def empty_source_resolution_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=SOURCE_RESOLUTION_AUDIT_SCHEMA)


@st.cache_data(show_spinner=False)
def load_source_resolution_audit() -> tuple[pd.DataFrame, list[str]]:
    path = DATA_DIR / SOURCE_RESOLUTION_AUDIT_FILE
    if not path.exists():
        return empty_source_resolution_audit(), [f"Optional source-resolution audit file not found: {path}"]
    try:
        audit = normalize_columns(pd.read_csv(path, dtype=str).fillna(""))
    except Exception as exc:  # noqa: BLE001 - app should stay usable and show a friendly warning.
        return empty_source_resolution_audit(), [f"Could not read source-resolution audit CSV: {exc}"]

    warnings = []
    missing_columns = [column for column in SOURCE_RESOLUTION_AUDIT_SCHEMA if column not in audit.columns]
    if missing_columns:
        warnings.append(
            "Source-resolution audit CSV is missing expected columns: " + ", ".join(missing_columns)
        )
        audit = ensure_columns(audit, SOURCE_RESOLUTION_AUDIT_SCHEMA)
    return audit, warnings


@st.cache_data(show_spinner=False)
def as_csv_download(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def load_data() -> dict[str, pd.DataFrame]:
    data = {}
    for key, file_name in FILES.items():
        try:
            data[key] = load_csv(file_name)
        except FileNotFoundError as exc:
            st.error(str(exc))
            data[key] = pd.DataFrame()
        except Exception as exc:  # noqa: BLE001 - Streamlit should show useful load failures.
            st.error(f"Could not load {file_name}: {exc}")
            data[key] = pd.DataFrame()
    audit, audit_warnings = load_source_resolution_audit()
    data["source_resolution_audit"] = audit
    data["source_resolution_audit_warnings"] = audit_warnings
    return data


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0)


def count_value(df: pd.DataFrame, column: str, value: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].astype(str).str.strip().str.lower().eq(value.lower()).sum())


def count_contains(df: pd.DataFrame, column: str, token: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].astype(str).str.contains(token, case=False, na=False).sum())


def value_counts_df(df: pd.DataFrame, column: str, label: str | None = None) -> pd.DataFrame:
    if column not in df.columns or df.empty:
        return pd.DataFrame(columns=[label or column, "count"])
    counts = (
        df[column]
        .replace("", "Unknown")
        .fillna("Unknown")
        .value_counts()
        .rename_axis(label or column)
        .reset_index(name="count")
    )
    return counts


def select_existing(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]].copy()


def pretty_label(column: str) -> str:
    labels = {
        "program_name": "Programme",
        "programme": "Programme",
        "current_methodology_row_count": "Current Methodology Rows",
        "official_organization": "Official Organization",
        "official_website": "Official Website",
        "registry_url": "Registry URL",
        "method_source_url": "Method Source URL",
        "terminology_used": "Terminology Used",
        "source_type": "Source Type",
        "connector_type": "Source Pattern",
        "extraction_strategy": "Extraction Strategy",
        "automation_priority": "Automation Priority",
        "maintenance_burden": "Maintenance Burden",
        "refresh_frequency": "Refresh Frequency",
        "confidence": "Confidence",
        "evidence_urls": "Evidence URLs",
        "notes": "Notes",
        "recommended_action": "Recommended Action",
        "next_action": "Next Action",
        "action_type": "Action Type",
        "issue_type": "Issue Type",
        "affected_programme": "Affected Programme",
        "recommended_resolution": "Recommended Resolution",
        "human_review_required": "Human Review Required",
        "currently_has_methodology_rows": "Has Methodology Rows",
        "populated_source_status": "Source Status",
        "methodology_rows": "Methodology Rows",
        "standards": "Standards",
        "reusable_connector": "Reusable Extractor",
        "source_url": "Source URL",
        "checked_at": "Checked At",
        "status_code": "Status Code",
        "final_url": "Final URL",
        "content_type": "Content Type",
        "response_size_bytes": "Response Size Bytes",
        "page_title": "Page Title",
        "total_links": "Total Links",
        "pdf_links": "PDF Links",
        "likely_link_count": "Likely Link Count",
        "likely_links": "Likely Methodology / Document Links",
        "check_status": "Check Status",
        "content_hash": "Content Hash",
        "error": "Error",
        "program_id": "Programme ID",
        "methodunit_code": "MethodUnit Code",
        "methodunit_name": "MethodUnit Name",
        "unit_type": "Unit Type",
        "candidate_type": "Candidate Type",
        "classification_reason": "Classification Reason",
        "sector": "Sector",
        "version": "Version",
        "status": "Status",
        "document_url": "Document URL",
        "extraction_method": "Extraction Method",
        "review_status": "Review Status",
        "extracted_at": "Extracted At",
        "error_type": "Error Type",
        "error_message": "Error Message",
        "suggested_action": "Suggested Action",
        "dedicated_methodology_page": "Dedicated Methodology Page",
        "where_methodology_info_lives": "Where Methodology Info Lives",
        "methodology_model": "Methodology Model",
        "recommended_catalogue_action": "Recommended Catalogue Action",
        "recommended_ingestion_mode": "Recommended Ingestion Mode",
        "evidence_url": "Evidence URL",
        "resolved_at": "Resolved At",
    }
    return labels.get(column, column.replace("_", " ").title())


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    ensured = df.copy()
    for column in columns:
        if column not in ensured.columns:
            ensured[column] = ""
    return ensured


def text_blob(row: pd.Series, columns: list[str]) -> str:
    return " ".join(str(row.get(column, "")) for column in columns).lower()


def program_in(row: pd.Series, names: list[str]) -> bool:
    program_name = str(row.get("program_name", "")).lower()
    return any(name.lower() in program_name for name in names)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_url(value: str) -> str:
    url = str(value or "").strip()
    if url.startswith("www."):
        url = f"https://{url}"
    return url


def is_fetchable_url(url: str) -> bool:
    parsed = urlparse(clean_url(url))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def looks_like_url(text: str) -> bool:
    value = normalize_text(text).lower()
    if value.startswith(("http://", "https://", "www.")):
        return True
    return " " not in value and any(marker in value for marker in ["/", "?", "#", "=", "."]) and bool(re.fullmatch(r"[/#?=&.\w:-]+", value))


def is_pdf_or_document_url(url: str) -> bool:
    parsed_path = urlparse(clean_url(url)).path.lower()
    return parsed_path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"))


def get_program_profile(profiles: pd.DataFrame, program_names: list[str]) -> dict:
    if profiles.empty or "program_name" not in profiles.columns:
        return {}
    lookup = profiles.copy()
    lookup["_name_l"] = lookup["program_name"].astype(str).str.strip().str.lower()
    for program_name in program_names:
        matches = lookup[lookup["_name_l"].eq(program_name.lower())]
        if not matches.empty:
            return matches.iloc[0].to_dict()
    for program_name in program_names:
        matches = lookup[lookup["_name_l"].str.contains(re.escape(program_name.lower()), na=False)]
        if not matches.empty:
            return matches.iloc[0].to_dict()
    return {}


def profile_source_url(profile: dict) -> str:
    return clean_url(profile.get("method_source_url") or profile.get("official_website"))


def make_extraction_error(
    program_name: str,
    source_url: str,
    error_type: str,
    error_message: str,
    suggested_action: str,
) -> dict:
    return {
        "program_name": program_name,
        "source_url": clean_url(source_url),
        "error_type": error_type,
        "error_message": error_message,
        "suggested_action": suggested_action,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
    }


def normalized_protocol_key(value: str) -> str:
    key = normalize_text(value).lower()
    key = re.sub(r"\b(protocol|version|v\d+(?:\.\d+)*)\b", "", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    return normalize_text(key)


def is_clear_car_protocol_detail_link(name: str, document_url: str) -> bool:
    name_l = normalize_text(name).lower()
    url_l = clean_url(document_url).lower()
    if not name_l or "protocol" not in name_l:
        return False
    if any(term in f"{name_l} {url_l}" for term in SUPPORTING_DOCUMENT_TERMS + DEVELOPMENT_PAGE_TERMS):
        return False
    return "/protocol" in url_l or "/how/protocols" in url_l


def should_capture_source_link(text: str, href: str, source_kind: str) -> bool:
    href = str(href or "").strip()
    if not href:
        return False
    if href.startswith(("mailto:", "tel:", "javascript:")):
        return False
    combined = f"{normalize_text(text).lower()} {href.lower()}"
    if source_kind in {"icr", "aci"} and (CODE_PATTERNS["icr"].search(combined) or CODE_PATTERNS["aci"].search(combined) or CODE_PATTERNS["cdm"].search(combined)):
        return True
    if source_kind == "car" and any(term in combined for term in CAR_METHODUNIT_TERMS):
        return True
    if any(term in combined for term in SUPPORTING_DOCUMENT_TERMS + DEVELOPMENT_PAGE_TERMS + NAVIGATION_LINK_TERMS):
        return True
    if any(term in combined for term in LIKELY_LINK_TERMS):
        return True
    if href.startswith("#"):
        return True
    return False


def classify_candidate(candidate: dict, source_kind: str) -> tuple[str, str]:
    name = normalize_text(candidate.get("methodunit_name", ""))
    code = normalize_text(candidate.get("methodunit_code", ""))
    document_url = clean_url(candidate.get("document_url", ""))
    extraction_method = normalize_text(candidate.get("extraction_method", ""))
    combined_l = f"{name} {code} {document_url}".lower()

    if not name and not code and not document_url:
        return "exclude", "Empty extracted item."

    if any(term in combined_l for term in ["facebook", "linkedin", "twitter", "youtube", "instagram", "cookie", "privacy", "terms"]):
        return "exclude", "Social, footer, or policy link."

    if source_kind == "icr" and CODE_PATTERNS["icr"].search(combined_l):
        return "methodunit_candidate", "M-ICR methodology code detected."

    if source_kind == "aci":
        if CODE_PATTERNS["cdm"].search(combined_l):
            return "methodunit_candidate", "CDM methodology code detected; classify as adopted external method."
        if CODE_PATTERNS["aci"].search(combined_l):
            return "methodunit_candidate", "ACI-specific methodology code detected."

    exact_nav_phrases = {
        "next",
        "previous",
        "methodology development",
        "procedural",
        "icr methodologies",
        "approved methodologies",
        "under development",
    }
    if name.lower() in exact_nav_phrases or document_url.endswith("#") or "#" in document_url and len(name) < 40:
        return "navigation_link", "Generic navigation or page-section link."

    if any(term in combined_l for term in DEVELOPMENT_PAGE_TERMS):
        return "development_page", "Development, consultation, concept, adaptation, or issue-paper language detected."

    if any(term in combined_l for term in SUPPORTING_DOCUMENT_TERMS):
        return "supporting_document", "Supporting document language detected."

    if source_kind == "car":
        has_protocol_name = any(term in combined_l for term in CAR_METHODUNIT_TERMS)
        if extraction_method == "table_parse" and has_protocol_name:
            return "methodunit_candidate", "Climate Action Reserve main protocol table row."
        if extraction_method == "link_parse" and is_clear_car_protocol_detail_link(name, document_url):
            return "methodunit_candidate", "Climate Action Reserve protocol detail link detected."
        if extraction_method == "link_parse" and has_protocol_name:
            return "supporting_document", "Climate Action Reserve protocol-related support link, not a main table row."

    if any(term in name.lower() for term in GENERIC_NAV_TERMS) or len(name) <= 3:
        return "navigation_link", "Generic navigation text."

    return "exclude", "No MethodUnit, supporting document, development, or navigation rule matched."


def apply_candidate_classification(candidates: list[dict], source_kind: str) -> list[dict]:
    classified = []
    seen_methodunit_keys = set()
    car_table_urls = {
        clean_url(candidate.get("document_url", "")).lower()
        for candidate in candidates
        if source_kind == "car" and candidate.get("extraction_method") == "table_parse" and candidate.get("document_url")
    }
    car_table_names = {
        normalized_protocol_key(candidate.get("methodunit_name", ""))
        for candidate in candidates
        if source_kind == "car" and candidate.get("extraction_method") == "table_parse" and candidate.get("methodunit_name")
    }
    for candidate in candidates:
        candidate_type, reason = classify_candidate(candidate, source_kind)
        candidate["candidate_type"] = candidate_type
        candidate["classification_reason"] = reason

        if (
            source_kind == "car"
            and candidate.get("candidate_type") == "methodunit_candidate"
            and candidate.get("extraction_method") == "link_parse"
        ):
            link_url = clean_url(candidate.get("document_url", "")).lower()
            link_name = normalized_protocol_key(candidate.get("methodunit_name", ""))
            if link_url in car_table_urls or link_name in car_table_names:
                candidate["candidate_type"] = "exclude"
                candidate["classification_reason"] = "Duplicate protocol link already captured from main table."

        if candidate.get("candidate_type") == "methodunit_candidate":
            key = (
                candidate.get("program_name", "").lower(),
                candidate.get("methodunit_code", "").lower(),
                candidate.get("methodunit_name", "").lower(),
                candidate.get("document_url", "").lower(),
            )
            if key in seen_methodunit_keys:
                candidate["candidate_type"] = "exclude"
                candidate["classification_reason"] = "Duplicate MethodUnit candidate."
            else:
                seen_methodunit_keys.add(key)

        if candidate.get("candidate_type") == "methodunit_candidate":
            if source_kind == "icr" and candidate.get("methodunit_code") and not candidate.get("methodunit_name"):
                candidate["confidence"] = "medium"
                candidate["notes"] = "title missing; detail page review required."
            if source_kind == "aci" and CODE_PATTERNS["cdm"].search(
                f"{candidate.get('methodunit_code', '')} {candidate.get('methodunit_name', '')} {candidate.get('document_url', '')}"
            ):
                candidate["unit_type"] = "adopted_external_method"
                candidate["notes"] = "Appears to be adopted from CDM."
        classified.append({column: candidate.get(column, "") for column in CANDIDATE_SCHEMA})
    return classified


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for candidate in candidates:
        key = (
            candidate.get("program_name", "").lower(),
            candidate.get("methodunit_code", "").lower(),
            candidate.get("methodunit_name", "").lower(),
            candidate.get("document_url", "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append({column: candidate.get(column, "") for column in CANDIDATE_SCHEMA})
    return deduped


def is_icr_program_name(value: str) -> bool:
    program_name = normalize_text(value).lower()
    return "international carbon registry" in program_name or program_name == "icr" or " / icr" in program_name


def is_suspicious_icr_methodunit_name(value: str) -> bool:
    title = normalize_text(value)
    title_l = title.lower()
    if not title:
        return True
    if title_l == "title requires review":
        return True
    if len(title) > 140:
        return True
    suspicious_markers = [
        "summary:",
        "sectoral scope",
        "date of first approval",
        "current stage",
    ]
    if title_l.startswith("id:"):
        return True
    return any(marker in title_l for marker in suspicious_markers)


def append_note(existing: str, note: str) -> str:
    existing = normalize_text(existing)
    if note.lower() in existing.lower():
        return existing
    return normalize_text(f"{existing} {note}")


def apply_output_safeguards(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "program_name" not in df.columns or "methodunit_name" not in df.columns:
        return df.copy()
    safe = df.copy()
    for column in ["candidate_type", "confidence", "review_status", "notes"]:
        if column not in safe.columns:
            safe[column] = ""
    suspicious_icr = safe.apply(
        lambda row: str(row.get("candidate_type", "")) in ["", "methodunit_candidate"]
        and is_icr_program_name(row.get("program_name", ""))
        and is_suspicious_icr_methodunit_name(row.get("methodunit_name", "")),
        axis=1,
    )
    if suspicious_icr.any():
        safe.loc[suspicious_icr, "confidence"] = "medium"
        safe.loc[suspicious_icr, "review_status"] = "needs_research"
        safe.loc[suspicious_icr, "notes"] = safe.loc[suspicious_icr, "notes"].map(
            lambda value: append_note(value, "ICR title requires manual review.")
        )
    return safe


def add_record_readiness(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        ready = df.copy()
        ready["record_readiness"] = ""
        return ready
    ready = apply_output_safeguards(df)
    ready["record_readiness"] = "ready_for_review"
    source_issue = ready.get("source_url", pd.Series("", index=ready.index)).astype(str).str.strip().eq("")
    needs_research = (
        ready.get("review_status", pd.Series("", index=ready.index)).astype(str).str.lower().eq("needs_research")
        | ready.get("methodunit_name", pd.Series("", index=ready.index)).astype(str).str.strip().isin(["", "Title requires review"])
        | ready.get("confidence", pd.Series("", index=ready.index)).astype(str).str.lower().eq("low")
        | ready.apply(
            lambda row: is_icr_program_name(row.get("program_name", ""))
            and is_suspicious_icr_methodunit_name(row.get("methodunit_name", "")),
            axis=1,
        )
    )
    ready.loc[needs_research, "record_readiness"] = "needs_research"
    ready.loc[source_issue, "record_readiness"] = "source_issue"
    return ready


def current_extracted_links() -> pd.DataFrame:
    return apply_output_safeguards(
        st.session_state.get("candidate_extraction_results", pd.DataFrame(columns=CANDIDATE_SCHEMA)).copy()
    )


def current_methodunit_candidates() -> pd.DataFrame:
    candidates = current_extracted_links()
    if candidates.empty or "candidate_type" not in candidates.columns:
        return pd.DataFrame(columns=CANDIDATE_SCHEMA)
    return candidates[candidates["candidate_type"].eq("methodunit_candidate")].copy()


def current_extraction_errors() -> pd.DataFrame:
    return st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA)).copy()


def current_live_source_failures() -> pd.DataFrame:
    checks = st.session_state.get("live_source_check_results", pd.DataFrame())
    if checks.empty or "check_status" not in checks.columns:
        return pd.DataFrame()
    return checks[checks["check_status"].astype(str).str.upper().eq("FAILED")].copy()


def load_output_csv(file_name: str, columns: list[str] | None = None) -> pd.DataFrame:
    path = OUTPUTS_DIR / file_name
    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    try:
        df = normalize_columns(pd.read_csv(path, dtype=str).fillna(""))
        return ensure_columns(df, columns) if columns else df
    except Exception as exc:  # noqa: BLE001 - visible app warning is more useful than failing the page.
        st.warning(f"Could not load {path}: {exc}")
        return pd.DataFrame(columns=columns or [])


def latest_output_csv(prefix: str, columns: list[str] | None = None) -> pd.DataFrame:
    if not OUTPUTS_DIR.exists():
        return pd.DataFrame(columns=columns or [])
    matches = sorted(OUTPUTS_DIR.glob(f"{prefix}_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        return pd.DataFrame(columns=columns or [])
    try:
        df = normalize_columns(pd.read_csv(matches[0], dtype=str).fillna(""))
        return ensure_columns(df, columns) if columns else df
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load {matches[0]}: {exc}")
        return pd.DataFrame(columns=columns or [])


def session_or_output(
    session_df: pd.DataFrame,
    exact_file_name: str,
    latest_prefix: str,
    columns: list[str],
) -> tuple[pd.DataFrame, str]:
    if not session_df.empty:
        df = ensure_columns(session_df, columns)
        if columns == CANDIDATE_SCHEMA:
            df = apply_output_safeguards(df)
        return df, "current Streamlit session"
    latest = latest_output_csv(latest_prefix, columns)
    if not latest.empty:
        if columns == CANDIDATE_SCHEMA:
            latest = apply_output_safeguards(latest)
        return latest, f"latest outputs/{latest_prefix}_*.csv"
    exact = load_output_csv(exact_file_name, columns)
    if not exact.empty:
        if columns == CANDIDATE_SCHEMA:
            exact = apply_output_safeguards(exact)
        return exact, f"outputs/{exact_file_name}"
    return pd.DataFrame(columns=columns), "none"


def save_timestamped_outputs(data: dict[str, pd.DataFrame]) -> list[Path]:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outputs = {
        f"methodunit_candidates_review_{timestamp}.csv": current_methodunit_candidates(),
        f"extracted_source_links_full_{timestamp}.csv": current_extracted_links(),
        f"extraction_errors_{timestamp}.csv": current_extraction_errors(),
        f"source_registry_{timestamp}.csv": data.get("source_profiles", pd.DataFrame()),
        f"qa_flags_{timestamp}.csv": data.get("qa_flags", pd.DataFrame()),
    }
    saved_paths = []
    for file_name, df in outputs.items():
        if df.empty:
            continue
        path = OUTPUTS_DIR / file_name
        df.to_csv(path, index=False)
        saved_paths.append(path)
    return saved_paths


def derive_onboarding_plan(profiles: pd.DataFrame) -> pd.DataFrame:
    planned = profiles.copy()
    if planned.empty:
        return planned
    for column in [
        "program_name",
        "method_source_url",
        "official_website",
        "connector_type",
        "source_type",
        "confidence",
        "populated_source_status",
        "automation_priority",
        "notes",
        "extraction_strategy",
        "extraction_wave",
    ]:
        if column not in planned.columns:
            planned[column] = ""

    rows = []
    live_checks = st.session_state.get("live_source_check_results", pd.DataFrame())
    failed_urls = set()
    if not live_checks.empty and "check_status" in live_checks.columns:
        failed = live_checks[live_checks["check_status"].astype(str).str.upper().eq("FAILED")]
        failed_urls = set(failed.get("source_url", pd.Series(dtype=str)).astype(str).str.lower())

    for _, row in planned.iterrows():
        combined = text_blob(row, ["program_name", "connector_type", "source_type", "notes", "extraction_strategy", "method_source_url"])
        source_url = clean_url(row.get("method_source_url") or row.get("official_website"))
        has_source_url = bool(source_url)
        confidence = str(row.get("confidence", ""))
        populated_status = str(row.get("populated_source_status", ""))

        extraction_status = "not implemented"
        category = "Ready for extraction"
        wave = "Wave 3: Add more catalogue-style sources"
        action = "Validate source URL, then design a small source-specific extractor."

        if program_in(row, ["Climate Action Reserve"]):
            extraction_status = "working extractor"
            category = "Working extractor"
            wave = "Wave 1: Stabilize working extractors"
            action = "Keep CAR stable and use it as the structured-table reference pattern."
        elif program_in(row, ["International Carbon Registry", "ICR"]):
            extraction_status = "partial extractor: discovery-only"
            category = "Working extractor"
            wave = "Wave 1: Stabilize working extractors"
            action = "Keep discovery-only until title review and detail-page enrichment are reliable."
        elif program_in(row, ["Asia Carbon Institute"]):
            extraction_status = "partial extractor: blocked/source exception"
            category = "Working extractor"
            wave = "Wave 1: Stabilize working extractors"
            action = "Treat as source exception until SSL/source access is resolved; preserve adopted-method logic."
        elif program_in(row, ["City Forest Credits"]):
            extraction_status = "partial extractor: document/protocol-family links"
            category = "Working extractor"
            wave = "Wave 1: Stabilize working extractors"
            action = "Use document/protocol-family extraction; full PDF parsing is not yet implemented."
        elif program_in(row, ["Artisan C-sink", "Artisan C-Sink"]):
            extraction_status = "source resolution implemented: document-family capture"
            category = "Working extractor"
            wave = "Wave 3: Add more catalogue-style sources"
            action = "Capture as single standard/document-family record; review clarification documents and stable PDF URL."
        elif source_url and source_url.lower() in failed_urls:
            extraction_status = "source URL failed live check"
            category = "Needs URL repair"
            wave = "Wave 3: Add more catalogue-style sources"
            action = "Repair or replace the stale source URL before building extraction logic."
        elif program_in(row, ["American Carbon Registry", "ACR"]):
            extraction_status = "not implemented: URL readiness needs confirmation"
            category = "Needs URL repair"
            wave = "Wave 3: Add more catalogue-style sources"
            action = "Confirm the current methodologies URL before adding the ACR extractor."
        elif any(term in combined for term in ["js-heavy", "portal", "dynamic", "headless", "verra", "gold standard", "isometric", "riverse", "puro"]):
            category = "Needs browser automation later"
            wave = "Wave 5: Complex/high-value sources"
            action = "Defer until a browser/API/network strategy is designed; do not treat as basic HTML scraping."
        elif any(term in combined for term in ["adopted", "external", "cdm", "verra", "gold standard"]) or program_in(row, ["BioCarbon", "Cercarbono", "Social Carbon", "Global Carbon Council", "GCC"]):
            category = "Needs adopted-method handling"
            wave = "Wave 4: Handle adopted-method sources"
            action = "Separate native methods from adopted external methods and preserve source references."
        elif any(term in combined for term in ["pdf", "document", "guideline"]) or program_in(row, ["City Forest Credits", "Nori", "ART/TREES", "Peatland Code", "Plan Vivo"]):
            category = "Needs document/PDF parsing"
            wave = "Wave 2: Add reachable document-family sources"
            action = "Start with document listing metadata; defer PDF content extraction to a controlled follow-up."
        elif (
            not has_source_url
            or "low" in confidence.lower()
            or "unresolved" in populated_status.lower()
            or any(term in combined for term in ["unclear", "manual", "monitor", "no clear", "unresolved"])
        ):
            category = "Needs manual investigation"
            wave = "Wave 6: Long-tail unresolved sources"
            action = "Manually verify whether a methodology source exists and update the Source Registry."
        elif any(term in combined for term in ["catalog", "catalogue", "html", "list", "methodologies"]):
            category = "Ready for extraction"
            wave = "Wave 3: Add more catalogue-style sources"
            action = "Build a small HTML/catalogue extractor after confirming URL stability."

        rows.append(
            {
                **row.to_dict(),
                "current_source_url": source_url,
                "current_extraction_status": extraction_status,
                "onboarding_category": category,
                "suggested_wave": wave,
                "recommended_next_action": action,
            }
        )

    return pd.DataFrame(rows)


def run_candidate_extractors(
    selected_extractors: list[str],
    profiles: pd.DataFrame,
    allow_insecure_ssl: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from extractors import (
        extract_climate_action_reserve_candidates,
        extract_icr_candidates,
        extract_asia_carbon_institute_candidates,
        extract_cfc_candidates,
    )

    extractor_map = {
        "Climate Action Reserve": extract_climate_action_reserve_candidates,
        "International Carbon Registry / ICR": extract_icr_candidates,
        "Asia Carbon Institute": extract_asia_carbon_institute_candidates,
        "City Forest Credits": extract_cfc_candidates,
    }
    all_candidates = []
    errors = []
    enrichment_metrics = {
        "icr_candidates_found": 0,
        "icr_detail_pages_fetched": 0,
        "icr_titles_extracted": 0,
        "icr_titles_still_requiring_review": 0,
        "icr_fetch_failures": 0,
        "icr_suspicious_titles_rejected": 0,
        "cfc_records_found": 0,
        "cfc_document_links_found": 0,
        "cfc_supporting_links_found": 0,
        "cfc_records_missing_version": 0,
        "cfc_fetch_failures": 0,
    }
    for extractor_name in selected_extractors:
        extractor = extractor_map.get(extractor_name)
        if extractor is None:
            continue
        result = extractor(profiles, allow_insecure_ssl)
        candidates = result[0]
        error = result[1] if len(result) > 1 else ""
        metrics = result[2] if len(result) > 2 else {}
        all_candidates.extend(candidates)
        if error:
            if isinstance(error, list):
                errors.extend(error)
            else:
                errors.append(error)
        for key in enrichment_metrics:
            enrichment_metrics[key] += int(metrics.get(key, 0) or 0)
    return (
        apply_output_safeguards(
            pd.DataFrame([{column: candidate.get(column, "") for column in CANDIDATE_SCHEMA} for candidate in all_candidates], columns=CANDIDATE_SCHEMA)
        ),
        pd.DataFrame([{column: error.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for error in errors], columns=EXTRACTION_ERROR_SCHEMA),
        enrichment_metrics,
    )
