# Carbon Methodology Intelligence Platform

**Carbon Methodology Intelligence Platform / SourceOps Workbench for carbon methodology intelligence.**

`Carbon Methodology SourceOps Workbench` is a local Streamlit prototype that maps the carbon methodology source universe, tracks extraction readiness, runs source-specific ingestion workflows, preserves evidence behind extracted records, and shows how AI can responsibly assist messy review tasks — without blindly scraping the web.

## Problem

Carbon methodology information is scattered across heterogeneous official sources: structured HTML tables, methodology catalogues with detail pages, PDF / document families, adopted external methods, JS-heavy portals, and small programmes with no clear methodology page. One generic scraper is not enough.

## Six Ideas This App Is Built Around

1. **Source map.** A picture of the source universe and how heterogeneous it is.
2. **Assembly line.** A pipeline from official source to review-ready catalogue export, with operational controls to run each step.
3. **Coverage progress tracker.** Source-by-source implementation state, plus onboarding waves.
4. **Evidence-first review.** Every extracted record is paired with its supporting material, its issues, and an export handoff — nothing goes to a catalogue automatically.
5. **Connector governance.** Source verification, connector capability metadata, and reviewer decisions make the workbench easier to demo and easier to extend.
6. **AI-assisted analyst.** A roadmap for AI to help on messy cases with clear evidence and human control.

The current app is framed as an ecosystem intelligence platform first, with SourceOps workflows available as operational controls behind the platform views.

## App Pages

1. **Home** - executive platform snapshot, plain-language purpose, current priorities, and advanced landscape details.
2. **Programme Intelligence** - programme dossier with source status, URLs, connector approach, verification checklist, and loaded evidence.
3. **Source Explorer** - simple source exploration flow plus advanced source checks, extraction, and source-resolution controls.
4. **Review Desk** - candidate methods, evidence documents, issues, review decisions, and exports.
5. **Connector Roadmap** - future build planning from source intelligence and verification plans.
6. **Method / About** - explanation of the SourceOps method, evidence model, and verification-before-implementation workflow.

## Connector Governance

The app exposes a lightweight connector manifest and richer review handoff files:

- **Connector capability matrix** - derived from the Source Registry and research matrix; describes connector status, run mode, expected outputs, capabilities, and next action.
- **Source verification results** - produced from source access checks; records whether a URL was reached, what type of content was found, and the recommended next action before connector coding.
- **Normalized source documents** - derived from extracted supporting links; preserves the original extraction output while creating a document/evidence inventory for review.
- **Review decisions** - optional local reviewer decisions saved only when explicitly requested; extracted records are not overwritten.
- **MethodUnit dossier** - combines candidate records, evidence links, source-resolution context, issues, and connector metadata for one programme.

## Source Intelligence Inputs

The Connector Roadmap and Programme Intelligence pages read research-derived source intelligence from `data/source_intelligence/`:

- `connector_source_matrix_synthesized.csv` powers the Connector Roadmap table and roadmap metrics.
- `connector_source_matrix_synthesized.json` provides metadata such as the matrix generation timestamp.
- `source_verification_plan.csv` lists URLs and assumptions to verify before coding new connectors.

This supports a verification-before-implementation workflow: research identifies where methodology information appears to live, analysts verify the source behavior, and only then should a connector be implemented.

## User Flow

1. **Home** answers the state of the source landscape.
2. **Programme Intelligence** answers what is known about one programme.
3. **Source Explorer** runs or verifies a source.
4. **Review Desk** shows what records and evidence are ready for review or export.
5. **Connector Roadmap** turns research audits into future build planning.
6. **Method / About** explains the operating method and review guardrails.

## Workflow

```text
Official source
-> source access check
-> source-specific extraction
-> source resolution where needed
-> extracted methodology records
-> supporting links separated
-> issues logged
-> human review
-> catalogue export
```

Source-specific extractors are small, source-aware ingestion routines — not one generic scraper. Extracted records are never automatically approved; they are review-ready outputs.

## Currently Supported Source-Specific Extractors

- **Climate Action Reserve** — working structured-table extraction.
- **International Carbon Registry / ICR** — discovery-only; M-ICR codes and detail URLs found, but titles require manual review.
- **Asia Carbon Institute** — source-access / SSL exception handling; not bypassed by default.
- **City Forest Credits** — document / protocol-family extraction; linked PDFs are discovered but not fully parsed.

Other programmes appear in Home, Programme Intelligence, and Connector Roadmap views but do not yet have implemented extractors.

## Source Resolution

Some standards do not publish a clean, dedicated methodologies section. Some have only one methodology-like document, some use a single standard PDF, some point to adopted methods, some require an access request, and some remain unresolved until an official platform is accessible.

Source Resolution handles those cases before a normal extractor is designed. Valid outcomes include automated extraction, document-family capture, adopted-method pointer, access request, unresolved, or park.

The current implemented example is **Artisan C-sink**:

- no separate methodology index;
- methodology information lives in the Global Artisan C-Sink Standard page/PDF plus clarification documents;
- methodology model is a single protocol/document family;
- recommended catalogue action is `capture-document-family`;
- recommended ingestion mode is semi-automated extraction or one-shot manual capture.

The app fetches only the public source page, does not parse full PDFs, creates one pending-review document-family record, preserves clarification documents as Supporting Material, and logs missing or unstable document links as Issues. This directly addresses standards with one or a few methodologies where a full catalogue scraper would be unnecessary.

The app also loads `data/source_resolution_audit_mid_activity.csv` when present. That file is a review-ready source-resolution audit for mid-activity standards, not approved catalogue truth. It classifies sources into catalogue actions such as automated extraction, document-family capture, adopted-method pointer, access request, project-derived review, unresolved, or parked. Advanced details summarize it, and Review Desk surfaces audit rows that need issue records or follow-up. Audit rows do not automatically generate methodology catalogue exports.

## Session-State Model

The app treats extraction and source resolution as producer steps, and everything downstream as consumers of the latest outputs:

- **Producers**: Source Explorer and its advanced source-check, extraction, and source-resolution controls.
- **Consumers**: Review Desk (Candidate Methods, Evidence Documents, Issues, Review Decisions, Exports).

All producers write to the same session-state keys (`candidate_extraction_results`, `candidate_extraction_errors`, `candidate_extraction_enrichment_metrics`, `candidate_extraction_sources_attempted`). Consumers read those same keys and fall back to the latest saved `outputs/` CSVs if no session data is loaded. A quick demo run or Source Resolution run therefore populates the same downstream tabs as a full extraction run.

## Evidence and Review Rules

- Extracted records are not approved methodologies. They are review-ready candidates.
- `review_status = pending_review` means human review is still required.
- **High confidence** means the extraction looked structurally strong. It does not mean the methodology is legally, commercially, or carbon-market approved.
- For ICR, discovery records with suspicious or incomplete titles are labelled `needs_research` even when codes and detail URLs are found. These records are preserved, but they should be treated as discovery records until titles are manually verified.
- Supporting documents, development pages, navigation links, and excluded rows are preserved separately from extracted methodology records.

## Coverage Approach

Coverage expansion follows onboarding waves — not a blind scrape of every standard:

1. **Wave 1** — Stabilize working extractors (CAR, ICR discovery, ACI as source exception).
2. **Wave 2** — Add reachable document-family sources (Plan Vivo, Nori, ART/TREES, Peatland Code).
3. **Wave 3** — Add more catalogue-style sources (ACR after URL repair, Climate Forward, BioCarbon Registry, Cercarbono).
4. **Wave 4** — Handle adopted-method sources (native vs adopted CDM / Verra / Gold Standard).
5. **Wave 5** — Complex / high-value sources (CDM, JCM, Verra, Gold Standard, Isometric, Puro Earth).
6. **Wave 6** — Long-tail unresolved sources — manual investigation and periodic checks.

## AI-Assisted Scaling (Roadmap)

No AI API is called in the current prototype. The AI-Assisted Scaling page describes:

- Messy cases where AI can help (PDF metadata, ambiguous link classification, ICR titles, adopted CDM detection, duplicate/alias detection).
- A future AI workflow: raw source text → AI suggestion with evidence → human approve / edit / reject → catalogue export.
- A future AI task output schema (`task_id`, `program_name`, `problem_type`, `raw_text_context`, `current_extracted_fields`, `ai_suggestion`, `evidence_text`, `confidence`, `reviewer_decision`).
- Guardrails: every AI suggestion must carry its evidence, a human must approve, and deterministic source-specific extractors remain the first layer.

## Limitations

- Linked PDFs are discovered where visible, but full PDF text is not fetched or parsed.
- No JavaScript-heavy portals are automated yet.
- No logins, paywalls, CAPTCHAs, DocSend gates, or access controls are bypassed.
- No accounts are created.
- No database is used; review decisions are not persisted across sessions.
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
- `source_resolution_audit_mid_activity.csv` (optional but used for the mid-activity source-resolution audit layer)

## Outputs

The Review Desk -> Exports tab can write timestamped files to `outputs/`, including:

- `methodunit_candidates_review_YYYYMMDD_HHMMSS.csv`
- `extracted_source_links_full_YYYYMMDD_HHMMSS.csv`
- `source_documents_YYYYMMDD_HHMMSS.csv`
- `extraction_errors_YYYYMMDD_HHMMSS.csv`
- `source_resolution_results_YYYYMMDD_HHMMSS.csv`
- `source_verification_results_YYYYMMDD_HHMMSS.csv`
- `review_decisions_YYYYMMDD_HHMMSS.csv`
- `connector_manifest_YYYYMMDD_HHMMSS.csv`
- `source_registry_YYYYMMDD_HHMMSS.csv`
- `qa_flags_YYYYMMDD_HHMMSS.csv`

## Next Development Priorities

1. Repair or confirm stale source-registry URLs before building more extractors.
2. Follow the Connector Roadmap and verification plan to pick the next extractor.
3. Add Plan Vivo and Climate Forward as the next controlled extractors.
4. Add the next stable HTML catalogue extractor (likely ACR after URL repair).
5. Add controlled PDF metadata extraction for document-first sources.
6. Prototype a bounded AI-assist step for one messy case (for example, ICR title suggestions from detail-page text).
7. Add catalogue import validation once the extracted-record and review-decision schemas stabilize.
