# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""预测：SSA 时序预测 + 共形预测区间。"""
from fastapi import APIRouter, Request

from core.dependencies import get_user_id, validate_days
from routers.insights_common import _load_daily_metrics

router = APIRouter()


@router.get("/predictions")
async def insights_predictions(request: Request, metric: str = "steps",
                                days_ahead: int = 7, days: int = 30):
    """SSA 预测 + 共形预测区间。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    days_ahead = min(days_ahead, 30)
    days = validate_days(days, max_days=90)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"predictions": [], "message": "数据不足"}

    dates = sorted(daily_metrics.keys())
    values = []
    for d in dates:
        v = daily_metrics[d].get(metric)
        if v is not None:
            values.append(v)
        else:
            values.append(values[-1] if values else 0)

    if len(values) < 14:
        return {"predictions": [], "message": "该指标数据不足"}

    from fitai.analysis.ssa_forecast import ssa_forecast
    from fitai.analysis.conformal import ConformalPredictor

    # SSA forecast
    forecast_result = ssa_forecast(values, steps=days_ahead)
    forecast_values = forecast_result.get("forecast", [])

    # Conformal prediction intervals (80% coverage)
    try:
        cp = ConformalPredictor(alpha=0.2)
        n_train = len(values) * 2 // 3
        cp.calibrate(values[:n_train], values[n_train:])
        intervals = [cp.predict_intervals([fv])[0] for fv in forecast_values]
    except Exception:
        intervals = [{"lower": fv * 0.8, "upper": fv * 1.2, "prediction": fv} for fv in forecast_values]

    from datetime import date as dt_date, timedelta
    last_date_str = dates[-1]
    try:
        last_date = dt_date.fromisoformat(last_date_str)
    except (ValueError, TypeError):
        last_date = dt_date.today()

    predictions = []
    for i, fv in enumerate(forecast_values):
        d = (last_date + timedelta(days=i + 1)).isoformat()
        iv = intervals[i] if i < len(intervals) else {}
        predictions.append({
            "date": d,
            "predicted": round(fv, 1),
            "ci_lower": round(iv.get("lower", fv * 0.8), 1),
            "ci_upper": round(iv.get("upper", fv * 1.2), 1),
        })

    return {
        "metric": metric,
        "days_ahead": days_ahead,
        "n_historical_days": len(values),
        "predictions": predictions,
        "trend_direction": "up" if (forecast_values[-1] if forecast_values else 0) > values[-1] else "down",
    }
