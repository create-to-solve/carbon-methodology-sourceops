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
OUTPUTS_DIR = Path(__file__).parent / "outputs"
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
ARTISAN_C_SINK_FALLBACK_SOURCE_URL = "https://www.carbon-standards.com/en/standards/service-505~global-artisan-c-sink.html"
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
CFC_METHODUNIT_TERMS = (
    "city forest credits standard",
    "preservation protocol",
    "afforestation",
    "reforestation",
    "afforestation/reforestation",
    "carbon protocol",
    "protocol",
    "standard",
)
ICR_GENERIC_TITLE_LABELS = {
    "and public",
    "approved icr methodologies",
    "approved methodologies",
    "current stage",
    "date of first approval",
    "icr methodologies",
    "methodology development",
    "next",
    "previous",
    "sectoral scope",
    "under development",
}
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
    "connectors": "Extraction archetypes grouped by source pattern, with reusability and maintenance implications.",
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


def looks_like_url(text: str) -> bool:
    value = normalize_text(text).lower()
    if value.startswith(("http://", "https://", "www.")):
        return True
    return " " not in value and any(marker in value for marker in ["/", "?", "#", "=", "."]) and bool(re.fullmatch(r"[/#?=&.\w:-]+", value))


def clean_icr_methodology_title(text: str, code: str = "") -> str:
    title = clean_candidate_name(text, code)
    title = re.sub(r"\b(approved methodologies|approved icr methodologies|under development|icr methodologies|methodology development)\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(previous|next|international carbon registry|documentation|icr program)\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(approved|active|valid|draft|consultation|under development)\b", "", title, flags=re.IGNORECASE)
    title = normalize_text(title.strip(" :-|"))
    if not is_plausible_icr_methodology_title(title):
        return ""
    return title


def is_plausible_icr_methodology_title(title: str) -> bool:
    value = normalize_text(title)
    value_l = value.lower().strip(" :-|")
    if not value or looks_like_url(value):
        return False
    if value_l in ICR_GENERIC_TITLE_LABELS or value_l in GENERIC_NAV_TERMS:
        return False
    if any(value_l == term or value_l.startswith(f"{term}:") for term in ICR_GENERIC_TITLE_LABELS):
        return False
    if value_l.startswith(("and ", "or ")):
        return False
    if extract_status(value) or extract_version(value):
        return False
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", value_l):
        return False
    alpha_words = re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", value)
    if len(value) < 12 or len(alpha_words) < 2:
        return False
    return True


def icr_code_pattern(code: str):
    return re.compile(re.escape(code).replace(r"\ ", r"\s*").replace(r"\-", r"[-\s]?"), re.IGNORECASE)


def icr_title_from_code_block(text: str, code: str) -> tuple[str, bool]:
    code_pattern = icr_code_pattern(code)
    if not code_pattern.search(text or ""):
        return "", False
    title = clean_icr_methodology_title(text, code)
    if title:
        return title, False
    return "", True


def is_pdf_or_document_url(url: str) -> bool:
    parsed_path = urlparse(clean_url(url)).path.lower()
    return parsed_path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"))


def title_from_icr_detail_page(response_text: str, code: str) -> tuple[str, str, int]:
    soup = BeautifulSoup(response_text, "html.parser")
    code_pattern = icr_code_pattern(code)
    suspicious_rejections = 0

    h1 = soup.find("h1")
    if h1:
        title, rejected = icr_title_from_code_block(h1.get_text(" ", strip=True), code)
        suspicious_rejections += int(rejected)
        if title:
            return title, "detail page h1", suspicious_rejections

    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title, rejected = icr_title_from_code_block(page_title, code)
    suspicious_rejections += int(rejected)
    if title:
        return title, "detail page title", suspicious_rejections

    for heading in soup.find_all(["h2", "h3"]):
        heading_text = normalize_text(heading.get_text(" ", strip=True))
        sibling_text = ""
        for sibling in heading.find_next_siblings(limit=3):
            sibling_text = normalize_text(f"{sibling_text} {sibling.get_text(' ', strip=True)}")
        context = normalize_text(f"{heading_text} {sibling_text}")
        if code_pattern.search(context):
            title, rejected = icr_title_from_code_block(context, code)
            suspicious_rejections += int(rejected)
            if title:
                return title, "detail page heading near code", suspicious_rejections

    visible_lines = [
        normalize_text(line)
        for line in soup.get_text("\n", strip=True).splitlines()
        if normalize_text(line)
    ]
    for line in visible_lines:
        if code_pattern.search(line):
            title, rejected = icr_title_from_code_block(line, code)
            suspicious_rejections += int(rejected)
            if title:
                return title, "detail page text line containing code", suspicious_rejections

    return "", "", suspicious_rejections


def fetch_icr_detail_title(document_url: str, code: str, allow_insecure_ssl: bool) -> tuple[str, str, dict | None, bool, int]:
    url = clean_url(document_url)
    if not is_fetchable_url(url):
        return "", "", make_extraction_error(
            "International Carbon Registry / ICR",
            url,
            "invalid_detail_url",
            "ICR detail URL is missing or is not an HTTP/HTTPS URL.",
            "Review the index-page candidate manually.",
        ), False, 0
    if is_pdf_or_document_url(url):
        return "", "", None, False, 0
    try:
        response = requests.get(
            url,
            headers={"User-Agent": POLITE_USER_AGENT},
            allow_redirects=True,
            timeout=SOURCE_CHECK_TIMEOUT_SECONDS,
            verify=not allow_insecure_ssl,
        )
    except requests.RequestException as exc:
        return "", "", make_extraction_error(
            "International Carbon Registry / ICR",
            url,
            "icr_detail_fetch_failed",
            str(exc),
            "Open the detail page manually or retry later.",
        ), False, 0
    if response.status_code != 200:
        return "", "", make_extraction_error(
            "International Carbon Registry / ICR",
            response.url or url,
            "icr_detail_non_200_status",
            f"Non-200 status: {response.status_code}",
            "Open the detail page manually or retry later.",
        ), False, 0
    if "html" not in response.headers.get("content-type", "").lower():
        return "", "", None, False, 0
    title, source, suspicious_rejections = title_from_icr_detail_page(response.text, code)
    return title, source, None, True, suspicious_rejections


def enrich_icr_candidates_from_detail_pages(
    candidates: list[dict],
    allow_insecure_ssl: bool,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    enriched = []
    errors = []
    metrics = {
        "icr_candidates_found": 0,
        "icr_detail_pages_fetched": 0,
        "icr_titles_extracted": 0,
        "icr_titles_still_requiring_review": 0,
        "icr_fetch_failures": 0,
        "icr_suspicious_titles_rejected": 0,
    }

    for candidate in candidates:
        is_icr_methodunit = (
            candidate.get("candidate_type") == "methodunit_candidate"
            and bool(CODE_PATTERNS["icr"].search(candidate.get("methodunit_code", "")))
        )
        if not is_icr_methodunit:
            enriched.append(candidate)
            continue

        metrics["icr_candidates_found"] += 1
        existing_title = normalize_text(candidate.get("methodunit_name", ""))
        document_url = clean_url(candidate.get("document_url", ""))
        code = normalize_text(candidate.get("methodunit_code", ""))

        if existing_title and existing_title != "Title requires review" and not is_plausible_icr_methodology_title(existing_title):
            candidate["methodunit_name"] = "Title requires review"
            existing_title = "Title requires review"
            candidate["confidence"] = "medium"
            metrics["icr_suspicious_titles_rejected"] += 1

        if existing_title and existing_title != "Title requires review":
            candidate["notes"] = normalize_text(f"{candidate.get('notes', '')} Title from index page.")

        if document_url:
            detail_title, detail_source, error, fetched, suspicious_rejections = fetch_icr_detail_title(
                document_url,
                code,
                allow_insecure_ssl,
            )
            metrics["icr_suspicious_titles_rejected"] += suspicious_rejections
            if fetched:
                metrics["icr_detail_pages_fetched"] += 1
            if error:
                metrics["icr_fetch_failures"] += 1
                errors.append(error)
            if detail_title:
                candidate["methodunit_name"] = detail_title
                candidate["notes"] = normalize_text(f"{candidate.get('notes', '')} Title enriched from {detail_source}.")
                if candidate.get("methodunit_code") and is_plausible_icr_methodology_title(detail_title) and candidate.get("document_url"):
                    candidate["confidence"] = "high"
                else:
                    candidate["confidence"] = "medium"
                metrics["icr_titles_extracted"] += 1

        if not normalize_text(candidate.get("methodunit_name", "")) or candidate.get("methodunit_name") == "Title requires review":
            candidate["methodunit_name"] = "Title requires review"
            candidate["confidence"] = "medium"
            candidate["notes"] = "M-ICR code found; title not confidently extracted"
            metrics["icr_titles_still_requiring_review"] += 1

        enriched.append(candidate)

    return enriched, errors, metrics


def table_cell_is_metadata(header: str, value: str) -> bool:
    header_l = header.lower()
    value_l = normalize_text(value).lower()
    if not value_l:
        return True
    if any(term in header_l for term in ["code", "status", "version", "sector", "category", "date", "link"]):
        return True
    if extract_status(value) or extract_version(value) or looks_like_url(value):
        return True
    return False


def infer_icr_title_from_cells(headers: list[str], cell_texts: list[str], row_text: str, code: str) -> str:
    for header, value in zip(headers, cell_texts):
        if any(term in header for term in ["title", "name", "methodology"]):
            title = clean_icr_methodology_title(value, code)
            if title:
                return title
    for header, value in zip(headers, cell_texts):
        if not table_cell_is_metadata(header, value):
            title = clean_icr_methodology_title(value, code)
            if title and len(title) > 5:
                return title
    title = clean_icr_methodology_title(row_text, code)
    return title


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
    if source_kind == "icr":
        name = clean_icr_methodology_title(text, code)
        if not name and code:
            name = "Title requires review"
        elif not name and not code:
            name = ""
    elif not name and document_url:
        name = document_url
    status = extract_status(combined)
    version = extract_version(combined)
    if source_kind == "aci" and CODE_PATTERNS["cdm"].search(combined):
        unit_type = "adopted_external_method"
        notes = "Appears to be adopted from CDM."
    confidence = "high" if name and document_url and (code or source_kind == "car") else "medium"
    if source_kind == "icr" and code and is_plausible_icr_methodology_title(name) and document_url:
        confidence = "high"
    elif source_kind == "icr" and code:
        confidence = "medium"
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
            if source_kind == "icr":
                title = infer_icr_title_from_cells(headers, cell_texts, row_text, code)
            elif not title:
                title = next((value for value in cell_texts if value and value != code and len(value) > 5), row_text)
            if source_kind == "aci" and CODE_PATTERNS["cdm"].search(row_text):
                candidate_unit_type = "adopted_external_method"
                candidate_notes = "Appears to be adopted from CDM."
            else:
                candidate_unit_type = unit_type
                candidate_notes = notes
            candidate_name = clean_icr_methodology_title(title, code) if source_kind == "icr" else clean_candidate_name(title, code)
            if source_kind == "icr" and code and not candidate_name:
                candidate_name = "Title requires review"
                candidate_notes = "M-ICR code found; title not confidently extracted"
            confidence = "high" if candidate_name and candidate_name != "Title requires review" and (row_link or code) else "medium"
            if source_kind == "icr" and code and is_plausible_icr_methodology_title(candidate_name) and row_link:
                confidence = "high"
            candidates.append(
                make_candidate(
                    profile,
                    code,
                    candidate_name,
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
        parse_text = text
        if source_kind == "icr":
            parent_text = ""
            for parent_name in ["tr", "li", "p", "div"]:
                parent = anchor.find_parent(parent_name)
                candidate_text = normalize_text(parent.get_text(" ", strip=True)) if parent else ""
                if candidate_text and len(candidate_text) < 500:
                    parent_text = candidate_text
                    break
            if parent_text and CODE_PATTERNS["icr"].search(parent_text):
                parse_text = parent_text
        candidate = candidate_from_text_and_link(
            profile,
            parse_text,
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
    classified = apply_candidate_classification(candidates, "icr")
    enriched, detail_errors, metrics = enrich_icr_candidates_from_detail_pages(classified, allow_insecure_ssl)
    return enriched, detail_errors, metrics


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


def clean_cfc_title(text: str) -> str:
    title = normalize_text(text)
    title = re.sub(r"\b(download|view|open|read|pdf|document)\b\s*[:|-]?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[-|]\s*(city forest credits|carbon credits|urban forest carbon registry).*$", "", title, flags=re.IGNORECASE)
    return normalize_text(title.strip(" :-|"))


def is_likely_cfc_methodunit(text: str, href: str) -> bool:
    combined = f"{normalize_text(text)} {href}".lower()
    if any(term in combined for term in SUPPORTING_DOCUMENT_TERMS + DEVELOPMENT_PAGE_TERMS):
        return False
    if any(term in combined for term in ["blog", "news", "press", "contact", "donate", "login", "webinar"]):
        return False
    if "protocol" in combined and any(term in combined for term in ["preservation", "afforestation", "reforestation", "carbon"]):
        return True
    if "city forest credits standard" in combined:
        return True
    if "standard" in combined and any(term in combined for term in ["city forest", "carbon", "credit"]):
        return True
    return False


def is_relevant_cfc_supporting_link(text: str, href: str) -> bool:
    combined = f"{normalize_text(text)} {href}".lower()
    if not combined.strip():
        return False
    if any(term in combined for term in SUPPORTING_DOCUMENT_TERMS + DEVELOPMENT_PAGE_TERMS):
        return True
    if any(term in combined for term in ["protocol", "standard", "carbon", "credit", ".pdf", "guidance", "template"]):
        return True
    return False


def extract_cfc_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], dict | str, dict[str, int]]:
    profile = get_program_profile(profiles, ["City Forest Credits"])
    source_url = profile_source_url(profile)
    response, error = fetch_public_source(source_url, "City Forest Credits", allow_insecure_ssl)
    metrics = {
        "cfc_records_found": 0,
        "cfc_document_links_found": 0,
        "cfc_supporting_links_found": 0,
        "cfc_records_missing_version": 0,
        "cfc_fetch_failures": 0,
    }
    if error:
        metrics["cfc_fetch_failures"] = 1
        return [], error, metrics

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    seen_links = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        link_text = normalize_text(anchor.get_text(" ", strip=True))
        document_url = urljoin(response.url, href)
        link_key = document_url.lower()
        if link_key in seen_links:
            continue
        seen_links.add(link_key)

        if is_pdf_or_document_url(document_url) or ".pdf" in href.lower():
            metrics["cfc_document_links_found"] += 1

        title = clean_cfc_title(link_text)
        if not title:
            title = clean_cfc_title(Path(urlparse(document_url).path).stem.replace("-", " ").replace("_", " "))
        version = extract_version(f"{link_text} {href}")

        if is_likely_cfc_methodunit(link_text, href):
            unit_type = "Standard" if "standard" in f"{title} {href}".lower() and "protocol" not in f"{title} {href}".lower() else "Protocol"
            confidence = "high" if title and document_url else "medium"
            if not version:
                metrics["cfc_records_missing_version"] += 1
            metrics["cfc_records_found"] += 1
            candidates.append(
                make_candidate(
                    profile,
                    "",
                    title,
                    unit_type,
                    "",
                    version,
                    "pending/public source",
                    response.url,
                    document_url,
                    "cfc_document_link_parse",
                    confidence,
                    "Extracted from the City Forest Credits carbon protocols page; linked documents are discovered but not fully parsed.",
                )
            )
            candidates[-1]["candidate_type"] = "methodunit_candidate"
            candidates[-1]["classification_reason"] = "City Forest Credits protocol/standard document link detected."
        elif is_relevant_cfc_supporting_link(link_text, href):
            metrics["cfc_supporting_links_found"] += 1
            candidates.append(
                make_candidate(
                    profile,
                    "",
                    title or document_url,
                    "supporting_link",
                    "",
                    version,
                    "",
                    response.url,
                    document_url,
                    "cfc_supporting_link_parse",
                    "medium",
                    "Supporting link found on the City Forest Credits carbon protocols page; not treated as a methodology/protocol record.",
                )
            )
            candidates[-1]["candidate_type"] = "supporting_document"
            candidates[-1]["classification_reason"] = "City Forest Credits supporting or non-protocol link."

    return dedupe_candidates(candidates), "", metrics


def first_url_from_text(value: str) -> str:
    match = re.search(r"https?://[^\s,\"']+", str(value or ""))
    return clean_url(match.group(0)) if match else ""


def artisan_source_url(profile: dict) -> str:
    for column in ["method_source_url", "official_website", "registry_url", "evidence_urls"]:
        url = first_url_from_text(profile.get(column, ""))
        if url and not is_pdf_or_document_url(url):
            return url
    return ARTISAN_C_SINK_FALLBACK_SOURCE_URL


def is_artisan_standard_link(text: str, href: str) -> bool:
    combined = f"{normalize_text(text)} {href}".lower()
    return (
        "artisan c-sink" in combined
        and any(term in combined for term in ["standard", "guideline", "global-artisan-c-sink", "global artisan c-sink"])
        and any(term in combined for term in [".pdf", ".doc", "download", "media"])
    )


def is_artisan_supporting_link(text: str, href: str) -> bool:
    combined = f"{normalize_text(text)} {href}".lower()
    return any(
        term in combined
        for term in [
            "clarification",
            "faq",
            "guidance",
            "document",
            "form",
            "annex",
            "update",
            "positive list",
            "calculation",
            "manual",
            "template",
        ]
    )


def check_document_link_issue(program_name: str, document_url: str, source_url: str) -> dict | None:
    if not document_url:
        return make_extraction_error(
            program_name,
            source_url,
            "document_link_missing",
            "No stable standard PDF/document link was found on the public source page.",
            "Open the source page manually and capture a stable document URL before catalogue ingestion.",
        )
    if requests is None:
        return None
    try:
        response = requests.head(
            document_url,
            headers={"User-Agent": POLITE_USER_AGENT},
            allow_redirects=False,
            timeout=SOURCE_CHECK_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return make_extraction_error(
            program_name,
            document_url,
            "document_link_check_failed",
            str(exc),
            "Open the document link manually and confirm whether a stable PDF/document URL is available.",
        )
    if 300 <= response.status_code < 400:
        return make_extraction_error(
            program_name,
            document_url,
            "document_link_redirected",
            f"Document link returned redirect status {response.status_code}.",
            "Capture the final stable PDF/document URL before catalogue ingestion.",
        )
    if response.status_code >= 400:
        return make_extraction_error(
            program_name,
            document_url,
            "document_link_non_200_status",
            f"Document link returned status {response.status_code}.",
            "Find a working standard PDF/document URL or preserve this as a source issue.",
        )
    return None


def resolve_artisan_c_sink_source(profiles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile = get_program_profile(profiles, ["Artisan C-sink", "Artisan C-Sink"])
    if not profile:
        profile = {"program_id": "", "program_name": "Artisan C-sink"}
    program_name = "Artisan C-sink"
    source_url = artisan_source_url(profile)
    resolved_at = datetime.now().isoformat(timespec="seconds")
    resolution = {
        "programme": program_name,
        "dedicated_methodology_page": "Partial / No separate methodology index",
        "where_methodology_info_lives": "standard PDF + clarification documents",
        "methodology_model": "single protocol/document family",
        "recommended_catalogue_action": "capture-document-family",
        "recommended_ingestion_mode": "semi-automated extraction or one-shot manual capture",
        "review_status": "pending_review",
        "evidence_url": source_url,
        "resolved_at": resolved_at,
    }

    response, error = fetch_public_source(source_url, program_name)
    errors = []
    if error:
        resolution["review_status"] = "needs_research"
        errors.append(error)
        return (
            pd.DataFrame([resolution], columns=SOURCE_RESOLUTION_SCHEMA),
            pd.DataFrame(columns=CANDIDATE_SCHEMA),
            pd.DataFrame([{column: row.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for row in errors], columns=EXTRACTION_ERROR_SCHEMA),
        )

    soup = BeautifulSoup(response.text, "html.parser")
    standard_document_url = ""
    supporting_candidates = []
    seen_links = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        link_text = normalize_text(anchor.get_text(" ", strip=True))
        document_url = urljoin(response.url, href)
        link_key = document_url.lower()
        if link_key in seen_links:
            continue
        seen_links.add(link_key)

        if not standard_document_url and is_artisan_standard_link(link_text, href):
            standard_document_url = document_url
            continue

        if is_artisan_supporting_link(link_text, href):
            supporting = make_candidate(
                profile,
                "",
                link_text or Path(urlparse(document_url).path).stem.replace("-", " ").replace("_", " "),
                "supporting_link",
                "",
                extract_version(f"{link_text} {href}"),
                "",
                response.url,
                document_url,
                "source_resolution_link_parse",
                "medium",
                "Clarification or supporting document preserved during Artisan C-sink source resolution.",
            )
            supporting["candidate_type"] = "supporting_document"
            supporting["classification_reason"] = "Artisan C-sink clarification/supporting document, not a methodology record."
            supporting_candidates.append(supporting)

    document_issue = check_document_link_issue(program_name, standard_document_url, response.url)
    if document_issue:
        errors.append(document_issue)

    methodunit = make_candidate(
        profile,
        "",
        "Global Artisan C-Sink Standard",
        "Standard / Document family",
        "",
        "",
        "pending/public source",
        response.url,
        standard_document_url,
        "source_resolution_document_family",
        "high" if standard_document_url and not document_issue else "medium",
        "No separate methodology index; captured as document-family source resolution.",
    )
    methodunit["candidate_type"] = "methodunit_candidate"
    methodunit["classification_reason"] = "No separate methodology index; standard treated as document-family MethodUnit candidate."

    candidates = dedupe_candidates([methodunit, *supporting_candidates])
    return (
        pd.DataFrame([resolution], columns=SOURCE_RESOLUTION_SCHEMA),
        apply_output_safeguards(pd.DataFrame([{column: candidate.get(column, "") for column in CANDIDATE_SCHEMA} for candidate in candidates], columns=CANDIDATE_SCHEMA)),
        pd.DataFrame([{column: row.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for row in errors], columns=EXTRACTION_ERROR_SCHEMA),
    )


def run_candidate_extractors(
    selected_extractors: list[str],
    profiles: pd.DataFrame,
    allow_insecure_ssl: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    ensured = df.copy()
    for column in columns:
        if column not in ensured.columns:
            ensured[column] = ""
    return ensured


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


def text_blob(row: pd.Series, columns: list[str]) -> str:
    return " ".join(str(row.get(column, "")) for column in columns).lower()


def program_in(row: pd.Series, names: list[str]) -> bool:
    program_name = str(row.get("program_name", "")).lower()
    return any(name.lower() in program_name for name in names)


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


def coverage_plan_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Coverage Plan")
    page_summary("A practical onboarding roadmap for answering: What about the rest of the standards?")
    profiles = data.get("source_profiles", pd.DataFrame())
    if not require_rows(profiles, "Source Registry"):
        return

    st.write(
        "The app currently proves the extraction workflow on a small number of sources. "
        "The next challenge is scaling coverage across the remaining standards without turning the project into one generic scraper."
    )
    st.info(
        "The goal is not to automate all 61 sources blindly. The goal is to convert the source registry into a managed onboarding pipeline."
    )
    st.write(
        "Sources should be onboarded in waves based on source type, URL readiness, extraction difficulty, and business value."
    )

    plan = derive_onboarding_plan(profiles)
    metric_row(
        [
            ("Total sources in registry", len(plan)),
            ("Working or partial extractor", count_value(plan, "onboarding_category", "Working extractor")),
            ("Ready for extraction", count_value(plan, "onboarding_category", "Ready for extraction")),
            ("Needs URL repair", count_value(plan, "onboarding_category", "Needs URL repair")),
        ]
    )
    metric_row(
        [
            ("Needs PDF/document parsing", count_value(plan, "onboarding_category", "Needs document/PDF parsing")),
            ("Needs browser automation later", count_value(plan, "onboarding_category", "Needs browser automation later")),
            ("Needs manual investigation", count_value(plan, "onboarding_category", "Needs manual investigation")),
        ]
    )

    st.subheader("Onboarding Waves")
    waves = pd.DataFrame(
        [
            {
                "Wave": "Wave 1: Stabilize working extractors",
                "Goal": "Make CAR solid, keep ICR discovery-only unless titles improve, keep ACI as source exception.",
                "Source archetype": "Currently supported sources",
                "Example sources": "CAR, ICR, ACI",
                "Recommended next action": "Stabilize outputs, review edge cases, and keep exports reliable.",
                "Expected output": "Reliable review queue and export.",
            },
            {
                "Wave": "Wave 2: Add reachable document-family sources",
                "Goal": "Add City Forest Credits or Nori-style sources.",
                "Source archetype": "PDF/document-family",
                "Example sources": "City Forest Credits, Nori, ART/TREES, Peatland Code, Plan Vivo",
                "Recommended next action": "List document/protocol families first; defer PDF content parsing.",
                "Expected output": "Document/protocol family candidates.",
            },
            {
                "Wave": "Wave 3: Add more catalogue-style sources",
                "Goal": "ACR, Climate Forward, BioCarbon Registry, Cercarbono where source URLs are valid.",
                "Source archetype": "Catalogue-first HTML",
                "Example sources": "ACR, Climate Forward, BioCarbon Registry, Cercarbono",
                "Recommended next action": "Repair stale URLs, then parse code/title/status/detail URLs.",
                "Expected output": "Code/title/status/detail URL candidates.",
            },
            {
                "Wave": "Wave 4: Handle adopted-method sources",
                "Goal": "Distinguish native methodologies from adopted CDM/Verra/GS methods.",
                "Source archetype": "Adopted external methods",
                "Example sources": "Asia Carbon Institute, BioCarbon Registry, Cercarbono, Social Carbon, GCC",
                "Recommended next action": "Model native records separately from adopted-method references.",
                "Expected output": "Native method records plus adopted-method references.",
            },
            {
                "Wave": "Wave 5: Complex/high-value sources",
                "Goal": "CDM, JCM, Verra, Gold Standard, Isometric, Puro Earth.",
                "Source archetype": "Large catalogues, JS-heavy portals, complex registries",
                "Example sources": "CDM, JCM, Verra, Gold Standard, Isometric, Puro Earth",
                "Recommended next action": "Design source-specific extractors and freshness monitoring.",
                "Expected output": "Larger-scale source-specific extractors and freshness monitoring.",
            },
            {
                "Wave": "Wave 6: Long-tail unresolved sources",
                "Goal": "Manual investigation and periodic checks.",
                "Source archetype": "Unclear/no methodology page",
                "Example sources": "Low-confidence and unresolved Source Registry entries",
                "Recommended next action": "Confirm source status and decide monitor, manual, or skip.",
                "Expected output": "Source status decisions and manual review notes.",
            },
        ]
    )
    st.dataframe(waves, hide_index=True, use_container_width=True)

    st.subheader("Source-Level Coverage Plan")
    filtered = inline_filters(
        plan,
        ["onboarding_category", "suggested_wave", "connector_type", "confidence", "populated_source_status"],
        "coverage_plan",
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
    show_dataframe(select_existing(filtered, display_columns), "coverage_plan", height=520)

    st.info(
        "If asked whether the rest can be done: yes, but in waves. Each source should first be classified, checked, "
        "assigned an extraction strategy, and routed through review before catalogue export."
    )


def start_here_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Start Here")
    page_summary("Use this page first. It explains the problem, the SourceOps role, the operating pipeline, and what the prototype proves today.")

    profiles = data.get("source_profiles", pd.DataFrame())
    total_programmes = len(profiles)

    st.subheader("The Problem")
    st.write(
        "Carbon methodology information is scattered across heterogeneous official sources. "
        "Some programmes publish structured protocol tables, some use documentation portals, some rely on PDFs, "
        "some adopt external methods, and some have no clear public methodology page."
    )

    st.subheader("The Role of This App")
    st.write(
        "This is an upstream SourceOps layer for methodology catalogues. It does not replace the catalogue. "
        "It organizes source locations, checks official pages, extracts possible methodology/protocol records, preserves Supporting Links, "
        "surfaces Issues to Resolve, and prepares reviewed outputs for Export for Catalogue."
    )

    st.subheader("Pipeline")
    st.write(
        "Source Registry -> Live Source Check -> Source-Specific Extraction -> Extracted Methodology Records -> "
        "Supporting Links -> Issues to Resolve -> Review -> Export for Catalogue"
    )

    st.subheader("What This Prototype Proves")
    st.write(
        "The app can load a 61-programme Source Registry, check selected public source URLs, run three controlled source-specific extractors, "
        "separate extracted methodology records from supporting links, log source-access issues, and export review-ready CSVs."
    )

    st.subheader("What It Does Not Yet Do")
    st.write(
        "It does not approve methodologies, fetch linked PDFs, scrape at scale, bypass access controls, create accounts, "
        "persist reviewer decisions in a database, or cover every standard."
    )

    st.subheader("Current Capability Snapshot")
    capability_rows = [
        {"Capability": "Source Registry", "Current State": f"{total_programmes or 61} programmes loaded"},
        {"Capability": "Live Source Check", "Current State": "working"},
        {"Capability": "Climate Action Reserve extractor", "Current State": "working structured-table extraction"},
        {"Capability": "ICR extractor", "Current State": "discovery-only / pending review"},
        {"Capability": "Asia Carbon Institute", "Current State": "source-access issue due to SSL"},
        {"Capability": "City Forest Credits extractor", "Current State": "document/protocol-family links; no full PDF parsing yet"},
        {"Capability": "Review Extracted Records", "Current State": "prototype"},
        {"Capability": "Export for Catalogue", "Current State": "working"},
        {"Capability": "Persistent database", "Current State": "not yet"},
    ]
    st.dataframe(pd.DataFrame(capability_rows), hide_index=True, use_container_width=True)

    st.subheader("How to Read the Rest of the App")
    st.write(
        "Start with Extraction Strategies and Current Capabilities for context. Then inspect Source Registry, extract from sources, "
        "review extracted records, audit Supporting Links, resolve issues, and export only reviewed records."
    )


def extraction_strategies_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Extraction Strategies")
    page_summary("Use this page to understand why SourceOps needs multiple extraction strategies instead of one generic scraper.")
    st.write(
        "One generic scraper is not enough because carbon standards publish methodology information through very different source patterns. "
        "A reliable workflow needs source-specific extractors, bounded extraction rules, and human review."
    )

    rows = [
        {
            "Source Archetype": "Structured HTML table",
            "Example Sources": "Climate Action Reserve",
            "Extraction Strategy": "Parse the official table, preserve source/detail links, classify rows as extracted methodology records.",
            "Current Status": "Implemented for CAR",
            "Role of AI": "Assist review and duplicate detection, not blind scraping.",
        },
        {
            "Source Archetype": "Methodology catalogue with detail pages",
            "Example Sources": "International Carbon Registry / ICR",
            "Extraction Strategy": "Discover methodology codes and detail URLs, then enrich cautiously from detail-page text.",
            "Current Status": "Discovery-only / pending title review",
            "Role of AI": "Help summarize detail pages after bounded retrieval.",
        },
        {
            "Source Archetype": "PDF / document family",
            "Example Sources": "City Forest Credits, ART/TREES, C-Capsule",
            "Extraction Strategy": "List official documents, then extract metadata from PDFs only in a later controlled workflow.",
            "Current Status": "Implemented for City Forest Credits at document-link level",
            "Role of AI": "Assist document metadata extraction with citations.",
        },
        {
            "Source Archetype": "Adopted external methods",
            "Example Sources": "Asia Carbon Institute, Social Carbon",
            "Extraction Strategy": "Detect native methods separately from adopted CDM/external MethodUnits.",
            "Current Status": "Partially implemented for ACI, currently blocked by source access/SSL in some runs",
            "Role of AI": "Help reconcile adopted method references to canonical source records.",
        },
        {
            "Source Archetype": "JS-heavy portal",
            "Example Sources": "Verra, Gold Standard, Isometric, Riverse",
            "Extraction Strategy": "Use explicit source-specific analysis later; do not treat as simple HTML scraping.",
            "Current Status": "Not implemented",
            "Role of AI": "Assist mapping fields once official access pattern is understood.",
        },
        {
            "Source Archetype": "No clear methodology page",
            "Example Sources": "Small or unresolved programmes",
            "Extraction Strategy": "Manual source profile, monitoring, and issue tracking.",
            "Current Status": "Represented in Source Registry and Issues to Resolve",
            "Role of AI": "Assist source triage and reviewer notes.",
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.info(
        "AI should assist bounded extraction and review. It should not blindly crawl the web, infer approval status, "
        "or bypass official source controls."
    )


def current_capabilities_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Current Capabilities")
    page_summary("Use this page to see what the prototype can do today and where the extraction roadmap still has gaps.")

    capabilities = [
        "Check whether selected source URLs are reachable.",
        "Extract Climate Action Reserve protocol table candidates.",
        "Discover ICR M-ICR methodology codes and detail URLs.",
        "Extract City Forest Credits protocol/standard document links without parsing full PDFs.",
        "Log Asia Carbon Institute SSL/source-access failure as an issue to resolve.",
        "Classify Supporting Links into methodunit_candidate, supporting_document, development_page, navigation_link, and exclude.",
        "Export extracted methodology records, Supporting Links, QA flags, Source Registry records, and extraction errors.",
    ]
    for item in capabilities:
        st.write(f"- {item}")

    st.subheader("Extractor Status")
    connector_rows = [
        {"Extractor": "CAR", "Status": "working extractor", "Interpretation": "Structured protocol table extraction is working."},
        {"Extractor": "ICR", "Status": "discovery-only / needs title review", "Interpretation": "M-ICR codes and detail URLs are discovered, but titles require cautious review."},
        {"Extractor": "ACI", "Status": "blocked/source exception", "Interpretation": "Public source may fail SSL verification; error is logged instead of bypassed by default."},
        {"Extractor": "CFC", "Status": "document/protocol-family extractor implemented", "Interpretation": "Protocol and standard document links are discovered; full PDF parsing is not implemented."},
        {"Extractor": "ACR", "Status": "stale URL to repair before extractor", "Interpretation": "Fix Source Registry URL before building extraction logic."},
        {"Extractor": "CDM", "Status": "reachable/review", "Interpretation": "Large source; needs careful scoped extraction design."},
    ]
    st.dataframe(pd.DataFrame(connector_rows), hide_index=True, use_container_width=True)

    st.subheader("Current Session Counts")
    metric_row(
        [
            ("Extracted Methodology Records", len(current_methodunit_candidates())),
            ("Supporting Links", len(current_extracted_links())),
            ("Extraction errors", len(current_extraction_errors())),
            ("Live source failures", len(current_live_source_failures())),
        ]
    )


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


def demo_source_to_catalogue_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Demo: Source to Catalogue")
    page_summary("A short stakeholder-facing loop from an official source page to review-ready catalogue export files.")

    st.write(
        "This is an upstream ingestion layer for a carbon methodology catalogue. It does not replace the catalogue. "
        "It checks official source pages, runs source-specific extraction, separates supporting links, logs issues, "
        "and exports review-ready records."
    )
    st.info(
        "Extracted records are not automatically approved methodologies. They remain pending review until a human reviewer accepts, rejects, or researches them."
    )

    st.subheader("Source-to-Catalogue Loop")
    step_columns = st.columns(4)
    for column, label, detail in zip(
        step_columns,
        ["Official Source", "Extract Records", "Review", "Export for Catalogue"],
        [
            "Start from a public programme source page.",
            "Run a small source-specific extractor.",
            "Separate records, supporting links, and issues.",
            "Download review-ready CSVs for catalogue work.",
        ],
    ):
        with column:
            st.markdown(f"**{label}**")
            st.caption(detail)
    st.markdown("**Official Source -> Extract Records -> Review -> Export for Catalogue**")

    st.subheader("What This Demo Shows")
    summary_columns = st.columns(4)
    cards = [
        ("What is this?", "Upstream ingestion layer for methodology catalogues."),
        ("What works now?", "CAR structured-table extraction; CFC document/protocol-family extraction; ICR discovery; ACI source exception."),
        ("What does it produce?", "Extracted records, supporting links, issues, and export files."),
        ("What is next?", "Plan Vivo and Climate Forward."),
    ]
    for column, (title, body) in zip(summary_columns, cards):
        with column:
            st.markdown(f"**{title}**")
            st.write(body)

    st.subheader("Run a Quick Demo")
    st.write(
        "Choose one small, public source and run the existing extraction logic. "
        "Run Climate Action Reserve first to see the complete source-to-export loop."
    )
    st.caption("Running a quick demo also populates the Workbench review, supporting links, issues, and export tabs.")

    demo_source = st.selectbox(
        "Demo source",
        ["Climate Action Reserve", "City Forest Credits"],
        key="demo_source_selector",
    )
    extractor_map = {
        "Climate Action Reserve": extract_climate_action_reserve_candidates,
        "City Forest Credits": extract_cfc_candidates,
    }

    if st.button("Run demo extraction", type="primary"):
        extractor = extractor_map[demo_source]
        with st.spinner(f"Checking official source and extracting records for {demo_source}..."):
            candidates, errors, metrics = normalize_demo_extraction_result(
                extractor(data.get("source_profiles", pd.DataFrame()))
            )
        st.session_state["candidate_extraction_results"] = candidates
        st.session_state["candidate_extraction_errors"] = errors
        st.session_state["candidate_extraction_enrichment_metrics"] = metrics
        st.session_state["candidate_extraction_sources_attempted"] = 1
        st.session_state["demo_source_last_run"] = demo_source

    candidates = apply_output_safeguards(
        st.session_state.get("candidate_extraction_results", pd.DataFrame(columns=CANDIDATE_SCHEMA))
    )
    errors = st.session_state.get("candidate_extraction_errors", pd.DataFrame(columns=EXTRACTION_ERROR_SCHEMA))
    enrichment_metrics = st.session_state.get("candidate_extraction_enrichment_metrics", {})
    sources_attempted = st.session_state.get("candidate_extraction_sources_attempted", 0)
    last_run = st.session_state.get("demo_source_last_run", "")

    if candidates.empty and errors.empty:
        st.info("Run Climate Action Reserve first to see the complete source-to-export loop.")
        return

    if last_run:
        st.caption(f"Current demo/session output: {last_run}")
    extracted_records = candidates[candidates.get("candidate_type", pd.Series(dtype=str)).eq("methodunit_candidate")].copy()
    supporting_links = candidates[~candidates.get("candidate_type", pd.Series(dtype=str)).eq("methodunit_candidate")].copy()
    extracted_with_readiness = add_record_readiness(extracted_records)
    issues_attention = len(errors) + count_value(extracted_with_readiness, "record_readiness", "needs_research") + count_value(
        extracted_with_readiness,
        "record_readiness",
        "source_issue",
    )

    metric_row(
        [
            ("Sources attempted", sources_attempted or (1 if last_run else 0)),
            ("Extracted methodology/protocol records", len(extracted_records)),
            ("Supporting links separated", len(supporting_links)),
            ("Issues requiring attention", issues_attention),
        ]
    )

    st.subheader("Result Interpretation")

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
            "International Carbon Registry|ICR",
            case=False,
            na=False,
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
    st.write(
        "These links are preserved for audit and follow-up, but they are not treated as methodology/protocol records."
    )
    st.dataframe(separated_rows, hide_index=True, use_container_width=True)

    with st.expander("Detailed extraction diagnostics", expanded=False):
        methodunit_rows = extracted_records
        missing_title = methodunit_rows[
            methodunit_rows.get("methodunit_name", pd.Series("", index=methodunit_rows.index)).astype(str).str.strip().isin(["", "Title requires review"])
        ]
        missing_status = methodunit_rows[
            methodunit_rows.get("status", pd.Series("", index=methodunit_rows.index)).astype(str).str.strip().eq("")
        ]
        metric_row(
            [
                ("Development pages", count_value(candidates, "candidate_type", "development_page")),
                ("Navigation links", count_value(candidates, "candidate_type", "navigation_link")),
                ("Excluded rows", count_value(candidates, "candidate_type", "exclude")),
                ("Table-derived records", count_value(methodunit_rows, "extraction_method", "table_parse")),
            ]
        )
        metric_row(
            [
                ("Link-derived records", count_value(methodunit_rows, "extraction_method", "link_parse")),
                ("Records missing title", len(missing_title)),
                ("Records missing status", len(missing_status)),
                ("ICR suspicious titles rejected", int(enrichment_metrics.get("icr_suspicious_titles_rejected", 0) or 0)),
            ]
        )
        metric_row(
            [
                ("CFC document links found", int(enrichment_metrics.get("cfc_document_links_found", 0) or 0)),
                ("CFC supporting links found", int(enrichment_metrics.get("cfc_supporting_links_found", 0) or 0)),
                ("CFC records missing version", int(enrichment_metrics.get("cfc_records_missing_version", 0) or 0)),
            ]
        )

    st.subheader("Extracted Records Preview")
    if extracted_records.empty:
        st.warning("No extracted methodology/protocol records were found in this run.")
    else:
        preview_columns = [
            "program_name",
            "methodunit_code",
            "methodunit_name",
            "unit_type",
            "status",
            "document_url",
            "confidence",
            "review_status",
            "record_readiness",
        ]
        show_dataframe(select_existing(extracted_with_readiness.head(10), preview_columns), "demo_extracted_records", height=260)
        st.download_button(
            "Download extracted records CSV",
            data=as_csv_download(select_existing(extracted_records, CANDIDATE_SCHEMA)),
            file_name="methodunit_candidates_review.csv",
            mime="text/csv",
            key="demo_download_records",
        )

    st.subheader("Supporting Links Preview")
    if supporting_links.empty:
        st.info("No supporting links were separated in this run.")
    else:
        preview_columns = [
            "program_name",
            "methodunit_name",
            "candidate_type",
            "classification_reason",
            "document_url",
            "notes",
        ]
        show_dataframe(select_existing(supporting_links.head(10), preview_columns), "demo_supporting_links", height=260)
        st.download_button(
            "Download supporting links CSV",
            data=as_csv_download(select_existing(supporting_links, CANDIDATE_SCHEMA)),
            file_name="extracted_source_links_full.csv",
            mime="text/csv",
            key="demo_download_links",
        )

    if not errors.empty:
        st.subheader("Issues Found")
        show_dataframe(select_existing(errors, EXTRACTION_ERROR_SCHEMA), "demo_extraction_errors", height=220)


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
        st.subheader("Source Pattern Mix")
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
        ("Programmes by Source Pattern", "connector_type"),
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
    st.header("Extraction Strategy")
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
    st.subheader("Source Archetypes")
    section_note("Each row describes a source pattern and the standards currently assigned to that pattern.")
    show_dataframe(select_existing(strategy, display_columns), "connector_strategy", height=360)

    st.subheader("Programmes per Source Pattern")
    profiles = data["source_profiles"]
    chart = value_counts_df(profiles, "connector_type", "connector_type")
    show_bar_chart(chart, "connector_type", "count", "Source-pattern counts are unavailable.")


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


def command_center_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Command Center")
    page_summary("Operational overview for Source Registry coverage, extractor readiness, extracted records, issues to resolve, and next actions.")
    profiles = data["source_profiles"]
    if not require_rows(profiles, "source registry"):
        return

    methodunit_candidates = current_methodunit_candidates()
    extracted_links = current_extracted_links()
    extraction_errors = current_extraction_errors()

    total_programmes = len(profiles)
    populated = count_value(profiles, "currently_has_methodology_rows", "Yes")
    unresolved = count_value(profiles, "currently_has_methodology_rows", "No")
    total_rows = int(numeric_series(profiles, "current_methodology_row_count").sum())
    metric_row(
        [
            ("Source Registry programmes", total_programmes),
            ("Populated programmes", populated),
            ("Unresolved programmes", unresolved),
            ("Current catalogue rows", total_rows),
        ]
    )
    metric_row(
        [
            ("Extracted Methodology Records", len(methodunit_candidates)),
            ("Supporting Links", len(extracted_links)),
            ("Extraction errors", len(extraction_errors)),
            ("Issues to Resolve", len(data.get("qa_flags", pd.DataFrame()))),
        ]
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Programme Coverage")
        chart = value_counts_df(profiles, "populated_source_status", "populated_source_status")
        show_bar_chart(chart, "populated_source_status", "count", "Coverage status is unavailable.")
    with right:
        st.subheader("Extractor Status Summary")
        chart = value_counts_df(profiles, "connector_type", "connector_type")
        show_bar_chart(chart, "connector_type", "count", "Extractor summary is unavailable.")

    st.subheader("Extraction Candidate Summary")
    if extracted_links.empty:
        st.info("No current extraction run is loaded. Extract from Sources or load saved outputs to populate extracted records and Supporting Links.")
    else:
        chart = value_counts_df(extracted_links, "candidate_type", "candidate_type")
        show_bar_chart(chart, "candidate_type", "count", "No candidate type summary is available.")

    st.subheader("Next Recommended Actions")
    actions = add_profile_context(
        data["next_actions"],
        profiles,
        ["extraction_wave", "automation_priority", "confidence", "connector_type"],
    )
    if "priority" not in actions.columns and "automation_priority" in actions.columns:
        actions["priority"] = actions["automation_priority"]
    show_dataframe(
        select_existing(actions, ["priority", "program_name", "extraction_wave", "confidence", "connector_type", "next_action"]).head(20),
        "command_center_next_actions",
        height=300,
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


def run_connectors_workflow_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Extract from Sources")
    page_summary("Check official source pages and run source-specific extraction logic for supported public sources.")
    st.info(
        "Purpose: create the outputs used by the other Workbench tabs. Step 1 checks whether official source URLs are reachable. "
        "Step 2 extracts possible methodology/protocol records and separates supporting links and issues. "
        "A source-specific extractor is a small extractor designed for a specific source or source type."
    )
    precheck_tab, extraction_tab = st.tabs(["Step 1: Check source access", "Step 2: Extract or resolve records"])
    with precheck_tab:
        st.write("Check whether official source URLs are reachable before deciding whether an extraction run is likely to work.")
        live_source_check_page(data)
    with extraction_tab:
        st.write(
            "Run extraction for supported public sources. The run creates extracted records, supporting links, and extraction issues "
            "for the downstream Workbench tabs."
        )
        candidate_extraction_page(data)


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
    source_registry = data.get("source_profiles", pd.DataFrame())
    qa = data.get("qa_flags", pd.DataFrame())
    st.caption(
        f"Export sources: records = {methodunit_source}; supporting links = {links_source}; extraction errors = {errors_source}."
    )

    if methodunits.empty and links.empty and errors.empty:
        st.info(
            "No extraction output is available yet. Open Workbench -> Extract from Sources, use Source Resolution, or run a quick Demo before returning here to export."
        )

    downloads = [
        ("Current extracted methodology records", methodunits, "methodunit_candidates_review.csv"),
        ("Full Supporting Links", links, "extracted_source_links_full.csv"),
        ("Extraction errors", errors, "extraction_errors.csv"),
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


def workbench_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Workbench")
    page_summary("The operational layer for inspecting sources, running extraction, reviewing records, resolving issues, and preparing exports.")
    st.info(
        "Use this page after the demo. Extract from Sources and Source Resolution create the latest outputs used by Review Extracted Records, Supporting Links, Issues to Resolve, and Export for Catalogue."
    )
    st.markdown("**Choose sources -> check access -> extract or resolve records -> review records/supporting links/issues -> export**")
    st.write(
        "Review Extracted Records, Supporting Links, and Issues to Resolve read from the latest extraction or source-resolution run first, then from saved outputs if no run is loaded. "
        "A quick demo run also populates the same latest extraction state used by these tabs."
    )

    tabs = st.tabs(
        [
            "Source Registry",
            "Extract from Sources",
            "Source Resolution",
            "Review Extracted Records",
            "Supporting Links",
            "Issues to Resolve",
            "Export for Catalogue",
            "How to Read Outputs",
        ]
    )
    with tabs[0]:
        source_registry_workflow_page(data)
    with tabs[1]:
        run_connectors_workflow_page(data)
    with tabs[2]:
        source_resolution_page(data)
    with tabs[3]:
        candidate_review_page(data)
    with tabs[4]:
        evidence_links_page(data)
    with tabs[5]:
        qa_exceptions_page(data)
    with tabs[6]:
        export_page(data)
    with tabs[7]:
        interpreting_outputs_page(data)


def strategy_notes_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("Roadmap")
    page_summary("Extraction strategy, extraction waves, and methodology rationale behind the SourceOps workflow.")
    st.info(
        "Purpose: explain design choices and future roadmap. Interpret this as strategy context for why different sources need different extraction approaches. "
        "Action: use Coverage Plan to expand in waves, then use this page to explain the source strategy and priorities."
    )
    st.write(
        "Expansion should follow the Coverage Plan waves. The right next step is not a one-shot scrape; it is to classify each source, "
        "check URL readiness, choose an extraction strategy, and route outputs through review before catalogue export."
    )
    st.subheader("Roadmap Summary")
    roadmap_rows = [
        {
            "Stage": "Implemented now",
            "Focus": "Climate Action Reserve, City Forest Credits, ICR discovery, ACI exception handling",
            "Outcome": "Small source-to-export loop with review-ready records, supporting links, and logged issues.",
        },
        {
            "Stage": "Next sources",
            "Focus": "Plan Vivo and Climate Forward, then ACR after URL validation",
            "Outcome": "Extend the working patterns without broad scraping.",
        },
        {
            "Stage": "Later document parsing",
            "Focus": "Controlled PDF metadata and document-family extraction",
            "Outcome": "Richer version, status, and evidence fields for PDF-first sources.",
        },
        {
            "Stage": "Later portal handling",
            "Focus": "Browser automation for JS-heavy sources such as Verra, Gold Standard, Isometric, and Puro Earth",
            "Outcome": "Source-specific extractors only after official access patterns are understood.",
        },
        {
            "Stage": "Later AI assistance",
            "Focus": "Bounded extraction review, source-change summaries, duplicate detection, and reviewer notes",
            "Outcome": "Faster human review without treating AI output as automatic approval.",
        },
        {
            "Stage": "Later persistence",
            "Focus": "Persistent review decisions and catalogue import validation",
            "Outcome": "Operational review workflow instead of session-only decisions.",
        },
    ]
    st.dataframe(pd.DataFrame(roadmap_rows), hide_index=True, use_container_width=True)

    connector_tab, waves_tab, methodology_tab = st.tabs(["Extraction Strategy", "Extraction Waves", "Methodology Notes"])
    with connector_tab:
        connector_strategy_page(data)
    with waves_tab:
        extraction_waves_page(data)
    with methodology_tab:
        about_page()
        st.subheader("How AI Could Assist Later")
        st.write(
            "AI can help classify Supporting Links, compare source-page changes, summarize methodology PDFs, "
            "draft reviewer notes, and suggest duplicate or adopted-external MethodUnit relationships. "
            "Those steps should remain review-assisted until source reliability and audit trails are stronger."
        )
        st.subheader("How This Feeds Dinesh's Methodology Catalogue")
        st.write(
            "This upstream workbench prepares reviewed extracted methodology records, evidence URLs, source confidence, "
            "and issues to resolve so Dinesh's catalogue can ingest cleaner records with traceable provenance."
        )
        st.subheader("Next Recommended Sources")
        st.write(
            "After City Forest Credits, the next recommended sources are Plan Vivo and Climate Forward. "
            "Plan Vivo extends the document/protocol-family pattern, while Climate Forward is a smaller catalogue-style source suitable for a controlled extractor."
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

    st.subheader("Source Universe Snapshot")
    metric_row(
        [
            ("Total sources", len(plan)),
            ("Working or partial extractor", count_value(plan, "onboarding_category", "Working extractor")),
            ("Ready for extraction", count_value(plan, "onboarding_category", "Ready for extraction")),
            ("Needs URL repair", count_value(plan, "onboarding_category", "Needs URL repair")),
        ]
    )
    metric_row(
        [
            ("Needs PDF/document parsing", count_value(plan, "onboarding_category", "Needs document/PDF parsing")),
            ("Needs browser automation later", count_value(plan, "onboarding_category", "Needs browser automation later")),
            ("Needs manual investigation", count_value(plan, "onboarding_category", "Needs manual investigation")),
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
            ("Blocked / URL repair", count_value(plan, "onboarding_category", "Needs URL repair")),
            ("Recommended next sources", 2),
        ]
    )
    metric_row(
        [
            ("Needs document/PDF parsing", count_value(plan, "onboarding_category", "Needs document/PDF parsing")),
            ("Needs browser automation later", count_value(plan, "onboarding_category", "Needs browser automation later")),
            ("Needs manual investigation", count_value(plan, "onboarding_category", "Needs manual investigation")),
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
            "Open **Ingestion Workflow -> Quick Demo** or **Step 2: Extract or resolve records** to produce records, then return here."
        )
    else:
        with st.expander("Result interpretation summary", expanded=True):
            if last_run:
                st.caption(f"Latest session run: {last_run}")
            render_result_interpretation(candidates, errors)

    tabs = st.tabs(["Extracted Records", "Supporting Material", "Issues", "Export"])
    with tabs[0]:
        candidate_review_page(data)
    with tabs[1]:
        evidence_links_page(data)
    with tabs[2]:
        qa_exceptions_page(data)
    with tabs[3]:
        export_page(data)


def ai_assisted_scaling_page(data: dict[str, pd.DataFrame]) -> None:
    st.header("AI-Assisted Scaling")
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
    sidebar_data_status(data)
    page = st.sidebar.radio(
        "Pages",
        [
            "Source Landscape",
            "Ingestion Workflow",
            "Coverage Progress",
            "Evidence & Review",
            "AI-Assisted Scaling",
        ],
    )

    if page == "Source Landscape":
        source_landscape_page(data)
    elif page == "Ingestion Workflow":
        ingestion_workflow_page(data)
    elif page == "Coverage Progress":
        coverage_progress_page(data)
    elif page == "Evidence & Review":
        evidence_and_review_page(data)
    elif page == "AI-Assisted Scaling":
        ai_assisted_scaling_page(data)


if __name__ == "__main__":
    main()
