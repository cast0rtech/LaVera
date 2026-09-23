-- ==============================================================================
-- LaVera EV Telemetry Hub - TimescaleDB Initialization Script
-- ==============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 1. Main Telemetry Hypertable (High-frequency real-time metrics)
CREATE TABLE IF NOT EXISTS telemetry (
    time TIMESTAMPTZ NOT NULL,
    vin VARCHAR(32) NOT NULL DEFAULT 'DEFAULT',
    provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
    speed_kmh DOUBLE PRECISION,
    soc_percent DOUBLE PRECISION,
    power_kw DOUBLE PRECISION,
    energy_used_kwh DOUBLE PRECISION,
    odometer_km DOUBLE PRECISION,
    range_estimated_km DOUBLE PRECISION,
    range_ideal_km DOUBLE PRECISION,
    battery_temp_c DOUBLE PRECISION,
    inside_temp_c DOUBLE PRECISION,
    outside_temp_c DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    elevation_m DOUBLE PRECISION,
    is_charging BOOLEAN DEFAULT FALSE,
    is_driving BOOLEAN DEFAULT FALSE,
    raw_payload JSONB
);

-- Convert telemetry to TimescaleDB hypertable partitioned by time
SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);

-- Create indexes for ultra-fast time-series and vehicle queries
CREATE INDEX IF NOT EXISTS idx_telemetry_vin_time ON telemetry (vin, time DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_provider_time ON telemetry (provider, time DESC);

-- 2. Drive Sessions Table
CREATE TABLE IF NOT EXISTS drives (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
    vin VARCHAR(32) NOT NULL DEFAULT 'DEFAULT',
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_s INTEGER DEFAULT 0,
    distance_km DOUBLE PRECISION DEFAULT 0.0,
    energy_kwh DOUBLE PRECISION DEFAULT 0.0,
    efficiency_wh_km DOUBLE PRECISION DEFAULT 0.0,
    start_soc DOUBLE PRECISION DEFAULT 0.0,
    end_soc DOUBLE PRECISION DEFAULT 0.0,
    start_temp_c DOUBLE PRECISION DEFAULT 0.0,
    end_temp_c DOUBLE PRECISION DEFAULT 0.0,
    start_location TEXT,
    end_location TEXT,
    start_odometer_km DOUBLE PRECISION DEFAULT 0.0,
    end_odometer_km DOUBLE PRECISION DEFAULT 0.0,
    max_speed_kmh DOUBLE PRECISION DEFAULT 0.0,
    raw_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_drives_vin_start ON drives (vin, started_at DESC);

-- 3. Charge Sessions Table
CREATE TABLE IF NOT EXISTS charges (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
    vin VARCHAR(32) NOT NULL DEFAULT 'DEFAULT',
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_s INTEGER DEFAULT 0,
    energy_added_kwh DOUBLE PRECISION DEFAULT 0.0,
    start_soc DOUBLE PRECISION DEFAULT 0.0,
    end_soc DOUBLE PRECISION DEFAULT 0.0,
    range_added_km DOUBLE PRECISION DEFAULT 0.0,
    peak_kw DOUBLE PRECISION DEFAULT 0.0,
    cost DOUBLE PRECISION DEFAULT 0.0,
    location TEXT,
    is_fast_charge BOOLEAN DEFAULT FALSE,
    raw_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_charges_vin_start ON charges (vin, started_at DESC);

-- 4. Battery Health Reports Table
CREATE TABLE IF NOT EXISTS battery_health (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
    vin VARCHAR(32) NOT NULL DEFAULT 'DEFAULT',
    reported_at TIMESTAMPTZ NOT NULL,
    capacity_kwh DOUBLE PRECISION DEFAULT 0.0,
    original_capacity_kwh DOUBLE PRECISION DEFAULT 0.0,
    degradation_pct DOUBLE PRECISION DEFAULT 0.0,
    max_range_km DOUBLE PRECISION DEFAULT 0.0,
    odometer_km DOUBLE PRECISION DEFAULT 0.0,
    raw_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_battery_vin_time ON battery_health (vin, reported_at DESC);

-- 5. Idle / Vampire Drain Logs Table
CREATE TABLE IF NOT EXISTS idle_logs (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
    vin VARCHAR(32) NOT NULL DEFAULT 'DEFAULT',
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_s INTEGER DEFAULT 0,
    soc_loss_pct DOUBLE PRECISION DEFAULT 0.0,
    range_loss_km DOUBLE PRECISION DEFAULT 0.0,
    raw_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_idles_vin_start ON idle_logs (vin, started_at DESC);
