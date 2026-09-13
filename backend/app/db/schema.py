"""DuckDB schema definitions for the Apple Health export.

``SQL_CREATE_TABLES`` is additive and safe to run against an existing database.
Call :func:`reset_schema` explicitly when a staging import needs a destructive
reset before loading a fresh export.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

SQL_CREATE_TABLES = """
-- Records: the main health measurement table.
CREATE TABLE IF NOT EXISTS records (
    id            INTEGER PRIMARY KEY,
    type          VARCHAR NOT NULL,
    source_name   VARCHAR NOT NULL,
    source_version VARCHAR,
    device        VARCHAR,
    unit          VARCHAR,
    creation_date TIMESTAMP,
    start_date    TIMESTAMP NOT NULL,
    end_date      TIMESTAMP NOT NULL,
    value         DOUBLE,
    text_value    VARCHAR
);

-- Metadata attached to records (e.g. AutoSleep fields, HR motion context).
CREATE TABLE IF NOT EXISTS record_metadata (
    record_id INTEGER NOT NULL,
    key       VARCHAR NOT NULL,
    value     VARCHAR NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id)
);

-- Per-beat HRV data (InstantaneousBeatsPerMinute children).
CREATE TABLE IF NOT EXISTS hrv_beats (
    record_id   INTEGER NOT NULL,
    bpm         INTEGER NOT NULL,
    time_offset DOUBLE NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id)
);

-- Workout sessions.
CREATE TABLE IF NOT EXISTS workouts (
    id              INTEGER PRIMARY KEY,
    activity_type   VARCHAR NOT NULL,
    duration        DOUBLE,
    duration_unit   VARCHAR,
    source_name     VARCHAR NOT NULL,
    source_version  VARCHAR,
    device          VARCHAR,
    creation_date   TIMESTAMP,
    start_date      TIMESTAMP NOT NULL,
    end_date        TIMESTAMP NOT NULL
);

-- Per-metric aggregates within a workout (HR, distance, energy, etc.).
CREATE TABLE IF NOT EXISTS workout_statistics (
    workout_id INTEGER NOT NULL,
    type       VARCHAR NOT NULL,
    start_date TIMESTAMP,
    end_date   TIMESTAMP,
    average    DOUBLE,
    minimum    DOUBLE,
    maximum    DOUBLE,
    sum        DOUBLE,
    unit       VARCHAR,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- In-workout events (laps, pauses, segments).
CREATE TABLE IF NOT EXISTS workout_events (
    workout_id    INTEGER NOT NULL,
    type          VARCHAR NOT NULL,
    date          TIMESTAMP,
    duration      DOUBLE,
    duration_unit VARCHAR,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- GPS route file references.
CREATE TABLE IF NOT EXISTS workout_routes (
    workout_id    INTEGER NOT NULL,
    source_name   VARCHAR,
    creation_date TIMESTAMP,
    start_date    TIMESTAMP,
    end_date      TIMESTAMP,
    file_path     VARCHAR,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- Arbitrary key-value metadata on workouts (METs, elevation, brand, timezone).
CREATE TABLE IF NOT EXISTS workout_metadata (
    workout_id INTEGER NOT NULL,
    key        VARCHAR NOT NULL,
    value      VARCHAR NOT NULL,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- Daily activity ring summaries.
CREATE TABLE IF NOT EXISTS activity_summaries (
    date_components          VARCHAR PRIMARY KEY,
    active_energy_burned     DOUBLE,
    active_energy_burned_goal DOUBLE,
    active_energy_burned_unit VARCHAR,
    apple_move_time          DOUBLE,
    apple_move_time_goal     DOUBLE,
    apple_exercise_time      DOUBLE,
    apple_exercise_time_goal DOUBLE,
    apple_stand_hours        INTEGER,
    apple_stand_hours_goal   INTEGER
);

-- Index for common filter paths.
CREATE INDEX IF NOT EXISTS idx_records_type_date ON records(type, start_date);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_name);
CREATE INDEX IF NOT EXISTS idx_workouts_type_date ON workouts(activity_type, start_date);
CREATE INDEX IF NOT EXISTS idx_workout_stats_workout_type ON workout_statistics(workout_id, type);
"""

SQL_RESET_SCHEMA = """
DROP TABLE IF EXISTS hrv_beats;
DROP TABLE IF EXISTS record_metadata;
DROP TABLE IF EXISTS records;
DROP TABLE IF EXISTS workout_routes;
DROP TABLE IF EXISTS workout_metadata;
DROP TABLE IF EXISTS workout_statistics;
DROP TABLE IF EXISTS workout_events;
DROP TABLE IF EXISTS workouts;
DROP TABLE IF EXISTS activity_summaries;
"""

if TYPE_CHECKING:
    import duckdb


def reset_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Destructively clear all health tables, then recreate them."""
    conn.execute(SQL_RESET_SCHEMA)
    conn.execute(SQL_CREATE_TABLES)
