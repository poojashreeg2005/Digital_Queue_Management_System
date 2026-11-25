from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from ml.generate_peak_data import generate_peak_data
from ml.peak_hour_forecasting import (
    get_model_metrics,
    predict_department,
)
from ml.train_peak_model import train_peak_model
from models import (
    db,
    Department,
    ForecastModelRun,
    PeakForecast,
)
from routes.auth import role_required


forecasting_bp = Blueprint(
    "forecasting",
    __name__,
    url_prefix="/admin/forecasting",
)


def ensure_peak_model(department_names: list[str]) -> dict:
    model_path = Path(current_app.config["PEAK_MODEL_PATH"])
    dataset_path = Path(current_app.config["PEAK_DATASET_PATH"])

    if not dataset_path.exists():
        generate_peak_data(department_names, dataset_path)

    if not model_path.exists():
        train_peak_model(
            dataset_path=dataset_path,
            model_path=model_path,
            metadata_path=model_path.with_name("peak_model_metadata.json"),
        )

    return get_model_metrics(model_path.with_name("peak_model_metadata.json"))


def get_forecast_payload(
    department_id: int | None = None,
    forecast_days: int | None = None,
) -> dict:
    departments = Department.query.filter_by(active=True).order_by(
        Department.name
    ).all()

    if not departments:
        return {
            "departments": [],
            "predictions": [],
            "metrics": {},
            "warning": "No active departments are available for forecasting.",
        }

    department_names = [department.name for department in departments]
    metrics = ensure_peak_model(department_names)
    selected_departments = departments
    if department_id:
        selected_departments = [
            department
            for department in departments
            if department.id == department_id
        ]

    if not selected_departments:
        return {
            "departments": [
                {"id": department.id, "name": department.name}
                for department in departments
            ],
            "predictions": [],
            "metrics": metrics,
            "warning": "The selected department was not found.",
        }

    days = forecast_days or current_app.config["PEAK_FORECAST_DAYS"]
    predictions = []
    for department in selected_departments:
        predictions.extend(
            predict_department(
                department.name,
                forecast_days=days,
                dataset_path=current_app.config["PEAK_DATASET_PATH"],
                model_path=current_app.config["PEAK_MODEL_PATH"],
            )
        )

    return {
        "departments": [
            {"id": department.id, "name": department.name}
            for department in departments
        ],
        "predictions": predictions,
        "metrics": metrics,
        "warning": None,
    }


def persist_forecasts(payload: dict) -> str | None:
    if not payload["predictions"]:
        return payload["warning"]

    metrics = payload["metrics"]
    department_lookup = {
        department["name"]: department["id"]
        for department in payload["departments"]
    }

    try:
        model_run = ForecastModelRun(
            model_path=current_app.config["PEAK_MODEL_PATH"],
            dataset_path=current_app.config["PEAK_DATASET_PATH"],
            training_rows=metrics.get("training_rows", 0),
            test_rows=metrics.get("test_rows", 0),
            mae=metrics.get("mae", 0),
            rmse=metrics.get("rmse", 0),
            r2=metrics.get("r2", 0),
            is_simulated=True,
        )
        db.session.add(model_run)
        db.session.flush()

        for prediction in payload["predictions"]:
            forecast_date = date.fromisoformat(
                prediction["forecast_date"]
            )
            existing = PeakForecast.query.filter_by(
                department_id=department_lookup[prediction["department"]],
                forecast_date=forecast_date,
                time_slot=prediction["time_slot"],
            ).first()
            if existing:
                existing.expected_bookings = prediction["expected_bookings"]
                existing.demand_level = prediction["demand_level"]
                existing.active_counters = prediction["recommended_counters"]
                existing.recommendation = prediction["recommendation"]
                existing.model_run_id = model_run.id
                existing.generated_at = db.func.now()
            else:
                db.session.add(PeakForecast(
                    department_id=department_lookup[
                        prediction["department"]
                    ],
                    forecast_date=forecast_date,
                    time_slot=prediction["time_slot"],
                    expected_bookings=prediction["expected_bookings"],
                    demand_level=prediction["demand_level"],
                    active_counters=prediction["recommended_counters"],
                    recommendation=prediction["recommendation"],
                    model_run_id=model_run.id,
                ))

        db.session.commit()
        return None
    except SQLAlchemyError:
        db.session.rollback()
        return (
            "Forecast results are available, but existing database tables "
            "are not migrated for forecast storage yet."
        )


@forecasting_bp.route("/api")
@login_required
@role_required("admin")
def forecast_api():
    department_id = request.args.get("department_id", type=int)
    forecast_days = request.args.get("days", type=int)
    if forecast_days is not None:
        forecast_days = max(1, min(forecast_days, 30))

    payload = get_forecast_payload(department_id, forecast_days)
    warning = persist_forecasts(payload)
    if warning:
        payload["warning"] = warning
    return jsonify(payload)
