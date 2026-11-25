"""
services/waiting_time.py
Wait-Time Estimation Adapter for QueueFlow AI.

IMPORTANT:
The Machine Learning waiting-time prediction model is currently under development
separately by team member Poojashree.

Until the trained model binary and interface are delivered, this module provides
a transparent, clearly-labelled heuristic estimation based on average service durations
and queue depth.

DO NOT label this heuristic calculation as an "AI" or "ML" prediction in the UI.
When Poojashree provides her trained model, connect it inside the `predict_ml_waiting_time`
hook below without modifying any routes or templates.
"""

from datetime import datetime
from pathlib import Path
import os

import joblib
import pandas as pd

from flask import has_app_context, current_app


ML_ARTIFACT_PATH = (
    Path(__file__).resolve().parent.parent
    / "ml"
    / "artifacts"
    / "waiting_time_model.joblib"
)
ML_METADATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "ml"
    / "artifacts"
    / "model_metadata.json"
)
_ML_MODEL = None
_ML_MODEL_LOADED = False
_ML_MODEL_ERROR = None


def _ml_predictions_enabled():
    if has_app_context():
        configured = current_app.config.get("ML_WAITING_TIME_ENABLED")
        if configured is not None:
            return bool(configured)

    value = os.getenv("ML_WAITING_TIME_ENABLED", "true").lower()
    return value in ("1", "true", "yes", "on")


def _load_ml_model():
    global _ML_MODEL, _ML_MODEL_LOADED, _ML_MODEL_ERROR
    if _ML_MODEL_LOADED:
        return _ML_MODEL, _ML_MODEL_ERROR

    _ML_MODEL_LOADED = True
    try:
        if not ML_ARTIFACT_PATH.exists():
            _ML_MODEL_ERROR = "Model artifact was not found."
            return None, _ML_MODEL_ERROR
        _ML_MODEL = joblib.load(ML_ARTIFACT_PATH)
        _ML_MODEL_ERROR = None
    except Exception as error:
        _ML_MODEL = None
        _ML_MODEL_ERROR = str(error)

    return _ML_MODEL, _ML_MODEL_ERROR


def calculate_waiting_time(queue_position, average_service_minutes=15, is_serving=False):
    """
    Computes an estimated waiting time using a deterministic heuristic algorithm.

    Inputs:
        - queue_position (int): 1-based position in queue.
          (1 = currently next up, 2 = 1 person ahead, etc.)
        - average_service_minutes (int): Expected minutes per visitor service (default 15).
        - is_serving (bool): True if this specific token is currently being called.

    Outputs:
        dict:
            - estimated_minutes (int): Total expected waiting time in minutes.
            - people_ahead (int): Number of visitors ahead in the queue.
            - label (str): User-friendly display text clearly stating heuristic nature.
            - is_ml (bool): False for this heuristic adapter.
            - model_source (str): Explanatory identifier.
    """
    if is_serving:
        return {
            "estimated_minutes": 0,
            "people_ahead": 0,
            "label": "Now Serving at Counter",
            "is_ml": False,
            "model_source": "Active Service Desk"
        }

    if not queue_position or queue_position <= 0:
        return {
            "estimated_minutes": 0,
            "people_ahead": 0,
            "label": "Awaiting Counter Assignment",
            "is_ml": False,
            "model_source": "Pre-Queue Processing"
        }

    people_ahead = max(0, queue_position - 1)

    if people_ahead == 0:
        return {
            "estimated_minutes": 3,
            "people_ahead": 0,
            "label": "~3 mins (You are next in queue)",
            "is_ml": False,
            "model_source": "Standard Queue Heuristic"
        }

    # Heuristic calculation: people ahead * service duration, with a lower bound
    estimated_mins = people_ahead * max(5, average_service_minutes)

    return {
        "estimated_minutes": estimated_mins,
        "people_ahead": people_ahead,
        "label": f"~{estimated_mins} mins ({people_ahead} ahead in queue)",
        "is_ml": False,
        "model_source": "Standard Queue Heuristic (Heuristic Estimation)"
    }


def predict_ml_waiting_time(
    department_id,
    counter_id,
    queue_position,
    priority="normal",
    average_service_minutes=15,
    active_counters=None,
    estimated_workload_ahead=None,
    arrival_datetime=None,
    queue_category="student",
    service_category=None,
    ml_enabled=None,
):
    """Predict waiting time with a cached ML artifact and safe fallback."""
    people_ahead = max(0, int(queue_position or 0) - 1)
    heuristic = calculate_waiting_time(
        queue_position=queue_position,
        average_service_minutes=average_service_minutes,
    )

    enabled = _ml_predictions_enabled() if ml_enabled is None else bool(ml_enabled)
    if not enabled:
        fallback = dict(heuristic)
        fallback["model_source"] = "HEURISTIC_FALLBACK (ML disabled)"
        return fallback

    model, model_error = _load_ml_model()
    if model is None:
        fallback = dict(heuristic)
        fallback["model_source"] = "HEURISTIC_FALLBACK (model unavailable)"
        fallback["fallback_reason"] = model_error
        return fallback

    try:
        queue_position_value = int(queue_position or 0)
        if queue_position_value <= 0:
            return dict(heuristic)

        active_counter_count = int(active_counters or 1)
        active_counter_count = max(1, active_counter_count)
        service_minutes = max(5, int(average_service_minutes or 15))
        workload = (
            int(estimated_workload_ahead)
            if estimated_workload_ahead is not None
            else people_ahead * service_minutes
        )
        workload = max(0, workload)

        arrival_datetime = arrival_datetime or datetime.now()
        normalized_priority = str(priority or "normal").strip().lower()
        allowed_priorities = {"normal", "accessibility", "urgent", "emergency"}
        if normalized_priority not in allowed_priorities:
            normalized_priority = "normal"

        normalized_queue_category = (
            "visitor" if str(queue_category).lower() == "visitor" else "student"
        )
        department_category = f"department_{int(department_id)}" if department_id else "department_unknown"
        if service_category:
            service_name = str(service_category).strip().lower()
            if any(word in service_name for word in ("bonafide", "certificate", "id card")):
                service_category = "certificate_or_id"
            elif "fee" in service_name:
                service_category = "fee_assistance"
            elif any(word in service_name for word in ("wifi", "network")):
                service_category = "network_support"
            elif any(word in service_name for word in ("computer", "lab")):
                service_category = "computer_lab"
            elif any(word in service_name for word in ("book", "issue", "return")):
                service_category = "book_issue"
            elif "library" in service_name or "account" in service_name:
                service_category = "account_assistance"
            else:
                service_category = "account_assistance"
        else:
            service_category = "account_assistance"

        features = pd.DataFrame([{
            "queue_length_ahead": people_ahead,
            "active_counters": active_counter_count,
            "estimated_workload_ahead": workload,
            "token_priority": normalized_priority,
            "department_category": department_category,
            "service_category": service_category,
            "hour_of_arrival": int(arrival_datetime.hour),
            "day_of_week": int(arrival_datetime.weekday()),
            "queue_category": normalized_queue_category,
        }])

        raw_prediction = float(model.predict(features)[0])
        predicted_minutes = max(0, int(round(raw_prediction)))
        return {
            "estimated_minutes": predicted_minutes,
            "people_ahead": people_ahead,
            "label": f"~{predicted_minutes} mins (Prototype ML prediction)",
            "is_ml": True,
            "model_source": "ML_MODEL",
            "dataset_type": "SYNTHETIC DEMONSTRATION DATA",
        }
    except Exception as error:
        fallback = dict(heuristic)
        fallback["model_source"] = "HEURISTIC_FALLBACK (invalid model input)"
        fallback["fallback_reason"] = str(error)
        return fallback
