# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI 工具层 — 从 FitAI/tools.py 移植，所有函数增加 user_id"""
import json
import hashlib
import os
import re
import time as _time
import urllib.parse
from collections import OrderedDict as _OrderedDict

# ── 分析工具结果缓存（Agent 对话中同一用户重复调用时避免重算）──
_analysis_cache = _OrderedDict()
_ANALYSIS_CACHE_TTL = 180  # 3 分钟 TTL
_ANALYSIS_CACHE_MAX = 200


def _analysis_cached(user_id: int, cache_key: str, compute_fn):
    """通用分析缓存：命中返回缓存值，否则计算并缓存。

    缓存键 = f\"{user_id}:{cache_key}\"，TTL = 3 分钟，
    超容时淘汰最旧 50 条。"""
    full_key = f"{user_id}:{cache_key}"
    if full_key in _analysis_cache:
        value, ts = _analysis_cache[full_key]
        if _time.time() - ts < _ANALYSIS_CACHE_TTL:
            _analysis_cache.move_to_end(full_key)
            return value
        del _analysis_cache[full_key]

    result = compute_fn()
    _analysis_cache[full_key] = (result, _time.time())
    _analysis_cache.move_to_end(full_key)

    if len(_analysis_cache) > _ANALYSIS_CACHE_MAX:
        for _ in range(50):
            _analysis_cache.popitem(last=False)

    return result


def invalidate_user_analysis_cache(user_id: int):
    """用户数据变更时清除该用户所有分析缓存。"""
    uid_prefix = f"{user_id}:"
    to_delete = [k for k in _analysis_cache if k.startswith(uid_prefix)]
    for k in to_delete:
        del _analysis_cache[k]
    # Also clear causal graph cache from insights router
    try:
        from routers.insights import _invalidate_causal_cache
        _invalidate_causal_cache(user_id)
    except ImportError:
        pass
    # Also clear Bayesian recovery model
    try:
        from fitai.analysis.bayesian_recovery import invalidate_user_model
        invalidate_user_model(user_id)
    except ImportError:
        pass

import httpx
from tavily import TavilyClient

from tools.fitai_database import (
    insert_workout, insert_body_metric, insert_nutrition,
    get_workout_history, get_body_metrics_history, get_nutrition_history,
    get_workout_history_json, get_body_metrics_history_json, get_nutrition_history_json,
    get_health_data_history, get_health_data_history_json,
    insert_health_data_batch,
)

tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))

WBI_MIXIN_KEY = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]
_bilibili_session = None
_wbi_keys = None
_wbi_keys_time = 0


def _get_bilibili_session():
    global _bilibili_session
    if _bilibili_session is None:
        _bilibili_session = httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bilibili.com/"}, timeout=httpx.Timeout(8.0))
        try:
            _bilibili_session.get("https://www.bilibili.com/")
        except Exception:
            pass
    return _bilibili_session


def _fetch_wbi_keys():
    global _wbi_keys, _wbi_keys_time
    now = time.time()
    if _wbi_keys and (now - _wbi_keys_time) < 1800:
        return _wbi_keys
    try:
        sess = _get_bilibili_session()
        resp = sess.get("https://api.bilibili.com/x/web-interface/nav", timeout=5, headers={"Referer": "https://www.bilibili.com/"})
        data = resp.json()
        wbi_img = data.get("data", {}).get("wbi_img", {})
        img_key = wbi_img.get("img_url", "") or wbi_img.get("img_key", "")
        sub_key = wbi_img.get("sub_url", "") or wbi_img.get("sub_key", "")
        if img_key and sub_key:
            img_key = os.path.splitext(os.path.basename(urllib.parse.urlparse(img_key).path))[0]
            sub_key = os.path.splitext(os.path.basename(urllib.parse.urlparse(sub_key).path))[0]
            _wbi_keys = (img_key, sub_key)
            _wbi_keys_time = now
            return _wbi_keys
    except Exception:
        pass
    return None


def _wbi_sign(params: dict) -> dict:
    keys = _fetch_wbi_keys()
    if not keys:
        return params
    img_key, sub_key = keys
    mixin = img_key + sub_key
    params["wts"] = int(time.time())
    sorted_keys = sorted(params.keys())
    query = urllib.parse.urlencode({k: params[k] for k in sorted_keys})
    sign = hashlib.md5((query + mixin).encode()).hexdigest()
    sign_chars = list(sign)
    params["w_rid"] = "".join(sign_chars[v] if v < 32 else sign_chars[0] for v in WBI_MIXIN_KEY[:32])
    return params


def search_bilibili_videos(exercise_name: str, max_results: int = 3) -> str:
    try:
        params = _wbi_sign({"keyword": exercise_name, "search_type": "video", "order": "click", "duration": 0, "page": 1})
        resp = _get_bilibili_session().get("https://api.bilibili.com/x/web-interface/wbi/search/all/v2", params=params, timeout=8)
        data = resp.json()
        if data.get("code") != 0:
            return f"B站搜索失败: {data.get('message', 'unknown')}"
        videos = data.get("data", {}).get("result", [])
        if not videos:
            return f"未找到'{exercise_name}'相关视频"
        results = []
        for v in videos[:max_results]:
            arcurl = v.get("arcurl") or f"https://www.bilibili.com/video/{v.get('bvid', '')}"
            title = re.sub(r'<.*?>', '', v.get("title", ""))
            results.append(f"{title}\n  {arcurl}")
        return "\n".join(results)
    except Exception as e:
        return f"B站搜索异常: {e}"


def search(query: str) -> str:
    try:
        result = tavily.search(query, search_depth="basic", max_results=3)
        if not result.get("results"):
            return f"未找到'{query}'相关信息"
        lines = []
        for r in result["results"]:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            lines.append(f"{title}\n  {content[:200]}...\n  {url}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"搜索异常: {e}。请稍后重试。"


def get_video_url(exercise_name: str) -> str:
    bili_result = search_bilibili_videos(exercise_name, max_results=3)
    if "失败" not in bili_result and "异常" not in bili_result and "未找到" not in bili_result:
        return bili_result
    try:
        result = tavily.search(f"{exercise_name} 教学视频 site:bilibili.com", search_depth="basic", max_results=2)
        if result.get("results"):
            lines = []
            for r in result["results"]:
                lines.append(f"{r.get('title', '')}\n  {r.get('url', '')}")
            return "\n".join(lines)
    except Exception:
        pass
    return bili_result


def log_workout(user_id: int, exercise_name: str = "", sets=None, reps=None, weight_kg=None, duration_minutes=None, notes=None, rpe=None) -> str:
    return insert_workout(user_id, exercise_name, sets, reps, weight_kg, duration_minutes, notes, rpe=rpe)


def log_body_metric(user_id: int, weight_kg=None, body_fat_pct=None, notes=None) -> str:
    return insert_body_metric(user_id, weight_kg=weight_kg, body_fat_pct=body_fat_pct, notes=notes)


def log_nutrition(user_id: int, meal_type=None, food_name="", calories=None, protein_g=None, carbs_g=None, fat_g=None) -> str:
    return insert_nutrition(user_id, meal_type=meal_type, food_name=food_name, calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g)


def query_workout_history(user_id: int, days: int = 30) -> str:
    return get_workout_history(user_id, int(days))


def query_body_metrics(user_id: int, days: int = 30) -> str:
    return get_body_metrics_history(user_id, int(days))


def query_nutrition_history(user_id: int, days: int = 30) -> str:
    return get_nutrition_history(user_id, int(days))


def query_health_data(user_id: int, data_type: str = "", days: int = 30) -> str:
    history = get_health_data_history(user_id, int(days))
    if data_type and data_type.strip():
        filtered = [l for l in history.split("\n") if data_type.strip().lower() in l.lower() or l.startswith("最近")]
        return "\n".join(filtered) if len(filtered) > 1 else f"最近{days}天暂无'{data_type}'相关健康数据。"
    return history


def sync_health_now(user_id: int, platform: str = "google_fit") -> str:
    try:
        from fitai.health_platforms.sync_service import sync_service
        results = sync_service.sync_now(user_id, platform)
        if results:
            return f"已从 {platform} 同步 {len(results)} 条健康数据。"
        return f"{platform} 同步完成，暂未获取到新数据。"
    except ImportError:
        return "健康平台同步功能未安装。"
    except Exception as e:
        return f"同步失败: {e}"


def analyze_correlations(user_id: int, days: int = 60) -> str:
    """分析用户健康数据之间的关联模式。轻量级：只做日期对齐的 Pearson 相关。"""
    def _compute():
        from tools.fitai_database import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT date, data_type, value FROM health_data WHERE user_id = ? AND date >= date('now', ?) ORDER BY date",
            (user_id, f"-{max(days, 7)} days"),
        ).fetchall()

        if len(rows) < 10:
            return "数据不足（需要至少 10 条记录），请先导入或记录更多健康数据。"

        by_date = {}
        for r in rows:
            d = r["date"]
            if d not in by_date:
                by_date[d] = {}
            by_date[d][r["data_type"]] = float(r["value"])

        types = set()
        for d in by_date:
            types.update(by_date[d].keys())
        types = sorted(types)

        from math import sqrt
        correlations = []
        for i in range(len(types)):
            for j in range(i + 1, len(types)):
                t1, t2 = types[i], types[j]
                pairs = [(by_date[d][t1], by_date[d][t2]) for d in by_date if t1 in by_date[d] and t2 in by_date[d]]
                if len(pairs) < 5:
                    continue
                n = len(pairs)
                sx = sum(p[0] for p in pairs)
                sy = sum(p[1] for p in pairs)
                sxx = sum(p[0] ** 2 for p in pairs)
                syy = sum(p[1] ** 2 for p in pairs)
                sxy = sum(p[0] * p[1] for p in pairs)
                denom = sqrt((n * sxx - sx * sx) * (n * syy - sy * sy))
                if denom == 0:
                    continue
                r = (n * sxy - sx * sy) / denom
                if abs(r) >= 0.3:
                    direction = "正相关" if r > 0 else "负相关"
                    strength = "强" if abs(r) >= 0.7 else "中等" if abs(r) >= 0.5 else "弱"
                    correlations.append((abs(r), t1, t2, round(r, 2), direction, strength, n))

        correlations.sort(reverse=True)
        if not correlations:
            return f"在最近 {days} 天数据中，暂未发现明显的数据关联。继续记录更多类型的健康数据（如同时记录步数、睡眠、体重），我会帮你找到隐藏的规律。"

        lines = [f"最近 {days} 天的数据关联分析（共 {len(rows)} 条记录）："]
        for _, t1, t2, r, d, s, n in correlations[:5]:
            lines.append(f"- {t1} 与 {t2}: {s}{d}（r={r}, n={n}天）")
        return "\n".join(lines)

    return _analysis_cached(user_id, f"analyze_correlations:{days}", _compute)


def predict_trends(user_id: int, days: int = 60) -> str:
    """分析各项健康指标的趋势并预测未来走向。轻量：只做线性回归外推。"""
    def _compute():
        from tools.fitai_database import get_db
        from fitai.analysis.trends import detect_trend

        conn = get_db()
        rows = conn.execute(
            "SELECT date, data_type, value FROM health_data WHERE user_id = ? AND date >= date('now', ?) ORDER BY date",
            (user_id, f"-{max(days, 14)} days"),
        ).fetchall()

        if len(rows) < 7:
            return "数据不足（需要至少 7 条记录），请先记录或导入更多健康数据。"

        by_type = {}
        for r in rows:
            dt = r["data_type"]
            if dt not in by_type:
                by_type[dt] = {"dates": [], "values": []}
            by_type[dt]["dates"].append(r["date"])
            by_type[dt]["values"].append(float(r["value"]))

        lines = []
        has_findings = False
        for dt, data in sorted(by_type.items()):
            vals = data["values"]
            if len(vals) < 5:
                continue
            trend = detect_trend(vals, data["dates"])
            slope = trend["slope_per_day"]
            pct = trend["percent_change_per_week"]
            conf = trend["confidence"]
            latest = vals[-1]
            avg = sum(vals) / len(vals) if vals else 0

            if abs(pct) < 1.0 and conf < 0.3:
                continue

            has_findings = True
            predicted_14d = round(latest + slope * 14, 1)
            unit_map = {"steps": "步", "sleep": "分钟", "weight": "kg", "calories": "千卡", "heart_rate": "bpm", "body_fat": "%", "water": "杯"}

            direction_emoji = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
            unit = unit_map.get(dt, "")

            if dt == "weight":
                if pct < -0.5:
                    lines.append(f"体重 {direction_emoji} 每周下降 {abs(pct):.1f}%（当前 {latest}kg → 预计 2 周后 {predicted_14d}kg）——减重趋势良好！")
                elif pct > 0.5:
                    lines.append(f"体重 {direction_emoji} 每周上升 {pct:.1f}%（当前 {latest}kg → 预计 2 周后 {predicted_14d}kg）——需要关注饮食和训练")
            elif dt == "steps":
                if pct < -1.0:
                    lines.append(f"步数 {direction_emoji} 每周下降 {abs(pct):.1f}%（日均 {avg:.0f} 步）——活动量在减少，试试定个小目标")
                elif pct > 1.0:
                    lines.append(f"步数 {direction_emoji} 每周增长 {pct:.1f}%（日均 {avg:.0f} 步）——越来越活跃了！")
            elif dt == "sleep":
                hours = latest / 60
                if pct < -1.0:
                    lines.append(f"睡眠 {direction_emoji} 每周减少 {abs(pct):.1f}%（平均 {hours:.1f} 小时/天）——睡眠不足会影响恢复，试试提前 30 分钟上床")
                elif pct > 1.0:
                    lines.append(f"睡眠 {direction_emoji} 每周增加 {pct:.1f}%（平均 {hours:.1f} 小时/天）——睡眠质量在改善！")
            elif dt == "heart_rate":
                if pct > 1.0:
                    lines.append(f"静息心率 {direction_emoji} 每周上升 {pct:.1f}%（当前 {latest:.0f}bpm）——可能训练过度，建议减量或增加休息日")
                elif pct < -1.0:
                    lines.append(f"静息心率 {direction_emoji} 每周下降 {abs(pct):.1f}%（当前 {latest:.0f}bpm）——心肺功能在变强！")
            else:
                if abs(pct) > 2:
                    lines.append(f"{dt} {direction_emoji} 每周变化 {pct:+.1f}%（当前 {latest}{unit} → 预计 2 周后 {predicted_14d}{unit}）")

        if not has_findings:
            return f"最近 {days} 天数据趋势稳定，各项指标没有明显变化。继续保持！"

        return "\n".join(lines)

    return _analysis_cached(user_id, f"predict_trends:{days}", _compute)


def get_weather(city: str = "北京") -> str:
    """获取指定城市的今天天气（免费 Open-Meteo API，无密钥）。使用城市名查经纬度近似值。"""
    # 常见城市经纬度映射（避免额外 API 调用）
    city_coords = {
        "北京": (39.9, 116.4), "上海": (31.2, 121.5), "广州": (23.1, 113.3),
        "深圳": (22.5, 114.1), "杭州": (30.3, 120.2), "成都": (30.6, 104.1),
        "武汉": (30.6, 114.3), "南京": (32.1, 118.8), "西安": (34.3, 108.9),
        "重庆": (29.6, 106.5), "天津": (39.1, 117.2), "苏州": (31.3, 120.6),
        "长沙": (28.2, 113.0), "郑州": (34.7, 113.6), "济南": (36.7, 117.0),
        "青岛": (36.1, 120.4), "大连": (38.9, 121.6), "厦门": (24.5, 118.1),
        "福州": (26.1, 119.3), "昆明": (25.0, 102.7), "合肥": (31.8, 117.2),
        "哈尔滨": (45.8, 126.5), "沈阳": (41.8, 123.4), "长春": (43.9, 125.3),
    }
    coords = city_coords.get(city, (39.9, 116.4))
    lat, lon = coords[0], coords[1]

    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=auto&forecast_days=2"
        resp = httpx.get(url, timeout=5.0)
        data = resp.json()
        daily = data.get("daily", {})
        if not daily:
            return f"无法获取 {city} 天气数据"

        today_max = daily["temperature_2m_max"][0]
        today_min = daily["temperature_2m_min"][0]
        rain_pct = daily.get("precipitation_probability_max", [0])[0] or 0

        # 天气码转中文
        code = daily.get("weather_code", [0])[0] or 0
        weather_map = {0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 51: "小雨", 61: "中雨", 63: "大雨", 71: "小雪", 80: "阵雨", 95: "雷暴"}
        weather_desc = weather_map.get(code, "多云")

        tomorrow_max = daily["temperature_2m_max"][1] if len(daily["temperature_2m_max"]) > 1 else today_max

        lines = [f"{city}今日天气：{weather_desc}，{today_min}°C ~ {today_max}°C"]
        if rain_pct > 50:
            lines.append(f"降水概率 {rain_pct}%，建议室内训练")
        elif today_max > 35:
            lines.append(f"高温 {today_max}°C，建议避开中午户外运动，多喝水")
        elif today_max < 5:
            lines.append("低温天气，记得充分热身后再运动")
        elif weather_desc in ("晴", "少云") and today_max <= 30 and today_max >= 15:
            lines.append(f"很适合户外运动！明天 {tomorrow_max}°C")

        return "。".join(lines)
    except Exception as e:
        return f"天气查询失败: {e}"


def compute_daily_score(user_id: int) -> str:
    """计算今天的综合健康分(0-100)。融合步数、睡眠、卡路里、心率等指标。"""
    def _compute():
        from tools.fitai_database import get_db
        from fitai.analysis.trends import compute_health_score
        from datetime import date as dt_date

        conn = get_db()
        today = dt_date.today().isoformat()
        yesterday = dt_date.fromordinal(dt_date.today().toordinal() - 1).isoformat()

        rows = conn.execute(
            "SELECT data_type, value FROM health_data WHERE user_id=? AND date IN (?, ?)",
            (user_id, today, yesterday),
        ).fetchall()

        if not rows:
            return "今日暂无健康数据，记录步数、睡眠等数据后即可获得综合健康分。"

        metrics = {}
        for r in rows:
            dt = r["data_type"]
            if r["date"] == today:
                metrics[dt] = float(r["value"])
            if r["date"] == yesterday and dt == "weight":
                metrics["weight_prev"] = float(r["value"])

        result = compute_health_score(metrics)
        return f"今日综合健康分: {result['score']}/100 ({result['level']})\n{result['details']}"

    return _analysis_cached(user_id, "compute_daily_score", _compute)


def recovery_score(user_id: int) -> str:
    """计算今日恢复评分。根据昨日训练强度、睡眠、心率给出训练建议。"""
    from tools.fitai_database import get_db
    from fitai.analysis.recovery import compute_recovery_score
    from datetime import date as dt_date, timedelta

    conn = get_db()
    yesterday = (dt_date.today() - timedelta(days=1)).isoformat()
    today = dt_date.today().isoformat()
    thirty_days_ago = (dt_date.today() - timedelta(days=30)).isoformat()

    # ── 查询 1/2：一次获取昨日健康数据 + 今日心率（合并 3 次独立查询）──
    health_rows = conn.execute("""
        SELECT data_type, value FROM health_data
        WHERE user_id=? AND date=? AND data_type IN ('sleep', 'steps')
        UNION ALL
        SELECT 'heart_rate' as data_type, value FROM health_data
        WHERE user_id=? AND date=? AND data_type='heart_rate'
    """, (user_id, yesterday, user_id, today)).fetchall()

    sleep_hours, steps, resting_hr = 8.0, 10000.0, 65.0
    for r in health_rows:
        if r["data_type"] == "sleep":
            sleep_hours = float(r["value"]) / 60
        elif r["data_type"] == "steps":
            steps = float(r["value"])
        elif r["data_type"] == "heart_rate":
            resting_hr = float(r["value"])

    # ── 查询 2/2：30 天心率基线（聚合查询，需独立）──
    hr_30d = conn.execute(
        "SELECT AVG(value) as avg_hr FROM health_data WHERE user_id=? AND data_type='heart_rate' AND date >= ?",
        (user_id, thirty_days_ago)
    ).fetchone()
    baseline_hr = float(hr_30d["avg_hr"]) if hr_30d and hr_30d["avg_hr"] else 60

    # ── 连续训练天数 + 昨日强度（一次查询替代最多 14 次循环查询）──
    # 取最近 14 天有训练记录的日期，在 Python 中计算连续天数
    wk_rows = conn.execute("""
        SELECT date, SUM(duration_minutes) as dur
        FROM workout_logs WHERE user_id=? AND date >= ?
        GROUP BY date ORDER BY date DESC
    """, (user_id, thirty_days_ago)).fetchall()

    # 计算连续训练天数（从今天往回找）
    streak = 0
    d = dt_date.today()
    for _ in range(14):
        d_str = (d - timedelta(days=streak)).isoformat()
        if any(row["date"] == d_str for row in wk_rows):
            streak += 1
        else:
            break

    # 昨日训练强度
    yest_wk = next((row for row in wk_rows if row["date"] == yesterday), None)
    if yest_wk and yest_wk["dur"] and yest_wk["dur"] > 0:
        intensity = min(10, float(yest_wk["dur"]) / 10 + 2)
    else:
        intensity = 0

    result = compute_recovery_score(intensity, sleep_hours, resting_hr, baseline_hr, steps, streak)
    return f"今日恢复评分: {result['score']}/100\n建议: {result['advice']}\n{result['details']}"


def search_exercises(body_part: str = "", equipment: str = "", keyword: str = "") -> str:
    """搜索标准动作库（1,324个标准健身动作，含中文指导）。"""
    from tools.fitai_database import search_exercises_db
    results = search_exercises_db(
        body_part=body_part or None,
        equipment=equipment or None,
        keyword=keyword or None,
        limit=10
    )
    if not results:
        return "未找到匹配的健身动作，请尝试其他关键词"
    lines = [f"找到 {len(results)} 个匹配动作："]
    for r in results:
        img = r.get("image_url", "")
        img_tag = f" ![演示]({img})" if img else ""
        lines.append(f"• {r['name']} [{r['body_part']}] ({r['equipment']}) — 难度{r['difficulty_level']}/5{img_tag}")
    return "\n".join(lines)


def get_exercise_instructions(exercise_name: str) -> str:
    """获取特定动作的详细中文指导，含演示动图URL。"""
    from tools.fitai_database import search_exercises_db
    results = search_exercises_db(keyword=exercise_name, limit=1)
    if not results:
        return f"未找到「{exercise_name}」的动作指导"
    r = results[0]
    inst = r.get("instructions_zh") or r.get("instructions_en") or "暂无详细指导"
    img = r.get("image_url", "")
    img_line = f"\n![演示]({img})\n" if img else ""
    return f"【{r['name']}】\n部位：{r['body_part']} | 器材：{r['equipment']} | 难度：{r['difficulty_level']}/5{img_line}\n\n{inst}"


def recommend_workouts(user_id: int) -> str:
    """基于用户数据和训练历史推荐动作。协同过滤——找相似用户常练的动作。"""
    from tools.fitai_database import get_db

    conn = get_db()
    # 查询用户自己的训练历史
    my = conn.execute("SELECT exercise_name, COUNT(*) as cnt FROM workout_logs WHERE user_id=? GROUP BY exercise_name ORDER BY cnt DESC LIMIT 5", (user_id,)).fetchall()
    my_exercises = set(r["exercise_name"] for r in my)

    # 找其他用户常练但自己没练过的动作
    others = conn.execute(
        "SELECT exercise_name, COUNT(*) as cnt FROM workout_logs WHERE user_id!=? AND exercise_name NOT IN ({}) GROUP BY exercise_name ORDER BY cnt DESC LIMIT 5"
        .format(",".join(["?"] * len(my_exercises)) if my_exercises else "''"),
        [user_id] + list(my_exercises) if my_exercises else [user_id],
    ).fetchall()

    lines = []
    if my:
        lines.append("你最常练的动作：")
        for r in my[:3]:
            lines.append(f"- {r['exercise_name']} ({r['cnt']}次)")
    if others:
        lines.append("推荐尝试的新动作：")
        for r in others[:3]:
            lines.append(f"- {r['exercise_name']}（社区热门 {r['cnt']}次）")
    if not lines:
        lines.append("暂无足够训练数据，开始记录训练后我会给你个性化推荐！")
    return "\n".join(lines)


def training_plan(goal: str = "综合", frequency: str = "3") -> str:
    """生成训练计划。goal: 减脂/增肌/综合, frequency: 每周训练天数。返回文字描述 + [PLAN_CARD]结构化数据。"""
    from fitai.analysis.daily_planner import generate_daily_plan
    freq = int(frequency) if frequency.isdigit() else 3
    freq = max(min(freq, 6), 2)
    plan = generate_daily_plan(goal=goal, frequency=freq)

    # Build text summary
    lines = [f"【{goal}】7天训练计划（每周{freq}练）："]
    for d in plan.get("days", []):
        day_name = d.get("day_name", "")
        if d.get("is_rest"):
            lines.append(f"{day_name}: 休息")
        else:
            ex_names = [e["name"] for e in d.get("exercises", [])]
            lines.append(f"{day_name} - {d.get('focus', '训练')}（{d.get('estimated_time', '')}）: {', '.join(ex_names)}")
            if d.get("tip"):
                lines.append(f"  💡 {d['tip']}")

    # Append structured plan data for plan_card rendering
    import json as _json
    plan_json = _json.dumps(plan, ensure_ascii=False)
    lines.append(f"\n[PLAN_CARD]{plan_json}[/PLAN_CARD]")
    return "\n".join(lines)


def advanced_health_score(user_id: int) -> str:
    """指数加权健康评分，近期数据权重更高。"""
    def _compute():
        from tools.fitai_database import get_db
        db = get_db()
        rows = db.execute(
            "SELECT date, data_type, value FROM health_data WHERE user_id = ? AND date >= date('now', '-30 days') ORDER BY date",
            (user_id,),
        ).fetchall()

        if not rows:
            return "暂无近30天健康数据，请先记录步数、睡眠等健康数据"

        from collections import defaultdict
        daily = defaultdict(dict)
        for r in rows:
            daily[r["date"]][r["data_type"]] = r["value"]

        from fitai.analysis.advanced import ewma_health_score
        result = ewma_health_score(
            [{"date": d, **metrics} for d, metrics in sorted(daily.items())]
        )

        lines = [
            f"📊 指数加权健康评分: {result['score']}/100 ({result['level']})",
            f"📈 趋势: {result['trend']} (变化 {result['change']:+.1f})",
            f"📅 覆盖 {result['data_days']} 天数据",
        ]
        if result["stale_penalty"] > 0:
            lines.append(f"⚠️ 数据陈旧扣分: -{result['stale_penalty']}（近3天数据不完整）")
        return "\n".join(lines)

    return _analysis_cached(user_id, "advanced_health_score", _compute)


def cross_anomaly_check(user_id: int) -> str:
    """跨指标组合异常检测，识别隐性风险。"""
    def _compute():
        from tools.fitai_database import get_db
        db = get_db()
        rows = db.execute(
            "SELECT date, data_type, value FROM health_data WHERE user_id = ? AND date >= date('now', '-14 days') ORDER BY date",
            (user_id,),
        ).fetchall()

        if not rows:
            return "暂无近14天健康数据，无法进行交叉异常检测"

        from collections import defaultdict
        daily = defaultdict(dict)
        for r in rows:
            daily[r["date"]][r["data_type"]] = r["value"]

        from fitai.analysis.advanced import cross_metric_anomaly
        signals = cross_metric_anomaly(dict(daily))

        if not signals:
            return "✅ 近14天未检测到跨指标组合异常，各项指标协调良好"

        lines = ["🔍 跨指标交叉异常检测结果："]
        for s in signals:
            severity_icon = "🔴" if s["severity"] == "high" else "🟡" if s["severity"] == "medium" else "🟢"
            lines.append(f"{severity_icon} {s['date']}: {s['pattern']}（综合偏差: {s['combined_score']}）")
        return "\n".join(lines)

    return _analysis_cached(user_id, "cross_anomaly_check", _compute)


def adaptive_training_plan(user_id: int, goal: str = "综合") -> str:
    """基于历史训练数据自适应调整的计划。"""
    def _compute():
        from tools.fitai_database import get_workout_history_json, get_user_profile_summary
        workouts = get_workout_history_json(user_id, 90)
        profile_text = get_user_profile_summary(user_id)

        from fitai.analysis.advanced import adaptive_periodization
        plan = adaptive_periodization(goal, workouts, {"summary": profile_text}, 4)

        lines = [f"【{goal}】{plan['weeks']}周自适应训练计划"]
        lines.append(f"📊 完成率: {plan['adjustment_factors']['compliance_rate']:.0%}")
        lines.append(f"🔥 强度{'已上调' if plan['adjustment_factors']['intensity_adjusted'] else '维持默认'}")

        for w in plan["plan"]:
            adj_mark = " ⚡" if w.get("adjusted") else ""
            lines.append(f"第{w['week']}周 - {w['focus']}（{w['intensity']}强度）{adj_mark}")
            lines.append(f"  有氧: {w['cardio']}  |  力量: {w['strength']}")
            lines.append(f"  💡 {w['note']}")

        if plan.get("insights"):
            lines.append("")
            lines.extend(plan["insights"])
        return "\n".join(lines)

    return _analysis_cached(user_id, f"adaptive_training_plan:{goal}", _compute)


def get_current_plan(user_id: int) -> str:
    """读取用户当前活跃的训练计划和进度。让 AI 知道用户目前练什么、练到哪了。"""
    from tools.fitai_database import get_db
    import json as _json
    db = get_db()
    row = db.execute(
        "SELECT * FROM training_plans WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if not row:
        return "你目前还没有活跃的训练计划。可以先通过「定制训练计划」或让我（AI 教练）帮你生成一份。"

    plan_data = _json.loads(row["plan_data"]) if isinstance(row["plan_data"], str) else row["plan_data"]
    progress = _json.loads(row["day_progress"]) if isinstance(row["day_progress"], str) else (row["day_progress"] or {})

    days = plan_data.get("days", [])
    completed_days = [d for d in days if progress.get(f"day-{d.get('day', 0)}")]
    remaining_days = [d for d in days if not progress.get(f"day-{d.get('day', 0)}") and not d.get("is_rest")]

    lines = [
        f"📋 当前计划：{row['goal']} · 每周{plan_data.get('frequency', '?')}练",
        f"📅 创建于 {row['created_at'][:10] if row['created_at'] else '未知'}",
        f"✅ 已完成 {len(completed_days)} 天，剩余 {len(remaining_days)} 个训练日",
        "",
        "每日安排：",
    ]
    for d in days:
        day_key = f"day-{d.get('day', 0)}"
        status = "✅完成" if progress.get(day_key) else ("休息" if d.get("is_rest") else "⏳待练")
        focus = d.get("focus", "训练") if not d.get("is_rest") else "休息"
        ex_count = len(d.get("main", []))
        ex_str = f"（{ex_count}个动作）" if ex_count > 0 else ""
        lines.append(f"  {d.get('day_name', '')} - {focus} {ex_str} - {status}")

    # 最近反馈
    feedbacks = db.execute(
        "SELECT * FROM training_feedback WHERE user_id=? AND plan_id=? ORDER BY created_at DESC LIMIT 5",
        (user_id, row["id"]),
    ).fetchall()
    if feedbacks:
        lines.append("")
        lines.append("最近反馈：")
        for fb in feedbacks:
            parts = []
            if fb["rpe"]: parts.append(f"RPE {fb['rpe']}/10")
            if fb["difficulty"]: parts.append(fb["difficulty"])
            if fb["soreness"]: parts.append(f"酸痛: {fb['soreness']}")
            lines.append(f"  {fb['day_key']}: {', '.join(parts) if parts else '已记录'}")

    return "\n".join(lines)


def adjust_training_plan(user_id: int, changes: str = "") -> str:
    """基于当前计划和用户反馈调整训练计划。用户说「引体向上做不了」「太累了」「周三没时间」时调用。"""
    import json as _json
    from tools.fitai_database import get_db
    from fitai.analysis.daily_planner import adjust_plan

    db = get_db()
    row = db.execute(
        "SELECT * FROM training_plans WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if not row:
        return "没有找到当前活跃的训练计划，请先生成计划。"

    prev_plan = _json.loads(row["plan_data"]) if isinstance(row["plan_data"], str) else row["plan_data"]

    # 读取反馈
    fb_rows = db.execute(
        "SELECT * FROM training_feedback WHERE user_id=? AND plan_id=? ORDER BY created_at DESC",
        (user_id, row["id"]),
    ).fetchall()
    feedbacks = [dict(fb) for fb in fb_rows]

    # 如果有用户明确说的改动，把它作为额外上下文注入
    if changes:
        prev_plan["_user_request"] = changes

    adjusted = adjust_plan(prev_plan, feedbacks, user_id)

    # 构建文字摘要
    lines = [f"🔧 已根据你的情况调整训练计划（{'用户要求: ' + changes if changes else '基于训练反馈'}）："]
    for d in adjusted.get("days", []):
        day_name = d.get("day_name", "")
        if d.get("is_rest"):
            lines.append(f"  {day_name}: 休息")
        else:
            ex_names = [e["name"] for e in d.get("main", [])]
            lines.append(f"  {day_name} - {d.get('focus', '训练')}（{d.get('total_time', '')}）: {', '.join(ex_names)}")
            if d.get("tip"):
                lines.append(f"    💡 {d['tip']}")

    if adjusted.get("_adjustment_note"):
        lines.insert(1, f"📝 {adjusted['_adjustment_note']}")

    # 嵌入 [PLAN_CARD] 让前端渲染可确认的计划卡片
    plan_json = _json.dumps(adjusted, ensure_ascii=False)
    lines.append(f"\n[PLAN_CARD]{plan_json}[/PLAN_CARD]")
    return "\n".join(lines)


def analyze_food_photo(user_id: int) -> str:
    """Analyze a food photo. Note: requires CalorieNinjas API key configured."""
    from config import CALORIENINJAS_API_KEY

    if not CALORIENINJAS_API_KEY:
        return "CalorieNinjas API Key 未配置。请在 .env 中设置 CALORIENINJAS_API_KEY（免费注册 calorie.ninja）"

    try:
        import requests

        # Strip data URI prefix for API
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]

        resp = httpx.post(
            "https://api.calorieninjas.com/v1/imagetonutrition",
            json={"image": image_base64},
            headers={"X-API-Key": CALORIENINJAS_API_KEY},
            timeout=30.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
        elif resp.status_code == 402:
            return "CalorieNinjas API 免费额度已用完（10000次/月），请下月再试或升级套餐"
        else:
            return f"食物识别失败（{resp.status_code}），请确保拍摄的是清晰的食物照片"
    except Exception as e:
        return f"食物识别请求失败: {e}"

    if not items:
        return "未能识别照片中的食物，请确保拍摄的是清晰的食物照片（饭、菜、水果等）"

    lines = ["📸 食物识别结果："]
    total_cal = 0
    total_protein = 0
    total_carbs = 0
    total_fat = 0

    for item in items:
        name = item.get("name", "未知食物")
        cal = item.get("calories", 0)
        protein = item.get("protein_g", 0)
        carbs = item.get("carbohydrates_total_g", 0)
        fat = item.get("fat_total_g", 0)
        serving = item.get("serving_size_g", 100)

        lines.append(f"🍽️ {name}（约{serving}g）")
        lines.append(f"   热量: {cal}千卡 | 蛋白质: {protein}g | 碳水: {carbs}g | 脂肪: {fat}g")
        total_cal += cal
        total_protein += protein
        total_carbs += carbs
        total_fat += fat

    if len(items) > 1:
        lines.append(f"📊 合计: 热量{total_cal}千卡 | 蛋白质{total_protein}g | 碳水{total_carbs}g | 脂肪{total_fat}g")

    lines.append("")
    lines.append("💡 如需保存，请告诉我「保存」或「记录这餐」")

    return "\n".join(lines)


def causal_insight(user_id: int, question: str = "what_affects_recovery") -> str:
    """因果洞察：从用户健康数据中发现因果关系并给出可解释的答案。"""
    from collections import defaultdict

    conn = get_db()
    rows = conn.execute(
        "SELECT date, data_type, AVG(value) as value FROM health_data "
        "WHERE user_id = ? AND date >= date('now', '-30 days') "
        "GROUP BY date, data_type ORDER BY date",
        (user_id,),
    ).fetchall()

    if len(rows) < 20:
        return ("数据不足（需要至少 20 条记录），请先导入或记录更多健康数据。"
                "导入后我可以帮你发现指标间的因果关系——这不是简单的相关性，"
                "而是基于 Pearl 因果推断的因果效应分析。")

    daily_metrics = defaultdict(dict)
    for r in rows:
        try:
            daily_metrics[r["date"]][r["data_type"]] = float(r["value"])
        except (ValueError, TypeError):
            pass

    metrics = dict(daily_metrics)
    if len(metrics) < 14:
        return f"有效数据不足（{len(metrics)} 天，需至少 14 天）。继续记录数据，我就能帮你发现因果规律。"

    from fitai.analysis.causal_discovery import pc_stable
    from fitai.analysis.causal_effects import estimate_causal_effects
    from fitai.analysis.counterfactual import CounterfactualEngine

    discovery = pc_stable(metrics)
    graph = discovery.get("graph", {})
    effects = estimate_causal_effects(metrics, graph)
    significant = [e for e in effects if e["significant"]]

    if not significant:
        return (
            f"分析了 {len(metrics)} 天数据，暂未发现统计显著的因果关系。"
            f"建议继续记录数据，尤其在有变化的日子（训练日 vs 休息日），因果信号会更强。"
        )

    engine = CounterfactualEngine(effects, metrics)

    lines = [f"基于 {len(metrics)} 天数据分析，发现 {len(significant)} 个显著因果关系：\n"]
    for i, e in enumerate(significant[:5], 1):
        lines.append(f"{i}. {e['interpretation']}")

    if "如果" in question or "what_if" in question.lower() or "睡" in question:
        lines.append("\n反事实推演（如果...会怎样）：")
        if "睡" in question:
            what_if = engine.predict({"sleep": 480})
            for w in what_if[:3]:
                lines.append(f"  - {w['interpretation']}")

    lines.append(f"\n（基于 Pearl do-calculus 因果推断，{len(effects)} 条因果边）")

    return "\n".join(lines)
