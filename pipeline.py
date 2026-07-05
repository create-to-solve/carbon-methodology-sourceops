import hashlib
import re
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).parent / "data"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
SOURCE_INTELLIGENCE_DIR = DATA_DIR / "source_intelligence"


FILES = {
    "source_profiles": "source_profiles_final_fixed.csv",
    "connector_strategy": "connector_strategy_fixed.csv",
    "extraction_waves": "extraction_waves_fixed.csv",
    "qa_flags": "qa_flags_fixed.csv",
    "next_actions": "next_actions_fixed.csv",
}
SOURCE_RESOLUTION_AUDIT_FILE = "source_resolution_audit_mid_activity.csv"
CONNECTOR_SOURCE_MATRIX_FILE = "connector_source_matrix_synthesized.csv"
CONNECTOR_SOURCE_MATRIX_JSON_FILE = "connector_source_matrix_synthesized.json"
SOURCE_VERIFICATION_PLAN_FILE = "source_verification_plan.csv"
PLAN_VERIFICATION_RESULTS_FILE = "source_verification_results.csv"

PLAN_VERIFICATION_RESULT_SCHEMA = [
    "programme_name",
    "url_checked",
    "url_role",
    "http_status",
    "final_url",
    "content_type",
    "response_size_bytes",
    "fetch_ok",
    "error_message",
    "total_links",
    "pdf_links",
    "likely_detail_links",
    "methodology_keywords_hit",
    "codes_detected",
    "records_detected",
    "js_likely_required",
    "verification_status",
    "notes",
    "checked_at",
]


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
SOURCE_VERIFICATION_SCHEMA = [
    "checked_at",
    "program_name",
    "source_url",
    "final_url",
    "check_status",
    "status_code",
    "content_type",
    "response_size_bytes",
    "page_title",
    "total_links",
    "pdf_links",
    "likely_link_count",
    "likely_links",
    "content_hash",
    "error",
    "recommended_next_action",
]
SOURCE_DOCUMENT_SCHEMA = [
    "document_id",
    "program_name",
    "methodunit_code",
    "methodunit_name",
    "candidate_type",
    "document_title",
    "document_category",
    "document_url",
    "source_url",
    "extraction_method",
    "review_status",
    "evidence_stage",
    "notes",
    "extracted_at",
]
REVIEW_DECISION_SCHEMA = [
    "reviewed_at",
    "program_name",
    "methodunit_code",
    "methodunit_name",
    "candidate_type",
    "document_url",
    "source_url",
    "review_decision",
    "reviewer_note",
    "record_readiness",
    "confidence",
    "previous_review_status",
]
CONNECTOR_MANIFEST_SCHEMA = [
    "programme_name",
    "connector_id",
    "source_archetype",
    "connector_status",
    "run_mode",
    "output_types",
    "capabilities",
    "source_url",
    "next_action",
    "implementation_note",
]
PROGRAMME_INTELLIGENCE_SCHEMA = [
    "programme_name",
    "official_website",
    "registry_url",
    "methodology_source_url",
    "document_library_url",
    "source_pattern",
    "connector_type",
    "connector_status",
    "populated_source_status",
    "extraction_strategy",
    "recommended_connector",
    "recommended_priority",
    "verification_needed",
    "human_review_required",
    "confidence",
    "next_action",
    "notes",
    "data_coverage_level",
    "dossier_source_files",
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
    "Climate Forward",
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


def load_source_intelligence() -> tuple[dict[str, pd.DataFrame | dict], list[str]]:
    warnings = []
    loaded: dict[str, pd.DataFrame | dict] = {
        "connector_source_matrix": pd.DataFrame(),
        "source_verification_plan": pd.DataFrame(),
        "connector_source_matrix_metadata": {},
    }

    for key, file_name in [
        ("connector_source_matrix", CONNECTOR_SOURCE_MATRIX_FILE),
        ("source_verification_plan", SOURCE_VERIFICATION_PLAN_FILE),
    ]:
        path = SOURCE_INTELLIGENCE_DIR / file_name
        if not path.exists():
            warnings.append(f"Optional source-intelligence file not found: {path}")
            continue
        try:
            loaded[key] = normalize_columns(pd.read_csv(path, dtype=str).fillna(""))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not read source-intelligence CSV {path}: {exc}")

    json_path = SOURCE_INTELLIGENCE_DIR / CONNECTOR_SOURCE_MATRIX_JSON_FILE
    if not json_path.exists():
        warnings.append(f"Optional source-intelligence metadata file not found: {json_path}")
    else:
        try:
            loaded["connector_source_matrix_metadata"] = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not read source-intelligence metadata JSON {json_path}: {exc}")

    return loaded, warnings


@st.cache_data(show_spinner=False)
def as_csv_download(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def load_plan_verification_results() -> pd.DataFrame:
    """Load the plan-driven verification results file if present.

    Written by ``scripts/verify_source_intelligence.py``. Absent by default; the
    UI treats missing rows as "no verification has been run yet."
    """
    path = OUTPUTS_DIR / PLAN_VERIFICATION_RESULTS_FILE
    if not path.exists():
        return pd.DataFrame(columns=PLAN_VERIFICATION_RESULT_SCHEMA)
    try:
        df = normalize_columns(pd.read_csv(path, dtype=str).fillna(""))
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not read {path}: {exc}")
        return pd.DataFrame(columns=PLAN_VERIFICATION_RESULT_SCHEMA)
    return ensure_columns(df, PLAN_VERIFICATION_RESULT_SCHEMA)


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
    source_intelligence, source_intelligence_warnings = load_source_intelligence()
    data.update(source_intelligence)
    data["source_intelligence_warnings"] = source_intelligence_warnings
    data["plan_verification_results"] = load_plan_verification_results()
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
        "programme_name": "Programme",
        "recommended_priority": "Recommended Priority",
        "priority_stage": "Priority Stage",
        "recommended_order": "Recommended Order",
        "recommended_connector": "Recommended Connector",
        "source_archetype": "Source Archetype",
        "records_expected": "Records Expected",
        "expected_records": "Expected Records",
        "fields_visible": "Fields Visible",
        "fields_available": "Fields Available",
        "extractor_type": "Extractor Type",
        "implementation_difficulty": "Implementation Difficulty",
        "known_disagreement": "Known Disagreement",
        "disagreement_level": "Disagreement Level",
        "verification_needed": "Verification Needed",
        "document_library_url": "Document Library URL",
        "url_to_verify": "URL to Verify",
        "secondary_url_to_verify": "Secondary URL to Verify",
        "verification_priority": "Verification Priority",
        "what_to_check": "What to Check",
        "expected_result_from_reports": "Expected Result From Reports",
        "disagreement_to_resolve": "Disagreement to Resolve",
        "recommended_connector_if_verified": "Recommended Connector if Verified",
        "document_id": "Document ID",
        "document_title": "Document Title",
        "document_category": "Document Category",
        "evidence_stage": "Evidence Stage",
        "reviewed_at": "Reviewed At",
        "review_decision": "Review Decision",
        "reviewer_note": "Reviewer Note",
        "previous_review_status": "Previous Review Status",
        "connector_id": "Connector ID",
        "connector_status": "Connector Status",
        "run_mode": "Run Mode",
        "output_types": "Output Types",
        "capabilities": "Capabilities",
        "implementation_note": "Implementation Note",
        "methodology_source_url": "Methodology Source URL",
        "source_pattern": "Source Pattern",
        "recommended_priority": "Recommended Priority",
        "data_coverage_level": "Data Coverage Level",
        "dossier_source_files": "Dossier Source Files",
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


def current_source_resolution_results() -> pd.DataFrame:
    return st.session_state.get("source_resolution_results", pd.DataFrame(columns=SOURCE_RESOLUTION_SCHEMA)).copy()


def normalize_source_verification_results(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return pd.DataFrame(columns=SOURCE_VERIFICATION_SCHEMA)
    normalized = ensure_columns(normalize_columns(checks), SOURCE_VERIFICATION_SCHEMA)
    status = normalized["check_status"].astype(str).str.upper()
    normalized["recommended_next_action"] = "Verify source behavior before connector implementation."
    normalized.loc[status.eq("OK"), "recommended_next_action"] = "Source reached; review likely links and proceed to connector design."
    normalized.loc[status.eq("DOCUMENT"), "recommended_next_action"] = "Document endpoint reached; capture as document-family evidence before parsing."
    normalized.loc[status.eq("NO_LIKELY_LINKS"), "recommended_next_action"] = "Source reached but no obvious methodology links found; source resolution may be needed."
    normalized.loc[status.eq("FAILED"), "recommended_next_action"] = "Access issue; repair URL, retry later, or inspect manually before coding."
    return select_existing(normalized, SOURCE_VERIFICATION_SCHEMA)


def current_source_verification_results() -> pd.DataFrame:
    verification = st.session_state.get("source_verification_results", pd.DataFrame(columns=SOURCE_VERIFICATION_SCHEMA)).copy()
    if not verification.empty:
        return ensure_columns(verification, SOURCE_VERIFICATION_SCHEMA)
    live_checks = st.session_state.get("live_source_check_results", pd.DataFrame())
    return normalize_source_verification_results(live_checks)


def current_live_source_failures() -> pd.DataFrame:
    checks = st.session_state.get("live_source_check_results", pd.DataFrame())
    if checks.empty or "check_status" not in checks.columns:
        return pd.DataFrame()
    return checks[checks["check_status"].astype(str).str.upper().eq("FAILED")].copy()


def stable_document_id(row: pd.Series) -> str:
    source = "|".join(
        normalize_text(row.get(column, ""))
        for column in ["program_name", "candidate_type", "methodunit_code", "methodunit_name", "document_url", "source_url"]
    )
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def document_category(row: pd.Series) -> str:
    candidate_type = normalize_text(row.get("candidate_type", "")).lower()
    unit_type = normalize_text(row.get("unit_type", "")).lower()
    url = clean_url(row.get("document_url") or row.get("source_url")).lower()
    if candidate_type == "methodunit_candidate" and "document" in unit_type:
        return "methodology_document_family"
    if candidate_type == "methodunit_candidate":
        return "methodology_or_protocol_record"
    if candidate_type == "supporting_document":
        if url.endswith(".pdf") or ".pdf" in url:
            return "supporting_pdf_or_document"
        return "supporting_evidence_link"
    if candidate_type == "development_page":
        return "development_or_consultation_page"
    if candidate_type == "navigation_link":
        return "navigation_reference"
    if candidate_type == "exclude":
        return "excluded_reference"
    return candidate_type or "source_link"


def evidence_stage(row: pd.Series) -> str:
    category = document_category(row)
    if category in {"methodology_or_protocol_record", "methodology_document_family"}:
        return "candidate_methodology_record"
    if category in {"supporting_pdf_or_document", "supporting_evidence_link"}:
        return "supporting_evidence"
    if category == "development_or_consultation_page":
        return "methodology_development"
    return "reference_or_review"


def build_source_documents(links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return pd.DataFrame(columns=SOURCE_DOCUMENT_SCHEMA)
    prepared = ensure_columns(apply_output_safeguards(links), CANDIDATE_SCHEMA)
    rows = []
    for _, row in prepared.iterrows():
        document_url = clean_url(row.get("document_url") or row.get("source_url"))
        source_url = clean_url(row.get("source_url"))
        if not document_url and not source_url:
            continue
        document_row = {
            "document_id": stable_document_id(row),
            "program_name": normalize_text(row.get("program_name", "")),
            "methodunit_code": normalize_text(row.get("methodunit_code", "")),
            "methodunit_name": normalize_text(row.get("methodunit_name", "")),
            "candidate_type": normalize_text(row.get("candidate_type", "")),
            "document_title": normalize_text(row.get("methodunit_name", "")) or document_url or source_url,
            "document_category": document_category(row),
            "document_url": document_url,
            "source_url": source_url,
            "extraction_method": normalize_text(row.get("extraction_method", "")),
            "review_status": normalize_text(row.get("review_status", "")),
            "evidence_stage": evidence_stage(row),
            "notes": normalize_text(row.get("notes", "")),
            "extracted_at": normalize_text(row.get("extracted_at", "")),
        }
        rows.append(document_row)
    documents = pd.DataFrame(rows, columns=SOURCE_DOCUMENT_SCHEMA)
    if documents.empty:
        return documents
    return documents.drop_duplicates("document_id").reset_index(drop=True)


def current_source_documents() -> pd.DataFrame:
    return build_source_documents(current_extracted_links())


def current_review_decisions() -> pd.DataFrame:
    session_decisions = st.session_state.get("review_decisions", pd.DataFrame(columns=REVIEW_DECISION_SCHEMA)).copy()
    if not session_decisions.empty:
        return ensure_columns(session_decisions, REVIEW_DECISION_SCHEMA)
    return load_output_csv("review_decisions.csv", REVIEW_DECISION_SCHEMA)


def save_review_decisions(decisions: pd.DataFrame) -> Path | None:
    if decisions.empty:
        return None
    OUTPUTS_DIR.mkdir(exist_ok=True)
    path = OUTPUTS_DIR / "review_decisions.csv"
    new_rows = ensure_columns(decisions, REVIEW_DECISION_SCHEMA)
    if path.exists():
        existing = load_output_csv("review_decisions.csv", REVIEW_DECISION_SCHEMA)
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows
    combined.to_csv(path, index=False)
    st.session_state["review_decisions"] = combined
    return path


def connector_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", normalize_text(value).lower()).strip("_")
    return cleaned or "unknown_source"


def programme_key(value: str) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[()]", " ", text)
    text = text.replace("&", "and")
    text = re.sub(r"\bprogramme\b", "program", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(of|the)\b", " ", text)
    return normalize_text(text)


def row_lookup(df: pd.DataFrame, column: str) -> dict[str, pd.Series]:
    if df.empty or column not in df.columns:
        return {}
    lookup = {}
    for _, row in df.iterrows():
        key = programme_key(row.get(column, ""))
        if key and key not in lookup:
            lookup[key] = row
    return lookup


def matching_row(lookup: dict[str, pd.Series], programme: str) -> pd.Series | None:
    key = programme_key(programme)
    if key in lookup:
        return lookup[key]
    for candidate_key, row in lookup.items():
        if key and (key in candidate_key or candidate_key in key):
            return row
    return None


def connector_strategy_for_programme(strategy: pd.DataFrame, programme: str) -> pd.Series | None:
    if strategy.empty or "program_name" not in strategy.columns:
        return None
    target = programme_key(programme)
    for _, row in strategy.iterrows():
        raw = str(row.get("program_name", ""))
        candidates = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                candidates = [str(item) for item in parsed]
        except Exception:  # noqa: BLE001 - list-like CSV cells are best-effort metadata.
            candidates = [raw]
        candidate_keys = [programme_key(candidate) for candidate in candidates]
        if target in candidate_keys or any(target in candidate or candidate in target for candidate in candidate_keys if candidate):
            return row
    return None


def nonempty_join(values: list[str], separator: str = " | ") -> str:
    cleaned = []
    seen = set()
    for value in values:
        text = normalize_text(value)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return separator.join(cleaned)


def value_from_rows(rows: list[pd.Series | None], fields: list[str]) -> str:
    for row in rows:
        if row is None:
            continue
        for field in fields:
            value = normalize_text(row.get(field, ""))
            if value:
                return value
    return ""


def source_files_from_rows(row_map: dict[str, pd.Series | None], extracted: bool) -> str:
    file_map = {
        "resolution_session": "source_resolution_results.csv",
        "extracted": "extracted_source_links_full.csv",
        "matrix": "connector_source_matrix_synthesized.csv",
        "verification": "source_verification_plan.csv",
        "profile": "source_profiles_final_fixed.csv",
        "strategy": "connector_strategy_fixed.csv",
        "wave": "extraction_waves_fixed.csv",
        "action": "next_actions_fixed.csv",
        "qa": "qa_flags_fixed.csv",
        "audit": "source_resolution_audit_mid_activity.csv",
    }
    sources = []
    if extracted:
        sources.append(file_map["extracted"])
    for key, row in row_map.items():
        if row is not None and key in file_map:
            sources.append(file_map[key])
    return nonempty_join(sources, ", ")


def coverage_level(row_map: dict[str, pd.Series | None], extracted: bool) -> str:
    if extracted:
        return "extracted"
    if row_map.get("matrix") is not None:
        return "researched_connector"
    if row_map.get("resolution_session") is not None or row_map.get("audit") is not None:
        return "source_resolution_needed"
    if row_map.get("profile") is not None:
        return "baseline_profile"
    if any(row_map.get(key) is not None for key in ["strategy", "wave", "action", "qa", "verification"]):
        return "minimal_inventory_only"
    return "unknown"


def build_programme_intelligence(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    profiles = data.get("source_profiles", pd.DataFrame())
    matrix = data.get("connector_source_matrix", pd.DataFrame())
    verification = data.get("source_verification_plan", pd.DataFrame())
    strategy = data.get("connector_strategy", pd.DataFrame())
    waves = data.get("extraction_waves", pd.DataFrame())
    actions = data.get("next_actions", pd.DataFrame())
    qa = data.get("qa_flags", pd.DataFrame())
    audit = data.get("source_resolution_audit", pd.DataFrame())

    extracted_links = current_extracted_links()
    resolution_results = current_source_resolution_results()

    lookups = {
        "profile": row_lookup(profiles, "program_name"),
        "matrix": row_lookup(matrix, "programme_name"),
        "verification": row_lookup(verification, "programme_name"),
        "wave": row_lookup(waves, "program_name"),
        "action": row_lookup(actions, "program_name"),
        "qa": row_lookup(qa, "program_name"),
        "audit": row_lookup(audit, "programme"),
        "resolution_session": row_lookup(resolution_results, "programme"),
        "extracted": row_lookup(extracted_links, "program_name"),
    }

    names = []
    for df, column in [
        (profiles, "program_name"),
        (matrix, "programme_name"),
        (verification, "programme_name"),
        (waves, "program_name"),
        (actions, "program_name"),
        (qa, "program_name"),
        (audit, "programme"),
        (resolution_results, "programme"),
        (extracted_links, "program_name"),
    ]:
        if not df.empty and column in df.columns:
            names.extend(value for value in df[column].astype(str).str.strip().unique() if value)

    rows = []
    seen = set()
    for programme in names:
        key = programme_key(programme)
        if not key or key in seen or any(key in seen_key or seen_key in key for seen_key in seen if seen_key):
            continue
        seen.add(key)
        row_map = {
            "profile": matching_row(lookups["profile"], programme),
            "matrix": matching_row(lookups["matrix"], programme),
            "verification": matching_row(lookups["verification"], programme),
            "wave": matching_row(lookups["wave"], programme),
            "action": matching_row(lookups["action"], programme),
            "qa": matching_row(lookups["qa"], programme),
            "audit": matching_row(lookups["audit"], programme),
            "resolution_session": matching_row(lookups["resolution_session"], programme),
            "extracted": matching_row(lookups["extracted"], programme),
            "strategy": connector_strategy_for_programme(strategy, programme),
        }
        ordered = [
            row_map["extracted"],
            row_map["resolution_session"],
            row_map["matrix"],
            row_map["verification"],
            row_map["profile"],
            row_map["strategy"],
            row_map["wave"],
            row_map["action"],
            row_map["qa"],
            row_map["audit"],
        ]
        extracted = row_map["extracted"] is not None
        method_source = value_from_rows(ordered, ["source_url", "methodology_source_url", "url_to_verify", "method_source_url", "official_website", "evidence_url", "evidence_urls"])
        document_url = value_from_rows(ordered, ["document_url", "document_library_url", "secondary_url_to_verify", "evidence_url", "evidence_urls"])
        strategy_value = value_from_rows(ordered, ["extraction_strategy", "implementation_note", "recommended_ingestion_mode", "extraction_method"])
        next_action = value_from_rows(ordered, ["next_action", "recommended_next_action", "recommended_catalogue_action", "recommended_resolution", "issue"])
        notes = nonempty_join(
            [
                value_from_rows([row_map["profile"]], ["notes"]),
                value_from_rows([row_map["matrix"]], ["implementation_note", "known_disagreement"]),
                value_from_rows([row_map["audit"]], ["notes", "assessment_basis"]),
                value_from_rows([row_map["qa"]], ["issue"]),
            ]
        )
        verification_needed = "Yes" if row_map["verification"] is not None else ""
        if row_map["matrix"] is not None:
            matrix_text = nonempty_join(
                [
                    value_from_rows([row_map["matrix"]], ["next_action", "known_disagreement", "implementation_note"]),
                ]
            ).lower()
            if any(term in matrix_text for term in ["verify", "verification", "fetch", "check", "disagreement"]):
                verification_needed = "Yes"
        if row_map["audit"] is not None and value_from_rows([row_map["audit"]], ["review_status", "source_access_issue"]):
            verification_needed = verification_needed or "Yes"

        rows.append(
            {
                "programme_name": value_from_rows(ordered, ["program_name", "programme_name", "programme"]) or programme,
                "official_website": value_from_rows(ordered, ["official_website"]),
                "registry_url": value_from_rows(ordered, ["registry_url"]),
                "methodology_source_url": clean_url(method_source),
                "document_library_url": clean_url(document_url),
                "source_pattern": value_from_rows(ordered, ["source_archetype", "connector_type", "source_type"]),
                "connector_type": value_from_rows(ordered, ["extractor_type", "recommended_connector_if_verified", "connector_type", "extraction_method"]),
                "connector_status": "extracted in current session" if extracted else "",
                "populated_source_status": value_from_rows(ordered, ["populated_source_status", "source_resolves", "review_status"]),
                "extraction_strategy": strategy_value,
                "recommended_connector": value_from_rows(ordered, ["recommended_connector", "recommended_connector_if_verified", "extractor_type", "reusable_connector"]),
                "recommended_priority": value_from_rows(ordered, ["recommended_priority", "priority_stage", "priority", "automation_priority", "extraction_wave"]),
                "verification_needed": verification_needed or "No",
                "human_review_required": value_from_rows(ordered, ["human_review_required", "creates_issue_record"]),
                "confidence": value_from_rows(ordered, ["confidence", "consensus_confidence"]),
                "next_action": next_action,
                "notes": notes,
                "data_coverage_level": coverage_level(row_map, extracted),
                "dossier_source_files": source_files_from_rows(row_map, extracted),
            }
        )

    if not rows:
        return pd.DataFrame(columns=PROGRAMME_INTELLIGENCE_SCHEMA)
    intelligence = ensure_columns(pd.DataFrame(rows), PROGRAMME_INTELLIGENCE_SCHEMA)
    return intelligence[PROGRAMME_INTELLIGENCE_SCHEMA].sort_values("programme_name").reset_index(drop=True)


def build_connector_manifest(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    profiles = data.get("source_profiles", pd.DataFrame())
    if profiles.empty:
        return pd.DataFrame(columns=CONNECTOR_MANIFEST_SCHEMA)
    plan = derive_onboarding_plan(profiles)
    matrix = data.get("connector_source_matrix", pd.DataFrame())
    matrix_lookup = {}
    if not matrix.empty and "programme_name" in matrix.columns:
        matrix_copy = normalize_columns(matrix)
        for _, row in matrix_copy.iterrows():
            matrix_lookup[normalize_text(row.get("programme_name", "")).lower()] = row

    rows = []
    for _, row in plan.iterrows():
        programme = normalize_text(row.get("program_name", ""))
        key = programme.lower()
        intelligence = matrix_lookup.get(key)
        source_url = clean_url(row.get("current_source_url") or row.get("method_source_url") or row.get("official_website"))
        category = normalize_text(row.get("onboarding_category", ""))
        status = "planned"
        run_mode = "source verification first"
        output_types = "source verification"
        capabilities = "source classification"
        implementation_note = normalize_text(row.get("notes", ""))
        if programme in SUPPORTED_EXTRACTORS:
            status = "operational / partial"
            run_mode = "source-specific extraction"
            output_types = "candidate MethodUnits; supporting links; extraction errors"
            capabilities = "HTML/source-page fetch; link/table classification; evidence URL capture"
        elif any(name.lower() in key for name in ["artisan c-sink", "artisan c sink"]):
            status = "operational / source resolution"
            run_mode = "source resolution"
            output_types = "source-resolution result; document-family candidate; supporting links"
            capabilities = "no-index source classification; document-family capture"
        elif category == "Ready for extraction":
            status = "ready for connector design"
        elif category in {"Needs URL repair", "Needs manual investigation"}:
            status = "verification needed"
        elif "browser" in category.lower():
            status = "future optional JS connector"
            run_mode = "future browser/API investigation"
        elif "document" in category.lower():
            status = "document-family connector candidate"

        if intelligence is not None:
            source_url = clean_url(
                intelligence.get("methodology_source_url")
                or intelligence.get("registry_url")
                or intelligence.get("document_library_url")
                or source_url
            )
            capabilities = normalize_text(intelligence.get("fields_available") or intelligence.get("fields_visible") or capabilities)
            implementation_note = normalize_text(intelligence.get("next_action") or implementation_note)
            output_types = normalize_text(intelligence.get("expected_records") or intelligence.get("records_expected") or output_types)

        rows.append(
            {
                "programme_name": programme,
                "connector_id": connector_id(programme),
                "source_archetype": normalize_text(row.get("connector_type") or row.get("source_type")),
                "connector_status": status,
                "run_mode": run_mode,
                "output_types": output_types,
                "capabilities": capabilities,
                "source_url": source_url,
                "next_action": normalize_text(row.get("recommended_next_action", "")),
                "implementation_note": implementation_note,
            }
        )
    return pd.DataFrame(rows, columns=CONNECTOR_MANIFEST_SCHEMA)


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
        f"source_documents_{timestamp}.csv": current_source_documents(),
        f"extraction_errors_{timestamp}.csv": current_extraction_errors(),
        f"source_resolution_results_{timestamp}.csv": current_source_resolution_results(),
        f"source_verification_results_{timestamp}.csv": current_source_verification_results(),
        f"review_decisions_{timestamp}.csv": current_review_decisions(),
        f"connector_manifest_{timestamp}.csv": build_connector_manifest(data),
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
        extract_climate_forward_candidates,
    )

    extractor_map = {
        "Climate Action Reserve": extract_climate_action_reserve_candidates,
        "International Carbon Registry / ICR": extract_icr_candidates,
        "Asia Carbon Institute": extract_asia_carbon_institute_candidates,
        "City Forest Credits": extract_cfc_candidates,
        "Climate Forward": extract_climate_forward_candidates,
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
        "cf_records_found": 0,
        "cf_detail_pages_fetched": 0,
        "cf_detail_pages_failed": 0,
        "cf_pdf_links_attached": 0,
        "cf_supporting_documents": 0,
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
