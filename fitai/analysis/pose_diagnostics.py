# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V21: Pose diagnostics engine — causal root cause analysis for exercise form.

Takes per-rep squat metrics from the browser pose engine and produces:
1. Degradation signature: which metric failed first, what followed
2. Root cause diagnosis: mapped through biomechanical knowledge to muscle/joint causes
3. Actionable corrections: specific warmup/correction exercises

Architecture:
  - Rep correlation analysis identifies which form deviations co-occur
  - Degradation ordering (from changepoint) identifies the PRIMARY failure
  - Biomechanical KB maps deviation patterns → muscle weaknesses/mobility issues
  - KG fallback enriches with equipment alternatives and safety tips

Pure functions — no DB access, no side effects. Designed for 10–30 rep samples.
"""
from __future__ import annotations

import math
from typing import Optional

# ── Biomechanical Knowledge Base ──────────────────────────────

# Maps (primary_deviation, secondary_context) → (root_cause, correction, correction_exercise, confidence_boost)
_SQUAT_DIAGNOSES = {
    # Knee valgus (caving in) — the most common and dangerous squat fault
    ("kneeValgus", "hipAngle_shallow"): {
        "diagnosis": "膝盖内扣的主要原因是臀中肌力量不足，导致髋外展无力。同时髋角未到深度说明臀肌整体激活不够。",
        "causal_path": "臀中肌无力 → 髋外展控制差 → 膝内扣 → 膝关节内侧压力增大",
        "correction": "训练前做2组弹力带侧步走激活臀中肌；深蹲时想象'把地面拧开'，主动用臀肌推动膝盖向外",
        "correction_exercise": "弹力带侧步走（侧向行走）",
        "confidence_boost": 0.15,
    },
    ("kneeValgus", "backAngle_rounded"): {
        "diagnosis": "膝内扣伴随背部弯曲，说明核心和臀肌同时无力。身体在底部失去了稳定性。",
        "causal_path": "核心失稳 + 臀肌无力 → 身体前倾代偿 → 膝内扣 → 力线失衡",
        "correction": "优先加强核心稳定性（平板支撑、鸟狗式），再激活臀肌（臀桥、弹力带侧步走）。降低深蹲幅度到可以保持背部挺直的程度",
        "correction_exercise": "平板支撑 + 臀桥（降阶组合）",
        "confidence_boost": 0.10,
    },
    ("kneeValgus", "default"): {
        "diagnosis": "膝盖内扣说明臀中肌力量不足，髋关节外展肌群无法在蹲起过程中维持膝盖在脚踝正上方。",
        "causal_path": "臀中肌无力 → 髋外展控制差 → 膝内扣",
        "correction": "热身时加入弹力带侧步走或蛤蚌式开合（clamshell），激活臀中肌后再开始深蹲",
        "correction_exercise": "弹力带侧步走（侧向行走）",
        "confidence_boost": 0.05,
    },

    # Rounded back — core failure
    ("backAngle", "kneeValgus_caving"): {
        "diagnosis": "背部弯曲同时伴随膝内扣，说明核心和下肢稳定肌群全面疲劳。这是深蹲中最危险的代偿模式。",
        "causal_path": "核心肌群疲劳 → 脊柱屈曲代偿 → 骨盆后倾 → 膝关节代偿内扣",
        "correction": "立即降低训练强度。用高脚杯深蹲替代自重深蹲——胸前负重会自然迫使你保持躯干直立。训练后加强平板支撑和鸟狗式",
        "correction_exercise": "高脚杯深蹲（用轻哑铃或水瓶）",
        "confidence_boost": 0.12,
    },
    ("backAngle", "default"): {
        "diagnosis": "背部弯曲说明核心肌群（腹横肌、竖脊肌）在底部无法维持脊柱中立位。常见于核心力量不足或注意力分散。",
        "causal_path": "核心肌群无力/疲劳 → 脊柱屈曲 → 腰椎负荷增加 → 受伤风险上升",
        "correction": "深蹲前做1分钟平板支撑激活核心。深蹲时想象'挺胸、肩胛收紧'，眼睛看前方略高处。如果无法保持背部挺直，先练半蹲",
        "correction_exercise": "平板支撑（核心激活）",
        "confidence_boost": 0.05,
    },

    # Hip not deep enough — glute/hip flexor issue
    ("hipAngle", "kneeAngle_shallow"): {
        "diagnosis": "髋角和膝角都不够深，说明你可能在下意识地'自我保护'——髋屈肌紧张或对深蹲动作不熟悉。",
        "causal_path": "髋屈肌紧张 + 动作模式不熟练 → 不敢下蹲 → 臀肌刺激不足 → 训练效果打折",
        "correction": "训练前做弓步髋屈肌拉伸（每侧30秒）和自重深蹲练习（手扶墙，专注底部姿势）。不要追求深度，先追求动作正确",
        "correction_exercise": "弓步髋屈肌拉伸",
        "confidence_boost": 0.08,
    },
    ("hipAngle", "default"): {
        "diagnosis": "髋角不够说明臀肌在底部没有足够下降。常见原因是髋屈肌紧张或臀肌激活不足。",
        "causal_path": "髋屈肌紧张/臀肌激活不足 → 下蹲幅度受限 → 臀肌训练不足",
        "correction": "热身时做臀桥激活臀肌，然后做弓步拉伸髋屈肌。深蹲时想象'坐进椅子'，臀部主动向后向下",
        "correction_exercise": "臀桥（臀部激活）",
        "confidence_boost": 0.05,
    },

    # Knee too deep (butt wink / ankle mobility)
    ("kneeAngle", "backAngle_rounded"): {
        "diagnosis": "蹲得过深且背部弯曲，这被称为'屁股眨眼（butt wink）'——由踝关节背屈活动度不足导致骨盆在底部被迫后倾。",
        "causal_path": "踝关节背屈不足 → 底部骨盆后倾 → 腰椎屈曲 → 下背痛风险",
        "correction": "不要追求全蹲。蹲到背部开始弯曲前的深度即可。同时训练踝关节活动度：每天做足背屈拉伸（弓步推墙，后脚跟不离地）",
        "correction_exercise": "足背屈拉伸（弓步推墙）",
        "confidence_boost": 0.15,
    },
    ("kneeAngle", "default"): {
        "diagnosis": "蹲得太深了。超过活动度范围后骨盆会被迫后倾（butt wink），给腰椎带来压力。好的深度是背部开始弯曲前的那一点。",
        "causal_path": "蹲过活动度极限 → 骨盆后倾 → 腰椎屈曲 → 下背痛",
        "correction": "找到你自己的'安全深度'——在镜子前做深蹲，当背部开始弯曲时停住，那就是你的极限深度。日常训练踝关节和髋关节活动度来扩大这个范围",
        "correction_exercise": "控制深度（半蹲/平行蹲即可）",
        "confidence_boost": 0.05,
    },
}

# Fallback diagnosis when no clear pattern is found
_FALLBACK_DIAGNOSIS = {
    "diagnosis": "你的动作整体质量尚可，但仍有优化空间。建议对着镜子练习，关注动作的一致性和流畅性。",
    "causal_path": "无显著偏差 → 持续练习 → 动作自动化",
    "correction": "继续保持规律训练。可以录下自己的训练视频，对比标准动作找出细微差异",
    "correction_exercise": "镜子前慢速深蹲（动作控制训练）",
    "confidence_boost": 0.0,
}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _corr(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sx, sy = _std(xs), _std(ys)
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    return cov / (sx * sy)


def _identify_primary_deviation(reps: list[dict]) -> tuple[str, float, int]:
    """Find which metric degraded the most and earliest.

    Returns (metric_name, severity_score, first_bad_rep_index).
    """
    metrics = {
        "kneeAngle": {"ideal": 90, "values": [], "tolerance": 30},
        "hipAngle": {"ideal": 70, "values": [], "tolerance": 25},
        "backAngle": {"ideal": 10, "values": [], "tolerance": 20},  # lower is better
        "kneeValgus": {"ideal": 2, "values": [], "tolerance": 6},   # lower is better
    }

    for rep in reps:
        for key in metrics:
            val_key = key + "_min" if key in ("kneeAngle", "hipAngle") else key + "_max"
            raw = rep.get(val_key)
            if raw is not None:
                metrics[key]["values"].append(float(raw))

    # Score each metric: average deviation from ideal, weighted by recency
    best = None
    best_score = -1
    best_first_bad = len(reps)

    for mkey, md in metrics.items():
        vals = md["values"]
        if len(vals) < 3:
            continue
        ideal = md["ideal"]
        tol = md["tolerance"]

        # Severity: mean normalized deviation (more weight to later reps)
        deviations = [abs(v - ideal) / tol for v in vals]
        severity = sum(deviations) / len(deviations)

        # Find the first rep where deviation crosses threshold
        first_bad = len(vals)
        for i, d in enumerate(deviations):
            if d > 0.5:  # more than 50% of tolerance
                first_bad = i + 1  # 1-indexed rep number
                break

        # Composite: severity * (1 + recency bonus for later first_bad)
        recency_penalty = 1.0 + max(0, (len(vals) - first_bad) / max(len(vals), 1)) * 0.3
        score = severity * recency_penalty

        if score > best_score:
            best_score = score
            best = mkey
            best_first_bad = first_bad

    return (best or "kneeAngle", best_score, best_first_bad)


def _correlation_signature(reps: list[dict]) -> dict[str, dict]:
    """Compute pairwise correlations and co-deviation patterns."""
    metric_keys = ["kneeAngle_min", "hipAngle_min", "backAngle_max", "kneeValgus_max", "quality"]
    series = {}
    for key in metric_keys:
        series[key] = [float(rep.get(key, 0)) for rep in reps if key in rep]

    pairs = {}
    names = [
        ("kneeAngle_min", "kneeAngle"),
        ("hipAngle_min", "hipAngle"),
        ("backAngle_max", "backAngle"),
        ("kneeValgus_max", "kneeValgus"),
    ]

    for (k1, n1), (k2, n2) in zip(names, names[1:] + names[:1]):
        if k1 in series and k2 in series:
            r = _corr(series[k1], series[k2])
            pairs[f"{n1}_{n2}"] = {"correlation": round(r, 3), "significant": abs(r) > 0.3}

    # Quality correlations
    if "quality" in series:
        for key, name in names:
            if key in series:
                r = _corr(series["quality"], series[key])
                pairs[f"quality_vs_{name}"] = {"correlation": round(r, 3), "significant": abs(r) > 0.3}

    return pairs


def _match_diagnosis(primary: str, corr_sig: dict[str, dict]) -> dict:
    """Match the deviation pattern to a biomechanical diagnosis."""
    # Determine secondary context from correlations
    context = "default"

    # Check if another metric co-deviates significantly
    if primary != "kneeValgus":
        key = f"kneeValgus_{primary}"
        if key in corr_sig and corr_sig[key]["significant"]:
            context = f"kneeValgus_caving"
    if context == "default" and primary != "backAngle":
        key = f"backAngle_{primary}"
        if key in corr_sig and corr_sig[key]["significant"]:
            context = f"backAngle_rounded"
    if context == "default" and primary != "hipAngle":
        key = f"hipAngle_{primary}"
        if key in corr_sig and corr_sig[key]["significant"]:
            context = f"hipAngle_shallow"
    if context == "default" and primary != "kneeAngle":
        key = f"kneeAngle_{primary}"
        if key in corr_sig and corr_sig[key]["significant"]:
            context = f"kneeAngle_shallow"

    # Exact match
    key = (primary, context)
    if key in _SQUAT_DIAGNOSES:
        return _SQUAT_DIAGNOSES[key]

    # Fallback to primary-only match
    key = (primary, "default")
    if key in _SQUAT_DIAGNOSES:
        return _SQUAT_DIAGNOSES[key]

    return _FALLBACK_DIAGNOSIS


def analyze_squat_set(
    reps: list[dict],
    changepoint_state: Optional[dict] = None,
    user_pain_points: Optional[list[str]] = None,
) -> dict:
    """Analyze a set of squat reps and return root cause diagnosis.

    Args:
        reps: List of per-rep metrics from pose.js:
              [{rep, kneeAngle_min, hipAngle_min, backAngle_max, kneeValgus_max, quality, duration_ms}, ...]
        changepoint_state: Optional CUSUM state from browser changepoint detector
        user_pain_points: Optional list of user-reported pain areas (from onboarding)

    Returns:
        {
            diagnosis: str,          # human-readable root cause
            confidence: float,       # 0.0–1.0
            causal_path: str,        # chain of causation
            correction: str,         # actionable advice
            correction_exercise: str,# specific exercise to fix the issue
            quality_trend: str,      # 'improving' | 'stable' | 'declining'
            fatigue_detected: bool,
            fatigue_rep_index: int | null,
            correlation_signature: dict,
            primary_deviation: str,
        }
    """
    if not reps or len(reps) < 3:
        return {
            "diagnosis": "数据不足",
            "confidence": 0.0,
            "causal_path": "",
            "correction": "至少需要3个完整的深蹲 reps 才能进行分析",
            "correction_exercise": "",
            "quality_trend": "stable",
            "fatigue_detected": False,
            "fatigue_rep_index": None,
            "correlation_signature": {},
            "primary_deviation": "",
        }

    # 1. Identify primary deviation
    primary, severity, first_bad_rep = _identify_primary_deviation(reps)

    # 2. Correlation signature
    corr_sig = _correlation_signature(reps)

    # 3. Match to biomechanical diagnosis
    diagnosis = dict(_match_diagnosis(primary, corr_sig))

    # 4. Trend analysis
    qualities = [float(r.get("quality", 50)) for r in reps if "quality" in r]
    quality_trend = "stable"
    if len(qualities) >= 5:
        first_half = _mean(qualities[:len(qualities)//2])
        second_half = _mean(qualities[len(qualities)//2:])
        if second_half > first_half + 3:
            quality_trend = "improving"
        elif second_half < first_half - 3:
            quality_trend = "declining"

    # 5. Fatigue detection from changepoint state
    fatigue_detected = False
    fatigue_rep_index = None
    if changepoint_state:
        fatigue_detected = changepoint_state.get("state", "normal") != "normal"
        if fatigue_detected and first_bad_rep < len(reps):
            fatigue_rep_index = first_bad_rep

    # 6. Confidence computation
    base_conf = 0.55  # base confidence
    # Higher severity → higher confidence
    base_conf += min(severity * 0.08, 0.15)
    # More reps → higher confidence
    base_conf += min(len(reps) * 0.005, 0.10)
    # Quality declining → higher confidence in diagnosis
    if quality_trend == "declining":
        base_conf += 0.08
    # Co-deviation boosts confidence
    sig_count = sum(1 for v in corr_sig.values() if isinstance(v, dict) and v.get("significant"))
    base_conf += sig_count * 0.04
    # Biomechanical knowledge boost
    base_conf += diagnosis.pop("confidence_boost", 0.0)
    confidence = round(max(0.3, min(0.95, base_conf)), 3)

    return {
        "diagnosis": diagnosis["diagnosis"],
        "confidence": confidence,
        "causal_path": diagnosis["causal_path"],
        "correction": diagnosis["correction"],
        "correction_exercise": diagnosis["correction_exercise"],
        "quality_trend": quality_trend,
        "fatigue_detected": fatigue_detected,
        "fatigue_rep_index": fatigue_rep_index,
        "correlation_signature": corr_sig,
        "primary_deviation": primary,
    }


# ── V22: Push-up Diagnoses ──────────────────────────────────

_PUSHUP_DIAGNOSES = {
    ("elbowAngle", "bodyLine_bad"): {
        "diagnosis": "塌腰伴随肘角过大，核心肌群力量不足，无法在俯卧撑过程中维持身体直线。",
        "causal_path": "核心肌群无力 → 骨盆前倾/塌腰 → 身体代偿 → 胸肌刺激不足",
        "correction": "先练跪姿俯卧撑或上斜俯卧撑降低难度，每天加做1分钟平板支撑强化核心",
        "correction_exercise": "跪姿俯卧撑 + 平板支撑",
        "confidence_boost": 0.12,
    },
    ("elbowAngle", "default"): {
        "diagnosis": "俯卧撑幅度不够或过深。理想深度是肘关节呈90度。",
        "causal_path": "动作模式不熟练 → 幅度不稳定 → 训练效果打折",
        "correction": "在胸口下方放一个网球或瑜伽砖，每次下降到胸触到它再推起",
        "correction_exercise": "触胸俯卧撑（用物品辅助测深度）",
        "confidence_boost": 0.05,
    },
    ("bodyLine", "default"): {
        "diagnosis": "身体没有保持一条直线，核心没有收紧，臀部和腹部松弛。",
        "causal_path": "核心失稳 → 骨盆前倾 → 腰椎压力增大 → 胸肌训练不足",
        "correction": "做俯卧撑前先做30秒平板支撑激活核心，全程想象'肚脐往脊椎方向收'",
        "correction_exercise": "平板支撑 → 俯卧撑（核心激活后）",
        "confidence_boost": 0.08,
    },
}

_PLANK_DIAGNOSES = {
    ("hipSag", "default"): {
        "diagnosis": "臀部下沉（塌腰），核心肌群在平板支撑过程中疲劳导致腰椎过度前凸。",
        "causal_path": "腹横肌/腹直肌疲劳 → 骨盆前倾 → 腰椎受压 → 下背痛风险",
        "correction": "缩短单次平板时间，多做几组短时间高质量支撑。例如30秒×3组替代90秒×1组",
        "correction_exercise": "短时高频平板（30秒×3组）",
        "confidence_boost": 0.10,
    },
    ("hipRaise", "default"): {
        "diagnosis": "臀部上翘，用臀肌代偿核心力量不足。常见的'假平板'现象。",
        "causal_path": "核心力量不足 → 臀肌代偿抬高臀部 → 腹肌训练效果为零",
        "correction": "对着镜子做平板，确保肩、髋、膝、踝在一条直线上。如果无法维持5秒，从跪姿平板开始",
        "correction_exercise": "镜子前平板支撑（视觉反馈纠正）",
        "confidence_boost": 0.08,
    },
}

_LUNGE_DIAGNOSES = {
    ("frontKnee", "torso_bad"): {
        "diagnosis": "前膝过度前移伴随身体前倾，股四头肌发力过多而臀肌参与不足。",
        "causal_path": "臀肌激活不足 → 身体前倾代偿 → 膝压力增大 → 前十字韧带风险",
        "correction": "箭步蹲前先做臀桥激活臀肌。下蹲时想象'臀部向后坐'，膝盖不超脚尖",
        "correction_exercise": "臀桥 → 箭步蹲（臀肌激活后）",
        "confidence_boost": 0.10,
    },
    ("frontKnee", "default"): {
        "diagnosis": "前膝关节角度不理想，可能蹲得过深或不够深。",
        "causal_path": "动作控制不一致 → 训练刺激不稳定",
        "correction": "在镜子前练习，确保前大腿与地面平行（膝角90°），小腿与地面垂直",
        "correction_exercise": "镜子前慢速箭步蹲",
        "confidence_boost": 0.05,
    },
}

_YTW_DIAGNOSES = {
    ("shoulderShrug", "default"): {
        "diagnosis": "手臂抬起时耸肩，上斜方肌过度代偿，肩袖肌群和背部没有正确发力。",
        "causal_path": "上斜方肌过度活跃 → 肩胛骨上提 → 肩袖肌群抑制 → 肩部训练无效",
        "correction": "做YTW前先做'沉肩'练习：双肩向下向后沉，保持这个位置再开始动作。想象'肩胛骨往裤兜里塞'",
        "correction_exercise": "沉肩练习 + YTW（肩胛骨锁定后）",
        "confidence_boost": 0.10,
    },
    ("asymmetry", "default"): {
        "diagnosis": "左右手臂角度不对称，一侧肩关节活动度或力量受限。",
        "causal_path": "单侧灵活性受限 → 不对称发力 → 肌肉不平衡加剧",
        "correction": "用较轻的弹力带或徒手做单侧YTW，先改善弱侧的活动度再双侧对称练习",
        "correction_exercise": "单侧弹力带 YTW（改善不对称）",
        "confidence_boost": 0.08,
    },
}

_FALLBACK_PUSHUP = {"diagnosis":"动作整体还行。建议对着镜子检查身体是否成一条直线","causal_path":"持续练习 → 动作自动化","correction":"保持当前训练，每次关注一个细节","correction_exercise":"标准俯卧撑","confidence_boost":0.0}
_FALLBACK_PLANK = {"diagnosis":"平板支撑质量尚可。继续坚持，逐步延长支撑时间","causal_path":"持续练习 → 核心耐力提升","correction":"每次比上次多坚持5-10秒","correction_exercise":"平板支撑","confidence_boost":0.0}
_FALLBACK_LUNGE = {"diagnosis":"箭步蹲动作尚可。注意保持左右腿力量均衡","causal_path":"持续练习 → 下肢力量/稳定性提升","correction":"确保两腿训练量一致","correction_exercise":"交替箭步蹲","confidence_boost":0.0}
_FALLBACK_YTW = {"diagnosis":"YTW动作完成。注意控制动作速度，不要甩动手臂","causal_path":"持续练习 → 肩部健康和姿势改善","correction":"用慢速控制做每组YTW（每个位置停留2秒）","correction_exercise":"慢速控制 YTW","confidence_boost":0.0}


def analyze_pushup_set(reps: list[dict], changepoint_state: dict | None = None) -> dict:
    if not reps or len(reps) < 3:
        return {"diagnosis":"数据不足","confidence":0.0,"causal_path":"","correction":"至少需要3个完整俯卧撑","correction_exercise":"","quality_trend":"stable","fatigue_detected":False,"fatigue_rep_index":None,"primary_deviation":""}

    elbow_vals = [float(r.get("elbowAngle_min",90)) for r in reps if "elbowAngle_min" in r]
    body_vals = [float(r.get("bodyLine_max",0)) for r in reps if "bodyLine_max" in r]

    elbow_dev = sum(abs(v-90)/30 for v in elbow_vals) / max(len(elbow_vals),1)
    body_dev = sum(v/8 for v in body_vals) / max(len(body_vals),1)

    primary = "bodyLine" if body_dev > elbow_dev else "elbowAngle"
    diag = _FALLBACK_PUSHUP
    if primary == "bodyLine" and body_dev > 0.5:
        diag = _PUSHUP_DIAGNOSES.get(("bodyLine","default"), _FALLBACK_PUSHUP)
    elif primary == "elbowAngle":
        diag = _PUSHUP_DIAGNOSES.get(("elbowAngle","default"), _FALLBACK_PUSHUP)

    qualities = [float(r.get("quality",50)) for r in reps if "quality" in r]
    trend = "stable"
    if len(qualities)>=5:
        fh = sum(qualities[:len(qualities)//2])/max(len(qualities)//2,1)
        sh = sum(qualities[len(qualities)//2:])/max(len(qualities)-len(qualities)//2,1)
        if sh>fh+3: trend="improving"
        elif sh<fh-3: trend="declining"

    fatigue = changepoint_state.get("state","normal")!="normal" if changepoint_state else False
    conf = round(min(0.9, 0.5+body_dev*0.15+len(reps)*0.01), 3)
    return {"diagnosis":diag["diagnosis"],"confidence":conf,"causal_path":diag["causal_path"],"correction":diag["correction"],"correction_exercise":diag["correction_exercise"],"quality_trend":trend,"fatigue_detected":fatigue,"fatigue_rep_index":None,"primary_deviation":primary}


def analyze_plank_session(data: dict) -> dict:
    duration = data.get("duration_sec", 0)
    avg_quality = data.get("avg_quality", 70)
    hip_sag_count = data.get("hip_sag_events", 0)

    if hip_sag_count > 3:
        diag = _PLANK_DIAGNOSES[("hipSag","default")]
    elif avg_quality < 60:
        diag = _PLANK_DIAGNOSES[("hipRaise","default")]
    else:
        diag = _FALLBACK_PLANK

    conf = round(min(0.9, 0.5+duration*0.002+hip_sag_count*0.05), 3)
    return {"diagnosis":diag["diagnosis"],"confidence":conf,"causal_path":diag["causal_path"],"correction":diag["correction"],"correction_exercise":diag["correction_exercise"],"quality_trend":"stable","fatigue_detected":hip_sag_count>5,"fatigue_rep_index":None,"primary_deviation":"hipSag" if hip_sag_count>3 else "none"}


def analyze_lunge_set(reps: list[dict], changepoint_state: dict | None = None) -> dict:
    if not reps or len(reps) < 3:
        return {"diagnosis":"数据不足","confidence":0.0,"causal_path":"","correction":"至少需要3个完整箭步蹲","correction_exercise":"","quality_trend":"stable","fatigue_detected":False,"fatigue_rep_index":None,"primary_deviation":""}

    knee_vals = [float(r.get("frontKneeAngle_min",90)) for r in reps if "frontKneeAngle_min" in r]
    torso_vals = [float(r.get("torsoAngle_max",0)) for r in reps if "torsoAngle_max" in r]

    knee_dev = sum(abs(v-90)/30 for v in knee_vals) / max(len(knee_vals),1)
    torso_dev = sum(v/25 for v in torso_vals) / max(len(torso_vals),1)

    primary = "frontKnee"
    diag = _LUNGE_DIAGNOSES.get(("frontKnee","default"), _FALLBACK_LUNGE)
    if torso_dev > 0.5 and knee_dev > 0.5:
        diag = _LUNGE_DIAGNOSES[("frontKnee","torso_bad")]

    qualities = [float(r.get("quality",50)) for r in reps if "quality" in r]
    trend = "declining" if len(qualities)>=3 and qualities[-1]<qualities[0]-5 else "stable"

    fatigue = changepoint_state.get("state","normal")!="normal" if changepoint_state else False
    conf = round(min(0.9, 0.5+knee_dev*0.15+torso_dev*0.1+len(reps)*0.01), 3)
    return {"diagnosis":diag["diagnosis"],"confidence":conf,"causal_path":diag["causal_path"],"correction":diag["correction"],"correction_exercise":diag["correction_exercise"],"quality_trend":trend,"fatigue_detected":fatigue,"fatigue_rep_index":None,"primary_deviation":primary}


def analyze_ytw_session(reps: list[dict]) -> dict:
    if not reps or len(reps) < 2:
        return {"diagnosis":"数据不足","confidence":0.0,"causal_path":"","correction":"至少需要2组完整YTW","correction_exercise":"","quality_trend":"stable","fatigue_detected":False,"fatigue_rep_index":None,"primary_deviation":""}

    arm_vals = [float(r.get("avgArmAngle",45)) for r in reps if "avgArmAngle" in r]
    avg_arm = sum(arm_vals)/max(len(arm_vals),1)
    # Check for asymmetry by looking at variation
    asymmetry = max(arm_vals)-min(arm_vals) > 15 if len(arm_vals)>=2 else False

    diag = _YTW_DIAGNOSES[("asymmetry","default")] if asymmetry else _FALLBACK_YTW
    conf = round(min(0.85, 0.5+len(reps)*0.03), 3)
    return {"diagnosis":diag["diagnosis"],"confidence":conf,"causal_path":diag["causal_path"],"correction":diag["correction"],"correction_exercise":diag["correction_exercise"],"quality_trend":"stable","fatigue_detected":False,"fatigue_rep_index":None,"primary_deviation":"asymmetry" if asymmetry else "none"}
