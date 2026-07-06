import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import pandas as pd

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
    CODE_PATTERNS,
    EXTRACTION_ERROR_SCHEMA,
    LIKELY_LINK_TERMS,
    SOURCE_RESOLUTION_SCHEMA,
    SUPPORTING_DOCUMENT_TERMS,
    DEVELOPMENT_PAGE_TERMS,
    GENERIC_NAV_TERMS,
    append_note,
    apply_candidate_classification,
    apply_output_safeguards,
    clean_url,
    dedupe_candidates,
    get_program_profile,
    is_fetchable_url,
    is_pdf_or_document_url,
    looks_like_url,
    make_extraction_error,
    normalize_text,
    profile_source_url,
    should_capture_source_link,
)


POLITE_USER_AGENT = (
    "CarbonMethodologySourceOpsWorkbench/0.1 "
    "(local prototype; source reachability check; no bulk scraping)"
)
SOURCE_CHECK_MAX_PROGRAMMES = 10
SOURCE_CHECK_TIMEOUT_SECONDS = 20
ARTISAN_C_SINK_FALLBACK_SOURCE_URL = "https://www.carbon-standards.com/en/standards/service-505~global-artisan-c-sink.html"

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


CF_INDEX_METHODOLOGY_HEADERS = ("methodology",)
CF_INDEX_VERSION_HEADERS = ("current version", "version")
CF_INDEX_DATE_HEADERS = ("date issued", "date")
CF_INDEX_STATUS_HEADERS = ("development status", "status")
CF_INDEX_DOCUMENT_HEADERS = ("document",)


def find_table_by_headers(soup, required_headers: tuple[str, ...]):
    """Return the first <table> whose first row contains all required headers."""
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        header_text = " | ".join(
            normalize_text(cell.get_text(" ", strip=True)).lower() for cell in header_cells
        )
        if all(term in header_text for term in required_headers):
            return table
    return None


def parse_cf_methodology_row(row) -> dict:
    """Extract the (title, version, date, status, detail_url) tuple from a Climate Forward index row."""
    cells = row.find_all(["td", "th"])
    if len(cells) < 4:
        return {}
    title = normalize_text(cells[0].get_text(" ", strip=True))
    version = normalize_text(cells[1].get_text(" ", strip=True))
    date_issued = normalize_text(cells[2].get_text(" ", strip=True))
    status = normalize_text(cells[3].get_text(" ", strip=True))
    detail_url = ""
    for anchor in row.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if href and "climateforward.org" in href.lower() and "/methodolog" in href.lower():
            detail_url = href.rstrip("/") + "/"
            break
    return {
        "title": title,
        "version": version,
        "date_issued": date_issued,
        "status": status,
        "detail_url": detail_url,
    }


def cf_pdf_matches_methodology(text: str, href: str, title: str) -> bool:
    """Guess whether a detail-page PDF anchor is the primary methodology document.

    Climate Forward detail pages usually list the methodology PDF first, with a
    link text like "Dairy Digester Forecast Methodology v1.0". We accept anchors
    that share tokens with the title and that mention "methodology" — falling
    back to filename tokens if the link text is bare.
    """
    combined = normalize_text(f"{text} {href}").lower()
    if "methodology" not in combined and "protocol" not in combined:
        return False
    title_tokens = [t for t in re.split(r"[^a-z0-9]+", title.lower()) if len(t) > 3]
    if not title_tokens:
        return False
    return any(token in combined for token in title_tokens)


def collect_cf_detail_pdfs(profile: dict, methodology: dict, response, source_url: str,
                            metrics: dict) -> tuple[str, list[dict], list[dict]]:
    """Fetch a Climate Forward detail page and split its PDFs into (primary, supporting, errors)."""
    detail_pdfs: list = []
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href.lower().endswith(".pdf"):
            continue
        text = normalize_text(anchor.get_text(" ", strip=True))
        absolute = urljoin(response.url, href)
        detail_pdfs.append((text, absolute))

    primary_url = ""
    supporting = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    title = methodology["title"]
    for text, url in detail_pdfs:
        key = url.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        if not primary_url and cf_pdf_matches_methodology(text, url, title):
            primary_url = url
            continue
        supporting.append(
            make_candidate(
                profile,
                "",
                text or url,
                "supporting_document",
                "",
                methodology.get("version", ""),
                "",
                methodology.get("detail_url") or response.url,
                url,
                "cf_detail_pdf",
                "medium",
                f"Supporting PDF discovered on the Climate Forward detail page for '{title}'; body not parsed.",
            )
        )
        supporting[-1]["candidate_type"] = "supporting_document"
        supporting[-1]["classification_reason"] = "Climate Forward detail-page supporting document link."
        metrics["cf_supporting_documents"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "Climate Forward"),
                methodology.get("detail_url") or source_url,
                "document_link_missing",
                f"No primary methodology PDF was identified on the detail page for '{title}'.",
                "Open the detail page and confirm a stable methodology PDF URL before catalogue ingestion.",
            )
        )
    return primary_url, supporting, errors


def extract_climate_forward_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract forecast-methodology records from the Climate Forward program page.

    Reads the "Methodologies" table on the public index for title, version,
    date issued, development status, and detail URL. Follows each detail page
    to capture the primary methodology PDF (as ``document_url``) and any
    supporting PDFs. Also captures the four program-level document links
    (screening form, template, agreement, approval manual) as supporting
    documents. Detail-page follow-through is best-effort: a failed fetch
    produces an error record but does not drop the methodology candidate.
    """
    profile = get_program_profile(profiles, ["Climate Forward"])
    metrics = {
        "cf_records_found": 0,
        "cf_detail_pages_fetched": 0,
        "cf_detail_pages_failed": 0,
        "cf_pdf_links_attached": 0,
        "cf_supporting_documents": 0,
    }
    errors: list[dict] = []
    source_url = profile_source_url(profile)
    response, error = fetch_public_source(source_url, "Climate Forward", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")

    methodology_table = find_table_by_headers(soup, CF_INDEX_METHODOLOGY_HEADERS + CF_INDEX_VERSION_HEADERS[:1])
    if methodology_table is None:
        errors.append(
            make_extraction_error(
                "Climate Forward",
                response.url,
                "page_structure_changed",
                "Climate Forward methodologies page no longer contains the expected 'Methodology / Current Version' table.",
                "Open the source page manually and update the extractor's table selector.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str, str]] = set()
    rows = methodology_table.find_all("tr")
    for row in rows[1:]:
        methodology = parse_cf_methodology_row(row)
        if not methodology or not methodology["title"]:
            continue
        key = (
            methodology["title"].lower(),
            methodology["version"].lower(),
            methodology["detail_url"].lower(),
        )
        if key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(key)

        document_url = ""
        notes = (
            "Extracted from the Climate Forward forecast methodologies index; "
            "linked PDFs are captured but not fully parsed."
        )
        if methodology["detail_url"]:
            detail_response, detail_error = fetch_public_source(
                methodology["detail_url"], "Climate Forward", allow_insecure_ssl
            )
            if detail_error:
                metrics["cf_detail_pages_failed"] += 1
                errors.append(detail_error)
                notes += " Detail page fetch failed; no methodology PDF attached."
            else:
                metrics["cf_detail_pages_fetched"] += 1
                document_url, supporting, detail_errors = collect_cf_detail_pdfs(
                    profile, methodology, detail_response, response.url, metrics
                )
                candidates.extend(supporting)
                errors.extend(detail_errors)
                if document_url:
                    metrics["cf_pdf_links_attached"] += 1

        confidence = "high" if document_url and methodology["version"] else "medium"
        candidate = make_candidate(
            profile,
            "",
            methodology["title"],
            "forecast_methodology",
            "",
            methodology["version"],
            methodology["status"] or "Available",
            response.url,
            document_url,
            "cf_index_table_parse",
            confidence,
            append_note(notes, f"Date issued: {methodology['date_issued']}") if methodology["date_issued"] else notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = "Climate Forward forecast methodology index row."
        candidates.append(candidate)
        metrics["cf_records_found"] += 1

    documents_table = find_table_by_headers(soup, CF_INDEX_DOCUMENT_HEADERS)
    if documents_table is not None:
        for row in documents_table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            title = normalize_text(cells[0].get_text(" ", strip=True))
            description = normalize_text(cells[1].get_text(" ", strip=True))
            document_url = ""
            for anchor in row.find_all("a", href=True):
                href = anchor.get("href", "").strip()
                if href:
                    document_url = urljoin(response.url, href)
                    break
            if not title or not document_url:
                continue
            supporting = make_candidate(
                profile,
                "",
                title,
                "program_document",
                "",
                "",
                "",
                response.url,
                document_url,
                "cf_index_document_table",
                "medium",
                f"Climate Forward program-level document: {description[:180]}",
            )
            supporting["candidate_type"] = "supporting_document"
            supporting["classification_reason"] = "Climate Forward program-level document table row."
            candidates.append(supporting)
            metrics["cf_supporting_documents"] += 1

    return dedupe_candidates(candidates), errors, metrics


ACR_CANONICAL_SOURCE_URL = "https://acrcarbon.org/methodologies/approved-methodologies/"
ACR_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
ACR_INDEX_METHODOLOGY_HEADERS = ("methodology", "version")
ACR_PRIMARY_ANCHOR_TEXTS = ("download the methodology",)


def acr_source_url(profile: dict) -> str:
    """Return the canonical acrcarbon.org page, falling back to it when the profile URL is stale."""
    candidate = profile_source_url(profile)
    if candidate and "acrcarbon.org/methodolog" in candidate.lower():
        return candidate
    return ACR_CANONICAL_SOURCE_URL


def acr_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(ACR_DOCUMENT_EXTENSIONS)


def parse_acr_index_row(row) -> dict:
    cells = row.find_all(["td", "th"])
    if len(cells) < 3:
        return {}
    sector = normalize_text(cells[0].get_text(" ", strip=True))
    title = normalize_text(cells[1].get_text(" ", strip=True))
    version = normalize_text(cells[2].get_text(" ", strip=True))
    detail_url = ""
    for anchor in row.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if href and "acrcarbon.org/methodology/" in href.lower():
            detail_url = href.rstrip("/") + "/"
            break
    return {
        "sector": sector,
        "title": title,
        "version": version,
        "detail_url": detail_url,
    }


def acr_section_label(anchor) -> str:
    """Return the nearest preceding <h3>/<h4>/<h2> heading text for an anchor, if any."""
    heading = anchor.find_previous(["h4", "h3", "h2"])
    if not heading:
        return ""
    return normalize_text(heading.get_text(" ", strip=True))


def acr_classify_section(label: str) -> tuple[str, str]:
    """Return (candidate_type, evidence_stage) for an anchor sitting under ``label``."""
    label_l = (label or "").lower()
    if "previous approved" in label_l:
        return "supporting_document", "historical_version"
    if "process documentation" in label_l:
        return "supporting_document", "process_documentation"
    if "reference document" in label_l:
        return "supporting_document", "reference_document"
    if "current approved" in label_l:
        return "supporting_document", "current_version_supplement"
    return "supporting_document", "unlabelled_document"


def find_acr_primary_pdf(soup, response_url: str) -> str:
    """Return the current-approved-version PDF URL, preferring the 'Download the methodology' anchor."""
    for anchor in soup.find_all("a", href=True):
        text = normalize_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor.get("href", "").strip()
        if not href or not acr_is_document_href(href):
            continue
        if any(marker in text for marker in ACR_PRIMARY_ANCHOR_TEXTS):
            return urljoin(response_url, href)
    # Fallback: first PDF under a "Current Approved Version" heading that is not
    # an errata / peer review / public comment / summary document.
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or not acr_is_document_href(href):
            continue
        label = acr_section_label(anchor).lower()
        if "current approved" not in label:
            continue
        text = normalize_text(anchor.get_text(" ", strip=True)).lower()
        skip_terms = ("errata", "peer review", "public comment", "summary of changes", "reference", "calculator", "supplement")
        if any(term in text for term in skip_terms):
            continue
        return urljoin(response_url, href)
    return ""


def collect_acr_detail_documents(
    profile: dict,
    methodology: dict,
    response,
    metrics: dict,
) -> tuple[str, list[dict], list[dict]]:
    """Fetch a detail page and split its document anchors into (primary_url, supporting[], errors[])."""
    soup = BeautifulSoup(response.text, "html.parser")
    primary_url = find_acr_primary_pdf(soup, response.url)
    supporting: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    if primary_url:
        seen_urls.add(primary_url.lower())

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or not acr_is_document_href(href):
            continue
        absolute = urljoin(response.url, href)
        key = absolute.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        text = normalize_text(anchor.get_text(" ", strip=True)) or absolute
        section_label = acr_section_label(anchor)
        candidate_type, evidence_stage = acr_classify_section(section_label)
        note = (
            f"ACR detail-page supporting document for '{methodology['title']}' "
            f"({section_label or 'unlabelled section'}); body not parsed."
        )
        candidate = make_candidate(
            profile,
            "",
            text,
            "supporting_document",
            methodology.get("sector", ""),
            methodology.get("version", ""),
            "",
            methodology.get("detail_url") or response.url,
            absolute,
            "acr_detail_document",
            "medium",
            note,
        )
        candidate["candidate_type"] = candidate_type
        candidate["classification_reason"] = (
            f"ACR detail-page document ({evidence_stage})."
        )
        # Best-effort evidence stage — CANDIDATE_SCHEMA has no evidence column,
        # so we surface the stage through the notes for downstream review.
        candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {evidence_stage}")
        supporting.append(candidate)
        metrics["acr_supporting_documents"] += 1
        if evidence_stage == "historical_version":
            metrics["acr_historical_documents"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "American Carbon Registry (ACR)"),
                methodology.get("detail_url") or response.url,
                "document_link_missing",
                f"No current-approved-version PDF was identified on the detail page for '{methodology['title']}'.",
                "Open the detail page and confirm which anchor represents the current approved methodology PDF.",
            )
        )
        metrics["acr_primary_pdf_missing"] += 1
    return primary_url, supporting, errors


def extract_acr_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract approved-methodology records from the American Carbon Registry (ACR) public catalogue.

    Reads the "Approved Methodologies" index table (columns: ANAB Sectoral
    Scope, Methodology, Version), then follows each detail page to attach the
    current-approved-version PDF as ``document_url``. Detail pages expose
    ``Current Approved Version`` / ``Process Documentation`` / ``Previous
    Approved Versions`` sections; anchors under those sections are captured as
    supporting documents with an ``evidence_stage`` note (``current``,
    ``process_documentation``, ``historical_version``, ``reference_document``).
    Historical PDFs are never attached as the primary document. Detail-page
    fetch failures produce an extraction error but do not drop the record.
    """
    profile = get_program_profile(profiles, ["American Carbon Registry (ACR)", "American Carbon Registry"])
    metrics = {
        "acr_records_found": 0,
        "acr_detail_pages_fetched": 0,
        "acr_detail_pages_failed": 0,
        "acr_primary_pdf_attached": 0,
        "acr_primary_pdf_missing": 0,
        "acr_supporting_documents": 0,
        "acr_historical_documents": 0,
    }
    errors: list[dict] = []
    source_url = acr_source_url(profile)
    response, error = fetch_public_source(source_url, "American Carbon Registry (ACR)", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        errors.append(
            make_extraction_error(
                "American Carbon Registry (ACR)",
                response.url,
                "page_structure_changed",
                "ACR approved methodologies page contains no <table> elements.",
                "Open the page manually and update the extractor's table selector.",
            )
        )
        return [], errors, metrics

    methodology_table = find_table_by_headers(soup, ACR_INDEX_METHODOLOGY_HEADERS)
    if methodology_table is None:
        errors.append(
            make_extraction_error(
                "American Carbon Registry (ACR)",
                response.url,
                "page_structure_changed",
                "ACR approved methodologies page no longer contains a table with 'Methodology' and 'Version' headers.",
                "Open the source page manually and update the extractor's table selector.",
            )
        )
        return [], errors, metrics

    data_rows = methodology_table.find_all("tr")[1:]
    if not data_rows:
        errors.append(
            make_extraction_error(
                "American Carbon Registry (ACR)",
                response.url,
                "no_records_found",
                "ACR approved methodologies table has a header but no data rows.",
                "Confirm the source is still publishing approved methodologies.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str, str]] = set()
    for row in data_rows:
        methodology = parse_acr_index_row(row)
        if not methodology or not methodology["title"]:
            continue
        key = (
            methodology["title"].lower(),
            methodology["version"].lower(),
            methodology["detail_url"].lower(),
        )
        if key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(key)

        document_url = ""
        notes = (
            "Extracted from the American Carbon Registry approved methodologies index; "
            "linked PDFs are captured but not fully parsed."
        )
        if methodology["detail_url"]:
            detail_response, detail_error = fetch_public_source(
                methodology["detail_url"], "American Carbon Registry (ACR)", allow_insecure_ssl
            )
            if detail_error:
                metrics["acr_detail_pages_failed"] += 1
                errors.append(detail_error)
                notes += " Detail page fetch failed; primary PDF not attached."
            else:
                metrics["acr_detail_pages_fetched"] += 1
                document_url, supporting, detail_errors = collect_acr_detail_documents(
                    profile, methodology, detail_response, metrics
                )
                candidates.extend(supporting)
                errors.extend(detail_errors)
                if document_url:
                    metrics["acr_primary_pdf_attached"] += 1
        else:
            errors.append(
                make_extraction_error(
                    "American Carbon Registry (ACR)",
                    response.url,
                    "detail_url_missing",
                    f"No detail URL found for the '{methodology['title']}' row on the ACR index.",
                    "Open the source page manually and confirm the row still links to a per-methodology detail page.",
                )
            )

        confidence = "high" if document_url and methodology["version"] else "medium"
        candidate = make_candidate(
            profile,
            "",
            methodology["title"],
            "approved_methodology",
            methodology["sector"],
            methodology["version"],
            "Approved",
            response.url,
            document_url,
            "acr_index_table_parse",
            confidence,
            notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = "American Carbon Registry approved methodology index row."
        candidates.append(candidate)
        metrics["acr_records_found"] += 1

    return dedupe_candidates(candidates), errors, metrics


SOCIAL_CARBON_CANONICAL_SOURCE_URL = "https://www.socialcarbon.org/methodologies"
SOCIAL_CARBON_CODE_RE = re.compile(r"\bSCM\d{4}\b")
SOCIAL_CARBON_TITLE_RE = re.compile(r"^\s*(SCM\d{4})\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)
SOCIAL_CARBON_STATUS_RE = re.compile(
    r"Status[:\s]+(Live|Active|Inactive|Withdrawn|Sunset)[^A-Za-z0-9]*(?:since\s*)?([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})?",
    re.IGNORECASE,
)
SOCIAL_CARBON_MODULE_STOP_TERMS = ("description.", "version history.", "modules /")
SOCIAL_CARBON_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
SOCIAL_CARBON_PRIMARY_ANCHOR_TEXTS = ("view methodology",)


def social_carbon_source_url(profile: dict) -> str:
    candidate = profile_source_url(profile)
    if candidate and "socialcarbon.org" in candidate.lower() and "methodolog" in candidate.lower():
        return candidate
    return SOCIAL_CARBON_CANONICAL_SOURCE_URL


def social_carbon_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(SOCIAL_CARBON_DOCUMENT_EXTENSIONS)


def collect_social_carbon_index_records(soup, index_url: str) -> tuple[list[dict], list[str]]:
    """Return (records, seen_codes) parsed from the Social Carbon methodologies index.

    Each record has {code, title, detail_url, is_inactive_context}. ``seen_codes``
    is the ordered set of distinct SCM codes found on the index (used for
    fail-loud diagnostics if we discover zero codes).
    """
    records: list[dict] = []
    seen_codes: list[str] = []
    for heading in soup.find_all("h2"):
        heading_text = normalize_text(heading.get_text(" ", strip=True))
        match = SOCIAL_CARBON_TITLE_RE.match(heading_text)
        if not match:
            continue
        code = match.group(1).upper()
        title = normalize_text(match.group(2))
        if code not in seen_codes:
            seen_codes.append(code)
        # Detail URL: the surrounding container carries an anchor to /scmNNNN.
        detail_url = ""
        container = heading
        for _ in range(5):
            if container.parent is None:
                break
            container = container.parent
            for anchor in container.find_all("a", href=True):
                href = anchor.get("href", "").strip()
                if not href:
                    continue
                lowered = href.lower().rstrip("/")
                if lowered.endswith("/" + code.lower()) or lowered.endswith(code.lower()):
                    detail_url = urljoin(index_url, href)
                    break
            if detail_url:
                break
        # Inactive-section detection: any ancestor <h3>/<h4>/<section> label mentioning "Inactive".
        is_inactive = False
        section = heading.find_previous(["h1", "h2", "h3", "h4"])
        while section is not None:
            section_text = normalize_text(section.get_text(" ", strip=True)).lower()
            if "inactive methodolog" in section_text:
                is_inactive = True
                break
            section = section.find_previous(["h1", "h2", "h3", "h4"])
        records.append(
            {
                "code": code,
                "title": title,
                "detail_url": detail_url,
                "is_inactive_context": is_inactive,
            }
        )
    return records, seen_codes


def parse_social_carbon_status(body_text: str, is_inactive_context: bool) -> str:
    """Return a normalized status string parsed from detail-page body text."""
    match = SOCIAL_CARBON_STATUS_RE.search(body_text or "")
    if match:
        keyword = match.group(1).title()
        date = match.group(2) or ""
        return f"{keyword} since {date}".strip() if date else keyword
    return "Inactive" if is_inactive_context else "Live"


def parse_social_carbon_modules(body_text: str) -> str:
    """Return a compact string listing modules/tools mentioned on the detail page."""
    if not body_text:
        return ""
    lowered = body_text.lower()
    marker = "modules / key sources"
    idx = lowered.find(marker)
    if idx == -1:
        return ""
    snippet = body_text[idx + len(marker): idx + len(marker) + 400]
    for stop in SOCIAL_CARBON_MODULE_STOP_TERMS:
        cut = snippet.lower().find(stop)
        if cut != -1:
            snippet = snippet[:cut]
    return normalize_text(snippet)[:300]


def parse_social_carbon_version_history(soup) -> str:
    """Return a compact, semicolon-joined list of versions listed under 'Version History.'."""
    versions: list[str] = []
    for heading in soup.find_all(["h3", "h4"]):
        text = normalize_text(heading.get_text(" ", strip=True))
        if re.match(r"(?i)^version\s+\d", text):
            if text not in versions:
                versions.append(text)
    return "; ".join(versions)


def find_social_carbon_primary_pdf(soup, response_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        text = normalize_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor.get("href", "").strip()
        if not href or not social_carbon_is_document_href(href):
            continue
        if any(marker in text for marker in SOCIAL_CARBON_PRIMARY_ANCHOR_TEXTS):
            return urljoin(response_url, href)
    return ""


def collect_social_carbon_detail_documents(
    profile: dict,
    record: dict,
    response,
    metrics: dict,
) -> tuple[str, str, str, str, list[dict], list[dict]]:
    """Fetch a detail page and return (primary_url, status, modules, version_history, supporting, errors)."""
    soup = BeautifulSoup(response.text, "html.parser")
    body_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    primary_url = find_social_carbon_primary_pdf(soup, response.url)
    status = parse_social_carbon_status(body_text, record["is_inactive_context"])
    modules = parse_social_carbon_modules(body_text)
    version_history = parse_social_carbon_version_history(soup)

    supporting: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    if primary_url:
        seen_urls.add(primary_url.lower())

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or not social_carbon_is_document_href(href):
            continue
        absolute = urljoin(response.url, href)
        key = absolute.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        text = normalize_text(anchor.get_text(" ", strip=True)) or absolute
        section_heading = anchor.find_previous(["h4", "h3", "h2"])
        section_label = normalize_text(section_heading.get_text(" ", strip=True)) if section_heading else ""
        if re.match(r"(?i)^version\s+\d", section_label):
            evidence_stage = "historical_version" if section_label.lower() not in version_history.lower().split("; ")[-1:] else "current_version_supplement"
        elif "public comments" in text.lower():
            evidence_stage = "public_comments"
        elif any(term in text.lower() for term in ("feasibility", "vvb", "template", "checklist", "tool")):
            evidence_stage = "tool_or_template"
        elif "board decision" in text.lower() or "sunset" in text.lower():
            evidence_stage = "programme_decision"
        else:
            evidence_stage = "supporting_document"

        candidate = make_candidate(
            profile,
            record["code"],
            text,
            "supporting_document",
            "",
            "",
            "",
            record["detail_url"] or response.url,
            absolute,
            "social_carbon_detail_document",
            "medium",
            f"Social Carbon detail-page document for {record['code']} '{record['title']}' "
            f"(section: {section_label or 'unlabelled'}); body not parsed.",
        )
        candidate["candidate_type"] = "supporting_document"
        candidate["classification_reason"] = f"Social Carbon detail-page document ({evidence_stage})."
        candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {evidence_stage}")
        supporting.append(candidate)
        metrics["sc_supporting_documents"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "Social Carbon"),
                record.get("detail_url") or response.url,
                "document_link_missing",
                f"No 'View Methodology' anchor was found on the detail page for '{record['code']}'.",
                "Open the detail page and confirm which anchor represents the current methodology PDF.",
            )
        )
        metrics["sc_primary_pdf_missing"] += 1

    return primary_url, status, modules, version_history, supporting, errors


def extract_social_carbon_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract methodology records from the Social Carbon public methodologies index.

    The index page is a Squarespace-style card layout (no <table>). Each card
    exposes a ``SCM####:`` heading, a description, and a ``/scm####`` detail
    link; inactive methodologies sit under an ``Inactive Methodologies``
    section. Detail pages follow a consistent layout with a top ``View
    Methodology`` anchor for the current PDF, a ``Version History.`` block
    with per-version H4s and PDFs, and a ``Modules / Key Sources`` block.
    Sector, modules and version history are not first-class ``CANDIDATE_SCHEMA``
    columns; the extractor surfaces them via labelled ``notes`` entries.
    Historical PDFs and public-comment PDFs are captured as
    ``supporting_document`` candidates and never attached as the primary
    document.
    """
    profile = get_program_profile(profiles, ["Social Carbon"])
    metrics = {
        "sc_records_found": 0,
        "sc_inactive_records": 0,
        "sc_detail_pages_fetched": 0,
        "sc_detail_pages_failed": 0,
        "sc_primary_pdf_attached": 0,
        "sc_primary_pdf_missing": 0,
        "sc_supporting_documents": 0,
        "sc_index_codes_seen": 0,
    }
    errors: list[dict] = []
    source_url = social_carbon_source_url(profile)
    response, error = fetch_public_source(source_url, "Social Carbon", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")
    index_records, seen_codes = collect_social_carbon_index_records(soup, response.url)
    metrics["sc_index_codes_seen"] = len(seen_codes)
    if not index_records:
        errors.append(
            make_extraction_error(
                "Social Carbon",
                response.url,
                "page_structure_changed",
                "Social Carbon methodologies index no longer exposes 'SCM####:' methodology headings.",
                "Open the source page manually and update the index selector.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str, str]] = set()
    for record in index_records:
        if not record["code"]:
            continue
        key = (
            record["code"].lower(),
            record["detail_url"].lower(),
            "",  # placeholder for document_url in dedupe key; recomputed below.
        )
        if key in seen_dedupe_keys:
            continue

        document_url = ""
        status_value = "Live"
        modules = ""
        version_history = ""
        notes = (
            "Extracted from the Social Carbon methodologies index; detail-page "
            "documents captured but not fully parsed."
        )
        if record["detail_url"]:
            detail_response, detail_error = fetch_public_source(
                record["detail_url"], "Social Carbon", allow_insecure_ssl
            )
            if detail_error:
                metrics["sc_detail_pages_failed"] += 1
                errors.append(detail_error)
                status_value = "Inactive" if record["is_inactive_context"] else "Live"
                notes += " Detail page fetch failed; no methodology PDF attached."
            else:
                metrics["sc_detail_pages_fetched"] += 1
                (
                    document_url,
                    status_value,
                    modules,
                    version_history,
                    supporting,
                    detail_errors,
                ) = collect_social_carbon_detail_documents(
                    profile, record, detail_response, metrics
                )
                candidates.extend(supporting)
                errors.extend(detail_errors)
                if document_url:
                    metrics["sc_primary_pdf_attached"] += 1
        else:
            errors.append(
                make_extraction_error(
                    "Social Carbon",
                    response.url,
                    "detail_url_missing",
                    f"No detail URL found alongside the '{record['code']}' heading on the Social Carbon index.",
                    "Open the index manually and confirm the SCM row still links to a /scm#### detail page.",
                )
            )

        dedupe_key = (
            record["code"].lower(),
            record["detail_url"].lower(),
            document_url.lower(),
        )
        if dedupe_key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(dedupe_key)

        rich_notes = notes
        rich_notes = append_note(rich_notes, "sector: (not published on Social Carbon detail page)")
        if modules:
            rich_notes = append_note(rich_notes, f"modules: {modules}")
        if version_history:
            rich_notes = append_note(rich_notes, f"version_history: {version_history}")

        confidence = "high" if document_url and version_history else "medium"
        candidate = make_candidate(
            profile,
            record["code"],
            record["title"] or f"{record['code']} (title requires review)",
            "methodology",
            "",
            version_history.split("; ")[-1] if version_history else "",
            status_value,
            response.url,
            document_url,
            "social_carbon_index_scan",
            confidence,
            rich_notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = "Social Carbon methodology index card ({code}).".format(code=record["code"])
        candidates.append(candidate)
        metrics["sc_records_found"] += 1
        if record["is_inactive_context"] or status_value.lower().startswith("inactive"):
            metrics["sc_inactive_records"] += 1

    return dedupe_candidates(candidates), errors, metrics


PLAN_VIVO_CANONICAL_SOURCE_URL = (
    "https://www.planvivo.org/projects/certify-a-project/pvclimate/methodologies/approved-methodologies"
)
PLAN_VIVO_CODE_RE = re.compile(r"\bPM\s?\d{3,}\b", re.IGNORECASE)
PLAN_VIVO_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
PLAN_VIVO_METADATA_LABELS = {
    "status": re.compile(r"Status:\s*([^\|\n\r]+?)(?=\s+(?:Type|Version|Developer|Reviewers?|Active from)\b|$)", re.IGNORECASE),
    "type": re.compile(r"Type:\s*([^\|\n\r]+?)(?=\s+(?:Status|Version|Developer|Reviewers?|Active from)\b|$)", re.IGNORECASE),
    "version": re.compile(r"Version\s+([0-9]+(?:\.[0-9]+)?):", re.IGNORECASE),
    "active_from": re.compile(r"Active from:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", re.IGNORECASE),
    "developer": re.compile(r"Developer:\s*([^\n\r]+?)(?=\s+Reviewers?:|$)", re.IGNORECASE),
    "reviewers": re.compile(r"Reviewers?:\s*([^\n\r]+?)(?=\s+(?:Status|Type|Version|Developer|Active from)\b|$)", re.IGNORECASE),
}


def plan_vivo_source_url(profile: dict) -> str:
    """Prefer the verified approved-methodologies URL, ignoring any stale entries."""
    candidate = profile_source_url(profile)
    if candidate and "planvivo.org/projects/certify-a-project" in candidate.lower():
        return candidate
    return PLAN_VIVO_CANONICAL_SOURCE_URL


def plan_vivo_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(PLAN_VIVO_DOCUMENT_EXTENSIONS)


def _plan_vivo_extract_label(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text or "")
    return normalize_text(match.group(1)) if match else ""


def parse_plan_vivo_metadata(text: str) -> dict[str, str]:
    return {label: _plan_vivo_extract_label(pattern, text) for label, pattern in PLAN_VIVO_METADATA_LABELS.items()}


def parse_plan_vivo_article(article) -> dict:
    """Return {code, title, description, metadata_text, anchors} for a Plan Vivo methodology article."""
    headings = article.find_all(["h2", "h3", "h4"])
    code = ""
    title = ""
    for heading in headings:
        text = normalize_text(heading.get_text(" ", strip=True))
        if not code:
            match = PLAN_VIVO_CODE_RE.search(text)
            if match:
                code = match.group(0).replace(" ", "").upper()
                # If the same heading also contains the title (e.g. "PM001 Agriculture ..."),
                # grab the tail as the title.
                trailing = normalize_text(text[match.end():])
                if trailing and not title:
                    title = trailing
                continue
        if code and not title:
            title = text
            break
    if not code:
        return {}
    metadata_text = ""
    for paragraph in article.find_all("p"):
        p_text = normalize_text(paragraph.get_text(" ", strip=True))
        if "Status" in p_text and ("Type" in p_text or "Version" in p_text):
            metadata_text = p_text
            break
    if not metadata_text:
        # Fallback: full article text minus title/code.
        metadata_text = normalize_text(article.get_text(" ", strip=True))
    description = ""
    for paragraph in article.find_all("p"):
        p_text = normalize_text(paragraph.get_text(" ", strip=True))
        if p_text and "Status" not in p_text and PLAN_VIVO_CODE_RE.search(p_text) is None and len(p_text) > 40:
            description = p_text
            break
    return {
        "code": code,
        "title": title,
        "description": description,
        "metadata_text": metadata_text,
        "anchors": article.find_all("a", href=True),
    }


def classify_plan_vivo_anchor(text: str, code: str) -> str:
    """Return a stage tag for a Plan Vivo document anchor.

    ``primary`` = the current-version methodology PDF (link text starts with the
    PM code or is exactly ``View PM###``). ``assessment`` = the paired
    assessment/review report. ``supporting`` = anything else.
    """
    text_l = (text or "").strip().lower()
    if not text_l:
        return "supporting"
    if text_l.startswith("view " + code.lower()):
        return "primary"
    if text_l.startswith(code.lower()):
        # Matches "PM001 V1.0" style link text.
        return "primary"
    if "assessment" in text_l or "review" in text_l:
        return "assessment"
    if "public comment" in text_l or "consultation" in text_l:
        return "public_comments"
    return "supporting"


def collect_plan_vivo_documents(profile: dict, record: dict, index_url: str, metrics: dict) -> tuple[str, list[dict], list[dict]]:
    """Split an article's document anchors into (primary_url, supporting[], errors[])."""
    primary_url = ""
    supporting: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    for anchor in record["anchors"]:
        href = anchor.get("href", "").strip()
        if not href or not plan_vivo_is_document_href(href):
            continue
        absolute = urljoin(index_url, href)
        text = normalize_text(anchor.get_text(" ", strip=True)) or absolute
        stage = classify_plan_vivo_anchor(text, record["code"])
        if stage == "primary" and not primary_url:
            primary_url = absolute
            seen_urls.add(absolute.lower())
            continue
        key = absolute.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        candidate = make_candidate(
            profile,
            record["code"],
            text,
            "supporting_document",
            "",
            "",
            "",
            index_url,
            absolute,
            "plan_vivo_index_document",
            "medium",
            f"Plan Vivo document for {record['code']} '{record['title']}' "
            f"(stage: {stage}); body not parsed.",
        )
        candidate["candidate_type"] = "supporting_document"
        candidate["classification_reason"] = f"Plan Vivo methodology supporting document ({stage})."
        candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {stage}")
        supporting.append(candidate)
        metrics["pv_supporting_documents"] += 1
        if stage == "assessment":
            metrics["pv_assessment_reports_captured"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "Plan Vivo"),
                index_url,
                "document_link_missing",
                f"No primary methodology PDF was identified in the Plan Vivo article for '{record['code']}'.",
                "Open the source page and confirm which anchor represents the current methodology PDF.",
            )
        )
        metrics["pv_primary_pdf_missing"] += 1
    return primary_url, supporting, errors


def extract_plan_vivo_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract Plan Vivo approved-methodology records from the public PV Climate page.

    The approved-methodologies page hosts one ``<article>`` block per
    methodology (currently PM001 and PM002). Each article carries a PM code,
    title, description, and a ``Status: … Type: … Version …: PM### V… |
    Assessment Report (Active from: …) Developer: … Reviewers: …`` metadata
    line, plus S3-hosted PDFs for the methodology, an assessment report, and
    any supporting documents. No detail-page follow-through is required.

    Non-schema fields (``type``, ``active_from``, ``developer``,
    ``reviewers``) are surfaced through labelled ``notes`` entries so the
    ``CANDIDATE_SCHEMA`` is preserved. The assessment PDF is captured as a
    supporting document tagged ``evidence_stage: assessment``; the current
    methodology PDF is attached as ``document_url``.
    """
    profile = get_program_profile(profiles, ["Plan Vivo"])
    metrics = {
        "pv_records_found": 0,
        "pv_primary_pdf_attached": 0,
        "pv_primary_pdf_missing": 0,
        "pv_assessment_reports_captured": 0,
        "pv_supporting_documents": 0,
    }
    errors: list[dict] = []
    source_url = plan_vivo_source_url(profile)
    response, error = fetch_public_source(source_url, "Plan Vivo", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")

    # The page nests per-methodology articles inside a wrapper article; only
    # leaf articles (no nested <article> children) hold a single PM record.
    articles = [article for article in soup.find_all("article") if not article.find("article")]
    parsed_records: list[dict] = []
    for article in articles:
        record = parse_plan_vivo_article(article)
        if record and record.get("code"):
            parsed_records.append(record)

    if not parsed_records:
        errors.append(
            make_extraction_error(
                "Plan Vivo",
                response.url,
                "page_structure_changed",
                "Plan Vivo approved-methodologies page no longer contains <article> blocks with PM### codes.",
                "Open the source page manually and update the article/code selectors.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str]] = set()
    for record in parsed_records:
        metadata = parse_plan_vivo_metadata(record["metadata_text"])
        document_url, supporting, doc_errors = collect_plan_vivo_documents(
            profile, record, response.url, metrics
        )
        errors.extend(doc_errors)
        if document_url:
            metrics["pv_primary_pdf_attached"] += 1
            candidates.extend(supporting)
        else:
            # Still capture supporting docs even when the primary PDF failed.
            candidates.extend(supporting)

        dedupe_key = (record["code"].lower(), document_url.lower())
        if dedupe_key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(dedupe_key)

        rich_notes = (
            "Extracted from the Plan Vivo approved-methodologies page; linked PDFs "
            "are captured but not fully parsed."
        )
        if metadata.get("type"):
            rich_notes = append_note(rich_notes, f"type: {metadata['type']}")
        if metadata.get("active_from"):
            rich_notes = append_note(rich_notes, f"active_from: {metadata['active_from']}")
        if metadata.get("developer"):
            rich_notes = append_note(rich_notes, f"developer: {metadata['developer']}")
        if metadata.get("reviewers"):
            rich_notes = append_note(rich_notes, f"reviewers: {metadata['reviewers']}")
        if record.get("description"):
            rich_notes = append_note(rich_notes, f"description: {record['description'][:200]}")

        version_value = f"Version {metadata['version']}" if metadata.get("version") else ""
        status_value = metadata.get("status") or "Approved"
        confidence = "high" if document_url and metadata.get("version") else "medium"
        candidate = make_candidate(
            profile,
            record["code"],
            record["title"] or f"{record['code']} (title requires review)",
            "approved_methodology",
            "",
            version_value,
            status_value,
            response.url,
            document_url,
            "plan_vivo_index_article_parse",
            confidence,
            rich_notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = f"Plan Vivo approved-methodology article ({record['code']})."
        candidates.append(candidate)
        metrics["pv_records_found"] += 1

    return dedupe_candidates(candidates), errors, metrics


BIOCARBON_CANONICAL_SOURCE_URL = "https://biocarbonstandard.com/en/afolu/"
BIOCARBON_CODE_RE = re.compile(r"\bBCR\d{4}\b")
BIOCARBON_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
BIOCARBON_ADOPTED_CODE_RE = re.compile(r"\b(?:AR-AMS[-\s]?[A-Z0-9.]+|AR-AM\d{4}|ACM\d{4}|AM\d{4}|AMS[-\s][A-Z0-9.]+)\b")
BIOCARBON_PRIMARY_ANCHOR_TEXTS = ("methodological document",)


def biocarbon_source_url(profile: dict) -> str:
    candidate = profile_source_url(profile)
    if candidate and "biocarbonstandard.com" in candidate.lower() and "/afolu" in candidate.lower():
        return candidate
    return BIOCARBON_CANONICAL_SOURCE_URL


def biocarbon_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(BIOCARBON_DOCUMENT_EXTENSIONS)


def find_biocarbon_card_container(node):
    """Walk up from an H3 until an ancestor also contains document anchors.

    BioCarbon Registry uses nested Elementor row containers; the H3 for a card
    sits in one column widget while the PDF anchors sit in a sibling widget.
    The lowest ancestor that carries any document anchor is the card wrapper.
    """
    current = node
    for _ in range(8):
        if current.parent is None:
            return current
        current = current.parent
        for anchor in current.find_all("a", href=True):
            if biocarbon_is_document_href(anchor.get("href", "")):
                return current
    return current


def classify_biocarbon_anchor(text: str, href: str) -> str:
    text_l = (text or "").strip().lower()
    href_l = (href or "").lower()
    if any(marker in text_l for marker in BIOCARBON_PRIMARY_ANCHOR_TEXTS):
        return "primary"
    if "public consultation" in text_l:
        return "public_consultation"
    if "previous versions" in text_l or "previous-versions" in href_l or "previous_versions" in href_l:
        return "previous_versions"
    if "guideline" in text_l or "directrices" in href_l:
        return "guideline"
    return "supporting"


def parse_biocarbon_heading(heading_text: str) -> tuple[str, str, str]:
    """Return (code, title, adopted_code) parsed from a BioCarbon card heading."""
    text = normalize_text(heading_text)
    bcr_match = BIOCARBON_CODE_RE.search(text)
    adopted_match = BIOCARBON_ADOPTED_CODE_RE.search(text)
    code = bcr_match.group(0) if bcr_match else ""
    adopted_code = adopted_match.group(0) if adopted_match else ""
    title = text
    if code:
        title = normalize_text(text[bcr_match.end():])
    return code, title, adopted_code


def collect_biocarbon_documents(profile: dict, code: str, title: str, source_url: str,
                                 container, is_adopted_external: bool, metrics: dict) -> tuple[str, str, list[dict], list[dict]]:
    """Return (primary_url, adopted_code_from_docs, supporting[], errors[]) for one card."""
    primary_url = ""
    adopted_code_from_docs = ""
    supporting: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    for anchor in container.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or not biocarbon_is_document_href(href):
            continue
        absolute = urljoin(source_url, href)
        text = normalize_text(anchor.get_text(" ", strip=True)) or absolute
        stage = classify_biocarbon_anchor(text, href)
        if stage == "primary":
            if not primary_url:
                primary_url = absolute
                seen_urls.add(absolute.lower())
                # Adopted-external sections have no BCR code; pull it from the PDF filename.
                if is_adopted_external:
                    external_match = BIOCARBON_ADOPTED_CODE_RE.search(href)
                    if external_match:
                        adopted_code_from_docs = external_match.group(0)
                continue
        key = absolute.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        candidate = make_candidate(
            profile,
            code,
            text,
            "supporting_document",
            "",
            "",
            "",
            source_url,
            absolute,
            "biocarbon_index_document",
            "medium",
            f"BioCarbon Registry supporting document for {code or 'adopted external'} "
            f"'{title}' (stage: {stage}); body not parsed.",
        )
        candidate["candidate_type"] = "supporting_document"
        candidate["classification_reason"] = f"BioCarbon Registry AFOLU card document ({stage})."
        candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {stage}")
        supporting.append(candidate)
        metrics["bcr_supporting_documents"] += 1
        if stage == "previous_versions":
            metrics["bcr_previous_version_bundles"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "BioCarbon Registry"),
                source_url,
                "document_link_missing",
                f"No primary 'Methodological Document' PDF was identified for '{code or title}' on the BioCarbon AFOLU page.",
                "Open the source page and confirm which anchor represents the current methodology PDF.",
            )
        )
        metrics["bcr_primary_pdf_missing"] += 1
    return primary_url, adopted_code_from_docs, supporting, errors


def extract_biocarbon_registry_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract methodology records from the BioCarbon Registry AFOLU page.

    Each methodology is laid out as an Elementor "row" that pairs an image-box
    widget (H3 with the ``BCR####`` code + title) with a button-widget column
    holding one or more document anchors ("Methodological Document",
    "Public Consultation Results", "Previous Versions", occasional
    "Guidelines…" links). A sibling "Coastal Ecosystems" card carries no BCR
    code and links to an adopted CDM methodology (``AR-AM0014``); that card is
    captured with ``unit_type = "adopted_external_method"`` and the CDM code
    extracted from the PDF filename.

    Version and status are not published on this page; both fields are left
    blank and reviewers are expected to open the PDF for that detail. Sector
    is derived from the H1 ("AFOLU Sector") and stored in ``notes`` with a
    label.
    """
    profile = get_program_profile(profiles, ["BioCarbon Registry", "BioCarbon Registry (BCR)"])
    metrics = {
        "bcr_records_found": 0,
        "bcr_adopted_external_records": 0,
        "bcr_primary_pdf_attached": 0,
        "bcr_primary_pdf_missing": 0,
        "bcr_supporting_documents": 0,
        "bcr_previous_version_bundles": 0,
    }
    errors: list[dict] = []
    source_url = biocarbon_source_url(profile)
    response, error = fetch_public_source(source_url, "BioCarbon Registry", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")
    sector_label = ""
    h1 = soup.find("h1")
    if h1:
        sector_label = normalize_text(h1.get_text(" ", strip=True))

    all_h3 = soup.find_all("h3")
    bcr_headings = []
    for heading in all_h3:
        code, title, _ = parse_biocarbon_heading(heading.get_text(" ", strip=True))
        if code:
            bcr_headings.append((heading, code, title, False))
        elif title and normalize_text(title).lower() in {"coastal ecosystems"}:
            bcr_headings.append((heading, "", title, True))

    if not bcr_headings:
        errors.append(
            make_extraction_error(
                "BioCarbon Registry",
                response.url,
                "no_records_found" if all_h3 else "page_structure_changed",
                "BioCarbon Registry AFOLU page did not expose any 'BCR####' methodology headings.",
                "Open the source page and confirm the AFOLU cards still start with a 'BCR####' H3.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str]] = set()
    for heading, code, title, is_adopted_external in bcr_headings:
        container = find_biocarbon_card_container(heading)
        primary_url, adopted_code_from_docs, supporting, doc_errors = collect_biocarbon_documents(
            profile, code, title, response.url, container, is_adopted_external, metrics
        )
        errors.extend(doc_errors)
        candidates.extend(supporting)

        effective_code = code or adopted_code_from_docs
        dedupe_key = (effective_code.lower(), primary_url.lower())
        if dedupe_key in seen_dedupe_keys and effective_code:
            continue
        seen_dedupe_keys.add(dedupe_key)

        rich_notes = (
            "Extracted from the BioCarbon Registry AFOLU page; linked PDFs are captured but not fully parsed."
        )
        if sector_label:
            rich_notes = append_note(rich_notes, f"sector: {sector_label}")
        if is_adopted_external:
            rich_notes = append_note(
                rich_notes,
                "adopted_external_methodology: this card links to an external methodology (e.g. CDM) rather than a native BCR PDF.",
            )
            if adopted_code_from_docs:
                rich_notes = append_note(rich_notes, f"adopted_external_code: {adopted_code_from_docs}")
            metrics["bcr_adopted_external_records"] += 1

        if primary_url:
            metrics["bcr_primary_pdf_attached"] += 1

        unit_type = "adopted_external_method" if is_adopted_external else "methodology"
        confidence = "high" if primary_url and effective_code else "medium"
        candidate = make_candidate(
            profile,
            effective_code,
            title or f"{effective_code} (title requires review)",
            unit_type,
            "",
            "",
            "",
            response.url,
            primary_url,
            "biocarbon_afolu_card_scan",
            confidence,
            rich_notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = (
            f"BioCarbon Registry adopted-external card ({adopted_code_from_docs or 'no code'})."
            if is_adopted_external
            else f"BioCarbon Registry AFOLU methodology card ({code})."
        )
        candidates.append(candidate)
        metrics["bcr_records_found"] += 1

    return dedupe_candidates(candidates), errors, metrics


CERCARBONO_CANONICAL_SOURCE_URL = "https://cercarbono.com/methodologies/"
CERCARBONO_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
CERCARBONO_NATIVE_PRIMARY_TEXTS = ("download methodology",)
CERCARBONO_CDM_PRIMARY_TEXTS = ("download excel", "download xlsx")
CERCARBONO_NATIVE_PROGRAMMES = (
    "carbon programme",
    "biodiversity programme",
    "circular economy programme",
)
CERCARBONO_CDM_PROGRAMMES = ("cdm methodologies",)
CERCARBONO_SECTION_H2_MARKERS = ("explore approved methodologies",)
CERCARBONO_VERSION_RE = re.compile(r"V[\s_.\-]?(\d+(?:[\._-]\d+)?)", re.IGNORECASE)


def cercarbono_source_url(profile: dict) -> str:
    candidate = profile_source_url(profile)
    if candidate and "cercarbono.com" in candidate.lower() and "methodolog" in candidate.lower():
        return candidate
    return CERCARBONO_CANONICAL_SOURCE_URL


def cercarbono_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(CERCARBONO_DOCUMENT_EXTENSIONS)


def find_cercarbono_card_container(node):
    """Walk up from an H4 heading until an ancestor also holds a document anchor.

    Cercarbono uses the same nested Elementor row-and-column pattern as
    BioCarbon Registry — the heading and its download link sit in sibling
    widgets under a common row container.
    """
    current = node
    for _ in range(8):
        if current.parent is None:
            return current
        current = current.parent
        for anchor in current.find_all("a", href=True):
            if cercarbono_is_document_href(anchor.get("href", "")):
                return current
    return current


def parse_cercarbono_version(text: str, href: str) -> str:
    """Return a normalized version string (e.g. ``V3.1``) parsed from filename or link text."""
    for source in (text, href):
        match = CERCARBONO_VERSION_RE.search(source or "")
        if match:
            return "V" + re.sub(r"[_\-]", ".", match.group(1))
    return ""


def cercarbono_programme_kind(programme_label: str) -> str:
    label_l = (programme_label or "").lower()
    if any(marker in label_l for marker in CERCARBONO_CDM_PROGRAMMES):
        return "cdm"
    if any(marker in label_l for marker in CERCARBONO_NATIVE_PROGRAMMES):
        return "native"
    return ""


def collect_cercarbono_documents(
    profile: dict,
    title: str,
    programme_label: str,
    programme_kind: str,
    source_url: str,
    container,
    metrics: dict,
) -> tuple[str, list[dict], list[dict]]:
    """Return (primary_url, supporting[], errors[]) for a single Cercarbono card."""
    primary_texts = CERCARBONO_CDM_PRIMARY_TEXTS if programme_kind == "cdm" else CERCARBONO_NATIVE_PRIMARY_TEXTS
    primary_url = ""
    supporting: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    for anchor in container.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or not cercarbono_is_document_href(href):
            continue
        absolute = urljoin(source_url, href)
        text = normalize_text(anchor.get_text(" ", strip=True)) or absolute
        text_l = text.lower()
        if not primary_url and any(marker in text_l for marker in primary_texts):
            primary_url = absolute
            seen_urls.add(absolute.lower())
            continue
        key = absolute.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        stage = "cdm_sector_catalogue" if programme_kind == "cdm" else "supplement"
        candidate = make_candidate(
            profile,
            "",
            text,
            "supporting_document",
            programme_label,
            "",
            "",
            source_url,
            absolute,
            "cercarbono_index_document",
            "medium",
            (
                f"Cercarbono supporting document for '{title}' "
                f"(programme: {programme_label}, stage: {stage}); body not parsed."
            ),
        )
        candidate["candidate_type"] = "supporting_document"
        candidate["classification_reason"] = f"Cercarbono methodology supporting document ({stage})."
        candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {stage}")
        supporting.append(candidate)
        metrics["cc_supporting_documents"] += 1

    if not primary_url:
        errors.append(
            make_extraction_error(
                profile.get("program_name", "Cercarbono"),
                source_url,
                "document_link_missing",
                f"No primary document was identified for '{title}' on the Cercarbono methodologies page.",
                "Open the source page and confirm the card still exposes a 'Download methodology' or 'Download Excel' anchor.",
            )
        )
        metrics["cc_primary_pdf_missing"] += 1
    return primary_url, supporting, errors


def extract_cercarbono_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract methodology records from the Cercarbono public methodologies page.

    The page groups H4 methodology cards under H3 programme headings:

    * ``Carbon programme`` / ``Biodiversity programme`` / ``Circular economy
      programme`` → native Cercarbono methodologies. Each card has a
      ``Download methodology`` primary PDF anchor; version is parsed from the
      PDF filename.
    * ``CDM methodologies`` → sector rows (Energy, Industry, …) each linking
      to an aggregate ``.xlsx`` catalogue of adopted CDM methods. Emitted as
      ``unit_type = "adopted_external_method"`` records because they are
      programme-level catalogues rather than per-methodology PDFs.

    Cards not sitting under a known programme heading (e.g. footer PDFs
    reached by the walk-up card container heuristic) are ignored. Machine
    codes are not published on the surface — reviewers open the PDF for the
    Cercarbono internal code — so ``methodunit_code`` is left blank and the
    dedupe key falls back to (title, version, document_url).
    """
    profile = get_program_profile(profiles, ["Cercarbono"])
    metrics = {
        "cc_records_found": 0,
        "cc_native_records": 0,
        "cc_adopted_cdm_records": 0,
        "cc_primary_pdf_attached": 0,
        "cc_primary_pdf_missing": 0,
        "cc_supporting_documents": 0,
    }
    errors: list[dict] = []
    source_url = cercarbono_source_url(profile)
    response, error = fetch_public_source(source_url, "Cercarbono", allow_insecure_ssl)
    if error:
        errors.append(error)
        return [], errors, metrics

    soup = BeautifulSoup(response.text, "html.parser")

    h4_headings = soup.find_all("h4")
    kept: list[tuple] = []  # (h4, title, programme_label, programme_kind)
    for heading in h4_headings:
        title = normalize_text(heading.get_text(" ", strip=True))
        if not title:
            continue
        # Bound to the "Explore approved methodologies" section — other H4s
        # (footer nav links, "Why our methodologies matter" quality tiles)
        # would otherwise attach to whatever programme H3 sat above them.
        preceding_h2 = heading.find_previous("h2")
        h2_text = normalize_text(preceding_h2.get_text(" ", strip=True)).lower() if preceding_h2 else ""
        if not any(marker in h2_text for marker in CERCARBONO_SECTION_H2_MARKERS):
            continue
        preceding_h3 = heading.find_previous("h3")
        programme_label = normalize_text(preceding_h3.get_text(" ", strip=True)) if preceding_h3 else ""
        programme_kind = cercarbono_programme_kind(programme_label)
        if not programme_kind:
            continue
        kept.append((heading, title, programme_label, programme_kind))

    if not kept:
        errors.append(
            make_extraction_error(
                "Cercarbono",
                response.url,
                "no_records_found" if h4_headings else "page_structure_changed",
                "Cercarbono methodologies page did not expose any H4 methodology cards under a known programme H3.",
                "Open the source page and confirm the 'Carbon programme'/'Biodiversity programme'/'Circular economy programme'/'CDM methodologies' groups still wrap H4 cards.",
            )
        )
        return [], errors, metrics

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str, str]] = set()
    for heading, title, programme_label, programme_kind in kept:
        container = find_cercarbono_card_container(heading)
        primary_url, supporting, doc_errors = collect_cercarbono_documents(
            profile, title, programme_label, programme_kind, response.url, container, metrics
        )
        errors.extend(doc_errors)
        candidates.extend(supporting)

        version = parse_cercarbono_version(title, primary_url)
        dedupe_key = (title.lower(), version.lower(), primary_url.lower())
        if dedupe_key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(dedupe_key)

        rich_notes = (
            "Extracted from the Cercarbono public methodologies page; linked PDFs are captured but not fully parsed."
        )
        rich_notes = append_note(rich_notes, f"category: {programme_label}")
        rich_notes = append_note(rich_notes, "language: English")
        if programme_kind == "cdm":
            rich_notes = append_note(
                rich_notes,
                "adopted_external_methodology: CDM sector catalogue (Excel spreadsheet lists the specific CDM methods adopted for this sector).",
            )
            metrics["cc_adopted_cdm_records"] += 1
        else:
            metrics["cc_native_records"] += 1

        if primary_url:
            metrics["cc_primary_pdf_attached"] += 1

        unit_type = "adopted_external_method" if programme_kind == "cdm" else "methodology"
        confidence = "high" if primary_url and (version or programme_kind == "cdm") else "medium"
        candidate = make_candidate(
            profile,
            "",
            title,
            unit_type,
            programme_label,
            version,
            "Approved",
            response.url,
            primary_url,
            "cercarbono_index_card_scan",
            confidence,
            rich_notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = (
            f"Cercarbono CDM sector catalogue ({programme_label})."
            if programme_kind == "cdm"
            else f"Cercarbono native methodology card ({programme_label})."
        )
        candidates.append(candidate)
        metrics["cc_records_found"] += 1

    return dedupe_candidates(candidates), errors, metrics


PURO_EARTH_LANDING_URL = "https://puro.earth/cdr-infrastructure/methodologies/"
PURO_EARTH_DOCUMENT_LIBRARY_URL = "https://puro.earth/cdr-infrastructure/methodologies/document-library/"
PURO_EARTH_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
PURO_EARTH_LEARN_MORE_TEXTS = ("learn more",)
PURO_EARTH_METHODOLOGY_DETAIL_PREFIX = "https://puro.earth/methodologies/"
PURO_EARTH_LIBRARY_H2_MARKERS = (
    "puro standard & methodologies",
    "puro standard and methodologies",
)
PURO_EARTH_PROGRAMME_H2_MARKERS = ("multi-program requirements",)
PURO_EARTH_TRANSITION_MARKERS = ("transition plan",)
PURO_EARTH_JS_SHELL_IDS = ("root", "app", "__next", "__nuxt")
PURO_EARTH_EDITION_RE = re.compile(
    r"Edition[\s._-]?(20\d{2})[\s(_-]*(?:version|v)?[\s._-]?(\d+(?:[._-]\d+)?)?", re.IGNORECASE
)
PURO_EARTH_VERSION_RE = re.compile(r"V[\s._-]?(\d+(?:[._-]\d+)?)", re.IGNORECASE)


def puro_earth_landing_url(profile: dict) -> str:
    candidate = profile_source_url(profile)
    if candidate and "puro.earth" in candidate.lower() and (
        "/methodolog" in candidate.lower() or "/carbon-removal-methods" in candidate.lower()
    ):
        return candidate
    return PURO_EARTH_LANDING_URL


def puro_earth_is_document_href(href: str) -> bool:
    href_l = (href or "").split("?", 1)[0].split("#", 1)[0].lower()
    return href_l.endswith(PURO_EARTH_DOCUMENT_EXTENSIONS)


def puro_earth_normalize_name(text: str) -> str:
    """Return a lowercase key with punctuation stripped for cross-page matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def parse_puro_earth_landing(soup, response_url: str) -> list[dict]:
    """Return methodology records with (title, detail_url) parsed from the landing page's H3 cards."""
    records: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        text = normalize_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor.get("href", "").strip()
        if not any(marker in text for marker in PURO_EARTH_LEARN_MORE_TEXTS):
            continue
        if PURO_EARTH_METHODOLOGY_DETAIL_PREFIX not in href.lower():
            continue
        heading = anchor.find_previous(["h3", "h4", "h2"])
        title = normalize_text(heading.get_text(" ", strip=True)) if heading else ""
        if not title:
            continue
        key = puro_earth_normalize_name(title)
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "title": title,
            "detail_url": urljoin(response_url, href.rstrip("/") + "/"),
        })
    return records


def parse_puro_earth_edition(text: str, href: str) -> str:
    """Return a normalized 'Edition YYYY vN' or 'Edition YYYY' string when parseable."""
    for source in (text, unquote(href or "")):
        if not source:
            continue
        edition_match = PURO_EARTH_EDITION_RE.search(source)
        if edition_match:
            year, version = edition_match.group(1), edition_match.group(2)
            if version:
                version_norm = re.sub(r"[_\-]", ".", version)
                return f"Edition {year} v{version_norm}"
            return f"Edition {year}"
        version_match = PURO_EARTH_VERSION_RE.search(source)
        if version_match:
            return "V" + re.sub(r"[_\-]", ".", version_match.group(1))
    return ""


def classify_puro_earth_pdf(anchor_text: str, href: str, methodology_title: str) -> str:
    text_l = normalize_text(anchor_text).lower()
    href_l = (href or "").lower()
    combined = f"{text_l} {href_l}"
    if any(marker in combined for marker in PURO_EARTH_TRANSITION_MARKERS):
        return "transition_plan"
    if "clarification" in combined:
        return "clarification"
    if "supplement" in combined or "annex" in combined:
        return "supplement"
    if "public consultation" in combined or "for consultation" in combined:
        return "public_consultation"
    if methodology_title and puro_earth_normalize_name(methodology_title) not in puro_earth_normalize_name(f"{text_l} {href_l}"):
        return "historical_version"
    return "supporting"


def puro_earth_pdf_search_text(anchor_text: str, href: str) -> str:
    """Return a URL-decoded, lowercased combination of anchor text + href for matching.

    Both inputs are unquoted before joining. Anchor text can be an
    icon-only fallback that carries the raw percent-encoded URL, and if we
    leave it encoded the score regex ends up matching ``%20`` + ``2025`` as
    year ``2020`` — a subtle but real bug.
    """
    return f"{normalize_text(unquote(anchor_text or '')).lower()} {unquote(href or '').lower()}"


def is_puro_earth_methodology_pdf(anchor_text: str, href: str, methodology_title: str) -> bool:
    """Return True when a PDF anchor plausibly represents a candidate for the primary methodology document.

    We trust the H3 heading match (established by ``library_by_key``) to
    scope a PDF to its methodology, so we only reject anchors whose
    **filename** clearly labels a transition plan, clarification, annex, or
    consultation draft. Folder paths are ignored — Puro sometimes stores the
    current published PDF under ``Public Consultations/`` even after the
    consultation closed.
    """
    filename = unquote(href or "").rsplit("/", 1)[-1].lower()
    if not filename:
        return False
    if "transition" in filename:
        return False
    if any(term in filename for term in ("clarification", "annex", "summary of", "public comment", "consultation")):
        return False
    return True


def score_puro_earth_primary_pdf(anchor_text: str, href: str) -> tuple[int, int, int]:
    """Rank a candidate primary PDF: higher edition year, then higher version, then shorter filename."""
    combined = puro_earth_pdf_search_text(anchor_text, href)
    year_match = re.search(r"edition\s*(20\d{2})|(20\d{2})", combined, re.IGNORECASE)
    year = int(year_match.group(1) or year_match.group(2)) if year_match else 0
    version_match = re.search(r"v[\s._-]?(\d+)", combined, re.IGNORECASE)
    version = int(version_match.group(1)) if version_match else 0
    # Prefer shorter filenames (avoids picking a "For Publication" archive over the canonical name).
    inverse_len = -len(href or "")
    return (year, version, inverse_len)


def collect_puro_earth_library_sections(soup, response_url: str) -> list[dict]:
    """Group document-library PDF anchors under their nearest preceding H3 heading."""
    sections: list[dict] = []
    current = None
    for element in soup.find_all(["h2", "h3", "a"]):
        if element.name == "h2":
            heading_text = normalize_text(element.get_text(" ", strip=True))
            current = {"section": heading_text, "heading": "", "pdfs": []}
            sections.append(current)
            continue
        if element.name == "h3":
            heading_text = normalize_text(element.get_text(" ", strip=True))
            current = {"section": sections[-1]["section"] if sections else "", "heading": heading_text, "pdfs": []}
            sections.append(current)
            continue
        if element.name == "a":
            href = element.get("href", "").strip()
            if not href or not puro_earth_is_document_href(href):
                continue
            if current is None:
                current = {"section": "", "heading": "", "pdfs": []}
                sections.append(current)
            absolute = urljoin(response_url, href)
            current["pdfs"].append({
                "text": normalize_text(element.get_text(" ", strip=True)) or absolute,
                "href": href,
                "url": absolute,
            })
    return [section for section in sections if section["pdfs"] or section["heading"]]


def extract_puro_earth_candidates(profiles: pd.DataFrame, allow_insecure_ssl: bool = False) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract methodology records from Puro.earth's public methodologies + document library.

    Two pages are consulted:

    * ``/cdr-infrastructure/methodologies/`` provides the canonical list of 8
      methodology cards (H3 title + ``learn more`` anchor to a per-methodology
      detail page).
    * ``/cdr-infrastructure/methodologies/document-library/`` groups every
      HubSpot-hosted PDF by H3 heading. Sections whose heading matches a
      landing-page methodology contribute the primary PDF + supporting
      documents (transition plans, historical editions, clarifications).
      Sections under ``Multi-program requirements`` are captured as
      programme-level supporting documents (Certification Procedures, Common
      Criteria, Puro Standard General Rules, Article 6, Additionality, …).

    Non-schema fields (``category``, ``removal_type``, ``version``, ``status``)
    are surfaced via labelled ``notes`` entries so ``CANDIDATE_SCHEMA`` is
    preserved. Detail-page follow-through is **not** required for the current
    methodology PDFs; the extractor never fetches per-methodology detail
    pages because the document library already exposes the current PDFs.
    """
    profile = get_program_profile(profiles, ["Puro Earth", "Puro.earth"])
    metrics = {
        "pe_records_found": 0,
        "pe_landing_methodologies_seen": 0,
        "pe_library_pdfs_seen": 0,
        "pe_primary_pdf_attached": 0,
        "pe_primary_pdf_missing": 0,
        "pe_supporting_documents": 0,
        "pe_programme_documents": 0,
        "pe_document_library_fetch_failed": 0,
    }
    errors: list[dict] = []
    landing_url = puro_earth_landing_url(profile)
    landing_response, landing_error = fetch_public_source(landing_url, "Puro Earth", allow_insecure_ssl)
    if landing_error:
        errors.append(landing_error)
        return [], errors, metrics

    landing_soup = BeautifulSoup(landing_response.text, "html.parser")
    # Detect JS shells even though we expect static HTML.
    for shell_id in PURO_EARTH_JS_SHELL_IDS:
        if landing_soup.find(id=shell_id):
            errors.append(
                make_extraction_error(
                    "Puro Earth",
                    landing_response.url,
                    "js_shell_detected",
                    f"Puro Earth landing page contains a '#{shell_id}' shell — content may be JS-rendered.",
                    "Manually verify whether methodology names are still present in raw HTML.",
                )
            )

    landing_records = parse_puro_earth_landing(landing_soup, landing_response.url)
    metrics["pe_landing_methodologies_seen"] = len(landing_records)
    if not landing_records:
        errors.append(
            make_extraction_error(
                "Puro Earth",
                landing_response.url,
                "page_structure_changed",
                "Puro Earth methodologies landing page exposed no H3 methodology cards with 'learn more' detail links.",
                "Open the source page and update the landing-page card selector.",
            )
        )
        return [], errors, metrics

    library_response, library_error = fetch_public_source(
        PURO_EARTH_DOCUMENT_LIBRARY_URL, "Puro Earth", allow_insecure_ssl
    )
    library_soup = None
    library_sections: list[dict] = []
    if library_error:
        metrics["pe_document_library_fetch_failed"] = 1
        errors.append(library_error)
    else:
        library_soup = BeautifulSoup(library_response.text, "html.parser")
        library_sections = collect_puro_earth_library_sections(library_soup, library_response.url)
        metrics["pe_library_pdfs_seen"] = sum(len(section["pdfs"]) for section in library_sections)

    # Build a lookup from methodology name key → collected PDFs (with section H2).
    library_by_key: dict[str, list[dict]] = {}
    programme_pdfs: list[dict] = []
    for section in library_sections:
        section_h2_l = (section.get("section") or "").lower()
        heading = section.get("heading") or ""
        key = puro_earth_normalize_name(heading)
        if any(marker in section_h2_l for marker in PURO_EARTH_PROGRAMME_H2_MARKERS):
            for pdf in section["pdfs"]:
                programme_pdfs.append({"section": section["section"], "heading": heading, **pdf})
            continue
        if not any(marker in section_h2_l for marker in PURO_EARTH_LIBRARY_H2_MARKERS):
            # Sections that fall outside the two H2s we care about are ignored to avoid
            # picking up navigation-heading noise.
            continue
        if key:
            library_by_key.setdefault(key, []).extend(section["pdfs"])

    candidates: list[dict] = []
    seen_dedupe_keys: set[tuple[str, str, str]] = set()
    for record in landing_records:
        methodology_title = record["title"]
        key = puro_earth_normalize_name(methodology_title)
        primary_url = ""
        version = ""
        supporting: list[dict] = []
        # Match library PDFs to this methodology by its normalized H3 name, including
        # fuzzy substring matches so partial-name headings still contribute PDFs.
        library_hits: list[dict] = list(library_by_key.get(key, []))
        for heading_key, pdfs in library_by_key.items():
            if heading_key == key or not key:
                continue
            if key in heading_key or heading_key in key:
                for pdf in pdfs:
                    if pdf not in library_hits:
                        library_hits.append(pdf)

        # Rank matching PDFs and pick the highest-scoring one as primary. A PDF
        # is "primary-eligible" if its filename/anchor mentions the methodology
        # title (after URL-decoding) and does not look like a transition plan,
        # clarification, or public consultation draft.
        eligible = [
            pdf for pdf in library_hits
            if is_puro_earth_methodology_pdf(pdf["text"], pdf["href"], methodology_title)
        ]
        if eligible:
            best = max(eligible, key=lambda pdf: score_puro_earth_primary_pdf(pdf["text"], pdf["href"]))
            primary_url = best["url"]
            version = parse_puro_earth_edition(best["text"], best["href"])

        # Emit any remaining PDFs from the same section as supporting docs.
        for pdf in library_hits:
            if pdf["url"] == primary_url:
                continue
            stage = classify_puro_earth_pdf(pdf["text"], pdf["href"], methodology_title)
            supporting_notes = (
                f"Puro Earth supporting document for '{methodology_title}' "
                f"(stage: {stage}); body not parsed."
            )
            candidate = make_candidate(
                profile,
                "",
                pdf["text"] or pdf["url"],
                "supporting_document",
                methodology_title,
                parse_puro_earth_edition(pdf["text"], pdf["href"]),
                "",
                record["detail_url"] or landing_response.url,
                pdf["url"],
                "puro_earth_library_document",
                "medium",
                supporting_notes,
            )
            candidate["candidate_type"] = "supporting_document"
            candidate["classification_reason"] = f"Puro Earth methodology supporting document ({stage})."
            candidate["notes"] = append_note(candidate["notes"], f"evidence_stage: {stage}")
            supporting.append(candidate)
            metrics["pe_supporting_documents"] += 1

        candidates.extend(supporting)

        dedupe_key = (
            key,
            (version or "").lower(),
            (primary_url or "").lower(),
        )
        if dedupe_key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(dedupe_key)

        rich_notes = (
            "Extracted from the Puro.earth methodologies landing + document library; "
            "linked PDFs are captured but not fully parsed."
        )
        rich_notes = append_note(rich_notes, f"category: {methodology_title}")
        rich_notes = append_note(rich_notes, f"removal_type: {methodology_title}")
        if version:
            rich_notes = append_note(rich_notes, f"version: {version}")
        rich_notes = append_note(rich_notes, "status: Live (published on Puro Standard document library)")
        if not primary_url:
            rich_notes = append_note(rich_notes, "primary PDF not identified in document library; reviewer should confirm.")
            errors.append(
                make_extraction_error(
                    "Puro Earth",
                    record["detail_url"] or landing_response.url,
                    "document_link_missing",
                    f"No primary PDF was matched for '{methodology_title}' in the Puro.earth document library.",
                    "Confirm the current methodology PDF filename or update the anchor-matching heuristic.",
                )
            )
            metrics["pe_primary_pdf_missing"] += 1
        else:
            metrics["pe_primary_pdf_attached"] += 1

        confidence = "high" if primary_url and version else "medium" if primary_url else "low"
        candidate = make_candidate(
            profile,
            "",
            methodology_title,
            "methodology",
            methodology_title,
            version,
            "Live",
            landing_response.url,
            primary_url,
            "puro_earth_landing_plus_library",
            confidence,
            rich_notes,
        )
        candidate["candidate_type"] = "methodunit_candidate"
        candidate["classification_reason"] = f"Puro Earth methodology card ({methodology_title})."
        candidates.append(candidate)
        metrics["pe_records_found"] += 1

    # Emit programme-level docs from "Multi-program requirements" as extra supporting rows.
    for pdf in programme_pdfs:
        candidate = make_candidate(
            profile,
            "",
            pdf["text"] or pdf["url"],
            "supporting_document",
            "",
            parse_puro_earth_edition(pdf["text"], pdf["href"]),
            "",
            landing_response.url,
            pdf["url"],
            "puro_earth_programme_document",
            "medium",
            (
                f"Puro Earth programme-level document ({pdf['section']} / {pdf['heading']}); "
                "linked to the Puro Standard rather than a single methodology."
            ),
        )
        candidate["candidate_type"] = "supporting_document"
        candidate["classification_reason"] = "Puro Earth programme-level standard/requirement document."
        candidate["notes"] = append_note(candidate["notes"], "evidence_stage: programme_requirement")
        candidates.append(candidate)
        metrics["pe_programme_documents"] += 1

    return dedupe_candidates(candidates), errors, metrics


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
