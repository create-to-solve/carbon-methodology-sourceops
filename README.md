# Carbon Methodology SourceOps Workbench

`Carbon Methodology SourceOps Workbench` is a lightweight Streamlit prototype for exploring the upstream source-intelligence layer behind a carbon-market methodology catalogue.

The existing methodology catalogue answers:

> What methodologies do we currently have?

This workbench answers:

> Where does methodology information come from, how should it be extracted, how confident are we, and what needs review?

The app does not scrape at scale, does not call external APIs, and does not modify the source CSV files. It reads the cleaned local CSV files already present in the `data/` folder. The optional **Live Source Check** page performs only small, user-triggered reachability checks against selected source pages.

## How to Run

Install the minimal dependencies:

```bash
pip install -r requirements.txt
```

Start the local Streamlit app:

```bash
streamlit run app.py
```

## Expected CSV Files

The app expects these files under `data/`:

- `source_profiles_final_fixed.csv`
- `connector_strategy_fixed.csv`
- `extraction_waves_fixed.csv`
- `qa_flags_fixed.csv`
- `next_actions_fixed.csv`

CSV headers are normalized defensively at load time by stripping whitespace, lower-casing, and replacing spaces with underscores. Optional columns are handled gracefully when missing.

## Main Pages

- **Home / Executive Summary**: Programme-level totals, methodology row coverage, connector and wave distributions, high-priority automation candidates, and manual-review or low-confidence cases.
- **Coverage Dashboard**: Coverage metrics and charts from `source_profiles_final_fixed.csv`.
- **Source Profiles**: Filterable source profile table with key source, connector, strategy, confidence, evidence, and notes fields.
- **Connector Strategy**: Connector archetypes, associated standards, extraction methods, reusability, maintenance burden, and priority.
- **Extraction Waves**: Wave distribution and enriched wave views joined to source profile context.
- **QA Flags**: QA issue table with highlighted classes such as duplicates, ambiguous standards, adopted external methods, evidence URL issues, and low-confidence sources.
- **Next Actions**: Filterable action queue for deciding what to do next by programme, priority, wave, and confidence.
- **Live Source Check**: Small-batch source reconnaissance for selected programmes. It fetches the selected `method_source_url` with a polite user-agent, follows redirects, records status, final URL, content type, response size, title, link counts, likely methodology/protocol/document links, and an HTML content hash for future change detection. It does not fetch linked PDFs or ingest methodologies.
- **Candidate Extraction**: Controlled candidate MethodUnit extraction for the first supported public sources. It produces a review-ready table using the standard candidate schema but does not write results to disk unless the user downloads them.
- **About / Methodology**: Explanation of MethodUnits, terminology differences, connector strategy, and how SourceOps feeds the methodology catalogue.

## Candidate Extraction

The **Candidate Extraction** page demonstrates the next step after source checking: acquiring usable methodology/protocol metadata from selected public source pages.

Supported first extractors:

- **Climate Action Reserve**: Extracts candidate protocol records from the public protocols page.
- **International Carbon Registry / ICR**: Extracts candidate methodology records from the public ICR methodology catalogue/documentation page.
- **Asia Carbon Institute**: Extracts candidate methodology records from the public methodologies page, including ACI-native methods and CDM-derived adopted external methods where visible.

Candidate rows use this schema:

- `program_id`
- `program_name`
- `methodunit_code`
- `methodunit_name`
- `unit_type`
- `candidate_type`
- `classification_reason`
- `sector`
- `version`
- `status`
- `source_url`
- `document_url`
- `extraction_method`
- `confidence`
- `review_status`
- `extracted_at`
- `notes`

The `candidate_type` field separates likely catalogue records from useful supporting links:

- `methodunit_candidate`: likely methodology, protocol, or adopted external method record.
- `supporting_document`: FAQ, template, guidance, manual, procedure, tool, form, or other support material.
- `development_page`: consultation, under-development, concept, adaptation, or issue-paper page.
- `navigation_link`: page section, generic listing, pagination, or catalogue navigation link.
- `exclude`: empty, duplicate, social/footer, unrelated, or otherwise non-useful row.

The MethodUnit review download, `methodunit_candidates_review.csv`, includes only `methodunit_candidate` rows. The full audit download, `extracted_source_links_full.csv`, includes all classified rows so useful supporting links are not lost.

All extracted MethodUnit rows are marked `pending_review` because this prototype uses lightweight heuristics over public HTML tables, links, and headings. A reviewer should confirm names, codes, versions, statuses, sectors, document URLs, and classifications before importing any candidate into the methodology catalogue.

Current limitations:

- Only three extractors are enabled.
- Linked PDFs and detail pages are listed but not fetched.
- JavaScript-heavy catalogues are intentionally excluded.
- The parser favors robust tables and obvious methodology/protocol/document links, so it may miss records hidden behind scripts or non-standard markup.
- Results are stored only in the Streamlit session until downloaded.

SSL handling:

- SSL verification remains enabled by default.
- If Asia Carbon Institute or another source fails with certificate verification errors, the app records the failure in the extraction errors table and suggests manual browser review or retrying later.
- Analysts may temporarily enable **Allow insecure SSL for analyst testing** for the selected run. This uses insecure SSL verification only for that run and should not be used for production ingestion.

Future extensions could add source-specific detail-page parsers, PDF metadata extraction, change detection from content hashes, reviewer approval workflows, and controlled connectors for additional standards.

## Prototype Scope

This is a local prototype for source intelligence and ingestion planning. It is not yet a crawler, connector runner, or production data pipeline.

The live source check is deliberately limited to small, manual runs. It must not be used to bypass logins, paywalls, CAPTCHAs, DocSend gates, or other access controls.

Candidate extraction follows the same rule: it is for small, manual public-source checks only, not broad scraping.
