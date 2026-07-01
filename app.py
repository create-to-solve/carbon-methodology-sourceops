import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

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


APP_TITLE = "Carbon Methodology SourceOps Workbench"
DATA_DIR = Path(__file__).parent / "data"
SOURCE_CHECK_MAX_PROGRAMMES = 10
SOURCE_CHECK_TIMEOUT_SECONDS = 20
POLITE_USER_AGENT = (
    "CarbonMethodologySourceOpsWorkbench/0.1 "
    "(local prototype; source reachability check; no bulk scraping)"
)
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
RECOMMENDED_SOURCE_CHECK_PRESETS = [
    "Climate Action Reserve",
    "International Carbon Registry (ICR)",
    "Asia Carbon Institute",
    "City Forest Credits",
    "Clean Development Mechanism (CDM)",
    "American Carbon Registry (ACR)",
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
]
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

FILES = {
    "source_profiles": "source_profiles_final_fixed.csv",
    "connector_strategy": "connector_strategy_fixed.csv",
    "extraction_waves": "extraction_waves_fixed.csv",
    "qa_flags": "qa_flags_fixed.csv",
    "next_actions": "next_actions_fixed.csv",
}

PAGE_SUMMARIES = {
    "home": "A board-level view of source coverage, automation readiness, and review risk across programmes.",
    "coverage": "Use this page to understand which programmes already have rows, where source status is unresolved, and how confident the source profile is.",
    "profiles": "Searchable source intelligence for each programme: official source locations, connector type, extraction strategy, confidence, and notes.",
    "connectors": "Connector archetypes grouped by source pattern, with reusability and maintenance implications.",
    "waves": "A pragmatic ingestion roadmap: automate stable catalogues first, then handle semi-automated, manual, and unresolved sources.",
    "qa": "Open source-quality concerns that should be resolved before or during ingestion.",
    "actions": "The operating queue for what to do next by programme, priority, wave, and confidence.",
    "live_check": "Small-batch reachability and link-discovery checks for selected methodology source pages.",
    "candidate_extraction": "Controlled extraction of candidate MethodUnits from the first supported public source pages.",
    "about": "Definitions and rationale behind the SourceOps layer.",
}

HELP_TEXT = {
    "currently_has_methodology_rows": "Whether this programme already has methodology rows in the current catalogue inventory.",
    "populated_source_status": "Whether the current source profile is populated, unresolved, or needs clarification.",
    "automation_priority": "How attractive this programme is for near-term automation.",
    "confidence": "Confidence in the source profile and extraction plan, not a judgment on the programme itself.",
    "human_review_required": "Whether a human should verify the source profile or ingestion outcome.",
    "extraction_wave": "Suggested onboarding wave for extraction and catalogue ingestion.",
}


st.set_page_config(page_title=APP_TITLE, layout="wide")


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
        "connector_type": "Connector Type",
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
        "reusable_connector": "Reusable Connector",
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
    }
    return labels.get(column, column.replace("_", " ").title())


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
            config[column] = st.column_config.LinkColumn(pretty_label(column), display_text=None)
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


def apply_sidebar_filters(
    df: pd.DataFrame,
    filter_columns: list[str],
    key_prefix: str,
) -> pd.DataFrame:
    filtered = df.copy()
    with st.sidebar:
        st.markdown("### Filters")
        st.caption("Filters apply to the current page only.")
        for column in filter_columns:
            if column not in filtered.columns:
                continue
            options = sorted([value for value in filtered[column].dropna().unique() if str(value).strip()])
            if not options:
                continue
            selected = st.multiselect(
                pretty_label(column),
                options,
                key=f"{key_prefix}_{column}",
                help=HELP_TEXT.get(column),
            )
            if selected:
                filtered = filtered[filtered[column].isin(selected)]
    return filtered


def add_profile_context(df: pd.DataFrame, profiles: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty or profiles.empty or "program_name" not in df.columns or "program_name" not in profiles.columns:
        return df.copy()
    wanted = ["program_name"] + [column for column in columns if column in profiles.columns]
    context = profiles[wanted].drop_duplicates(subset=["program_name"])
    merged = df.merge(context, on="program_name", how="left", suffixes=("", "_profile"))
    return merged.fillna("")


def metric_row(metrics: list[tuple[str, str | int | float]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)


def show_bar_chart(df: pd.DataFrame, x: str, y: str, empty_message: str) -> None:
    if df.empty or x not in df.columns or y not in df.columns or df[y].sum() == 0:
        st.info(empty_message)
        return
    st.bar_chart(df, x=x, y=y)


def sidebar_data_status(data: dict[str, pd.DataFrame]) -> None:
    with st.sidebar.expander("Data status", expanded=False):
        for key, file_name in FILES.items():
            row_count = len(data.get(key, pd.DataFrame()))
            st.write(f"{file_name}: {row_count} rows")


def clean_url(value: str) -> str:
    url = str(value or "").strip()
    if url.startswith("www."):
        url = f"https://{url}"
    return url


def is_fetchable_url(url: str) -> bool:
    parsed = urlparse(clean_url(url))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_document_response(content_type: str, final_url: str) -> bool:
    content_type_l = str(content_type or "").lower()
    final_url_l = str(final_url or "").lower()
    document_extensions = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")
    document_types = (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats",
        "application/octet-stream",
    )
    return any(item in content_type_l for item in document_types) or final_url_l.endswith(document_extensions)


def link_is_likely_document(text: str, href: str) -> bool:
    candidate = f"{text} {href}".lower()
    return any(term in candidate for term in LIKELY_LINK_TERMS)


def parse_html_source(response, source_url: str) -> dict:
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    links = []
    pdf_links = 0
    seen_likely_urls = set()
    likely_links = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        text = anchor.get_text(" ", strip=True)
        absolute_url = urljoin(response.url or source_url, href)
        links.append(absolute_url)

        if ".pdf" in href.lower() or "pdf" in text.lower():
            pdf_links += 1

        if link_is_likely_document(text, href) and absolute_url not in seen_likely_urls and len(likely_links) < 20:
            seen_likely_urls.add(absolute_url)
            label = text if text else absolute_url
            likely_links.append(f"{label} -> {absolute_url}")

    likely_links = likely_links[:20]
    content_hash = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    return {
        "page_title": title,
        "total_links": len(links),
        "pdf_links": pdf_links,
        "likely_link_count": len(likely_links),
        "likely_links": "\n".join(likely_links),
        "content_hash": content_hash,
    }


def classify_source_check(status_code: int | None, content_type: str, final_url: str, likely_link_count: int, error: str) -> str:
    if error or status_code != 200:
        return "FAILED"
    if is_document_response(content_type, final_url):
        return "PDF_OR_DOCUMENT"
    if likely_link_count > 0:
        return "OK"
    return "REVIEW"


def run_source_check(row: pd.Series) -> dict:
    checked_at = datetime.now().isoformat(timespec="seconds")
    programme = str(row.get("program_name", ""))
    source_url = clean_url(row.get("source_check_url") or row.get("method_source_url") or row.get("official_website"))

    result = {
        "checked_at": checked_at,
        "program_name": programme,
        "source_url": source_url,
        "status_code": "",
        "final_url": "",
        "content_type": "",
        "response_size_bytes": "",
        "page_title": "",
        "total_links": 0,
        "pdf_links": 0,
        "likely_link_count": 0,
        "likely_links": "",
        "check_status": "FAILED",
        "content_hash": "",
        "error": "",
    }

    if requests is None or BeautifulSoup is None:
        result["error"] = "Missing dependency. Install requests and beautifulsoup4."
        return result

    if not is_fetchable_url(source_url):
        result["error"] = "Source URL is missing or is not an HTTP/HTTPS URL."
        return result

    try:
        response = requests.get(
            source_url,
            headers={"User-Agent": POLITE_USER_AGENT},
            allow_redirects=True,
            timeout=SOURCE_CHECK_TIMEOUT_SECONDS,
        )
        content_type = response.headers.get("content-type", "")
        result.update(
            {
                "status_code": response.status_code,
                "final_url": response.url,
                "content_type": content_type,
                "response_size_bytes": len(response.content or b""),
            }
        )

        if response.status_code == 200 and "html" in content_type.lower():
            result.update(parse_html_source(response, source_url))

        result["check_status"] = classify_source_check(
            response.status_code,
            content_type,
            response.url,
            int(result.get("likely_link_count") or 0),
            "",
        )
    except requests.RequestException as exc:
        result["error"] = str(exc)
        result["check_status"] = "FAILED"

    return result


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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


def fetch_public_source(url: str, program_name: str, allow_insecure_ssl: bool = False):
    if requests is None or BeautifulSoup is None:
        return None, make_extraction_error(
            program_name,
            url,
            "missing_dependency",
            "Missing dependency. Install requests and beautifulsoup4.",
            "Install dependencies from requirements.txt.",
        )
    if not is_fetchable_url(url):
        return None, make_extraction_error(
            program_name,
            url,
            "invalid_url",
            "Source URL is missing or is not an HTTP/HTTPS URL.",
            "Check the programme source profile.",
        )
    try:
        response = requests.get(
            url,
            headers={"User-Agent": POLITE_USER_AGENT},
            allow_redirects=True,
            timeout=SOURCE_CHECK_TIMEOUT_SECONDS,
            verify=not allow_insecure_ssl,
        )
    except requests.exceptions.SSLError as exc:
        message = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in message:
            message = (
                "SSL certificate verification failed. The source may have an expired or misconfigured "
                "certificate. Open manually in browser or retry later."
            )
        return None, make_extraction_error(
            program_name,
            url,
            "ssl_certificate_error",
            message,
            "Open manually in browser, retry later, or use insecure SSL only for analyst testing.",
        )
    except requests.RequestException as exc:
        return None, make_extraction_error(
            program_name,
            url,
            "request_failed",
            str(exc),
            "Check source reachability manually or retry later.",
        )
    if response.status_code != 200:
        return response, make_extraction_error(
            program_name,
            response.url or url,
            "non_200_status",
            f"Non-200 status: {response.status_code}",
            "Open manually in browser and confirm the source URL.",
        )
    if "html" not in response.headers.get("content-type", "").lower():
        return response, make_extraction_error(
            program_name,
            response.url or url,
            "non_html_source",
            "Source is reachable but is not an HTML catalogue page.",
            "Review the document manually; linked documents are not fetched by this prototype.",
        )
    return response, ""


def extract_code(text: str, preferred: str = "") -> str:
    patterns = []
    if preferred == "icr":
        patterns = [CODE_PATTERNS["icr"]]
    elif preferred == "aci":
        patterns = [CODE_PATTERNS["aci"], CODE_PATTERNS["cdm"]]
    else:
        patterns = [CODE_PATTERNS["icr"], CODE_PATTERNS["aci"], CODE_PATTERNS["cdm"]]
    for pattern in patterns:
        match = pattern.search(text or "")
        if match:
            return normalize_text(match.group(0)).replace(" ", "-").upper()
    return ""


def extract_version(text: str) -> str:
    match = re.search(r"\b(?:version|ver\.?|v)\s*[:#-]?\s*(\d+(?:\.\d+)*)\b", text or "", re.IGNORECASE)
    return f"v{match.group(1)}" if match else ""


def extract_status(text: str) -> str:
    status_terms = [
        "approved",
        "active",
        "valid",
        "draft",
        "consultation",
        "withdrawn",
        "retired",
        "inactive",
        "under development",
        "superseded",
    ]
    text_l = str(text or "").lower()
    for term in status_terms:
        if term in text_l:
            return term.title()
    return ""


def clean_candidate_name(text: str, code: str = "") -> str:
    name = normalize_text(text)
    if code:
        name = re.sub(re.escape(code), "", name, flags=re.IGNORECASE)
        name = re.sub(re.escape(code.replace("-", " ")), "", name, flags=re.IGNORECASE)
    name = re.sub(r"^(download|view|open|read|pdf|document)\b\s*[:|-]?", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*[-|]\s*$", "", name).strip(" :-")
    return normalize_text(name)


def useful_candidate_link(text: str, href: str, source_kind: str) -> bool:
    href = str(href or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return False
    text_l = normalize_text(text).lower()
    href_l = href.lower()
    combined = f"{text_l} {href_l}"
    if text_l in GENERIC_NAV_TERMS:
        return False
    has_code = bool(CODE_PATTERNS["icr"].search(combined) or CODE_PATTERNS["cdm"].search(combined) or CODE_PATTERNS["aci"].search(combined))
    has_source_term = any(term in combined for term in LIKELY_LINK_TERMS)
    if source_kind == "car":
        return ("protocol" in combined or "pdf" in combined) and (len(text_l) > 8 or has_code)
    if source_kind == "icr":
        return has_code or ("methodolog" in combined and len(text_l) > 8)
    if source_kind == "aci":
        return has_code or ("methodolog" in combined and len(text_l) > 8)
    return has_code or has_source_term


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
        has_protocol_context = extraction_method == "table_parse" or "protocol" in combined_l
        has_protocol_name = any(term in combined_l for term in CAR_METHODUNIT_TERMS)
        if has_protocol_context and has_protocol_name:
            return "methodunit_candidate", "Climate Action Reserve protocol listing/name pattern detected."

    if any(term in name.lower() for term in GENERIC_NAV_TERMS) or len(name) <= 3:
        return "navigation_link", "Generic navigation text."

    return "exclude", "No MethodUnit, supporting document, development, or navigation rule matched."


def apply_candidate_classification(candidates: list[dict], source_kind: str) -> list[dict]:
    classified = []
    seen_methodunit_keys = set()
    for candidate in candidates:
        candidate_type, reason = classify_candidate(candidate, source_kind)
        candidate["candidate_type"] = candidate_type
        candidate["classification_reason"] = reason

        if candidate_type == "methodunit_candidate":
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


def make_candidate(
    profile: dict,
    methodunit_code: str,
    methodunit_name: str,
    unit_type: str,
    sector: str,
    version: str,
    status: str,
    source_url: str,
    document_url: str,
    extraction_method: str,
    confidence: str,
    notes: str,
) -> dict:
    return {
        "program_id": str(profile.get("program_id", "")),
        "program_name": str(profile.get("program_name", "")),
        "methodunit_code": normalize_text(methodunit_code),
        "methodunit_name": normalize_text(methodunit_name),
        "unit_type": normalize_text(unit_type),
        "candidate_type": "",
        "classification_reason": "",
        "sector": normalize_text(sector),
        "version": normalize_text(version),
        "status": normalize_text(status),
        "source_url": clean_url(source_url),
        "document_url": clean_url(document_url),
        "extraction_method": extraction_method,
        "confidence": confidence,
        "review_status": "pending_review",
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "notes": normalize_text(notes),
    }


def candidate_from_text_and_link(
    profile: dict,
    text: str,
    href: str,
    source_url: str,
    source_kind: str,
    unit_type: str,
    extraction_method: str,
    notes: str,
) -> dict | None:
    combined = normalize_text(f"{text} {href}")
    preferred = "icr" if source_kind == "icr" else "aci" if source_kind == "aci" else ""
    code = extract_code(combined, preferred)
    name = clean_candidate_name(text, code)
    document_url = urljoin(source_url, href) if href else ""
    if not name and not code and not document_url:
        return None
    if not name and document_url:
        name = document_url
    status = extract_status(combined)
    version = extract_version(combined)
    if source_kind == "aci" and CODE_PATTERNS["cdm"].search(combined):
        unit_type = "adopted_external_method"
        notes = "Appears to be adopted from CDM."
    confidence = "high" if name and document_url and (code or source_kind == "car") else "medium"
    if source_kind == "icr" and code and name and status:
        confidence = "high"
    return make_candidate(
        profile,
        code,
        name,
        unit_type,
        "",
        version,
        status,
        source_url,
        document_url,
        extraction_method,
        confidence,
        notes,
    )


def extract_table_candidates(profile: dict, soup, source_url: str, source_kind: str, unit_type: str, notes: str) -> list[dict]:
    candidates = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [normalize_text(cell.get_text(" ", strip=True)).lower() for cell in rows[0].find_all(["th", "td"])]
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            cell_texts = [normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
            row_text = normalize_text(" ".join(cell_texts))
            if not row_text:
                continue
            row_link = ""
            for anchor in row.find_all("a", href=True):
                if should_capture_source_link(anchor.get_text(" ", strip=True), anchor.get("href"), source_kind):
                    row_link = urljoin(source_url, anchor.get("href"))
                    break

            code = extract_code(row_text, "icr" if source_kind == "icr" else "aci" if source_kind == "aci" else "")
            status = extract_status(row_text)
            version = extract_version(row_text)
            sector = ""
            title = ""
            for header, value in zip(headers, cell_texts):
                if not value:
                    continue
                if any(term in header for term in ["title", "name", "methodology", "protocol"]):
                    title = value
                elif "sector" in header or "category" in header:
                    sector = value
                elif "status" in header and not status:
                    status = value
                elif "version" in header and not version:
                    version = value
                elif "code" in header and not code:
                    code = extract_code(value) or value
            if not title:
                title = next((value for value in cell_texts if value and value != code and len(value) > 5), row_text)
            if source_kind == "aci" and CODE_PATTERNS["cdm"].search(row_text):
                candidate_unit_type = "adopted_external_method"
                candidate_notes = "Appears to be adopted from CDM."
            else:
                candidate_unit_type = unit_type
                candidate_notes = notes
            confidence = "high" if clean_candidate_name(title, code) and (row_link or code) else "medium"
            if source_kind == "icr" and code and title and status:
                confidence = "high"
            candidates.append(
                make_candidate(
                    profile,
                    code,
                    clean_candidate_name(title, code),
                    candidate_unit_type,
                    sector,
                    version,
                    status,
                    source_url,
                    row_link,
                    "table_parse",
                    confidence,
                    candidate_notes,
                )
            )
    return candidates


def extract_link_candidates(profile: dict, soup, source_url: str, source_kind: str, unit_type: str, notes: str) -> list[dict]:
    candidates = []
    for anchor in soup.find_all("a", href=True):
        text = normalize_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href")
        if not should_capture_source_link(text, href, source_kind):
            continue
        candidate = candidate_from_text_and_link(
            profile,
            text,
            href,
            source_url,
            source_kind,
            unit_type,
            "link_parse",
            notes,
        )
        if candidate:
            candidates.append(candidate)
    return candidates


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


def extract_climate_action_reserve_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], dict | str]:
    profile = get_program_profile(profiles, ["Climate Action Reserve"])
    source_url = profile_source_url(profile)
    response, error = fetch_public_source(source_url, "Climate Action Reserve", allow_insecure_ssl)
    if error:
        return [], error
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = extract_table_candidates(
        profile,
        soup,
        response.url,
        "car",
        "protocol",
        "Candidate protocol from Climate Action Reserve public protocols page.",
    )
    candidates.extend(
        extract_link_candidates(
            profile,
            soup,
            response.url,
            "car",
            "protocol",
            "Candidate protocol from Climate Action Reserve public protocols page.",
        )
    )
    return apply_candidate_classification(candidates, "car"), ""


def extract_icr_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], dict | str]:
    profile = get_program_profile(profiles, ["International Carbon Registry (ICR)", "International Carbon Registry"])
    source_url = profile_source_url(profile)
    response, error = fetch_public_source(source_url, "International Carbon Registry / ICR", allow_insecure_ssl)
    if error:
        return [], error
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = extract_table_candidates(
        profile,
        soup,
        response.url,
        "icr",
        "methodology",
        "Candidate methodology from ICR public methodology page.",
    )
    candidates.extend(
        extract_link_candidates(
            profile,
            soup,
            response.url,
            "icr",
            "methodology",
            "Candidate methodology from ICR public methodology page.",
        )
    )
    return apply_candidate_classification(candidates, "icr"), ""


def extract_asia_carbon_institute_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], dict | str]:
    profile = get_program_profile(profiles, ["Asia Carbon Institute"])
    source_url = profile_source_url(profile)
    response, error = fetch_public_source(source_url, "Asia Carbon Institute", allow_insecure_ssl)
    if error:
        return [], error
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = extract_table_candidates(
        profile,
        soup,
        response.url,
        "aci",
        "methodology",
        "Appears to be ACI-native unless the code indicates an adopted CDM method.",
    )
    candidates.extend(
        extract_link_candidates(
            profile,
            soup,
            response.url,
            "aci",
            "methodology",
            "Appears to be ACI-native unless the code indicates an adopted CDM method.",
        )
    )
    return apply_candidate_classification(candidates, "aci"), ""


def run_candidate_extractors(
    selected_extractors: list[str],
    profiles: pd.DataFrame,
    allow_insecure_ssl: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    extractor_map = {
        "Climate Action Reserve": extract_climate_action_reserve_candidates,
        "International Carbon Registry / ICR": extract_icr_candidates,
        "Asia Carbon Institute": extract_asia_carbon_institute_candidates,
    }
    all_candidates = []
    errors = []
    for extractor_name in selected_extractors:
        extractor = extractor_map.get(extractor_name)
        if extractor is None:
            continue
        candidates, error = extractor(profiles, allow_insecure_ssl)
        all_candidates.extend(candidates)
        if error:
            errors.append(error)
    return (
        pd.DataFrame([{column: candidate.get(column, "") for column in CANDIDATE_SCHEMA} for candidate in all_candidates], columns=CANDIDATE_SCHEMA),
        pd.DataFrame([{column: error.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for error in errors], columns=EXTRACTION_ERROR_SCHEMA),
    )


def home_page(data: dict[str, pd.DataFrame]) -> None:
    profiles = data["source_profiles"]

    st.header("Home / Executive Summary")
    page_summary(PAGE_SUMMARIES["home"])
    if not require_rows(profiles, "source profiles"):
        return
    st.write(
        "This workbench is not another methodology database. It is the source-intelligence "
        "and ingestion-planning layer behind a methodology database."
    )
    st.write(
        "The existing methodology catalogue answers: What methodologies do we currently have? "
        "This SourceOps workbench answers: Where does methodology information come from, "
        "how should it be extracted, how confident are we, and what needs review?"
    )

    total_programmes = len(profiles)
    populated = count_value(profiles, "currently_has_methodology_rows", "Yes")
    unpopulated = count_value(profiles, "currently_has_methodology_rows", "No")
    total_rows = int(numeric_series(profiles, "current_methodology_row_count").sum())
    high_priority = count_contains(profiles, "automation_priority", "High")
    low_confidence = count_contains(profiles, "confidence", "Low")
    manual_review = count_value(profiles, "human_review_required", "Yes")

    metric_row(
        [
            ("Total programmes", total_programmes),
            ("Populated programmes", populated),
            ("Unresolved / unpopulated", unpopulated),
            ("Current methodology rows", total_rows),
        ]
    )
    metric_row(
        [
            ("High-priority automation candidates", high_priority),
            ("Low-confidence cases", low_confidence),
            ("Manual-review cases", manual_review),
        ]
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Connector Mix")
        section_note("Shows the dominant source patterns the ingestion layer must handle.")
        chart = value_counts_df(profiles, "connector_type", "connector_type")
        show_bar_chart(chart, "connector_type", "count", "Connector distribution is unavailable.")
    with right:
        st.subheader("Extraction Roadmap")
        section_note("Shows how programmes are staged for automation, semi-automation, manual onboarding, or monitoring.")
        chart = value_counts_df(profiles, "extraction_wave", "extraction_wave")
        show_bar_chart(chart, "extraction_wave", "count", "Extraction wave distribution is unavailable.")

    st.subheader("Review Focus")
    section_note("Programmes that need human review or have low-confidence source intelligence.")
    focus = profiles[
        profiles.get("human_review_required", pd.Series("", index=profiles.index)).astype(str).str.lower().eq("yes")
        | profiles.get("confidence", pd.Series("", index=profiles.index)).astype(str).str.contains("low", case=False)
    ]
    show_dataframe(
        select_existing(
            focus,
            [
                "program_name",
                "connector_type",
                "automation_priority",
                "confidence",
                "human_review_required",
                "extraction_wave",
                "notes",
            ],
        ),
        "executive_summary_review_cases",
        height=280,
    )


def coverage_dashboard(data: dict[str, pd.DataFrame]) -> None:
    profiles = data["source_profiles"]
    st.header("Coverage Dashboard")
    page_summary(PAGE_SUMMARIES["coverage"])
    if not require_rows(profiles, "source profiles"):
        return

    total_rows = int(numeric_series(profiles, "current_methodology_row_count").sum())
    metric_row(
        [
            ("Programme rows", len(profiles)),
            ("Has methodology rows", count_value(profiles, "currently_has_methodology_rows", "Yes")),
            ("No methodology rows", count_value(profiles, "currently_has_methodology_rows", "No")),
            ("Total methodology rows", total_rows),
        ]
    )

    st.subheader("Coverage Counts")
    section_note("Compact counts for source status, confidence, automation priority, and human-review need.")
    cols = st.columns(4)
    for chart_col, source_col in zip(
        cols,
        ["populated_source_status", "confidence", "automation_priority", "human_review_required"],
    ):
        with chart_col:
            st.caption(pretty_label(source_col))
            st.dataframe(value_counts_df(profiles, source_col), hide_index=True, use_container_width=True)

    st.subheader("Charts")
    section_note("Use these charts to spot where ingestion patterns, priority, and confidence are concentrated.")
    top_programmes = profiles.copy()
    if "current_methodology_row_count" in top_programmes.columns:
        top_programmes["methodology_rows"] = numeric_series(top_programmes, "current_methodology_row_count")
        top_programmes = top_programmes.sort_values("methodology_rows", ascending=False).head(15)

    chart_specs = [
        ("Programmes by Connector Type", "connector_type"),
        ("Programmes by Automation Priority", "automation_priority"),
        ("Programmes by Confidence", "confidence"),
    ]
    for idx in range(0, len(chart_specs), 2):
        left, right = st.columns(2)
        for container, (title, column) in zip([left, right], chart_specs[idx : idx + 2]):
            with container:
                st.caption(title)
                chart = value_counts_df(profiles, column, column)
                show_bar_chart(chart, column, "count", f"{title} is unavailable.")

    st.caption("Top Programmes by Methodology Row Count")
    if "program_name" in top_programmes.columns and "methodology_rows" in top_programmes.columns:
        show_bar_chart(
            top_programmes[["program_name", "methodology_rows"]],
            "program_name",
            "methodology_rows",
            "No methodology row counts are available.",
        )
    else:
        st.info("No programme name or methodology row count column is available.")


def source_profiles_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Source Profiles")
    page_summary(PAGE_SUMMARIES["profiles"])
    if not require_rows(data["source_profiles"], "source profiles"):
        return
    profiles = apply_sidebar_filters(
        data["source_profiles"],
        [
            "currently_has_methodology_rows",
            "connector_type",
            "automation_priority",
            "confidence",
            "populated_source_status",
            "human_review_required",
            "extraction_wave",
        ],
        "profiles",
    )
    display_columns = [
        "program_name",
        "current_methodology_row_count",
        "official_organization",
        "official_website",
        "registry_url",
        "method_source_url",
        "terminology_used",
        "source_type",
        "connector_type",
        "extraction_strategy",
        "automation_priority",
        "maintenance_burden",
        "refresh_frequency",
        "confidence",
        "evidence_urls",
        "notes",
    ]
    st.subheader("Programme Source Profiles")
    section_note(f"{len(profiles)} programme rows after filters. URLs are rendered as links where Streamlit can identify them.")
    show_dataframe(select_existing(profiles, display_columns), "source_profiles")


def connector_strategy_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Connector Strategy")
    page_summary(PAGE_SUMMARIES["connectors"])
    if not require_rows(data["connector_strategy"], "connector strategy"):
        return
    strategy = data["connector_strategy"].copy()
    if "standards" not in strategy.columns and "program_name" in strategy.columns:
        strategy["standards"] = strategy["program_name"]

    display_columns = [
        "connector_type",
        "standards",
        "extraction_method",
        "reusable_connector",
        "maintenance_burden",
        "priority",
    ]
    st.subheader("Connector Archetypes")
    section_note("Each row describes a source pattern and the standards currently assigned to that pattern.")
    show_dataframe(select_existing(strategy, display_columns), "connector_strategy", height=360)

    st.subheader("Programmes per Connector Type")
    profiles = data["source_profiles"]
    chart = value_counts_df(profiles, "connector_type", "connector_type")
    show_bar_chart(chart, "connector_type", "count", "Connector counts are unavailable.")


def extraction_waves_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Extraction Waves")
    page_summary(PAGE_SUMMARIES["waves"])
    if not require_rows(data["extraction_waves"], "extraction waves"):
        return
    waves = add_profile_context(
        data["extraction_waves"],
        data["source_profiles"],
        ["connector_type", "automation_priority", "confidence", "extraction_strategy"],
    )
    if "recommended_action" not in waves.columns and "extraction_strategy" in waves.columns:
        waves["recommended_action"] = waves["extraction_strategy"]
    waves = apply_sidebar_filters(
        waves,
        ["extraction_wave", "connector_type", "automation_priority", "confidence"],
        "waves",
    )

    st.subheader("Wave Distribution")
    section_note("Counts reflect the filtered set. Clear filters to return to the full roadmap.")
    chart = value_counts_df(waves, "extraction_wave", "extraction_wave")
    show_bar_chart(chart, "extraction_wave", "count", "No extraction wave data matches the current filters.")

    st.subheader("Wave Details")
    section_note("Wave tables are enriched at runtime with connector, priority, confidence, and extraction strategy from source profiles.")
    wave_definitions = [
        ("Wave 1: automate now", ["Wave 1: automate now"]),
        ("Wave 2: semi-automate", ["Wave 2: semi-automate"]),
        ("Wave 3: metadata-first manual onboarding", ["Wave 3: metadata-first manual onboarding", "Wave 3: manual onboarding"]),
        ("Wave 4: unresolved / monitor", ["Wave 4: unresolved / monitor", "Wave 4: unresolved/monitor"]),
    ]
    matched_labels = set()
    for display_name, source_labels in wave_definitions:
        if "extraction_wave" not in waves.columns:
            continue
        matched_labels.update(source_labels)
        subset = waves[waves["extraction_wave"].astype(str).isin(source_labels)]
        with st.expander(f"{display_name} ({len(subset)} programmes)", expanded=display_name.startswith("Wave 1")):
            show_dataframe(
                select_existing(
                    subset,
                    [
                        "program_name",
                        "recommended_action",
                        "connector_type",
                        "automation_priority",
                        "confidence",
                        "extraction_strategy",
                    ],
                ),
                f"extraction_{display_name.lower().replace(':', '').replace(' ', '_').replace('/', '_')}",
                height=220,
            )

    remaining = waves[
        ~waves.get("extraction_wave", pd.Series("", index=waves.index)).astype(str).isin(matched_labels)
    ]
    if not remaining.empty:
        with st.expander(f"Other / changed wave labels ({len(remaining)} programmes)"):
            show_dataframe(remaining, "extraction_other_waves", height=220)


def qa_flags_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("QA Flags")
    page_summary(PAGE_SUMMARIES["qa"])
    if not require_rows(data["qa_flags"], "QA flags"):
        return
    qa = add_profile_context(
        data["qa_flags"],
        data["source_profiles"],
        ["connector_type", "automation_priority", "confidence", "human_review_required", "evidence_urls"],
    )
    if "issue_type" not in qa.columns and "issue" in qa.columns:
        qa["issue_type"] = qa["issue"].str.extract(
            r"(duplicate|variant|ambiguous|external|malformed|incomplete|low-confidence|methodology)",
            expand=False,
            flags=2,
        ).fillna("review").str.lower()
    if "affected_programme" not in qa.columns and "program_name" in qa.columns:
        qa["affected_programme"] = qa["program_name"]
    if "description" not in qa.columns and "issue" in qa.columns:
        qa["description"] = qa["issue"]
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
        ).fillna("Review")
    if "recommended_resolution" not in qa.columns:
        qa["recommended_resolution"] = ""
    if "status" not in qa.columns:
        qa["status"] = ""

    st.subheader("Highlighted Issue Classes")
    section_note("These counts are keyword-based highlights for presentation and triage. The source issue text remains unchanged.")
    highlight_terms = {
        "Duplicate or variant names": "duplicate|variant",
        "Ambiguous standards": "ambiguous",
        "Adopted external methods": "external|accepted external|adopted",
        "Malformed or incomplete evidence URLs": "malformed|incomplete|url|source",
        "Low-confidence sources": "low-confidence|low confidence|manual investigation",
    }
    cols = st.columns(len(highlight_terms))
    for column, (label, pattern) in zip(cols, highlight_terms.items()):
        issue_text = qa.get("issue", pd.Series("", index=qa.index)).astype(str)
        column.metric(label, int(issue_text.str.contains(pattern, case=False, regex=True).sum()))

    filtered = apply_sidebar_filters(qa, ["severity", "issue_type", "confidence", "human_review_required"], "qa")
    st.subheader("QA Issue Queue")
    section_note(f"{len(filtered)} QA rows after filters.")
    display_columns = [
        "issue_type",
        "affected_programme",
        "severity",
        "description",
        "recommended_resolution",
        "status",
        "confidence",
        "human_review_required",
        "evidence_urls",
    ]
    show_dataframe(select_existing(filtered, display_columns), "qa_flags")


def next_actions_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Next Actions")
    page_summary(PAGE_SUMMARIES["actions"])
    if not require_rows(data["next_actions"], "next actions"):
        return
    actions = add_profile_context(
        data["next_actions"],
        data["source_profiles"],
        ["extraction_wave", "automation_priority", "confidence", "connector_type"],
    )
    if "priority" not in actions.columns and "automation_priority" in actions.columns:
        actions["priority"] = actions["automation_priority"]
    if "action_type" not in actions.columns and "next_action" in actions.columns:
        actions["action_type"] = actions["next_action"].str.extract(
            r"^(Develop|Build|Manually curate|Map|Monitor|Resolve|Create|Extract)",
            expand=False,
        ).fillna("Review")
    if "programme" not in actions.columns and "program_name" in actions.columns:
        actions["programme"] = actions["program_name"]
    if "wave" not in actions.columns and "extraction_wave" in actions.columns:
        actions["wave"] = actions["extraction_wave"]

    filtered = apply_sidebar_filters(actions, ["priority", "action_type", "programme", "wave", "confidence"], "actions")
    display_columns = [
        "priority",
        "action_type",
        "programme",
        "wave",
        "confidence",
        "connector_type",
        "next_action",
    ]
    st.subheader("Action Queue")
    section_note("What should we do next for each programme? Priority and wave are enriched from source profiles when not present in the action file.")
    show_dataframe(select_existing(filtered, display_columns), "next_actions")


def live_source_check_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Live Source Check")
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
    selected_connectors = st.multiselect("Connector Type", connector_options, help="Optional filter before selecting programmes.")
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
    st.header("Candidate Extraction")
    page_summary(PAGE_SUMMARIES["candidate_extraction"])
    if not require_rows(data["source_profiles"], "source profiles"):
        return

    st.write(
        "This page extracts candidate MethodUnits from selected public source pages. "
        "The outputs are not automatically approved; they enter a human review queue."
    )
    st.caption(
        "Supported in this prototype: Climate Action Reserve, International Carbon Registry / ICR, "
        "and Asia Carbon Institute. The extractors fetch only the selected public listing pages and "
        "collect candidate links or table rows; linked PDFs are not fetched."
    )

    if requests is None or BeautifulSoup is None:
        st.error("Candidate extraction requires `requests` and `beautifulsoup4`. Install dependencies from requirements.txt.")
        return

    selected_extractors = st.multiselect(
        "Supported extractors",
        SUPPORTED_EXTRACTORS,
        default=SUPPORTED_EXTRACTORS,
        help="Only these first three public-source extractors are enabled.",
    )
    allow_insecure_ssl = st.checkbox(
        "Allow insecure SSL for analyst testing",
        value=False,
        help="Use only for a selected manual run when a public source has a certificate verification issue.",
    )
    if allow_insecure_ssl:
        st.warning("Insecure SSL verification disabled for analyst testing. Do not use this for production ingestion.")
    run_extraction = st.button("Run candidate extraction", type="primary", disabled=not selected_extractors)

    if run_extraction:
        with st.spinner("Extracting candidate MethodUnits from selected public source pages..."):
            candidates_df, errors_df = run_candidate_extractors(
                selected_extractors,
                data["source_profiles"],
                allow_insecure_ssl=allow_insecure_ssl,
            )
        st.session_state["candidate_extraction_results"] = candidates_df
        st.session_state["candidate_extraction_errors"] = errors_df
        st.session_state["candidate_extraction_sources_attempted"] = len(selected_extractors)

    candidates = st.session_state.get("candidate_extraction_results", pd.DataFrame(columns=CANDIDATE_SCHEMA))
    errors = st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    sources_attempted = st.session_state.get("candidate_extraction_sources_attempted", 0)

    methodunit_count = count_value(candidates, "candidate_type", "methodunit_candidate")
    supporting_count = count_value(candidates, "candidate_type", "supporting_document")
    development_count = count_value(candidates, "candidate_type", "development_page")
    navigation_count = count_value(candidates, "candidate_type", "navigation_link")
    excluded_count = count_value(candidates, "candidate_type", "exclude")
    pending_review = count_value(candidates, "review_status", "pending_review")
    metric_row(
        [
            ("Sources attempted", sources_attempted),
            ("Total extracted rows", len(candidates)),
            ("MethodUnit candidates", methodunit_count),
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
        f"{len(filtered)} rows shown after filters. The default view shows MethodUnit candidates only; include other types to audit supporting links."
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
            "Download MethodUnit review CSV",
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


def about_page() -> None:
    st.header("About / Methodology")
    page_summary(PAGE_SUMMARIES["about"])
    st.subheader("What is a MethodUnit?")
    st.write(
        "A MethodUnit is the catalogue-friendly record for a method-like source object: a methodology, "
        "protocol, module, guideline, adopted external method, or standard-specific rule set that can "
        "drive crediting, validation, eligibility, or project documentation."
    )

    st.subheader("Why not everything is called a methodology")
    st.write(
        "Carbon programmes use different terms. Some publish methodologies, some publish protocols, "
        "some rely on modules, and some expose only standards, procedures, or external methods adopted "
        "from another programme. Treating these as MethodUnits keeps the catalogue consistent without "
        "flattening important source differences."
    )

    st.subheader("Why connector types differ")
    st.write(
        "Sources appear as static HTML catalogues, dynamic web apps, PDF-first document libraries, "
        "registry-derived references, adopted-external pointers, and manual small-standard profiles. "
        "Those patterns need different ingestion and QA approaches."
    )

    st.subheader("Why one scraper will not work")
    st.write(
        "A single scraper would miss dynamic filters, document-only standards, adopted external methods, "
        "login boundaries, registry-only references, and unresolved naming issues. The workbench separates "
        "source intelligence from extraction so each programme can use the right connector strategy."
    )

    st.subheader("How this feeds the methodology catalogue")
    st.write(
        "The output of this layer can become an ingestion plan for the catalogue: which programmes to "
        "automate first, which MethodUnits need manual onboarding, which evidence should be verified, "
        "and which programme names or aliases should be resolved before ingestion."
    )


def main() -> None:
    data = load_data()
    st.title(APP_TITLE)

    st.sidebar.title("Navigation")
    sidebar_data_status(data)
    page = st.sidebar.radio(
        "Pages",
        [
            "Home / Executive Summary",
            "Coverage Dashboard",
            "Source Profiles",
            "Connector Strategy",
            "Extraction Waves",
            "QA Flags",
            "Next Actions",
            "Live Source Check",
            "Candidate Extraction",
            "About / Methodology",
        ],
    )

    if page == "Home / Executive Summary":
        home_page(data)
    elif page == "Coverage Dashboard":
        coverage_dashboard(data)
    elif page == "Source Profiles":
        source_profiles_page(data)
    elif page == "Connector Strategy":
        connector_strategy_page(data)
    elif page == "Extraction Waves":
        extraction_waves_page(data)
    elif page == "QA Flags":
        qa_flags_page(data)
    elif page == "Next Actions":
        next_actions_page(data)
    elif page == "Live Source Check":
        live_source_check_page(data)
    elif page == "Candidate Extraction":
        candidate_extraction_page(data)
    elif page == "About / Methodology":
        about_page()


if __name__ == "__main__":
    main()
