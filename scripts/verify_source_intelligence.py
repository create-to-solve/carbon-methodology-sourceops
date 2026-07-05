"""Read-only verifier for the research-derived source intelligence.

Reads the two source-intelligence CSVs, fetches each recorded URL, records
lightweight signals (status, size, keyword hits, code hits, PDF count, JS
likelihood) and writes ``outputs/source_verification_results.csv``. It is a
verification runner only; it does not extract methodology records, does not
download PDF bodies, and does not attempt to bypass any access control.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

try:
    import requests
except ImportError as exc:  # pragma: no cover - script prerequisite
    raise SystemExit("requests is required to run verify_source_intelligence.py") from exc

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - script prerequisite
    raise SystemExit("beautifulsoup4 is required to run verify_source_intelligence.py") from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "source_intelligence"
OUTPUTS_DIR = REPO_ROOT / "outputs"
DEMO_DIR = OUTPUTS_DIR / "demo_latest"

VERIFICATION_PLAN_FILE = DATA_DIR / "source_verification_plan.csv"
CONNECTOR_MATRIX_FILE = DATA_DIR / "connector_source_matrix_synthesized.csv"
RESULTS_FILE = OUTPUTS_DIR / "source_verification_results.csv"
DEMO_RESULTS_FILE = DEMO_DIR / "source_verification_results.csv"

POLITE_USER_AGENT = (
    "CarbonMethodologySourceOpsWorkbench/0.1 "
    "(local prototype; source verification runner; no bulk scraping)"
)
TIMEOUT_SECONDS = 20
MAX_HTML_BYTES = 2_000_000  # cap parsed HTML size; verification does not need full PDFs

RESULT_SCHEMA = [
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

METHODOLOGY_KEYWORDS = (
    "methodology",
    "methodologies",
    "protocol",
    "protocols",
    "module",
    "modules",
    "standard",
    "standards",
    "quantification",
    "sectoral scope",
    "afolu",
    "removal",
)

DETAIL_LINK_HINTS = (
    "methodolog",
    "protocol",
    "module",
    "standard",
    "method-",
    "/method/",
    "/protocol/",
    "/methodologies/",
)

CODE_REGEXES: dict[str, re.Pattern] = {
    # existing extractor codes
    "M-ICR": re.compile(r"\bM-ICR\s*\d{3,}\b", re.IGNORECASE),
    "CDM ACM/AM/AMS": re.compile(r"\b(?:ACM\d{4}|AM\d{4}|AMS[-\s][A-Z0-9.]+)\b", re.IGNORECASE),
    # research targets
    "ACR": re.compile(r"\bACR[-\s]?[0-9]{3,}\b", re.IGNORECASE),
    "SCM (SocialCarbon)": re.compile(r"\bSCM[-\s]?\d{3,}\b", re.IGNORECASE),
    "BCR (BioCarbon)": re.compile(r"\bBCR[-\s]?[A-Z0-9\-]{2,}\b"),
    "PM (Puro)": re.compile(r"\bPM[-\s]?\d{2,}\b"),
    "CC-M (Credible Carbon)": re.compile(r"\bCC-M\d{3}(?:-[A-Z])?\b", re.IGNORECASE),
    "TREES": re.compile(r"\bTREES\b"),
    "VMD/VMR/VM (Verra)": re.compile(r"\bV(?:MD|MR|M)\d{3,}\b"),
    "GS (Gold Standard)": re.compile(r"\bGS\s?\d{3,}\b"),
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


URL_TOKEN_RE = re.compile(r"https?://[^\s,;]+", re.IGNORECASE)


def load_targets() -> list[dict]:
    """Return de-duplicated (programme, url, role) tuples from plan + matrix.

    Cells may contain more than one URL or trailing prose (e.g. "(reported)").
    We take every ``http(s)://…`` token we can find, stripping trailing
    punctuation, so verification treats each URL individually instead of
    fetching a garbled compound string.
    """

    targets: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(programme: str, cell: str, role: str) -> None:
        programme = (programme or "").strip()
        if not programme:
            return
        for match in URL_TOKEN_RE.findall(cell or ""):
            url = match.rstrip(").,;'\"")
            key = (programme, url)
            if key in seen:
                continue
            seen.add(key)
            targets.append({"programme_name": programme, "url_checked": url, "url_role": role})

    if VERIFICATION_PLAN_FILE.exists():
        plan = normalize_columns(pd.read_csv(VERIFICATION_PLAN_FILE, dtype=str).fillna(""))
        for _, row in plan.iterrows():
            add(row.get("programme_name", ""), row.get("url_to_verify", ""), "plan_primary")
            add(row.get("programme_name", ""), row.get("secondary_url_to_verify", ""), "plan_secondary")

    if CONNECTOR_MATRIX_FILE.exists():
        matrix = normalize_columns(pd.read_csv(CONNECTOR_MATRIX_FILE, dtype=str).fillna(""))
        for _, row in matrix.iterrows():
            add(row.get("programme_name", ""), row.get("methodology_source_url", ""), "matrix_methodology")
            add(row.get("programme_name", ""), row.get("document_library_url", ""), "matrix_document_library")

    return targets


def fetch(url: str) -> tuple[requests.Response | None, str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": POLITE_USER_AGENT},
            allow_redirects=True,
            timeout=TIMEOUT_SECONDS,
        )
        return response, ""
    except requests.exceptions.SSLError as exc:
        return None, f"ssl_error: {exc}"
    except requests.exceptions.Timeout as exc:
        return None, f"timeout: {exc}"
    except requests.exceptions.ConnectionError as exc:
        return None, f"connection_error: {exc}"
    except requests.RequestException as exc:
        return None, f"request_error: {exc}"


def is_html(content_type: str) -> bool:
    return "html" in (content_type or "").lower()


def is_pdf(content_type: str, final_url: str) -> bool:
    if "pdf" in (content_type or "").lower():
        return True
    return final_url.lower().endswith(".pdf")


def classify_link_role(text: str, href: str) -> str:
    combined = f"{(text or '').lower()} {(href or '').lower()}"
    if href and href.lower().endswith(".pdf"):
        return "pdf"
    if any(hint in combined for hint in DETAIL_LINK_HINTS):
        return "detail"
    return "other"


def detect_js_likely_required(soup: BeautifulSoup, visible_text_len: int, anchor_count: int) -> bool:
    if soup.find(id=re.compile(r"^(root|app|__next|__nuxt)$")):
        if visible_text_len < 2000 or anchor_count < 10:
            return True
    scripts = soup.find_all("script", src=True)
    if len(scripts) > 6 and anchor_count < 10 and visible_text_len < 2000:
        return True
    return False


def analyze_html(text: str) -> dict:
    soup = BeautifulSoup(text, "html.parser")
    visible_text = soup.get_text(" ", strip=True)
    visible_lower = visible_text.lower()

    anchors = soup.find_all("a", href=True)
    total_links = len(anchors)
    pdf_links = sum(1 for a in anchors if a["href"].lower().endswith(".pdf"))
    likely_detail = 0
    pdf_filename_texts = []
    for a in anchors:
        role = classify_link_role(a.get_text(" ", strip=True), a["href"])
        if role == "detail":
            likely_detail += 1
        if role == "pdf":
            pdf_filename_texts.append(a["href"])

    keywords_hit = sorted({kw for kw in METHODOLOGY_KEYWORDS if kw in visible_lower})

    code_hits: dict[str, int] = {}
    search_space = visible_text + " " + " ".join(pdf_filename_texts)
    for label, pattern in CODE_REGEXES.items():
        n = len(pattern.findall(search_space))
        if n:
            code_hits[label] = n

    # Conservative records_detected estimate.
    code_total = sum(code_hits.values())
    heading_hits = 0
    for tag in soup.find_all(["h2", "h3"]):
        if any(kw in tag.get_text(" ", strip=True).lower() for kw in METHODOLOGY_KEYWORDS):
            heading_hits += 1
    records_detected = min(max(code_total, likely_detail, heading_hits), 500)

    js_required = detect_js_likely_required(soup, len(visible_text), total_links)

    return {
        "total_links": total_links,
        "pdf_links": pdf_links,
        "likely_detail_links": likely_detail,
        "methodology_keywords_hit": "; ".join(keywords_hit),
        "codes_detected": "; ".join(f"{label}:{count}" for label, count in sorted(code_hits.items())),
        "records_detected": records_detected,
        "js_likely_required": "Yes" if js_required else "No",
        "visible_text_len": len(visible_text),
    }


def classify(status: str) -> str:
    return status  # placeholder for symmetry; classification is inlined below


def verify_target(target: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    row = {column: "" for column in RESULT_SCHEMA}
    row.update(target)
    row["checked_at"] = now
    row["fetch_ok"] = "No"

    response, error = fetch(target["url_checked"])
    if response is None:
        row["error_message"] = error
        row["verification_status"] = "access_or_fetch_issue"
        row["notes"] = "Fetch failed; open the URL manually and reassess."
        return row

    content_type = response.headers.get("content-type", "")
    row["http_status"] = response.status_code
    row["final_url"] = response.url
    row["content_type"] = content_type
    row["response_size_bytes"] = len(response.content)

    if response.status_code != 200:
        row["error_message"] = f"non_200_status: {response.status_code}"
        row["verification_status"] = "access_or_fetch_issue"
        row["notes"] = "Server returned non-200. Confirm URL is still the canonical source."
        return row

    row["fetch_ok"] = "Yes"

    if is_pdf(content_type, response.url):
        row["verification_status"] = "verified_document_source"
        row["notes"] = "URL resolves to a single document; treat as document-family source."
        row["pdf_links"] = 1
        row["records_detected"] = 1
        return row

    if not is_html(content_type):
        row["verification_status"] = "needs_manual_review"
        row["notes"] = f"Non-HTML content-type ({content_type}); review manually."
        return row

    if len(response.content) > MAX_HTML_BYTES:
        row["notes"] = "HTML body larger than analyzer cap; parsing only the head of the response."
        text = response.text[:MAX_HTML_BYTES]
    else:
        text = response.text

    analysis = analyze_html(text)
    row.update({
        "total_links": analysis["total_links"],
        "pdf_links": analysis["pdf_links"],
        "likely_detail_links": analysis["likely_detail_links"],
        "methodology_keywords_hit": analysis["methodology_keywords_hit"],
        "codes_detected": analysis["codes_detected"],
        "records_detected": analysis["records_detected"],
        "js_likely_required": analysis["js_likely_required"],
    })

    records = analysis["records_detected"]
    js_flag = analysis["js_likely_required"] == "Yes"
    if js_flag and records == 0:
        row["verification_status"] = "likely_js_required"
        row["notes"] = "Static HTML has app/root shell and little visible text; needs JS-capable fetcher."
    elif js_flag and records > 0:
        row["verification_status"] = "likely_js_required"
        row["notes"] = "Some records detected, but page shows JS shell markers; verify manually before coding."
    elif records == 0:
        row["verification_status"] = "no_records_detected"
        row["notes"] = "Page reachable but no methodology-shaped records found by heuristics."
    else:
        row["verification_status"] = "verified_static_source"
        row["notes"] = "Static HTML reachable with methodology signals; safe to attempt connector."
    return row


def summarize(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verification_status"]] = counts.get(row["verification_status"], 0) + 1
    return counts


def main() -> int:
    targets = load_targets()
    if not targets:
        print("No verification targets found. Check data/source_intelligence/ inputs.", file=sys.stderr)
        return 1

    results: list[dict] = []
    for i, target in enumerate(targets, 1):
        print(f"[{i:>2}/{len(targets)}] {target['programme_name']} <- {target['url_role']} : {target['url_checked']}")
        result = verify_target(target)
        print(f"        -> {result['verification_status']} (records={result['records_detected']}, pdfs={result['pdf_links']})")
        results.append(result)

    df = pd.DataFrame(results, columns=RESULT_SCHEMA)
    OUTPUTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_FILE, index=False)
    if DEMO_DIR.exists():
        df.to_csv(DEMO_RESULTS_FILE, index=False)

    print()
    print(f"Wrote {len(df)} rows to {RESULTS_FILE}")
    print("Verification summary by status:")
    for status, count in sorted(summarize(results).items()):
        print(f"  {status:32s} {count}")
    failed = [r for r in results if r["verification_status"] == "access_or_fetch_issue"]
    if failed:
        print("Failed URLs:")
        for r in failed:
            print(f"  {r['programme_name']:35s} {r['url_checked']}  ({r['error_message']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
