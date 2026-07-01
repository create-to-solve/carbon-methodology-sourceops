# Carbon Methodology SourceOps Workbench

`Carbon Methodology SourceOps Workbench` is a local Streamlit prototype for the upstream source-intelligence workflow behind a carbon-market methodology catalogue.

## Problem

Carbon methodology information is scattered across heterogeneous official sources. Some programmes publish clean HTML tables, some use documentation portals, some publish PDFs, some adopt external methods, some use JS-heavy portals, and some have no clear methodology page. A single generic scraper will not reliably handle this landscape.

## Approach

This app acts as a SourceOps layer before catalogue ingestion. It helps an analyst:

1. Maintain a **Source Registry** of official source locations.
2. Run bounded **Live Source Checks**.
3. Run supported **Connector Extraction** workflows.
4. Review **Candidate MethodUnits**.
5. Preserve **Evidence Links**.
6. Track **QA Exceptions**.
7. Prepare **Catalogue Export** files.

The app does not approve methodologies. It produces review-ready evidence and candidates.

## Workflow

```text
Source Registry
-> Live Source Check
-> Connector Extraction
-> Candidate MethodUnits
-> Evidence Links
-> QA Exceptions
-> Review
-> Catalogue Export
```

## App Pages

- **Start Here**: First-time reviewer briefing: problem, role of the app, pipeline, proof points, and current capability snapshot.
- **Extraction Strategies**: Explains source archetypes and why one scraper is not enough.
- **Current Capabilities**: Summarizes what works today and shows connector status.
- **Interpreting Outputs**: Defines Candidate MethodUnits, Evidence Links, QA Exceptions, Review Queue, and Catalogue Export.
- **Source Registry**: Filterable source registry from `source_profiles_final_fixed.csv`.
- **Run Connectors**: Source pre-checks and supported Candidate Extraction.
- **Candidate Review**: Review Queue for current, uploaded, or saved Candidate MethodUnits.
- **Evidence Links**: Full classified source-link audit table.
- **QA & Exceptions**: Data-quality issues, source-access failures, extraction errors, and review-needed records.
- **Export**: Download or timestamp-save current outputs.
- **Roadmap / Strategy Notes**: Connector strategy, extraction waves, MethodUnit rationale, and roadmap context.

## Current Capabilities

- Source Registry loads the current programme source profile table.
- Live Source Check can verify selected source URLs.
- Climate Action Reserve connector extracts structured protocol table candidates.
- ICR connector discovers M-ICR methodology codes and detail URLs, with conservative title enrichment.
- Asia Carbon Institute source-access/SSL failures are logged rather than bypassed by default.
- Evidence Links are classified as:
  - `methodunit_candidate`
  - `supporting_document`
  - `development_page`
  - `navigation_link`
  - `exclude`
- Export supports Candidate MethodUnits, Evidence Links, QA flags, Source Registry rows, and extraction errors.

## Supported Connectors

- **Climate Action Reserve**: working structured-table extraction.
- **International Carbon Registry / ICR**: discovery-only / needs title review.
- **Asia Carbon Institute**: blocked or source-exception-prone due to SSL/source access.

Other sources are represented in the Source Registry and strategy views but are not yet implemented as connectors.

## Limitations

- No linked PDFs are fetched.
- No JavaScript-heavy portals are automated yet.
- No logins, paywalls, CAPTCHAs, DocSend gates, or access controls are bypassed.
- No accounts are created.
- No database is used.
- Review decisions are not persisted automatically.
- Classification is rule-based and requires human review.
- High confidence means extraction confidence, not business, legal, or carbon-market approval.

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

The Export page can write timestamped files to `outputs/`, including:

- `methodunit_candidates_review_YYYYMMDD_HHMMSS.csv`
- `extracted_source_links_full_YYYYMMDD_HHMMSS.csv`
- `extraction_errors_YYYYMMDD_HHMMSS.csv`
- `source_registry_YYYYMMDD_HHMMSS.csv`
- `qa_flags_YYYYMMDD_HHMMSS.csv`

## Next Development Priorities

1. Repair or confirm stale Source Registry URLs before building more connectors.
2. Add the next stable HTML catalogue connector, likely ACR after URL repair.
3. Add controlled PDF metadata extraction for document-first sources.
4. Add persistent review decisions.
5. Add catalogue import validation once the Candidate MethodUnit schema stabilizes.
