"""DuckDB reconciliation phase: load Parquet shards and assign global IDs.

This module implements the DuckDB phase B of the parallel ingestion pipeline:
1. Load Parquet shards using DuckDB's COPY FROM read_parquet()
2. Assign global sequential IDs using ROW_NUMBER()
3. Rewrite FK columns using JOINs
4. Create indexes

The reconciliation uses Option A from the plan: worker-local IDs are assigned
during parsing, then global IDs are computed in DuckDB using window functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.db.schema import SQL_CREATE_TABLES

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# SQL statements to load Parquet shards and reconcile IDs
# These statements assume the schema has already been created via SQL_CREATE_TABLES
SQL_LOAD_AND_RECONCILE = """
-- Create a temporary mapping table to track worker_idx/local_id to global id
CREATE TEMPORARY TABLE record_id_mapping AS
SELECT
    worker_idx,
    local_id,
    ROW_NUMBER() OVER (ORDER BY worker_idx, local_id) AS id
FROM read_parquet('{shard_dir}/records-*.parquet');

-- Load records using the mapping table
INSERT INTO records
SELECT
    m.id,
    r.type,
    r.source_name,
    r.source_version,
    r.device,
    r.unit,
    r.creation_date,
    r.start_date,
    r.end_date,
    r.value
FROM read_parquet('{shard_dir}/records-*.parquet') r
JOIN record_id_mapping m ON r.worker_idx = m.worker_idx AND r.local_id = m.local_id;

-- Load record_metadata with rewritten FKs using the mapping table
INSERT INTO record_metadata
SELECT
    m.id AS record_id,
    rm.key,
    rm.value
FROM read_parquet('{shard_dir}/record_metadata-*.parquet') rm
JOIN record_id_mapping m ON rm.worker_idx = m.worker_idx AND rm.parent_local_id = m.local_id;

-- Load hrv_beats with rewritten FKs using the mapping table
INSERT INTO hrv_beats
SELECT
    m.id AS record_id,
    h.bpm,
    h.time_offset
FROM read_parquet('{shard_dir}/hrv_beats-*.parquet') h
JOIN record_id_mapping m ON h.worker_idx = m.worker_idx AND h.parent_local_id = m.local_id;

-- Create a temporary mapping table for workouts
CREATE TEMPORARY TABLE workout_id_mapping AS
SELECT
    worker_idx,
    local_id,
    ROW_NUMBER() OVER (ORDER BY worker_idx, local_id) AS id
FROM read_parquet('{shard_dir}/workouts-*.parquet');

-- Load workouts using the mapping table
INSERT INTO workouts
SELECT
    m.id,
    w.activity_type,
    w.duration,
    w.duration_unit,
    w.source_name,
    w.source_version,
    w.device,
    w.creation_date,
    w.start_date,
    w.end_date
FROM read_parquet('{shard_dir}/workouts-*.parquet') w
JOIN workout_id_mapping m ON w.worker_idx = m.worker_idx AND w.local_id = m.local_id;

-- Load workout_events with rewritten FKs using the mapping table
INSERT INTO workout_events
SELECT
    m.id AS workout_id,
    e.type,
    e.date,
    e.duration,
    e.duration_unit
FROM read_parquet('{shard_dir}/workout_events-*.parquet') e
JOIN workout_id_mapping m ON e.worker_idx = m.worker_idx AND e.parent_local_id = m.local_id;

-- Load workout_statistics with rewritten FKs using the mapping table
INSERT INTO workout_statistics
SELECT
    m.id AS workout_id,
    s.type,
    s.start_date,
    s.end_date,
    s.average,
    s.minimum,
    s.maximum,
    s.sum,
    s.unit
FROM read_parquet('{shard_dir}/workout_statistics-*.parquet') s
JOIN workout_id_mapping m ON s.worker_idx = m.worker_idx AND s.parent_local_id = m.local_id;

-- Load workout_routes with rewritten FKs using the mapping table
INSERT INTO workout_routes
SELECT
    m.id AS workout_id,
    r.source_name,
    r.creation_date,
    r.start_date,
    r.end_date,
    r.file_path
FROM read_parquet('{shard_dir}/workout_routes-*.parquet') r
JOIN workout_id_mapping m ON r.worker_idx = m.worker_idx AND r.parent_local_id = m.local_id;

-- Load workout_metadata with rewritten FKs using the mapping table
INSERT INTO workout_metadata
SELECT
    m.id AS workout_id,
    wm.key,
    wm.value
FROM read_parquet('{shard_dir}/workout_metadata-*.parquet') wm
JOIN workout_id_mapping m ON wm.worker_idx = m.worker_idx AND wm.parent_local_id = m.local_id;

-- Load activity_summaries (no FK reconciliation needed, keyed by date_components)
INSERT INTO activity_summaries
SELECT *
FROM read_parquet('{shard_dir}/activity_summaries-*.parquet');

-- Clean up temporary mapping tables
DROP TABLE record_id_mapping;
DROP TABLE workout_id_mapping;
"""


def load_shards_into_duckdb(db: duckdb.DuckDBPyConnection, shard_dir: str | Path) -> None:
    """Load Parquet shards into DuckDB and perform ID/FK reconciliation.

    This function:
    1. Creates the schema (DROP + CREATE for idempotent re-runs)
    2. Loads Parquet shards using COPY FROM read_parquet()
    3. Assigns global sequential IDs using ROW_NUMBER()
    4. Rewrites FK columns using JOINs

    Args:
        db: An open DuckDB connection
        shard_dir: Directory containing Parquet shards
    """
    shard_dir = Path(shard_dir).resolve()
    if not shard_dir.exists():
        raise FileNotFoundError(f"Shard directory not found: {shard_dir}")

    logger.info("Creating schema (DROP + CREATE)")
    db.execute(SQL_CREATE_TABLES)

    logger.info(f"Loading Parquet shards from {shard_dir}")

    # Verify parquet files exist before loading
    import glob

    parquet_files = glob.glob(str(shard_dir / "*.parquet"))
    if not parquet_files:
        logger.warning(f"No parquet files found in {shard_dir}")
        raise FileNotFoundError(f"No parquet files found in {shard_dir}")

    logger.info(f"Found {len(parquet_files)} parquet files")
    for pf in parquet_files[:5]:  # Log first 5 files
        logger.debug(f"  - {pf}")

    # Convert path to string with forward slashes for DuckDB compatibility
    shard_dir_str = str(shard_dir).replace("\\", "/")

    # Wrap everything in a single transaction for atomicity
    db.execute("BEGIN")

    try:
        # Format the SQL with the shard directory
        sql = SQL_LOAD_AND_RECONCILE.format(shard_dir=shard_dir_str)

        # Log the formatted SQL for debugging
        logger.debug(f"Formatted SQL length: {len(sql)}")
        logger.debug(f"Shard dir in SQL: {shard_dir_str}")

        # Execute each statement
        # Split by semicolon and filter out empty statements
        # Note: Comments are part of statements, so we don't filter them out
        raw_statements = sql.split(";")
        statements = []
        for stmt in raw_statements:
            # Remove comment lines and check if there's any SQL left
            lines = [
                line
                for line in stmt.split("\n")
                if line.strip() and not line.strip().startswith("--")
            ]
            if lines:
                statements.append(stmt.strip())

        logger.info(f"Found {len(statements)} statements to execute")

        for i, statement in enumerate(statements):
            if statement:
                logger.info(f"Executing statement {i + 1}/{len(statements)}: {statement[:150]}...")
                try:
                    db.execute(statement)
                    # Check if this was an INSERT and log affected rows
                    if statement.upper().startswith("INSERT"):
                        # Get the table name from the statement
                        parts = statement.split()
                        if len(parts) >= 3:
                            table_name = parts[2]
                            # Query the count for this table
                            count_result = db.execute(
                                f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608  # noqa: S608  # noqa: S608
                            ).fetchone()
                            count = count_result[0] if count_result else 0
                            logger.info(f"✓ Inserted into {table_name}: {count} rows total")
                except Exception as stmt_error:
                    logger.error(f"✗ Failed to execute statement {i + 1}: {statement[:150]}...")
                    logger.error(f"Error: {stmt_error}")
                    raise

        db.execute("COMMIT")
        logger.info("Successfully loaded and reconciled all shards")

    except Exception as e:
        db.execute("ROLLBACK")
        logger.error(f"Failed to load shards: {e}")
        raise
