-- Phase 2: Peak-hour forecasting
-- Run this script against the existing queue_flow MySQL database.
-- This migration does not modify existing rows or Stage 1 tables.

CREATE TABLE IF NOT EXISTS forecast_model_runs (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    model_path VARCHAR(255) NOT NULL,
    dataset_path VARCHAR(255) NOT NULL,
    trained_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    training_rows INT NOT NULL,
    test_rows INT NOT NULL,
    mae FLOAT NOT NULL,
    rmse FLOAT NOT NULL,
    r2 FLOAT NOT NULL,
    is_simulated BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS peak_forecasts (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    department_id INT NOT NULL,
    forecast_date DATE NOT NULL,
    time_slot VARCHAR(30) NOT NULL,
    expected_bookings FLOAT NOT NULL,
    demand_level VARCHAR(10) NOT NULL,
    active_counters INT NOT NULL,
    recommendation TEXT NOT NULL,
    model_run_id INT NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_peak_forecast_department_date_slot
        UNIQUE (department_id, forecast_date, time_slot),
    CONSTRAINT fk_peak_forecast_department
        FOREIGN KEY (department_id) REFERENCES departments(id),
    CONSTRAINT fk_peak_forecast_model_run
        FOREIGN KEY (model_run_id) REFERENCES forecast_model_runs(id)
);
