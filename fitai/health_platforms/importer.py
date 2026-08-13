# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""健康数据本地导入器。支持华为健康导出 CSV、Apple Health 导出 ZIP/XML、通用 CSV 格式。"""
import csv
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
import gc
from datetime import datetime
from tools.fitai_database import insert_health_data, insert_health_data_batch, get_db, insert_workout, insert_body_metric

# 全局聚合字典：{(platform, date, data_type, device): [values]}
# device 用于区分同一数据的不同记录设备，避免 iPhone + Watch 双重计数
_agg = {}


def _normalize_device(raw: str) -> str:
    """设备名归一化，避免同一设备的不同表述被当成多个源。"""
    if not raw:
        return ""
    lower = raw.lower()
    if "watch" in lower:
        return "Watch"
    if "iphone" in lower or "phone" in lower or "电话" in lower:
        return "iPhone"
    if "huawei" in lower or "华为" in raw:
        return "Huawei Health"
    if "samsung" in lower or "三星" in raw:
        return "Samsung Health"
    return raw


def _add_to_agg(platform, date, data_type, value, unit, device="", agg=None):
    """收集数据。若 agg 为 None 则使用全局 _agg（兼容旧代码）。"""
    if agg is None:
        agg = _agg
    device = _normalize_device(device)
    key = (platform, date, data_type, device)
    if key not in agg:
        agg[key] = {"values": [], "unit": str(unit)}
    try:
        agg[key]["values"].append(float(value))
    except (ValueError, TypeError):
        pass


def _flush_agg(user_id=1, agg=None):
    """聚合写入数据库。若 agg 为 None 则使用全局 _agg（兼容旧代码）。"""
    if agg is None:
        global _agg
        agg = _agg
    if not agg:
        return 0

    # 第一步：每个设备内聚合（步数/卡路里求和，心率/血氧取平均，睡眠取最大）
    device_aggs = {}
    for (platform, date, dt, device), info in agg.items():
        clean = [float(v) for v in info["values"]]
        if not clean:
            continue
        base = (platform, date, dt)
        if base not in device_aggs:
            device_aggs[base] = {"vals": [], "unit": str(info["unit"])}
        if dt in ("steps", "calories", "exercise"):
            device_aggs[base]["vals"].append(sum(clean))
        elif dt in ("heart_rate", "spo2"):
            device_aggs[base]["vals"].extend(clean)  # 保留原始值用于跨设备平均
        elif dt == "sleep":
            device_aggs[base]["vals"].append(max(clean))
        else:
            device_aggs[base]["vals"].append(sum(clean) / len(clean))

    # 第二步：跨设备聚合
    records = []
    for (platform, date, dt), info in device_aggs.items():
        dvals = info["vals"]
        if dt in ("steps", "calories", "exercise"):
            final = round(max(dvals), 1)
        elif dt in ("heart_rate", "spo2"):
            final = round(sum(dvals) / len(dvals), 1)  # 所有设备的原始值取平均
        elif dt == "sleep":
            final = round(max(dvals), 1)
            if final < 30:
                continue
        else:
            final = round(sum(dvals) / len(dvals), 1)
        records.append({
            "date": date, "source_platform": platform, "data_type": dt,
            "value": final, "unit": info["unit"],
        })

    agg.clear()
    if records:
        return insert_health_data_batch(user_id, records)
    return 0


def _clear_agg():
    global _agg
    _agg = {}


# 列名映射：中英文列名 → 内部 data_type
COLUMN_MAP = {
    # 步数
    "步数": "steps", "steps": "steps", "step_count": "steps", "step": "steps",
    "步行数": "steps",
    # 心率
    "心率": "heart_rate", "heart_rate": "heart_rate", "heartrate": "heart_rate",
    "bpm": "heart_rate", "平均心率": "heart_rate",
    # 睡眠
    "睡眠时长": "sleep", "睡眠": "sleep", "sleep": "sleep",
    "sleep_duration": "sleep", "sleep_minutes": "sleep", "深睡+浅睡": "sleep",
    # 卡路里
    "卡路里": "calories", "热量": "calories", "calories": "calories",
    "calorie": "calories", "energy": "calories", "消耗热量": "calories",
    # 血氧
    "血氧": "spo2", "spo2": "spo2", "oxygen_saturation": "spo2",
    "血氧饱和度": "spo2",
}

# 日期列名
DATE_COLUMNS = {"日期", "date", "时间", "time", "记录日期", "开始时间", "start_time",
                "day", "数据日期", "采集日期", "record_date", "测量时间", "创建时间"}

UNIT_MAP = {
    "steps": "步", "heart_rate": "bpm", "sleep": "分钟",
    "calories": "千卡", "spo2": "%", "weight": "kg", "body_fat": "%",
    "exercise": "分钟", "blood_pressure_sys": "mmHg", "blood_pressure_dia": "mmHg",
    "blood_glucose": "mmol/L",
}

# V14: Per-type upper bound sanity limits
VALUE_MAX = {
    "steps": 100000,
    "heart_rate": 220,
    "sleep": 1440,
    "calories": 10000,
    "spo2": 100,
    "weight": 500,
    "body_fat": 60,
    "blood_pressure_sys": 300,
    "blood_pressure_dia": 200,
    "blood_glucose": 35,
    "exercise": 1440,
}

VALUE_MIN = {
    "heart_rate": 30,
    "spo2": 50,
    "sleep": 10,
    "calories": 10,
}

# Apple Health workoutActivityType → 中文运动名称
WORKOUT_TYPE_MAP = {
    "HKWorkoutActivityTypeWalking": "步行",
    "HKWorkoutActivityTypeRunning": "跑步",
    "HKWorkoutActivityTypeSwimming": "游泳",
    "HKWorkoutActivityTypeCycling": "骑行",
    "HKWorkoutActivityTypeHiking": "徒步",
    "HKWorkoutActivityTypeRowing": "划船",
    "HKWorkoutActivityTypeElliptical": "椭圆机",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "HIIT",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "力量训练",
    "HKWorkoutActivityTypeFunctionalStrengthTraining": "功能性力量训练",
    "HKWorkoutActivityTypeCoreTraining": "核心训练",
    "HKWorkoutActivityTypeCrossTraining": "交叉训练",
    "HKWorkoutActivityTypeFlexibility": "柔韧性训练",
    "HKWorkoutActivityTypeYoga": "瑜伽",
    "HKWorkoutActivityTypePilates": "普拉提",
    "HKWorkoutActivityTypeDance": "舞蹈",
    "HKWorkoutActivityTypeBasketball": "篮球",
    "HKWorkoutActivityTypeSoccer": "足球",
    "HKWorkoutActivityTypeBadminton": "羽毛球",
    "HKWorkoutActivityTypeTableTennis": "乒乓球",
    "HKWorkoutActivityTypeTennis": "网球",
    "HKWorkoutActivityTypeVolleyball": "排球",
    "HKWorkoutActivityTypePickleball": "匹克球",
    "HKWorkoutActivityTypeMartialArts": "武术",
    "HKWorkoutActivityTypeBoxing": "拳击",
    "HKWorkoutActivityTypeKickboxing": "踢拳",
    "HKWorkoutActivityTypeJumpRope": "跳绳",
    "HKWorkoutActivityTypeSkiing": "滑雪",
    "HKWorkoutActivityTypeSnowboarding": "单板滑雪",
    "HKWorkoutActivityTypeSnowSports": "雪上运动",
    "HKWorkoutActivityTypeSkating": "滑冰",
    "HKWorkoutActivityTypeSurfing": "冲浪",
    "HKWorkoutActivityTypeWaterSports": "水上运动",
    "HKWorkoutActivityTypeClimbing": "攀岩",
    "HKWorkoutActivityTypeGolf": "高尔夫",
    "HKWorkoutActivityTypeStairClimbing": "爬楼梯",
    "HKWorkoutActivityTypeSwimBikeRun": "铁人三项",
    "HKWorkoutActivityTypeMixedCardio": "混合有氧",
    "HKWorkoutActivityTypeHandCycling": "手摇车",
    "HKWorkoutActivityTypeFitnessGaming": "健身游戏",
    "HKWorkoutActivityTypeWheelchairWalkPace": "轮椅步行",
    "HKWorkoutActivityTypeWheelchairRunPace": "轮椅跑步",
}


def import_file(file_path: str, platform: str = "local_import", user_id=1) -> dict:
    """自动识别并导入健康数据文件。返回 {success: int, skipped: int, errors: list}"""
    # Detect ZIP by magic bytes; use disk-based streaming for files
    with open(file_path, "rb") as f:
        header = f.read(4)
    if header[:4] == b'PK\x03\x04':
        return _import_zip_from_path(file_path, platform, user_id)
    # Text-based formats
    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()
    return _import_content(content, ext, platform, user_id)


def import_content(content: str, filename: str, platform: str = "local_import", user_id=1) -> dict:
    """从字符串内容导入。"""
    ext = os.path.splitext(filename)[1].lower() if "." in filename else ".csv"
    return _import_content(content, ext, platform, user_id)


def import_bytes(data: bytes, filename: str, platform: str = "local_import", user_id=1) -> dict:
    """从字节数据导入（支持 ZIP/XML/CSV/JSON）。"""
    ext = os.path.splitext(filename)[1].lower() if "." in filename else ""
    if ext == ".zip":
        result = _import_zip(data, platform, user_id)
    else:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception as e:
            return {"success": 0, "skipped": 0, "errors": [f"文件编码错误: {e}"]}
        result = import_content(text, filename, platform, user_id)

    workouts = result.get("workouts", 0)
    if workouts:
        result["message"] = f"已导入 {result['success']} 条健康数据 + {workouts} 条运动记录"
    return result


def _import_content(content: str, ext: str, platform: str, user_id=1) -> dict:
    if ext in (".csv", ".txt"):
        return _import_csv(content, platform, user_id)
    elif ext in (".xml",):
        return _import_apple_xml(content, platform, user_id)
    elif ext in (".json",):
        return _import_json(content, platform, user_id)
    elif ext in (".zip",):
        return {"success": 0, "skipped": 0, "errors": ["ZIP 文件请直接上传，不要粘贴内容"]}
    else:
        # 未知扩展名，尝试自动检测
        stripped = content.strip()
        if stripped.startswith("<?xml") or stripped.startswith("<HealthData") or stripped.startswith("<!DOCTYPE"):
            return _import_apple_xml(content, platform, user_id)
        elif stripped.startswith("{") or stripped.startswith("[{"):
            return _import_json(content, platform, user_id)
        else:
            return _import_csv(content, platform, user_id)


class _PeekStream:
    """Wrap a file-like object to allow peeking first N bytes, then reading the rest.

    Used to detect XML format from first bytes without consuming them for the parser.
    """
    def __init__(self, file_obj, peek_bytes: bytes):
        self._f = file_obj
        self._buf = peek_bytes
        self._pos = 0

    def read(self, size: int = -1):
        if self._pos < len(self._buf):
            if size < 0:
                data = self._buf[self._pos:] + self._f.read()
                self._pos = len(self._buf)
                return data
            data = self._buf[self._pos:self._pos + size]
            self._pos += len(data)
            if len(data) < size:
                data += self._f.read(size - len(data))
            return data
        return self._f.read(size)


def _import_zip(data: bytes, platform: str, user_id=1) -> dict:
    """从 Apple Health 导出的 ZIP 中流式提取 XML（不加载全量到内存）。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"success": 0, "skipped": 0, "errors": ["不是有效的 ZIP 文件，请解压后上传 export.xml"]}

    xml_files = [n for n in zf.namelist() if n.endswith(".xml")]
    if not xml_files:
        return {"success": 0, "skipped": 0,
                "errors": [f"ZIP 中未找到 XML 文件。内容: {', '.join(zf.namelist()[:10])}"]}

    total_success = 0
    total_skipped = 0
    total_workouts = 0
    all_errors = []
    debug_info = []

    for target in xml_files:
        try:
            print(f"[Importer] 正在流式解析: {target}")
            with zf.open(target) as f:
                peek = f.read(2000)
                stream = _PeekStream(f, peek)
                peek_str = peek.decode("utf-8-sig", errors="replace")
                if ("<ClinicalDocument" in peek_str or "urn:hl7-org:v3" in peek_str
                        or "<entry>" in peek_str or "<entry " in peek_str):
                    result = _import_cda(stream, platform, user_id)
                else:
                    result = _import_apple_record_xml(stream, platform, user_id)
        except Exception as e:
            all_errors.append(f"读取 {target} 失败: {e}")
            continue

        total_success += result.get("success", 0)
        total_skipped += result.get("skipped", 0)
        total_workouts += result.get("workouts", 0)
        if result.get("errors"):
            all_errors.extend(result["errors"])
        if result.get("debug"):
            debug_info.append(f"{target}: {result['debug']}")

    print(f"[Importer] 共导入 {total_success} 条数据 + {total_workouts} 条运动")

    return {"success": total_success, "skipped": total_skipped,
            "workouts": total_workouts,
            "message": f"已导入 {total_success} 条健康数据 + {total_workouts} 条运动记录" if total_workouts else None,
            "errors": all_errors[:10],
            "debug": "; ".join(debug_info) if debug_info else None}


def _import_zip_from_path(file_path: str, platform: str, user_id=1) -> dict:
    """从磁盘路径流式导入 ZIP（用 zipfile.ZipFile(file_path) 直接读磁盘，不加载全量到内存）。"""
    try:
        zf = zipfile.ZipFile(file_path, 'r')
    except zipfile.BadZipFile:
        return {"success": 0, "skipped": 0, "errors": ["不是有效的 ZIP 文件"]}

    xml_files = [n for n in zf.namelist() if n.endswith(".xml")]
    if not xml_files:
        return {"success": 0, "skipped": 0,
                "errors": [f"ZIP 中未找到 XML 文件。内容: {', '.join(zf.namelist()[:10])}"]}

    total_success = 0
    total_skipped = 0
    total_workouts = 0
    all_errors = []
    debug_info = []

    for target in xml_files:
        try:
            print(f"[Importer] 正在流式解析: {target}")
            with zf.open(target) as f:
                peek = f.read(2000)
                stream = _PeekStream(f, peek)
                peek_str = peek.decode("utf-8-sig", errors="replace")
                if ("<ClinicalDocument" in peek_str or "urn:hl7-org:v3" in peek_str
                        or "<entry>" in peek_str or "<entry " in peek_str):
                    result = _import_cda(stream, platform, user_id)
                else:
                    result = _import_apple_record_xml(stream, platform, user_id)
        except Exception as e:
            all_errors.append(f"读取 {target} 失败: {e}")
            continue

        total_success += result.get("success", 0)
        total_skipped += result.get("skipped", 0)
        total_workouts += result.get("workouts", 0)
        if result.get("errors"):
            all_errors.extend(result["errors"])
        if result.get("debug"):
            debug_info.append(f"{target}: {result['debug']}")

    print(f"[Importer] 共导入 {total_success} 条数据 + {total_workouts} 条运动")

    return {"success": total_success, "skipped": total_skipped,
            "workouts": total_workouts,
            "message": f"已导入 {total_success} 条健康数据 + {total_workouts} 条运动记录" if total_workouts else None,
            "errors": all_errors[:10],
            "debug": "; ".join(debug_info) if debug_info else None}


def _import_csv(content: str, platform: str, user_id=1) -> dict:
    """解析 CSV，自动识别列名。"""
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if len(rows) < 2:
        return {"success": 0, "skipped": 0, "errors": ["CSV 文件为空或只有表头"]}

    header = [h.strip().lower() for h in rows[0]]
    # 找日期列和数据列
    date_idx = None
    type_columns = {}  # idx → data_type

    for i, h in enumerate(rows[0]):
        original = h.strip()
        lower = original.lower()
        if lower in {d.lower() for d in DATE_COLUMNS} or original in DATE_COLUMNS:
            date_idx = i
        mapped = COLUMN_MAP.get(original) or COLUMN_MAP.get(lower)
        if mapped:
            type_columns[i] = mapped

    if date_idx is None:
        # 尝试第一列作为日期
        date_idx = 0

    if not type_columns:
        return {"success": 0, "skipped": 0,
                "errors": [f"未识别的列名: {rows[0]}。支持的列名: {list(COLUMN_MAP.keys())[:20]}"],
                "hint": "请确保 CSV 有中文或英文列名，如：日期、步数、心率、睡眠时长、卡路里、血氧"}

    success = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(rows[1:], 2):
        if not row or all(c.strip() == "" for c in row):
            continue
        date_str = _parse_date(row[date_idx]) if date_idx < len(row) else None
        if not date_str:
            skipped += 1
            continue

        for col_idx, data_type in type_columns.items():
            if col_idx >= len(row):
                continue
            try:
                val = float(row[col_idx].strip().replace(",", ""))
                if val <= 0:
                    continue
                if data_type in VALUE_MAX and val > VALUE_MAX[data_type]:
                    continue
                if data_type in VALUE_MIN and val < VALUE_MIN[data_type]:
                    continue
                insert_health_data(
                    user_id=user_id,
                    date=date_str,
                    source_platform=platform,
                    data_type=data_type,
                    value=val,
                    unit=UNIT_MAP.get(data_type, ""),
                )
                success += 1
            except (ValueError, TypeError):
                skipped += 1
            except Exception as e:
                errors.append(f"行{row_num}/{data_type}: {e}")

    return {"success": success, "skipped": skipped, "errors": errors[:10]}


def _import_apple_xml(content: str, platform: str, user_id=1) -> dict:
    """解析 Apple Health 导出 XML（字符串版本，向后兼容）。"""
    if "<ClinicalDocument" in content[:2000] or "urn:hl7-org:v3" in content[:2000] or "<entry>" in content[:2000] or "<entry " in content[:2000]:
        return _import_cda(content, platform, user_id)
    return _import_apple_record_xml(content, platform, user_id)


def _tag_name(elem) -> str:
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _import_cda(source, platform: str, user_id=1) -> dict:
    """解析 Apple Health CDA (Clinical Document Architecture) XML 格式。

    使用 iterparse 流式解析，避免大文件 OOM。source 可以是字符串或 file-like 对象。
    """
    success = 0
    skipped = 0
    errors = []

    print(f"[Importer] CDA format detected, streaming parse...")

    # Agg buffer for periodic flush (reuse _add_to_agg pattern from Record parser)
    agg = {}
    cnt_no_type = 0
    cnt_bad_value = 0
    cnt_bad_date = 0
    observation_count = 0
    workout_count = 0
    unmatched_names = set()
    matched_types = set()
    first_obs_printed = False

    # CDA 中 displayName 到内部 data_type 的映射（中英文）
    display_name_map = {
        # 步数
        "step count": "steps", "steps": "steps", "歩数": "steps", "步数": "steps",
        "number of steps": "steps",
        # 心率
        "heart rate": "heart_rate", "心率": "heart_rate",
        "resting heart rate": "heart_rate", "静息心率": "heart_rate",
        "walking heart rate average": "heart_rate",
        "heart rate variability": None,
        # 睡眠
        "sleep analysis": "sleep", "sleep": "sleep", "睡眠分析": "sleep", "睡眠": "sleep",
        "in bed": "sleep", "asleep": "sleep", "asleep core": "sleep",
        "asleep deep": "sleep", "asleep rem": "sleep",
        # 卡路里
        "active energy burned": "calories", "active energy": "calories",
        "活动能量": "calories", "活动消耗能量": "calories",
        "basal energy burned": "calories", "resting energy": "calories",
        "基础能量": "calories", "静息能量": "calories",
        "dietary energy": "calories", "饮食能量": "calories",
        # 血氧
        "oxygen saturation": "spo2", "spo2": "spo2",
        "blood oxygen": "spo2", "血氧": "spo2", "血氧饱和度": "spo2",
        # 不需要的数据（跳过后不报错）
        "flights climbed": None, "已爬楼层": None, "爬楼": None,
        "walking + running distance": None, "步行跑步距离": None,
        "walking running distance": None,
        "body mass": "weight", "体重": "weight", "body weight measured": "weight",
        "body mass index": None, "bmi": None, "身体质量指数": None,
        "height": None, "身高": None,
        "blood pressure systolic": "blood_pressure_sys", "收缩压": "blood_pressure_sys",
        "blood pressure diastolic": "blood_pressure_dia", "舒张压": "blood_pressure_dia",
        "dietary carbohydrates": None, "碳水": None,
        "dietary protein": None, "蛋白质": None,
        "dietary fat": None, "脂肪": None,
        "respiratory rate": None, "呼吸频率": None,
        "body temperature": None, "体温": None,
        "apple exercise time": "exercise", "锻炼时长": "exercise",
        "apple stand time": None, "站立时长": None,
        "environmental audio exposure": None, "环境音量": None,
        "headphone audio exposure": None, "耳机音量": None,
        "heart rate variability": None, "心率变异性": None,
        "menstrual flow": None, "经期": None,
        "cervical mucus quality": None,
        "basal body temperature": None,
        "sexual activity": None,
        "uv index": None,
        "water temperature": None,
        "swimming stroke count": None,
        "distance swimming": None,
        "distance cycling": None, "骑行距离": None,
        "distance wheelchair": None,
        "nikefuel": None,
        "push count": None,
        "vo2 max": None,
        "waist circumference": None,
        "insulin delivery": None,
        "blood glucose": "blood_glucose", "血糖": "blood_glucose",
    }

    # ── 流式解析：单次 iterparse 处理 observation + organizer ──
    try:
        if isinstance(source, str):
            context = ET.iterparse(io.StringIO(source), events=("start",))
        else:
            context = ET.iterparse(source, events=("start",))
    except ET.ParseError as e:
        return {"success": 0, "skipped": 0, "errors": [f"CDA XML 解析失败: {e}"]}

    for event, elem in context:
        tag = _tag_name(elem)

        # ═══ Observation: 健康数据 ═══
        if tag in ("observation", "Observation"):
            observation_count += 1
            if observation_count == 1:
                children_tags = [_tag_name(c) for c in list(elem)]
                print(f"[Importer] First CDA observation children: {children_tags}")

            # 从 <code> 获取数据类型
            code_elem = None
            value_elem = None
            time_elem = None
            for child in elem:
                ct = _tag_name(child)
                if ct == "code":
                    code_elem = child
                elif ct == "value":
                    value_elem = child
                elif ct == "effectiveTime":
                    time_elem = child

            if code_elem is None or value_elem is None:
                skipped += 1
                elem.clear()
                continue

            display_name = (code_elem.get("displayName") or code_elem.get("code") or "").lower().strip()
            dt = None
            for key, mapped in display_name_map.items():
                if key in display_name:
                    dt = mapped
                    break
            if dt is None:
                skipped += 1
                cnt_no_type += 1
                if len(unmatched_names) < 30:
                    unmatched_names.add(display_name)
                elem.clear()
                continue

            matched_types.add(dt)

            try:
                val = float(value_elem.get("value", 0))
                if val <= 0:
                    skipped += 1
                    cnt_bad_value += 1
                    elem.clear()
                    continue
                if dt in VALUE_MAX and val > VALUE_MAX[dt]:
                    skipped += 1
                    elem.clear()
                    continue
                if dt in VALUE_MIN and val < VALUE_MIN[dt]:
                    skipped += 1
                    elem.clear()
                    continue
            except (ValueError, TypeError):
                skipped += 1
                cnt_bad_value += 1
                elem.clear()
                continue

            # 日期
            date_str = None
            if time_elem is not None:
                date_str = _parse_date(time_elem.get("value", ""))
                if not date_str:
                    for tc in time_elem:
                        if _tag_name(tc) in ("low", "high"):
                            date_str = _parse_date(tc.get("value", ""))
                            if date_str:
                                break
            if not date_str:
                skipped += 1
                cnt_bad_date += 1
                elem.clear()
                continue

            if dt == "sleep":
                if time_elem is not None:
                    low_val = None
                    high_val = None
                    for tc in time_elem:
                        tn = _tag_name(tc)
                        if tn == "low":
                            low_val = tc.get("value", "")
                        elif tn == "high":
                            high_val = tc.get("value", "")
                    duration = _calc_duration_minutes(low_val or "", high_val or "")
                    if duration and duration > 0:
                        val = duration
                    else:
                        skipped += 1
                        elem.clear()
                        continue

            try:
                device = elem.get("sourceName", "")
                _add_to_agg(platform, date_str, dt, val, UNIT_MAP.get(dt, ""), device, agg=agg)
                success += 1
                if success % 50000 == 0:
                    print(f"[Importer] 已收集 {success} 条...")
                if success > 0 and success % 5000 == 0:
                    _flush_agg(user_id, agg=agg)
                    gc.collect()
            except Exception as e:
                errors.append(f"{display_name}: {e}")

            elem.clear()
            continue

        # ═══ Organizer: 运动记录 ═══
        if tag in ("organizer", "Organizer"):
            class_code = elem.get("classCode", "")
            if class_code != "CLUSTER":
                elem.clear()
                continue
            code_elem = None
            time_elem = None
            for child in elem:
                ct = _tag_name(child)
                if ct == "code":
                    code_elem = child
                elif ct == "effectiveTime":
                    time_elem = child

            if code_elem is None:
                elem.clear()
                continue
            activity_name = (code_elem.get("displayName") or code_elem.get("code") or "").strip()
            if not activity_name:
                elem.clear()
                continue

            exercise_name = WORKOUT_TYPE_MAP.get(activity_name)
            if not exercise_name:
                for hk_type, cn_name in WORKOUT_TYPE_MAP.items():
                    if cn_name == activity_name or activity_name.startswith(cn_name):
                        exercise_name = cn_name
                        break
            if not exercise_name:
                elem.clear()
                continue

            date_str = None
            duration_min = None
            if time_elem is not None:
                date_str = _parse_date(time_elem.get("value", ""))
                low_val = None
                high_val = None
                for tc in time_elem:
                    tn = _tag_name(tc)
                    if tn == "low":
                        low_val = tc.get("value", "")
                        date_str = _parse_date(low_val) if low_val else date_str
                    elif tn == "high":
                        high_val = tc.get("value", "")
                if low_val and high_val:
                    duration_min = _calc_duration_minutes(low_val, high_val)

            if not date_str:
                elem.clear()
                continue

            energy_kcal = 0
            distance_val = 0
            distance_unit = ""
            for child in elem.iter():
                ct = _tag_name(child)
                if ct not in ("entry", "Entry", "observation", "Observation", "component", "Component"):
                    continue
                for sub in child.iter():
                    st = _tag_name(sub)
                    if st != "code":
                        continue
                    dn = (sub.get("displayName") or "").lower()
                    if "active energy" in dn or "活动能量" in dn:
                        for sib in child.iter():
                            if _tag_name(sib) == "value":
                                try:
                                    energy_kcal += float(sib.get("value", 0))
                                except (ValueError, TypeError):
                                    pass
                                break
                    if "distance" in dn or "距离" in dn:
                        for sib in child.iter():
                            if _tag_name(sib) == "value":
                                try:
                                    distance_val += float(sib.get("value", 0))
                                    distance_unit = sib.get("unit", "")
                                except (ValueError, TypeError):
                                    pass
                                break

            notes_parts = []
            if energy_kcal > 0:
                notes_parts.append(f"{round(energy_kcal)}千卡")
            if distance_val > 0:
                dist_km = round(distance_val / 1000, 2) if distance_unit == "m" else distance_val
                dist_label = "km" if distance_unit == "m" else distance_unit
                notes_parts.append(f"{dist_km}{dist_label}")
            notes = " · ".join(notes_parts) if notes_parts else None

            try:
                insert_workout(user_id,
                    exercise_name=exercise_name,
                    duration_minutes=round(duration_min, 1) if duration_min else None,
                    notes=notes,
                    date=date_str,
                )
                workout_count += 1
            except Exception as e:
                errors.append(f"CDA Workout {activity_name}: {e}")

            elem.clear()

    # Final flush after iterparse
    _flush_agg(user_id, agg=agg)

    if observation_count == 0 and workout_count == 0:
        errors.append("CDA 格式中未找到有效数据")

    if workout_count > 0:
        print(f"[Importer] CDA 运动记录: {workout_count} 条")

    # 打印分阶段统计
    print(f"[Importer] 分阶段统计: total={observation_count}, matched_types={sorted(matched_types)}, "
          f"success={success}, no_type={cnt_no_type}, bad_value={cnt_bad_value}, bad_date={cnt_bad_date}")

    debug_parts = [f"CDA格式 {observation_count}条: 匹配类型{len(matched_types)}种({', '.join(sorted(matched_types))})",
                   f"无映射{cnt_no_type}, 值无效{cnt_bad_value}, 日期无效{cnt_bad_date}"]
    if workout_count:
        debug_parts.append(f"运动{workout_count}条")
    return {"success": success, "skipped": skipped, "errors": errors[:10],
            "workouts": workout_count,
            "debug": " · ".join(debug_parts) if observation_count > 0 or workout_count > 0 else None,
            "unmatched_display_names": sorted(unmatched_names)[:30] if unmatched_names else []}


def _import_apple_record_xml(source, platform: str, user_id=1, agg=None) -> dict:
    """解析 Apple Health 旧版 Record 格式 XML。使用 iterparse 流式解析。source 可以是字符串或 file-like 对象。"""
    if agg is None:
        agg = {}
    success = 0
    skipped = 0
    errors = []

    type_map = {
        "HKQuantityTypeIdentifierStepCount": "steps",
        "HKQuantityTypeIdentifierHeartRate": "heart_rate",
        "HKQuantityTypeIdentifierRestingHeartRate": "heart_rate",
        "HKQuantityTypeIdentifierWalkingHeartRateAverage": "heart_rate",
        "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
        "HKQuantityTypeIdentifierActiveEnergyBurned": "calories",
        "HKQuantityTypeIdentifierBasalEnergyBurned": "calories",
        "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
        "HKQuantityTypeIdentifierBodyMass": "weight",
        "HKQuantityTypeIdentifierBodyFatPercentage": "body_fat",
        "HKQuantityTypeIdentifierDistanceWalkingRunning": None,
        "HKQuantityTypeIdentifierFlightsClimbed": None,
        "HKQuantityTypeIdentifierAppleExerciseTime": None,
        "HKQuantityTypeIdentifierAppleStandTime": None,
    }

    # 流式解析 Record 数据
    record_count = 0
    workout_count = 0
    try:
        if isinstance(source, str):
            context = ET.iterparse(io.StringIO(source), events=("start",))
        else:
            context = ET.iterparse(source, events=("start",))
        for event, elem in context:
            tag = _tag_name(elem)
            if tag == "Record":
                record_count += 1
                if record_count == 1:
                    print(f"[Importer] First record attrs: {dict(list(elem.attrib.items())[:10])}")

                hk_type = elem.get("type", "")
                dt = type_map.get(hk_type)
                if dt is None:
                    skipped += 1
                    elem.clear()
                    continue
                try:
                    val_str = elem.get("value", "0").replace(",", "")
                    val = float(val_str)
                    if val <= 0:
                        skipped += 1
                        elem.clear()
                        continue
                    if dt in VALUE_MAX and val > VALUE_MAX[dt]:
                        skipped += 1
                        elem.clear()
                        continue
                    if dt in VALUE_MIN and val < VALUE_MIN[dt]:
                        skipped += 1
                        elem.clear()
                        continue
                    start_date = elem.get("startDate", "")
                    date_str = _parse_date(start_date)
                    if not date_str:
                        skipped += 1
                        elem.clear()
                        continue

                    if dt == "sleep":
                        end_date = elem.get("endDate", "")
                        duration = _calc_duration_minutes(start_date, end_date)
                        if duration and duration > 0:
                            val = duration
                        if val < 30:
                            skipped += 1
                            elem.clear()
                            continue

                    device = elem.get("sourceName", "")
                    _add_to_agg(platform, date_str, dt, val, UNIT_MAP.get(dt, ""), device, agg=agg)
                    success += 1
                except (ValueError, TypeError):
                    skipped += 1
                except Exception as e:
                    errors.append(f"{hk_type}: {e}")

                elem.clear()
                # 定期释放聚合数据避免 _agg 过大（5000条flush一次，减少内存峰值）
                if success > 0 and success % 5000 == 0:
                    print(f"[Importer] 已处理 {success} 条记录，中间聚合刷新...")
                    _flush_agg(user_id, agg=agg)
                    gc.collect()
            elif tag == "Workout":
                workout_type = elem.get("workoutActivityType", "")
                exercise_name = WORKOUT_TYPE_MAP.get(workout_type)
                if exercise_name:
                    try:
                        start_date = elem.get("startDate", "")
                        date_str = _parse_date(start_date)
                        if date_str:
                            duration_s = float(elem.get("duration", 0))
                            duration_min = round(duration_s / 60, 1) if duration_s > 0 else None
                            energy_kcal = float(elem.get("totalEnergyBurned", 0) or 0)
                            distance = float(elem.get("totalDistance", 0) or 0)
                            distance_unit = elem.get("totalDistanceUnit", "")

                            notes_parts = []
                            if energy_kcal > 0:
                                notes_parts.append(f"{round(energy_kcal)}千卡")
                            if distance > 0:
                                dist_km = round(distance / 1000, 2) if distance_unit == "m" else distance
                                dist_label = "km" if distance_unit == "m" else distance_unit
                                notes_parts.append(f"{dist_km}{dist_label}")
                            notes = " · ".join(notes_parts) if notes_parts else None

                            insert_workout(user_id,
                                exercise_name=exercise_name,
                                duration_minutes=duration_min,
                                notes=notes,
                                date=date_str,
                            )
                            workout_count += 1
                    except (ValueError, TypeError) as e:
                        errors.append(f"Workout {workout_type}: {e}")
                    except Exception as e:
                        errors.append(f"Workout parse error: {e}")
                elem.clear()
            else:
                elem.clear()
    except ET.ParseError as e:
        return {"success": 0, "skipped": 0, "errors": [f"XML 解析失败: {e}。文件可能不是有效的 XML，请确认上传的是 export.xml"]}

    if record_count == 0 and workout_count == 0:
        errors.append("XML 中未找到 Record 或 Workout 元素，请确认这是 Apple Health 导出的 export.xml")

    debug = f"共扫描 {record_count} 条记录"
    if workout_count:
        debug += f" + {workout_count} 条运动"

    # 最后把聚合中剩余的数据写入
    if agg:
        final_count = _flush_agg(user_id, agg=agg)
        if final_count > 0:
            success = final_count

    return {"success": success, "skipped": skipped, "errors": errors[:10],
            "workouts": workout_count,
            "debug": debug if record_count > 0 or workout_count > 0 else None}


def _import_json(content: str, platform: str, user_id=1) -> dict:
    """解析通用 JSON 格式。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"success": 0, "skipped": 0, "errors": [f"JSON 解析失败: {e}"]}

    # 支持两种格式：
    # 1. [{date, data_type, value, unit}, ...]
    # 2. {data: [{date, data_type, value}, ...]}

    if isinstance(data, dict):
        data = data.get("data") or data.get("records") or []
    if not isinstance(data, list):
        return {"success": 0, "skipped": 0, "errors": ["JSON 格式不支持，需为数组"]}

    success = 0
    skipped = 0
    errors = []

    for item in data:
        if not isinstance(item, dict):
            skipped += 1
            continue
        dt = item.get("data_type") or item.get("type") or ""
        dt = COLUMN_MAP.get(dt, dt)
        if dt not in UNIT_MAP:
            skipped += 1
            continue
        try:
            date_str = _parse_date(item.get("date") or item.get("time") or "")
            val = float(item.get("value", 0))
            if not date_str or val <= 0:
                skipped += 1
                continue
            if dt in VALUE_MAX and val > VALUE_MAX[dt]:
                skipped += 1
                continue
            if dt in VALUE_MIN and val < VALUE_MIN[dt]:
                skipped += 1
                continue
            insert_health_data(
                user_id=user_id,
                date=date_str, source_platform=platform,
                data_type=dt, value=val,
                unit=item.get("unit") or UNIT_MAP.get(dt, ""),
            )
            success += 1
        except (ValueError, TypeError):
            skipped += 1
        except Exception as e:
            errors.append(str(e))

    return {"success": success, "skipped": skipped, "errors": errors[:10]}


def _parse_date(raw: str) -> str | None:
    """解析各种日期格式 → YYYY-MM-DD。"""
    if not raw:
        return None
    raw = raw.strip()
    # 已经是标准格式
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # 2024/01/15
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # 20240115
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # HL7 时间戳: 20240605083000+0800 或 20240605083000
    m = re.match(r"^(\d{4})(\d{2})(\d{2})\d{6}", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # HL7 时间戳: 202406050830 或带时区
    m = re.match(r"^(\d{4})(\d{2})(\d{2})\d{4}", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # ISO 格式: 2024-01-15T08:30:00 / 2024-01-15 08:30:00
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ]", raw)
    if m:
        return m.group(1)
    # 2024年1月15日
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # 2024/1/15 08:30
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})\s", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # 尝试用标准库解析
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y",
                "%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _calc_duration_minutes(start_str: str, end_str: str) -> float | None:
    """计算两个时间字符串之间的分钟差。"""
    for fmt in ["%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S"]:
        try:
            s = datetime.strptime(start_str, fmt)
            e = datetime.strptime(end_str, fmt)
            return round((e - s).total_seconds() / 60, 1)
        except ValueError:
            continue
    return None
