# Carbon Methodology SourceOps Workbench

`Carbon Methodology SourceOps Workbench` is a local Streamlit prototype for preparing methodology-source information before it enters a carbon methodology catalogue.

## Problem

Carbon methodology information is scattered across official sources that look very different from one another: tables, documentation portals, PDFs, adopted external methods, JS-heavy portals, and sometimes unclear source pages. One generic scraper is not enough.

## Approach

The app helps an analyst:

1. Maintain a **Source Registry** of official source locations.
2. Check whether official source pages are reachable.
3. Run supported **source-specific extractors**.
4. Review **extracted methodology records**.
5. Preserve **Supporting Links**.
6. Track **Issues to Resolve**.
7. Prepare **Export for Catalogue** files.

The app does not approve methodologies. It produces review-ready records and evidence.

## Workflow

```text
Source Registry
-> Live Source Check
-> Source-Specific Extraction
-> Extracted Methodology Records
-> Supporting Links
-> Issues to Resolve
-> Review
-> Export for Catalogue
```

## App Pages

- **Start Here**: First-time reviewer briefing: problem, role of the app, pipeline, proof points, and current capability snapshot.
- **Extraction Strategies**: Explains source archetypes and why one scraper is not enough.
- **Current Capabilities**: Summarizes what works today and shows extractor status.
- **How to Read the Outputs**: Defines extracted records, Supporting Links, Issues to Resolve, Review Queue, and Export for Catalogue.
- **Source Registry**: Filterable source registry from `source_profiles_final_fixed.csv`.
- **Extract from Sources**: Source pre-checks and supported source-specific extraction.
- **Review Extracted Records**: Review queue for current, uploaded, or saved extracted methodology records.
- **Supporting Links**: Full classified source-link audit table.
- **Issues to Resolve**: Data-quality issues, source-access failures, extraction errors, and review-needed records.
- **Export for Catalogue**: Download or timestamp-save review-ready outputs.
- **Roadmap**: Extraction strategy, extraction waves, MethodUnit rationale, and future priorities.

## Current Capabilities

- Source Registry loads the current programme source profile table.
- Live Source Check can verify selected source URLs.
- Climate Action Reserve extractor pulls structured protocol table records.
- ICR extractor discovers M-ICR methodology codes and detail URLs, with conservative title review.
- Asia Carbon Institute source-access/SSL failures are logged rather than bypassed by default.
- Supporting Links are classified as:
  - `methodunit_candidate`
  - `supporting_document`
  - `development_page`
  - `navigation_link`
  - `exclude`
- Export for Catalogue supports extracted methodology records, Supporting Links, QA flags, Source Registry rows, and extraction errors.

## Supported Source-Specific Extractors

- **Climate Action Reserve**: working structured-table extraction.
- **International Carbon Registry / ICR**: discovery-only / needs title review.
- **Asia Carbon Institute**: blocked or source-exception-prone due to SSL/source access.

Other sources are represented in the Source Registry and Roadmap but are not yet implemented as extractors.

## How to Read Confidence

High confidence means the extraction looked structurally strong. It does not mean the methodology is legally, commercially, or carbon-market approved. All extracted records require human review before catalogue ingestion.

## Limitations

- No linked PDFs are fetched.
- No JavaScript-heavy portals are automated yet.
- No logins, paywalls, CAPTCHAs, DocSend gates, or access controls are bypassed.
- No accounts are created.
- No database is used.
- Review decisions are not persisted automatically.
- Classification is rule-based and requires human review.

## How to Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

Expected input files under `data/`:

- `source_profiles_final_fixed.csv`
- `connector_strategy_fixed.csv`
- `extraction_waves_fixed.csv`
- `qa_flags_fixed.csv`
- `next_actions_fixed.csv`

## Outputs

The Export for Catalogue page can write timestamped files to `outputs/`, including:

- `methodunit_candidates_review_YYYYMMDD_HHMMSS.csv`
- `extracted_source_links_full_YYYYMMDD_HHMMSS.csv`
- `extraction_errors_YYYYMMDD_HHMMSS.csv`
- `source_registry_YYYYMMDD_HHMMSS.csv`
- `qa_flags_YYYYMMDD_HHMMSS.csv`

## Next Development Priorities

1. Repair or confirm stale Source Registry URLs before building more extractors.
2. Add the next stable HTML catalogue extractor, likely ACR after URL repair.
3. Add controlled PDF metadata extraction for document-first sources.
4. Add persistent review decisions.
5. Add catalogue import validation once the extracted-record schema stabilizes.
