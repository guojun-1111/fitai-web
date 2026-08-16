# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""恢复评分：贝叶斯个性化恢复 + 层次贝叶斯人群对比。"""
from fastapi import APIRouter, Request, HTTPException

from core.dependencies import get_user_id, validate_days
from routers.insights_common import _load_daily_metrics

router = APIRouter()


@router.get("/recovery")
async def insights_recovery(request: Request, days: int = 30):
    """贝叶斯个性化恢复评分。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 7:
        return {"score": None, "message": f"数据不足（需至少 7 天，当前 {len(daily_metrics)} 天）"}

    from tools.fitai_database import get_workout_history_json
    from fitai.analysis.bayesian_recovery import BayesianRecoveryModel, get_user_model
    from fitai.analysis.trends import compute_health_score

    dates = sorted(daily_metrics.keys())
    model = get_user_model(user_id)

    # 增量更新：只喂入上次更新之后的新数据
    last_fed = getattr(model, '_last_fed_date', None)
    new_dates = dates if last_fed is None else [d for d in dates if d > last_fed]

    # Feed historical data to model
    workout_history = get_workout_history_json(user_id, days)
    workout_by_date = {}
    for w in workout_history:
        d = w.get("date", "")
        workout_by_date[d] = workout_by_date.get(d, 0) + 1

    for i, d in enumerate(dates):
        if d not in new_dates:
            continue
        m = daily_metrics[d]
        sleep_min = m.get("sleep", 0)
        steps = m.get("steps", 0)
        hr = m.get("heart_rate", 0)
        workout_count = workout_by_date.get(d, 0)
        workout_intensity = min(workout_count * 3, 10)
        sleep_hours = sleep_min / 60 if sleep_min > 0 else 7
        hr_deviation = abs(hr - 70) / 10 if hr > 30 else 0
        training_streak = 1 if workout_count > 0 else 0
        if i > 0:
            prev_m = daily_metrics[dates[i - 1]]
            prev_steps = prev_m.get("steps", 0)
            if steps >= prev_steps * 0.8:
                training_streak = min(training_streak + 1, 30)

        observed = None
        if i < len(dates) - 1:
            next_m = daily_metrics[dates[i + 1]]
            next_steps = next_m.get("steps", 0)
            next_hr = next_m.get("heart_rate", 0)
            if steps > 0 and next_hr > 0:
                recovery = max(0, min(100, 50 + (next_steps / max(steps, 1) - 1) * 30 - (next_hr / max(hr, 1) - 1) * 20))
                observed = recovery

        model.update(workout_intensity, sleep_hours, hr_deviation, steps, training_streak, observed)

    # 记录已喂入的最后日期
    model._last_fed_date = dates[-1] if dates else None

    # Predict today
    last_m = daily_metrics[dates[-1]]
    features = {
        "workout_intensity": workout_by_date.get(dates[-1], 0) * 3,
        "sleep_hours": last_m.get("sleep", 420) / 60,
        "hr_deviation": abs(last_m.get("heart_rate", 70) - 70) / 10,
        "steps": last_m.get("steps", 0),
        "training_streak": 1,
    }
    pred = model.predict(**features)

    health_score = compute_health_score(last_m) if last_m else 50

    return {
        "recovery_score": round(pred.get("score", 50), 1),
        "recovery_ci": [round(pred.get("ci_lower", 30), 1), round(pred.get("ci_upper", 70), 1)],
        "health_score": health_score,
        "n_days": len(daily_metrics),
        "message": _recovery_interpretation(pred.get("score", 50)),
    }


def _recovery_interpretation(score):
    if score >= 80: return "恢复良好，可以正常训练"
    if score >= 60: return "恢复一般，建议中低强度训练"
    if score >= 40: return "恢复不足，建议休息或轻度活动"
    return "恢复很差，建议今天休息"


@router.get("/recovery/population")
async def insights_recovery_population(request: Request, days: int = 30):
    """层次贝叶斯恢复评分（含人群对比）。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 7:
        return {"personal_score": None, "message": "数据不足"}

    from fitai.analysis.hierarchical_bayes import HierarchicalBayesianModel

    hbm = HierarchicalBayesianModel()
    dates = sorted(daily_metrics.keys())

    for i, d in enumerate(dates):
        m = daily_metrics[d]
        features = [
            m.get("sleep", 420) / 60,
            m.get("steps", 0) / 1000,
            m.get("heart_rate", 70),
            m.get("calories", 0) / 100,
        ]
        observed = None
        if i < len(dates) - 1:
            nm = daily_metrics[dates[i + 1]]
            nr = 50 + (nm.get("steps", 0) / max(m.get("steps", 1), 1) - 1) * 30
            observed = max(0, min(100, nr))
        hbm.update_user(user_id, features, observed)

    last_m = daily_metrics[dates[-1]]
    features = [
        last_m.get("sleep", 420) / 60,
        last_m.get("steps", 0) / 1000,
        last_m.get("heart_rate", 70),
        last_m.get("calories", 0) / 100,
    ]
    result = hbm.predict(user_id, features)

    return {
        "personal_score": round(result.get("prediction", 50), 1),
        "personal_ci": round(result.get("ci_width", 20), 1),
        "population_mean": round(hbm.mu_pop, 1) if hasattr(hbm, "mu_pop") else 50,
        "n_days": len(daily_metrics),
    }
