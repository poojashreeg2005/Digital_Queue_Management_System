"""Reusable evaluation helpers for QueueFlow waiting-time models."""

from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def evaluate_regression(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rm_squared_error = mean_squared_error(y_true, y_pred)
    rmse = rm_squared_error ** 0.5
    r2 = r2_score(y_true, y_pred)
    return {
        "mae": round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "r2": round(float(r2), 4),
    }
