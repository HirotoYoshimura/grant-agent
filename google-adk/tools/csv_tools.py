import os
import csv 
import logging
import pandas as pd
import datetime
from typing import Dict, List, Any  
from google.adk.tools import FunctionTool  

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# CSV column definition (candidates.csv)
# ----------------------------------------------------------------------------
CANDIDATE_CSV_HEADERS: List[str] = [
    "id",
    "title",
    "organization",
    "description",
    "url",
    "category",
    # ──────────────── place‑holders (initially empty) ────────────────
    "amount",
    "eligibility",
    "deadline",
    "application_process",
    "required_documents",
    "research_fields",
    "duration",
    "contact",
    "special_conditions",
    "is_deadline_passed",  # Added by investigation‑task
    # ──────────────── columns added/updated later ───────────────────
    "investigated",
    "completeness_score",
    "relevance_score",
    "updated_at",
    "deadline_status",
]

# ----------------------------------------------------------------------------
# CSV Writer
# ----------------------------------------------------------------------------

def write_grants_to_csv(grants_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Write *grants_data* to ``grants_candidates.csv``.

    * New rows are **appended** if the environment variable ``APPEND_MODE`` is a
      truthy value ("true", "1", "yes"). Otherwise the file is **overwritten**.
    * Missing columns are filled with an empty string so that the resulting CSV
      always has the full :pydata:`CANDIDATE_CSV_HEADERS` schema.
    """

    output_path = "/workspace/google-adk/results/grants_data/grants_candidates.csv"
    append = os.environ.get("APPEND_MODE", "").lower() in {"true", "1", "yes"}
    abs_path = os.path.abspath(output_path)

    logger.info(
        "Attempting to %s %d grants → %s",
        "append" if append else "write",
        len(grants_data),
        abs_path,
    )

    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        # ------------------------------------------------------------------
        # Load existing CSV (when appending)
        # ------------------------------------------------------------------
        existing_data: List[Dict[str, Any]] = []
        if append and os.path.exists(abs_path):
            try:
                existing_data = pd.read_csv(abs_path, dtype=str).to_dict("records")
            except pd.errors.EmptyDataError:
                logger.warning("CSV exists but is empty: %s", abs_path)
            except Exception as exc:
                logger.error("Error reading existing CSV (%s): %s", abs_path, exc)

        # ------------------------------------------------------------------
        # Merge & de‑duplicate by `id`
        # ------------------------------------------------------------------
        new_records = [g for g in grants_data if isinstance(g, dict)]
        if append and existing_data:
            existing_ids = {str(r.get("id", "")).strip() for r in existing_data}
            new_records = [g for g in new_records if str(g.get("id", "")).strip() not in existing_ids]

        # Combine
        combined = (existing_data + new_records) if append else new_records

        # Always generate a DataFrame with the full header order
        df = pd.DataFrame(combined, columns=CANDIDATE_CSV_HEADERS).fillna("")

        # Save
        df.to_csv(abs_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
        logger.info("CSV written. Rows: %d", len(df))
        return {"status": "success", "file_path": abs_path, "records_written": len(df)}

    except Exception as exc:
        logger.exception("Failed to write CSV: %s", exc)
        return {"status": "error", "error_message": str(exc)}

csv_writer_tool = FunctionTool(func=write_grants_to_csv)

# ----------------------------------------------------------------------------
# CSV Reader
# ----------------------------------------------------------------------------

def read_grants_from_csv(input_path: str) -> Dict[str, Any]:
    """Return the CSV content (always success, empty list if file is missing)."""

    abs_path = os.path.abspath(input_path)
    logger.info("Reading grants from CSV: %s", abs_path)

    if not os.path.exists(abs_path):
        logger.warning("CSV file not found: %s", abs_path)
        return {"status": "success", "data": [], "message": "File not found."}

    try:
        data = pd.read_csv(abs_path, dtype=str).fillna("").to_dict("records")
        return {"status": "success", "data": data}
    except pd.errors.EmptyDataError:
        logger.warning("CSV is empty: %s", abs_path)
        return {"status": "success", "data": [], "message": "CSV is empty."}
    except Exception as exc:
        logger.exception("Failed to read CSV: %s", exc)
        return {"status": "error", "error_message": str(exc), "data": []}

csv_reader_tool = FunctionTool(func=read_grants_from_csv)

# ----------------------------------------------------------------------------
# CSV Updater
# ----------------------------------------------------------------------------

def update_grant_in_csv(grant_id: str, update_data: Dict[str, Any], csv_path: str) -> Dict[str, Any]:
    """Patch a single row (matched by *grant_id*) in the CSV."""

    abs_path = os.path.abspath(csv_path)
    if not os.path.exists(abs_path):
        return {"status": "error", "message": "CSV not found."}

    try:
        df = pd.read_csv(abs_path, dtype=object)
    except pd.errors.EmptyDataError:
        return {"status": "error", "message": "CSV is empty."}

    if "id" not in df.columns:
        return {"status": "error", "message": "CSV missing 'id' column."}

    mask = df["id"].astype(str).str.fullmatch(str(grant_id), case=False, na=False)
    if not mask.any():
        return {"status": "not_found", "message": f"ID '{grant_id}' not found."}

    update_data["updated_at"] = datetime.datetime.utcnow().isoformat()
    for k, v in update_data.items():
        if k in df.columns:
            df.loc[mask, k] = "" if pd.isna(v) else v
        else:
            logger.warning("Unknown column '%s' – skipping", k)
    df["investigated"] = True
    df.fillna("", inplace=True)
    df.to_csv(abs_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    return {"status": "success", "message": "Grant updated."}

csv_updater_tool = FunctionTool(func=update_grant_in_csv)
