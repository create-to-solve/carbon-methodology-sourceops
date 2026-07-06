from pathlib import Path
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from extractors import (  # noqa: E402
    extract_acr_candidates,
    extract_biocarbon_registry_candidates,
    extract_cfc_candidates,
    extract_climate_action_reserve_candidates,
    extract_climate_forward_candidates,
    extract_plan_vivo_candidates,
    extract_social_carbon_candidates,
    resolve_artisan_c_sink_source,
)
from pipeline import (  # noqa: E402
    CANDIDATE_SCHEMA,
    EXTRACTION_ERROR_SCHEMA,
    FILES,
    SOURCE_RESOLUTION_SCHEMA,
    apply_output_safeguards,
    build_source_documents,
    load_csv,
)


OUTPUT_DIR = REPO_ROOT / "outputs" / "demo_latest"


def normalize_result(result: tuple) -> tuple[list[dict], list[dict], dict]:
    candidates = result[0] if len(result) > 0 else []
    error = result[1] if len(result) > 1 else ""
    metrics = result[2] if len(result) > 2 else {}
    errors = []
    if error:
        errors.extend(error if isinstance(error, list) else [error])
    return candidates, errors, metrics


def candidate_frame(candidates: list[dict]) -> pd.DataFrame:
    return apply_output_safeguards(
        pd.DataFrame(
            [{column: candidate.get(column, "") for column in CANDIDATE_SCHEMA} for candidate in candidates],
            columns=CANDIDATE_SCHEMA,
        )
    )


def error_frame(errors: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [{column: error.get(column, "") for column in EXTRACTION_ERROR_SCHEMA} for error in errors],
        columns=EXTRACTION_ERROR_SCHEMA,
    )


def main() -> None:
    profiles = load_csv(FILES["source_profiles"])
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    source_summaries = []
    all_candidates = []
    all_errors = []

    for source_name, extractor in [
        ("Climate Action Reserve", extract_climate_action_reserve_candidates),
        ("City Forest Credits", extract_cfc_candidates),
        ("Climate Forward", extract_climate_forward_candidates),
        ("American Carbon Registry (ACR)", extract_acr_candidates),
        ("Social Carbon", extract_social_carbon_candidates),
        ("Plan Vivo", extract_plan_vivo_candidates),
        ("BioCarbon Registry", extract_biocarbon_registry_candidates),
    ]:
        candidates, errors, _metrics = normalize_result(extractor(profiles, allow_insecure_ssl=False))
        all_candidates.extend(candidates)
        all_errors.extend(errors)
        source_summaries.append(
            {
                "source": source_name,
                "records": sum(1 for row in candidates if row.get("candidate_type") == "methodunit_candidate"),
                "total_links": len(candidates),
                "issues": len(errors),
            }
        )

    resolution_df, artisan_candidates_df, artisan_errors_df = resolve_artisan_c_sink_source(profiles)
    artisan_candidates = artisan_candidates_df.to_dict("records")
    artisan_errors = artisan_errors_df.to_dict("records")
    all_candidates.extend(artisan_candidates)
    all_errors.extend(artisan_errors)
    source_summaries.append(
        {
            "source": "Artisan C-sink",
            "records": int((artisan_candidates_df.get("candidate_type", pd.Series(dtype=str)) == "methodunit_candidate").sum()),
            "total_links": len(artisan_candidates_df),
            "issues": len(artisan_errors_df),
        }
    )

    links_df = candidate_frame(all_candidates)
    methodunits_df = links_df[links_df["candidate_type"].eq("methodunit_candidate")].copy()
    documents_df = build_source_documents(links_df)
    errors_df = error_frame(all_errors)
    resolution_df = pd.DataFrame(
        [{column: row.get(column, "") for column in SOURCE_RESOLUTION_SCHEMA} for row in resolution_df.to_dict("records")],
        columns=SOURCE_RESOLUTION_SCHEMA,
    )

    outputs = {
        "methodunit_candidates_review.csv": methodunits_df,
        "extracted_source_links_full.csv": links_df,
        "source_documents.csv": documents_df,
        "extraction_errors.csv": errors_df,
        "source_resolution_results.csv": resolution_df,
    }
    for file_name, df in outputs.items():
        df.to_csv(output_dir / file_name, index=False)

    print("Demo output package written to:", output_dir)
    for summary in source_summaries:
        print(
            f"{summary['source']}: records={summary['records']}, "
            f"total_links={summary['total_links']}, issues={summary['issues']}"
        )
    for file_name, df in outputs.items():
        print(f"{file_name}: rows={len(df)}")


if __name__ == "__main__":
    main()
