# Carbon Methodology Extraction Workbench

This Streamlit app demonstrates how methodology and standards information can be extracted from public carbon registries and standards bodies, even when each source publishes information differently.

The public app is a four-page workbench:

1. **Home** - what the app does, supported sources, and where to start.
2. **Extract** - choose a source, view the latest extracted records, and optionally check for updates.
3. **Review** - inspect records and evidence, save review decisions, and export reviewed records.
4. **About** - plain-language explanation of the extraction and human review approach.

## What the App Does

- Finds public methodology and standards pages.
- Extracts methodology or document records.
- Captures primary and supporting source documents.
- Routes extracted records for human review.
- Exports reviewed outputs.

The normal user path is:

```text
Home -> Extract -> Review -> Export reviewed records
```

## Public Source Coverage

The app currently presents **10 stable extractors** and **2 experimental source checks**.

Stable extractors:

- Climate Action Reserve
- City Forest Credits
- Climate Forward
- American Carbon Registry / ACR
- Social Carbon
- Plan Vivo
- BioCarbon Registry / BCR
- Cercarbono
- Puro Earth
- ART/TREES

Experimental source checks:

- International Carbon Registry / ICR
- Asia Carbon Institute

Experimental checks are included for source-access testing. They may not have saved records in the current package, and update checks can depend on source availability, SSL/certificate behavior, rate limits, or page changes.

Artisan C-sink is retained as a source-resolution routine outside the public Extract selector. It is included in the latest saved package generation, but it is not part of the public source list.

## Latest Saved Extraction Package

The Extract page automatically reads the latest saved package from:

```text
outputs/demo_latest/
```

At the current head, that package contains:

- `methodunit_candidates_review.csv` - 145 extracted methodology/document records
- `extracted_source_links_full.csv` - 704 evidence/source-link rows
- `source_documents.csv` - 677 normalized source-document rows
- `extraction_errors.csv` - 0 extraction errors
- `source_resolution_results.csv` - 1 source-resolution row retained outside the public Extract flow

The package is generated from the 10 stable extractors plus the retained Artisan C-sink source-resolution routine. ICR and Asia Carbon Institute are available for update checks but are not part of the stable saved package.

## Extract Page

Use Extract to choose a carbon standard or registry and view the latest extracted records for that source. The page shows:

- source pattern
- what is extracted
- primary source URL
- latest extracted records
- evidence/source-link counts
- extraction issues, if any

The optional **Check for updates** action tests the public source. If an update check succeeds, the page displays updated results. If it fails, the latest saved records remain visible when available.

## Review Page

Use Review to make human decisions on extracted records.

The page supports:

- source filtering
- review status filtering
- selecting a record
- opening the primary document
- inspecting supporting document links
- adding a reviewer note
- saving a review decision
- exporting reviewed records

Review decisions are:

- Approve
- Needs correction
- Reject

Saved decisions are written to the existing review-decision output and can be downloaded from the Review page.

## About the Approach

Carbon standards publish methodology information in many shapes: catalogue pages, static tables, document libraries, methodology cards, and standard-version document families. The app uses source-specific extractors for these patterns instead of treating every source as the same generic scrape.

Extracted records are review candidates. The app does not decide final market eligibility, interpret legal terms, or approve methodologies. A reviewer should open the evidence documents and decide whether each record is approved, rejected, or needs correction.

## How to Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

## Key Files

- `app.py` - Streamlit workbench UI
- `pipeline.py` - shared schemas, loading, output helpers, and extractor orchestration
- `extractors.py` - source-specific extraction routines
- `scripts/generate_demo_outputs.py` - regenerates the latest saved extraction package
- `scripts/verify_source_intelligence.py` - source access verification utility

## Outputs

Reviewed and extracted outputs are stored under `outputs/`. Common files include:

- `methodunit_candidates_review.csv`
- `extracted_source_links_full.csv`
- `source_documents.csv`
- `extraction_errors.csv`
- `review_decisions.csv`

Timestamped output files may also be created when export helpers are used.
