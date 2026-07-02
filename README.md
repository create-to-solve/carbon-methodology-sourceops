# Carbon Methodology SourceOps Workbench

`Carbon Methodology SourceOps Workbench` is a local Streamlit prototype for preparing methodology-source information before it enters a carbon methodology catalogue.

## Problem

Carbon methodology information is scattered across official sources that look very different from one another: tables, documentation portals, PDFs, adopted external methods, JS-heavy portals, and sometimes unclear source pages. One generic scraper is not enough.

## Approach

The app has two layers:

- a **stakeholder-facing demo layer** that shows one clear source-to-catalogue loop;
- an **operational workbench layer** for deeper source checks, extraction, review, issue handling, and exports.

It helps an analyst:

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
Official Source
-> Source-Specific Extraction
-> Extracted Methodology Records
-> Supporting Links Separated
-> Issues Flagged
-> Review
-> Export for Catalogue
```

## App Pages

- **Demo: Source to Catalogue**: Landing page and stakeholder demo. Runs a quick Climate Action Reserve or City Forest Credits extraction, then explains what worked, what needs review, what could not be accessed, and what was separated out.
- **Coverage Plan**: Converts the 61-source registry into a wave-based onboarding roadmap for the rest of the standards.
- **Workbench**: Operational tabs for Source Registry, Extract from Sources, Review Extracted Records, Supporting Links, Issues to Resolve, Export for Catalogue, and How to Read Outputs. This is where detailed diagnostics remain available.
- **Roadmap**: Current implemented sources, next sources, later PDF parsing, later browser automation, AI-assisted review, and persistent review workflow.

The old detailed pages are still available as Workbench tabs rather than separate sidebar pages.

## Current Capabilities

- Source Registry loads the current programme source profile table.
- Demo page can run a small source-to-export loop for Climate Action Reserve or City Forest Credits.
- Demo page presents interpreted results for stakeholders, while detailed extraction diagnostics stay in an expandable section and in the Workbench.
- Live Source Check can verify selected source URLs.
- Climate Action Reserve extractor pulls structured protocol table records.
- ICR extractor discovers M-ICR methodology codes and detail URLs, with conservative title review.
- City Forest Credits extractor discovers protocol/standard document links for review.
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
- **City Forest Credits**: document/protocol-family extraction implemented; linked PDFs are discovered but not fully parsed.

Other sources are represented in the Source Registry and Roadmap but are not yet implemented as extractors.

## Coverage Plan

The Coverage Plan page answers the stakeholder question: "What about the rest of the standards?"

Its purpose is to convert the Source Registry into a managed onboarding pipeline, not to automate all 61 sources blindly. Each source is assigned a derived planning category inside the app, such as:

- working extractor;
- ready for extraction;
- needs URL repair;
- needs document/PDF parsing;
- needs adopted-method handling;
- needs browser automation later;
- needs manual investigation.

The page also groups expansion into waves:

1. Stabilize working extractors.
2. Add reachable document-family sources.
3. Add more catalogue-style sources.
4. Handle adopted-method sources.
5. Tackle complex/high-value sources.
6. Resolve the long tail through manual investigation and periodic checks.

This makes coverage expansion auditable: classify the source, check URL readiness, choose the extraction strategy, review outputs, then export to the catalogue.

## Workbench

The Workbench is the operational area after a reviewer understands the demo. It keeps the existing workflow in tabs:

- **Source Registry**: filter and inspect official source profile rows.
- **Extract from Sources**: run live source checks and supported source-specific extraction.
- **Review Extracted Records**: inspect possible methodology/protocol records before catalogue handoff.
- **Supporting Links**: preserve useful non-record links such as PDFs, FAQs, templates, guidance pages, development pages, navigation links, and excluded links.
- **Issues to Resolve**: collect broken URLs, SSL problems, stale links, missing titles, source-access failures, and QA flags.
- **Export for Catalogue**: download or timestamp-save review-ready outputs.
- **How to Read Outputs**: explains confidence, review status, supporting links, and why candidates are not approved methodologies.

Within the Workbench, **Extract from Sources** is the producer step. It creates the latest extracted records, supporting links, and extraction issues. **Review Extracted Records**, **Supporting Links**, **Issues to Resolve**, and **Export for Catalogue** are consumer steps: they read from the latest extraction run first, then from the latest saved outputs when no run is loaded. A quick Demo run also populates the same session outputs used by the Workbench.

The Workbench intentionally remains more detailed than the Demo page. It includes operational diagnostics such as source-check status, extraction errors, classified links, missing fields, and extractor-specific quality metrics.

## How to Read Confidence

High confidence means the extraction looked structurally strong. It does not mean the methodology is legally, commercially, or carbon-market approved. All extracted records require human review before catalogue ingestion.

For ICR, discovery records with suspicious or incomplete titles are labelled for research even when codes and detail URLs are found. These records are preserved, but they should be treated as discovery records until titles are manually verified.

## Limitations

- Linked PDFs are discovered where visible, but full PDF text is not fetched or parsed.
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
2. Use Coverage Plan waves to pick the next extractor.
3. Add Plan Vivo and Climate Forward as the next controlled extractors after City Forest Credits.
4. Add the next stable HTML catalogue extractor, likely ACR after URL repair.
5. Add controlled PDF metadata extraction for document-first sources.
6. Add persistent review decisions.
7. Add catalogue import validation once the extracted-record schema stabilizes.
