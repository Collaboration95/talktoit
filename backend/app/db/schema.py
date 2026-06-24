"""DuckDB schema definitions for the Apple Health export.

Creates all tables on an empty database. Designed to be called once at the start
of ingestion (DROP IF EXISTS + CREATE to support idempotent re-runs).
"""

SQL_CREATE_TABLES = """
-- Drop in reverse dependency order (or with CASCADE on root tables).
DROP TABLE IF EXISTS hrv_beats;
DROP TABLE IF EXISTS record_metadata;
DROP TABLE IF EXISTS records;
DROP TABLE IF EXISTS workout_routes;
DROP TABLE IF EXISTS workout_metadata;
DROP TABLE IF EXISTS workout_statistics;
DROP TABLE IF EXISTS workout_events;
DROP TABLE IF EXISTS workouts;
DROP TABLE IF EXISTS activity_summaries;

-- Records: the main health measurement table.
CREATE TABLE records (
    id            INTEGER PRIMARY KEY,
    type          VARCHAR NOT NULL,
    source_name   VARCHAR NOT NULL,
    source_version VARCHAR,
    device        VARCHAR,
    unit          VARCHAR,
    creation_date TIMESTAMP,
    start_date    TIMESTAMP NOT NULL,
    end_date      TIMESTAMP NOT NULL,
    value         DOUBLE
);

-- Metadata attached to records (e.g. AutoSleep fields, HR motion context).
CREATE TABLE record_metadata (
    record_id INTEGER NOT NULL,
    key       VARCHAR NOT NULL,
    value     VARCHAR NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id)
);

-- Per-beat HRV data (InstantaneousBeatsPerMinute children).
CREATE TABLE hrv_beats (
    record_id   INTEGER NOT NULL,
    bpm         INTEGER NOT NULL,
    time_offset DOUBLE NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id)
);

-- Workout sessions.
CREATE TABLE workouts (
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
CREATE TABLE workout_statistics (
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
CREATE TABLE workout_events (
    workout_id    INTEGER NOT NULL,
    type          VARCHAR NOT NULL,
    date          TIMESTAMP,
    duration      DOUBLE,
    duration_unit VARCHAR,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- GPS route file references.
CREATE TABLE workout_routes (
    workout_id    INTEGER NOT NULL,
    source_name   VARCHAR,
    creation_date TIMESTAMP,
    start_date    TIMESTAMP,
    end_date      TIMESTAMP,
    file_path     VARCHAR,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- Arbitrary key-value metadata on workouts (METs, elevation, brand, timezone).
CREATE TABLE workout_metadata (
    workout_id INTEGER NOT NULL,
    key        VARCHAR NOT NULL,
    value      VARCHAR NOT NULL,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

-- Daily activity ring summaries.
CREATE TABLE activity_summaries (
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
