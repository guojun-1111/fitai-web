# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitKG — 健身动作知识图谱

为 daily_planner 提供结构化的运动科学知识：
- 动作类别 → 中文名 + 目标肌群
- 器械 → 替代方案（杠铃→哑铃→自重→弹力带）
- 伤病 → 禁忌部位 + 安全替代
- 关键动作中英文名映射
"""

# ── 类别 → 中文名 + 目标肌群 ──────────────────────────────

CATEGORY_INFO = {
    "upper legs": {
        "name": "下肢力量",
        "muscles": ["股四头肌", "腘绳肌", "臀大肌", "内收肌"],
        "joints": ["膝关节", "髋关节"],
        "movement": "蹲/推/拉",
    },
    "lower legs": {
        "name": "小腿",
        "muscles": ["腓肠肌", "比目鱼肌", "胫骨前肌"],
        "joints": ["踝关节"],
        "movement": "提踵/屈伸",
    },
    "chest": {
        "name": "胸部",
        "muscles": ["胸大肌", "胸小肌", "前锯肌"],
        "joints": ["肩关节"],
        "movement": "推/夹",
    },
    "back": {
        "name": "背部",
        "muscles": ["背阔肌", "斜方肌", "竖脊肌", "菱形肌"],
        "joints": ["肩关节", "脊柱"],
        "movement": "拉/划",
    },
    "shoulders": {
        "name": "肩部",
        "muscles": ["三角肌前束", "三角肌中束", "三角肌后束", "肩袖肌群"],
        "joints": ["肩关节"],
        "movement": "推/侧平举",
    },
    "waist": {
        "name": "核心/腰腹",
        "muscles": ["腹直肌", "腹外斜肌", "腹横肌", "腰方肌"],
        "joints": ["脊柱"],
        "movement": "屈/转/稳定",
    },
    "upper arms": {
        "name": "手臂",
        "muscles": ["肱二头肌", "肱三头肌", "肱肌"],
        "joints": ["肘关节"],
        "movement": "弯举/臂屈伸",
    },
    "lower arms": {
        "name": "前臂",
        "muscles": ["腕屈肌", "腕伸肌", "肱桡肌"],
        "joints": ["腕关节"],
        "movement": "腕弯举/旋转",
    },
    "cardio": {
        "name": "有氧/心肺",
        "muscles": ["心肺系统", "下肢肌群"],
        "joints": ["全身"],
        "movement": "持续运动",
    },
}

# ── 器械 → 替代链（从重到轻）──────────────────────────────

EQUIPMENT_ALTERNATIVES = {
    "barbell": ["dumbbell", "kettlebell", "body weight", "band"],
    "dumbbell": ["kettlebell", "body weight", "band"],
    "kettlebell": ["dumbbell", "body weight"],
    "cable": ["band", "body weight"],
    "leverage machine": ["dumbbell", "band", "body weight"],
    "smith machine": ["barbell", "dumbbell", "body weight"],
    "weighted": ["body weight"],
    "ez barbell": ["dumbbell", "band"],
    "sled machine": ["body weight"],
    "medicine ball": ["body weight"],
    "stability ball": ["body weight"],
    "bosu ball": ["body weight"],
    "body weight": [],  # 终极替代，无需器械
    "band": ["body weight"],
    "assisted": ["band", "body weight"],
    "resistance band": ["body weight"],
}

# ── 伤病 → 禁忌类别 + 安全建议 ─────────────────────────────

INJURY_CONTRAS = {
    "膝伤": {
        "avoid_categories": ["upper legs", "lower legs"],
        "avoid_movements": ["深蹲", "箭步蹲", "跳跃"],
        "safe_categories": ["upper arms", "chest", "shoulders", "waist"],
        "tip": "避免膝关节过度屈伸和高冲击动作，优先选择上肢训练和核心训练",
    },
    "腰伤": {
        "avoid_categories": ["waist", "back"],
        "avoid_movements": ["硬拉", "早安式", "大重量深蹲"],
        "safe_categories": ["upper arms", "chest", "shoulders", "upper legs"],
        "tip": "避免腰椎屈伸和旋转负重，核心训练以静态稳定为主（平板支撑、鸟狗式）",
    },
    "肩伤": {
        "avoid_categories": ["shoulders", "chest"],
        "avoid_movements": ["推举", "卧推", "侧平举"],
        "safe_categories": ["upper legs", "waist", "upper arms", "back"],
        "tip": "避免肩关节过顶推举和大幅度外展，优先下肢和稳定型背部训练",
    },
    "颈伤": {
        "avoid_categories": ["shoulders"],
        "avoid_movements": ["杠铃深蹲（颈后）", "过头推举"],
        "safe_categories": ["upper legs", "chest", "upper arms", "waist"],
        "tip": "避免颈后负重和颈部过度后仰，所有动作保持颈椎中立位",
    },
    "腕伤": {
        "avoid_categories": ["upper arms", "lower arms", "chest"],
        "avoid_movements": ["俯卧撑", "平板支撑", "杠铃弯举"],
        "safe_categories": ["upper legs", "waist", "back", "cardio"],
        "tip": "避免手掌承重和腕关节过度屈伸，优先下肢和核心训练",
    },
    "踝伤": {
        "avoid_categories": ["lower legs", "cardio"],
        "avoid_movements": ["跑步", "跳跃", "跳绳"],
        "safe_categories": ["upper arms", "chest", "shoulders", "back", "waist"],
        "tip": "避免踝关节承重和冲击，优先坐姿上肢训练和核心训练",
    },
}

# ── 常见疼痛 → 伤病类型映射 ──────────────────────────────

PAIN_TO_INJURY = {
    "怕受伤": None,  # 通用预防，不限制具体类别，但优先低风险动作
    "膝盖痛": "膝伤",
    "腰痛": "腰伤",
    "肩膀痛": "肩伤",
    "颈椎痛": "颈伤",
    "手腕痛": "腕伤",
    "脚踝痛": "踝伤",
    "全身酸痛": None,
}

# ── 关键动作中英文名（用于计划中的 why 说明）─────────────────

EXERCISE_ZH = {
    "squat": "深蹲",
    "goblet squat": "高脚杯深蹲",
    "bulgarian split squat": "保加利亚分腿蹲",
    "lunge": "箭步蹲",
    "step-up": "台阶步",
    "leg press": "腿举",
    "push-up": "俯卧撑",
    "bench press": "卧推",
    "dumbbell press": "哑铃卧推",
    "shoulder press": "肩推",
    "overhead press": "过头推举",
    "lateral raise": "侧平举",
    "front raise": "前平举",
    "bent over row": "俯身划船",
    "pull-up": "引体向上",
    "chin-up": "反手引体向上",
    "deadlift": "硬拉",
    "romanian deadlift": "罗马尼亚硬拉",
    "hip thrust": "臀推",
    "glute bridge": "臀桥",
    "plank": "平板支撑",
    "crunch": "卷腹",
    "russian twist": "俄罗斯转体",
    "dead bug": "死虫式",
    "bird dog": "鸟狗式",
    "bicep curl": "二头弯举",
    "tricep extension": "三头臂屈伸",
    "calf raise": "提踵",
    "burpee": "波比跳",
    "jumping jack": "开合跳",
    "mountain climber": "登山者",
    "high knees": "高抬腿",
    "jump squat": "跳跃深蹲",
    "cycling": "骑行",
    "running": "跑步",
    "walking": "快走",
    "swimming": "游泳",
    "yoga": "瑜伽",
    "stretching": "拉伸",
}

# ── 查询函数 ─────────────────────────────────────────────


def get_category_info(category: str) -> dict:
    """获取类别信息：中文名、目标肌群、关节、运动模式。"""
    return CATEGORY_INFO.get(category, {
        "name": category,
        "muscles": [category],
        "joints": [],
        "movement": "综合",
    })


def get_muscle_info(category: str) -> list:
    """获取类别的目标肌群列表。"""
    info = CATEGORY_INFO.get(category, {})
    return info.get("muscles", [category])


def get_contraindications(pain_point: str) -> dict | None:
    """
    根据痛点获取禁忌和替代建议。
    返回 None 表示无特殊限制（如「怕受伤」）。
    """
    injury = PAIN_TO_INJURY.get(pain_point)
    if not injury:
        return None
    return INJURY_CONTRAS.get(injury)


def get_alternatives(equipment: str) -> list:
    """获取器械的替代链（从轻到重）。始终包含 body weight 作为终极方案。"""
    alternatives = EQUIPMENT_ALTERNATIVES.get(equipment, ["body weight"])
    if "body weight" not in alternatives:
        alternatives.append("body weight")
    return alternatives


def get_exercise_zh(name: str) -> str:
    """查找动作的中文名，找不到就返回原名。"""
    name_lower = name.lower().strip()
    return EXERCISE_ZH.get(name_lower, name)


def query_exercises(
    db_conn,
    category: str | None = None,
    equipment: str = "body weight",
    difficulty_max: int = 3,
    limit: int = 10,
    exclude_ids: list | None = None,
) -> list[dict]:
    """
    从 exercise_library 查询符合条件的动作。
    自动应用器械替代链（如无指定器械，自动降级至自重）。
    """
    exclude_ids = exclude_ids or []
    equipment_chain = [equipment] + EQUIPMENT_ALTERNATIVES.get(equipment, [])
    placeholders = ",".join("?" * len(equipment_chain))

    clauses = ["1=1"]
    params: list = []

    if category:
        clauses.append(f"category = ?")
        params.append(category)

    clauses.append(f"equipment IN ({placeholders})")
    params.extend(equipment_chain)

    clauses.append("difficulty_level <= ?")
    params.append(difficulty_max)

    if exclude_ids:
        ex_placeholders = ",".join("?" * len(exclude_ids))
        clauses.append(f"id NOT IN ({ex_placeholders})")
        params.extend(exclude_ids)

    query = (
        f"SELECT id, name, category, body_part, equipment, difficulty_level "
        f"FROM exercise_library WHERE {' AND '.join(clauses)} "
        f"ORDER BY compound_score DESC, difficulty_level ASC LIMIT ?"
    )
    params.append(limit)

    rows = db_conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_exercise_detail(db_conn, exercise_id: str) -> dict | None:
    """获取单个动作的详细信息（含中英文指令）。"""
    row = db_conn.execute(
        "SELECT * FROM exercise_library WHERE id = ?", (exercise_id,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    cat_info = get_category_info(result.get("category", ""))
    result["category_zh"] = cat_info["name"]
    result["target_muscles"] = cat_info["muscles"]
    result["name_zh_display"] = get_exercise_zh(result.get("name", ""))
    return result
