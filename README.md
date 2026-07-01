# Carbon Methodology SourceOps Workbench

`Carbon Methodology SourceOps Workbench` is a local Streamlit prototype for running an upstream SourceOps workflow behind a carbon-market methodology catalogue.

The app is organized around this operating flow:

```text
Source Registry
-> Run Connectors
-> Candidate MethodUnits
-> Evidence Links
-> QA / Exceptions
-> Export to Catalogue
-> Strategy Notes
```

It reads the cleaned local CSV files in `data/`, runs only small user-triggered checks or supported connectors, and keeps extracted outputs in the Streamlit session until downloaded or explicitly saved to `outputs/`.

## How to Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
streamlit run app.py
```

## Expected Input CSV Files

The app expects these files under `data/`:

- `source_profiles_final_fixed.csv`
- `connector_strategy_fixed.csv`
- `extraction_waves_fixed.csv`
- `qa_flags_fixed.csv`
- `next_actions_fixed.csv`

CSV headers are normalized defensively at load time. Source CSV values are not changed.

## Workflow Pages

- **Command Center**: Executive operating view with Source Registry coverage, populated versus unresolved programmes, Connector status summary, current Candidate MethodUnit and Evidence Link counts, QA Exceptions, and next recommended actions.
- **Source Registry**: Filterable source registry from `source_profiles_final_fixed.csv`, including source URLs, Connector type, confidence, automation priority, populated status, and any live source-check summary from the current session.
- **Run Connectors**: Operational workspace for live source pre-checks and Candidate Extraction. Current supported connectors are Climate Action Reserve, International Carbon Registry / ICR, and Asia Carbon Institute.
- **Candidate Review**: Review Queue for Candidate MethodUnits. Uses current session candidates, `outputs/methodunit_candidates_review.csv`, latest timestamped output, or an uploaded CSV. Review decisions are added for display/download only and are not persisted automatically.
- **Evidence Links**: Full extracted Evidence Link audit table, including `methodunit_candidate`, `supporting_document`, `development_page`, `navigation_link`, and `exclude` rows.
- **QA & Exceptions**: Separates data-quality issues, source-access failures, Connector extraction errors, and review-needed Candidate MethodUnits.
- **Export**: Downloads current MethodUnit candidates, full Evidence Links, extraction errors, Source Registry, and QA flags. Also supports saving available current outputs into `outputs/` with timestamped filenames.
- **Strategy Notes**: Connector strategy, extraction waves, and methodology rationale, including why one scraper will not work and how this upstream workbench feeds Dinesh's methodology catalogue.

## Supported Connectors

The prototype currently supports controlled Candidate Extraction for:

- **Climate Action Reserve**: public protocols page.
- **International Carbon Registry / ICR**: public methodology catalogue/detail pages discovered from the index.
- **Asia Carbon Institute**: public methodologies page, including ACI-native methods and adopted CDM methods when visible.

Connectors use `requests` with a polite user-agent and `BeautifulSoup` parsing. They do not fetch linked PDFs, create accounts, bypass access controls, or scrape at scale.

## Candidate MethodUnits and Evidence Links

Candidate rows include:

- `candidate_type`
- `classification_reason`
- `methodunit_code`
- `methodunit_name`
- `unit_type`
- `source_url`
- `document_url`
- `confidence`
- `review_status`
- `notes`

`candidate_type` separates likely catalogue records from supporting links:

- `methodunit_candidate`
- `supporting_document`
- `development_page`
- `navigation_link`
- `exclude`

All Candidate MethodUnits remain `pending_review` until a human reviewer approves, rejects, or marks them as needing research.

## Outputs

The Export page can write timestamped files to `outputs/`, such as:

- `methodunit_candidates_review_YYYYMMDD_HHMMSS.csv`
- `extracted_source_links_full_YYYYMMDD_HHMMSS.csv`
- `extraction_errors_YYYYMMDD_HHMMSS.csv`
- `source_registry_YYYYMMDD_HHMMSS.csv`
- `qa_flags_YYYYMMDD_HHMMSS.csv`

The app also looks for non-timestamped files such as `outputs/methodunit_candidates_review.csv` and `outputs/extracted_source_links_full.csv` when loading saved review data.

## Current Limitations

- Only three Candidate Extraction connectors are implemented.
- No linked PDFs are fetched.
- JavaScript-heavy, login-gated, DocSend-gated, paywalled, or CAPTCHA-protected sources are out of scope.
- Classification is rule-based and requires human review.
- There is no database or persistent review-state system.
- The app does not call external APIs.

## Future Extensions

Useful next steps include adding the next stable HTML catalogue Connector, detail-page enrichment for more standards, PDF metadata extraction, reviewer state persistence, and catalogue import validation.
