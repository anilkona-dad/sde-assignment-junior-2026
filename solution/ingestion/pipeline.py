
from pathlib import Path

from config import load_workflow_schemas, load_dispositions
from database import get_connection, initialize_database
from ingestion.leads import ingest_leads_for_drop
from ingestion.events import ingest_events_for_drop


def ingest_drop(drop_path, database_path=None):
    """
    Transactional, incremental, idempotent ingestion of leads and events.
    """
    drop_path = Path(drop_path).resolve()

    if not drop_path.is_dir():
        raise FileNotFoundError(
            f"Drop directory does not exist: {drop_path}"
        )

    drop_id = drop_path.name

    schemas = load_workflow_schemas()
    dispositions = load_dispositions()

    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing_drop = connection.execute(
            """
            SELECT drop_id
            FROM ingestion_drops
            WHERE drop_id = ?
            """,
            (drop_id,),
        ).fetchone()

        if existing_drop is not None:
            connection.rollback()
            return {
                "status": "already_processed",
                "drop_id": drop_id,
            }

        connection.execute(
            """
            INSERT INTO ingestion_drops (drop_id, source_path)
            VALUES (?, ?)
            """,
            (drop_id, str(drop_path)),
        )

        # Process lead rows first. Events that cannot yet find a lead
        # are retained and resolved during this drop or a later drop.
        lead_metrics = ingest_leads_for_drop(
            connection=connection,
            drop_path=drop_path,
            drop_id=drop_id,
            schemas=schemas,
        )

        event_metrics = ingest_events_for_drop(
            connection=connection,
            drop_path=drop_path,
            drop_id=drop_id,
            dispositions=dispositions,
        )

        metrics = {
            **lead_metrics,
            **event_metrics,
        }

        for metric_name, metric_value in metrics.items():
            connection.execute(
                """
                INSERT INTO drop_metrics (
                    drop_id,
                    metric_name,
                    metric_value
                )
                VALUES (?, ?, ?)
                """,
                (drop_id, metric_name, metric_value),
            )

        connection.commit()

        return {
            "status": "processed",
            "drop_id": drop_id,
            "metrics": metrics,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def ingest_drop_leads(drop_path, database_path=None):
    """
    Backward-compatible lead-only entry point.

    Use ingest_drop() for complete lead and event ingestion.
    """
    return _ingest_leads_only(drop_path, database_path)


def _ingest_leads_only(drop_path, database_path=None):
    """
    Preserve the earlier lead-only behavior for existing tests.
    """
    drop_path = Path(drop_path).resolve()

    if not drop_path.is_dir():
        raise FileNotFoundError(
            f"Drop directory does not exist: {drop_path}"
        )

    drop_id = drop_path.name
    schemas = load_workflow_schemas()

    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing_drop = connection.execute(
            """
            SELECT drop_id
            FROM ingestion_drops
            WHERE drop_id = ?
            """,
            (drop_id,),
        ).fetchone()

        if existing_drop is not None:
            connection.rollback()
            return {
                "status": "already_processed",
                "drop_id": drop_id,
            }

        connection.execute(
            """
            INSERT INTO ingestion_drops (drop_id, source_path)
            VALUES (?, ?)
            """,
            (drop_id, str(drop_path)),
        )

        metrics = ingest_leads_for_drop(
            connection=connection,
            drop_path=drop_path,
            drop_id=drop_id,
            schemas=schemas,
        )

        for metric_name, metric_value in metrics.items():
            connection.execute(
                """
                INSERT INTO drop_metrics (
                    drop_id,
                    metric_name,
                    metric_value
                )
                VALUES (?, ?, ?)
                """,
                (drop_id, metric_name, metric_value),
            )

        connection.commit()

        return {
            "status": "processed",
            "drop_id": drop_id,
            "metrics": metrics,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
