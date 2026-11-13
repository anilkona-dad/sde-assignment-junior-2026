
from pathlib import Path
import json

# Repository root is the parent of the solution directory.
SOLUTION_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SOLUTION_DIR.parent

SCHEMA_DIR = PROJECT_DIR / "assignment-a-data" / "schemas"
DATA_DIR = PROJECT_DIR / "data"
DATABASE_PATH = SOLUTION_DIR / "interaction_ledger.db"

REPORTS_DIR = PROJECT_DIR / "reports"


def load_workflow_schemas():
    """Load all workflow JSON schemas dynamically."""
    schemas = {}

    for schema_path in sorted(SCHEMA_DIR.glob("*.json")):
        with schema_path.open("r", encoding="utf-8") as file:
            schema = json.load(file)

        workflow_id = schema["workflow_id"]

        if workflow_id in schemas:
            raise ValueError(
                f"Duplicate workflow schema: {workflow_id}"
            )

        schemas[workflow_id] = schema

    if not schemas:
        raise RuntimeError(
            f"No workflow schemas found in {SCHEMA_DIR}"
        )

    return schemas


def load_dispositions():
    """Load workflow-specific disposition definitions."""
    import csv

    path = SCHEMA_DIR / "dispositions.csv"
    dispositions = {}

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        required_columns = {
            "workflow_id",
            "code",
            "label",
            "is_terminal",
            "is_success",
        }

        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(
                "dispositions.csv is missing required columns"
            )

        for row in reader:
            workflow_id = row["workflow_id"].strip()
            code = row["code"].strip()

            if not workflow_id or not code:
                continue

            if workflow_id not in dispositions:
                dispositions[workflow_id] = {}

            if code in dispositions[workflow_id]:
                raise ValueError(
                    f"Duplicate disposition: {workflow_id}/{code}"
                )

            dispositions[workflow_id][code] = {
                "label": row["label"].strip(),
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true",
            }

    return dispositions
