# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V18: 7 天每日训练计划生成引擎 —— 规则驱动，零 LLM 依赖。

根据用户的目标、频率、痛点，生成每天具体可执行的训练单：
- 热身（2-3 个动作）
- 主体训练（3-5 个动作，含组数/次数/肌群说明）
- 拉伸放松（2-3 个动作）
- 每个动作带 why 解释字段（V20：增强版肌肉群信息）

V20: 集成 fitai.knowledge 知识图谱 —— 伤病过滤 + 器械替代 + 肌群精准描述
"""

from typing import Optional

# V20: 知识图谱集成
try:
    from fitai.knowledge import (
        get_muscle_info,
        get_contraindications,
        get_alternatives,
        get_category_info,
        get_exercise_zh,
        CATEGORY_INFO,
        INJURY_CONTRAS,
        PAIN_TO_INJURY,
    )
    _KG_AVAILABLE = True
except ImportError:
    _KG_AVAILABLE = False

# ── 动作库：按身体部位分组（中文名，适合直接呈现）───────────────── ─────────────────────────────────
# 每个动作: {name, body_part, equipment, difficulty, type: compound/isolated/rehab/cardio}

_BODYWEIGHT_EXERCISES = {
    "下肢": [
        {"name": "自重型深蹲", "body_part": "下肢", "equipment": "自重", "difficulty": 1, "type": "compound",
         "tip": "膝盖不要超过脚尖，保持腰背挺直"},
        {"name": "弓步蹲", "body_part": "下肢", "equipment": "自重", "difficulty": 2, "type": "compound",
         "tip": "前腿膝盖不要超过脚尖，身体保持直立"},
        {"name": "臀桥", "body_part": "下肢", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "收紧臀肌，在顶部停留 2 秒"},
        {"name": "靠墙静蹲", "body_part": "下肢", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "大腿与地面平行，保持呼吸均匀"},
        {"name": "侧卧抬腿", "body_part": "下肢", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "动作缓慢控制，感受臀部外侧发力"},
        {"name": "保加利亚分腿蹲", "body_part": "下肢", "equipment": "自重", "difficulty": 3, "type": "compound",
         "tip": "后脚放在椅子边缘，前腿发力为主"},
        {"name": "原地高抬腿", "body_part": "下肢", "equipment": "自重", "difficulty": 1, "type": "cardio",
         "tip": "尽可能将膝盖抬到腰部高度"},
    ],
    "上肢推": [
        {"name": "标准俯卧撑", "body_part": "上肢推", "equipment": "自重", "difficulty": 2, "type": "compound",
         "tip": "身体成一条直线，肘部与身体呈 45°"},
        {"name": "跪姿俯卧撑", "body_part": "上肢推", "equipment": "自重", "difficulty": 1, "type": "compound",
         "tip": "膝盖着地降低难度，同样保持身体直线"},
        {"name": "上斜俯卧撑", "body_part": "上肢推", "equipment": "自重", "difficulty": 1, "type": "compound",
         "tip": "手撑在桌/椅边缘，越倾斜越轻松"},
        {"name": "钻石俯卧撑", "body_part": "上肢推", "equipment": "自重", "difficulty": 3, "type": "isolated",
         "tip": "双手拇指食指组成钻石形，主要刺激肱三头肌"},
        {"name": "凳上臂屈伸", "body_part": "上肢推", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "手撑椅子边缘，弯曲手肘下降身体"},
    ],
    "上肢拉": [
        {"name": "弹力带划船", "body_part": "上肢拉", "equipment": "弹力带", "difficulty": 1, "type": "compound",
         "tip": "固定弹力带，模仿划船动作，感受背部发力"},
        {"name": "弹力带高位下拉", "body_part": "上肢拉", "equipment": "弹力带", "difficulty": 1, "type": "compound",
         "tip": "将弹力带固定在高处，下拉至锁骨位置"},
        {"name": "弹力带面拉", "body_part": "上肢拉", "equipment": "弹力带", "difficulty": 1, "type": "isolated",
         "tip": "绳索拉向面部，肘部向外打开"},
        {"name": "超人式", "body_part": "上肢拉", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "俯卧，同时抬起双臂和双腿，收紧背部"},
        {"name": "YTW 肩部训练", "body_part": "上肢拉", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "俯身，手臂依次摆出 Y、T、W 字形"},
    ],
    "核心": [
        {"name": "平板支撑", "body_part": "核心", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "身体成直线，收紧腹部和臀部"},
        {"name": "卷腹", "body_part": "核心", "equipment": "自重", "difficulty": 1, "type": "isolated",
         "tip": "只抬起肩胛骨，不要用手拉脖子"},
        {"name": "反向卷腹", "body_part": "核心", "equipment": "自重", "difficulty": 2, "type": "isolated",
         "tip": "下背部贴地，用腹部力量抬起臀部"},
        {"name": "鸟狗式", "body_part": "核心", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "对侧手脚同时抬起，保持身体稳定不晃动"},
        {"name": "死虫式", "body_part": "核心", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "仰卧，交替放下对侧手脚，腰部始终贴地"},
        {"name": "俄式转体", "body_part": "核心", "equipment": "自重", "difficulty": 2, "type": "isolated",
         "tip": "坐姿后仰，双手合十左右旋转"},
        {"name": "登山者", "body_part": "核心", "equipment": "自重", "difficulty": 2, "type": "cardio",
         "tip": "俯卧撑姿势，交替提膝至胸前"},
    ],
    "有氧": [
        {"name": "开合跳", "body_part": "有氧", "equipment": "自重", "difficulty": 1, "type": "cardio",
         "tip": "落地时膝盖微曲缓冲"},
        {"name": "原地跳绳", "body_part": "有氧", "equipment": "自重", "difficulty": 1, "type": "cardio",
         "tip": "模拟跳绳动作，用手腕画小圈"},
        {"name": "波比跳", "body_part": "有氧", "equipment": "自重", "difficulty": 3, "type": "cardio",
         "tip": "初学者可省略俯卧撑环节"},
        {"name": "高抬腿跑", "body_part": "有氧", "equipment": "自重", "difficulty": 2, "type": "cardio",
         "tip": "保持核心收紧，用前脚掌着地"},
        {"name": "登山跑", "body_part": "有氧", "equipment": "自重", "difficulty": 2, "type": "cardio",
         "tip": "控制节奏，保持呼吸均匀"},
    ],
    "康复": [
        {"name": "猫牛式", "body_part": "康复", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "配合呼吸：吸气弓背，呼气塌腰"},
        {"name": "骨盆卷动", "body_part": "康复", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "仰卧屈膝，用臀肌力量卷起骨盆"},
        {"name": "弹力带肩外旋", "body_part": "康复", "equipment": "弹力带", "difficulty": 1, "type": "rehab",
         "tip": "手肘夹紧身体，向外旋转前臂"},
        {"name": "靠墙天使", "body_part": "康复", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "后背贴墙，手臂贴墙上下滑动"},
        {"name": "髋屈肌拉伸", "body_part": "康复", "equipment": "自重", "difficulty": 1, "type": "rehab",
         "tip": "单膝跪地，前推髋部感受大腿前方拉伸"},
    ],
}

# 热身动作模板
_WARMUP_POOL = [
    {"name": "开合跳", "duration": "1分钟", "why": "提升心率，激活全身"},
    {"name": "原地小跑", "duration": "1分钟", "why": "逐步提升体温"},
    {"name": "肩部绕环", "duration": "30秒", "why": "润滑肩关节，预防损伤"},
    {"name": "髋部绕环", "duration": "30秒", "why": "激活髋关节活动度"},
    {"name": "躯干转体", "duration": "30秒", "why": "激活核心和脊柱旋转功能"},
    {"name": "踝关节活动", "duration": "30秒", "why": "提升踝关节灵活性"},
    {"name": "高抬腿", "duration": "30秒", "why": "动态激活下肢肌群"},
    {"name": "开合深蹲", "duration": "30秒", "why": "将深蹲模式加载到热身中"},
]

# 拉伸动作模板
_COOLDOWN_POOL = [
    {"name": "股四头肌拉伸", "duration": "30秒/侧", "why": "放松大腿前侧"},
    {"name": "腘绳肌拉伸", "duration": "30秒/侧", "why": "放松大腿后侧"},
    {"name": "胸部拉伸", "duration": "30秒", "why": "打开胸部，纠正圆肩"},
    {"name": "背阔肌拉伸", "duration": "30秒/侧", "why": "放松背阔肌"},
    {"name": "肩部拉伸", "duration": "30秒/侧", "why": "放松三角肌"},
    {"name": "猫式伸展", "duration": "30秒", "why": "放松脊柱和背部"},
    {"name": "婴儿式", "duration": "30秒", "why": "放松全身，调节呼吸"},
    {"name": "髋屈肌拉伸", "duration": "30秒/侧", "why": "放松髋部前侧"},
    {"name": "臀肌拉伸", "duration": "30秒/侧", "why": "放松臀大肌和梨状肌"},
    {"name": "小腿拉伸", "duration": "30秒/侧", "why": "放松腓肠肌和比目鱼肌"},
]

# 周几中文名
_DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _pick(items: list, n: int, start: int = 0) -> list:
    """从列表中循环取 n 个（从 start 位置开始轮转）。"""
    result = []
    for i in range(n):
        result.append(items[(start + i) % len(items)])
    return result


def _pick_by_type(pool: dict, types: list, n: int, start: int = 0) -> list:
    """从指定 body_part 池中挑选 n 个动作，按类型混合。"""
    candidates = []
    for t in types:
        if t in pool:
            candidates.extend(pool[t])
    if not candidates:
        return []
    return _pick(candidates, n, start)


def _build_day(
    day_index: int,
    focus: str,
    main_exercises: list,
    total_time: str,
    tip: str = "",
    warmup_offset: int = 0,
    cooldown_offset: int = 0,
    warmup_n: int = 0,
    cooldown_n: int = 0,
) -> dict:
    """组装一天的计划。"""
    if warmup_n <= 0:
        warmup_n = 3 if day_index % 2 == 0 else 2
    warmup = []
    for w in _pick(_WARMUP_POOL, warmup_n, warmup_offset + day_index * 2):
        warmup.append({"name": w["name"], "duration": w["duration"], "why": w["why"]})

    if cooldown_n <= 0:
        cooldown_n = 3 if day_index % 2 == 0 else 2
    cooldown = []
    for c in _pick(_COOLDOWN_POOL, cooldown_n, cooldown_offset + day_index * 2):
        cooldown.append({"name": c["name"], "duration": c["duration"], "why": c["why"]})

    return {
        "day": day_index + 1,
        "day_name": _DAY_NAMES[day_index],
        "focus": focus,
        "warmup": warmup,
        "main": main_exercises,
        "cooldown": cooldown,
        "total_time": total_time,
        "tip": tip,
    }


def _make_exercise(ex: dict, sets: int, reps: str) -> dict:
    """将动作池中的动作包装成计划条目（含组数/次数/why）。

    V20 增强：why 字段包含精准肌群信息（如果 KG 可用）。
    """
    body_part = ex.get("body_part", "")
    ex_type = ex.get("type", "")

    # V20: 将中文 body_part 映射到英文 category，再查肌群
    muscles_info = ""
    if _KG_AVAILABLE:
        cat = _get_bodypart_category(body_part)
        if cat:
            muscles = get_muscle_info(cat)
            if muscles:
                muscles_info = "（" + "、".join(muscles[:2]) + "）"

    why_map = {
        "compound": f"复合动作，高效刺激{body_part}{muscles_info}",
        "isolated": f"孤立强化{body_part}{muscles_info}，弥补弱项",
        "cardio": "提升心率，加速燃脂",
        "rehab": f"康复性练习，改善{body_part}功能",
    }
    return {
        "name": ex["name"],
        "sets": sets,
        "reps": reps,
        "why": why_map.get(ex_type, f"针对{body_part}的训练"),
        "equipment": ex["equipment"],
        "tip": ex.get("tip", ""),
    }


def _get_bodypart_category(body_part: str) -> str | None:
    """将 daily_planner 的 body_part 映射到 exercise_library 的 category。"""
    mapping = {
        "下肢": "upper legs",
        "上肢推": "chest",
        "上肢拉": "back",
        "核心": "waist",
        "有氧": "cardio",
        "康复": "waist",  # 康复类多为核心/拉伸
    }
    return mapping.get(body_part)


def _filter_by_injury(body_parts: list, pain_point: str) -> list:
    """V20: 根据痛点过滤不适合的身体部位，返回安全的 body_parts 列表。"""
    if not _KG_AVAILABLE or pain_point == "怕受伤":
        # 怕受伤：不过滤类别，但会降低难度
        return body_parts

    injury_type = PAIN_TO_INJURY.get(pain_point)
    if not injury_type or injury_type not in INJURY_CONTRAS:
        return body_parts

    contra = INJURY_CONTRAS[injury_type]
    avoid_categories = set(contra.get("avoid_categories", []))
    safe_categories = contra.get("safe_categories", [])

    filtered = []
    for bp in body_parts:
        cat = _get_bodypart_category(bp)
        if cat and cat in avoid_categories:
            continue
        filtered.append(bp)

    if not filtered:
        # 所有 body_parts 都被过滤了，用安全替代
        for sc in safe_categories[:3]:
            reverse_map = {v: k for k, v in {
                "下肢": "upper legs", "上肢推": "chest", "上肢拉": "back",
                "核心": "waist", "有氧": "cardio", "康复": "waist",
            }.items()}
            if sc in reverse_map:
                filtered.append(reverse_map[sc])

    return filtered if filtered else body_parts


def _get_safety_tip(pain_point: str) -> str:
    """V20: 根据痛点生成安全提示。"""
    tips = {
        "膝伤": "避免膝关节过度屈伸，所有下肢动作减小幅度",
        "腰伤": "保持腰椎中立位，避免含胸弓背",
        "肩伤": "避免肩关节过顶动作，侧平举不超过肩高",
        "颈伤": "保持颈椎中立位，不要仰头或过度低头",
        "腕伤": "用拳头支撑代替手掌支撑，减少腕关节压力",
        "踝伤": "选择坐姿动作，避免踝关节承重",
    }
    injury = PAIN_TO_INJURY.get(pain_point, "")
    return tips.get(injury, "注意动作控制，质量优先于数量。如有任何关节疼痛立即停止")


def _get_experience_adjustment(level: str) -> dict:
    """V34: 根据经验级别返回组数/次数调整因子。"""
    if level in ("beginner", "完全没练过", "beginner"):
        return {"set_mult": 0.7, "rep_bias": "high", "label": "新手友好", "max_sets": 3}
    elif level in ("intermediate", "断断续续练过", "规律练了半年以上"):
        return {"set_mult": 1.0, "rep_bias": "mid", "label": "标准", "max_sets": 4}
    elif level in ("advanced", "练了好几年了"):
        return {"set_mult": 1.3, "rep_bias": "low", "label": "进阶", "max_sets": 5}
    return {"set_mult": 1.0, "rep_bias": "mid", "label": "", "max_sets": 4}


def _get_time_preference(intent: str) -> dict:
    """V35: 根据执行意图返回训练时间偏好。Gollwitzer & Sheeran (2006)"""
    if intent == "morning":
        return {"warmup_emphasis": "充分", "avoid_late_high_intensity": False, "label": "晨练型"}
    elif intent == "evening":
        return {"warmup_emphasis": "标准", "avoid_late_high_intensity": True, "label": "晚间型"}
    elif intent == "weekend":
        return {"warmup_emphasis": "标准", "avoid_late_high_intensity": False, "label": "周末型"}
    else:
        return {"warmup_emphasis": "标准", "avoid_late_high_intensity": False, "label": "灵活型"}


def _get_time_adjustment(minutes: str) -> dict:
    """V34: 根据每次训练时长调整每训练日动作数。"""
    try:
        mins = int(minutes) if minutes else 30
    except (ValueError, TypeError):
        mins = 30
    if mins <= 15:
        return {"n_exercises_mult": 0.5, "warmup_ex": 1, "cooldown_ex": 1, "label": "15分钟快练"}
    elif mins <= 30:
        return {"n_exercises_mult": 1.0, "warmup_ex": 2, "cooldown_ex": 2, "label": "约25-30分钟"}
    elif mins <= 45:
        return {"n_exercises_mult": 1.3, "warmup_ex": 2, "cooldown_ex": 2, "label": "约35-45分钟"}
    else:
        return {"n_exercises_mult": 1.6, "warmup_ex": 3, "cooldown_ex": 3, "label": "约50-60分钟"}


def _build_exercise_pool_from_db(db_conn, equipment: str) -> dict:
    """V34: 从 exercise_library 按器械查询动作，组织为 {body_part: [exercises]}。"""
    from fitai.knowledge import query_exercises as _qe, CATEGORY_INFO
    pool = {}
    body_part_map = {
        "upper legs": "下肢", "lower legs": "下肢",
        "chest": "上肢推", "shoulders": "上肢推", "upper arms": "上肢推",
        "back": "上肢拉",
        "waist": "核心",
        "cardio": "有氧",
    }
    for db_cat, zh_cat in body_part_map.items():
        exercises = _qe(db_conn, category=db_cat, equipment=equipment, difficulty_max=4, limit=8)
        if exercises:
            converted = []
            for ex in exercises:
                converted.append({
                    "name": ex.get("name", ""),
                    "body_part": zh_cat,
                    "equipment": ex.get("equipment", equipment),
                    "difficulty": ex.get("difficulty_level", 2) or 2,
                    "type": "compound" if ex.get("compound_score", 0) > 0.5 else "isolated",
                    "tip": ex.get("instructions_cn", "")[:80] if ex.get("instructions_cn") else "",
                })
            pool[zh_cat] = converted
    # 补充有氧和康复（自重为主）
    if "有氧" not in pool:
        pool["有氧"] = _BODYWEIGHT_EXERCISES.get("有氧", [])
    if "康复" not in pool:
        pool["康复"] = _BODYWEIGHT_EXERCISES.get("康复", [])
    return pool if len(pool) >= 2 else _BODYWEIGHT_EXERCISES


def generate_daily_plan(
    goal: str = "更健康",
    frequency: int = 3,
    pain_point: str = "不知道练什么",
    equipment: str = "",
    experience_level: str = "",
    time_per_session: str = "",
    external_exercises: dict | None = None,
    # V35: Behavioral psychology parameters
    ttm_stage: str = "",
    motivation_types: str = "",
    self_efficacy: int = 0,
    implementation_intent: str = "",
    has_autonomous_motivation: bool = True,
) -> dict:
    """生成 7 天每日训练计划（V35：循证行为心理学 + 装备/经验个性化）。

    Args:
        goal: 减脂 / 增肌 / 更健康 / 缓解疼痛
        frequency: 每周训练天数 (2/3/4/5)
        pain_point: 不知道练什么 / 怕受伤 / 没动力 / 没效果
        equipment: 器械偏好
        experience_level: beginner / intermediate / advanced
        time_per_session: 15 / 30 / 45 / 60（分钟）
        external_exercises: 外部注入的动作池
        ttm_stage: precontemplation / preparation / action_early / action_maintenance
        motivation_types: 逗号分隔的动机类型字符串
        self_efficacy: 1-10 自信分数
        implementation_intent: morning / lunch / evening / weekend / flexible
        has_autonomous_motivation: 是否有自主型动机

    Returns:
        包含完整 7 天训练计划的 dict
    """
    # 标准化参数
    goal = goal.strip()
    if goal not in ("减脂", "增肌", "更健康", "缓解疼痛"):
        goal = "更健康"
    frequency = max(2, min(5, int(frequency)))
    pain_point = pain_point.strip()
    _known_pain = ("不知道练什么", "怕受伤", "没动力", "没效果")
    if _KG_AVAILABLE:
        _known_pain = _known_pain + tuple(PAIN_TO_INJURY.keys())
    if pain_point not in _known_pain:
        pain_point = "不知道练什么"

    # ── V35: TTM阶段 + 自我效能 → 训练频率调整 ──
    # 理论基础：Prochaska & DiClemente (1983) — 干预必须与阶段匹配
    # Bandura (1977) — 低自我效能者需要更温和的起始频率
    if ttm_stage in ("precontemplation", "preparation"):
        frequency = min(frequency, 2)  # 起步阶段最多2练
    if self_efficacy > 0 and self_efficacy <= 3:
        frequency = max(1, frequency - 1)  # 极低自信→减1天
    frequency = max(1, min(5, frequency))

    # ── V35: 执行意图 → 训练日分布偏好 ──
    # 理论基础：Gollwitzer & Sheeran (2006) — 指定时间/地点 → 运动率翻倍(d=0.65)
    _time_pref = _get_time_preference(implementation_intent)

    # ── V34: 经验级别 → 组数和难度映射 ──
    exp_adjust = _get_experience_adjustment(experience_level)

    # ── V34: 时长 → 每训练日动作数调整 ──
    time_adjust = _get_time_adjustment(time_per_session)

    # ── V34: 动作池选择（DB 查询 > 硬编码自重池）──
    exercise_pool = external_exercises if external_exercises else _BODYWEIGHT_EXERCISES
    if equipment and equipment not in ("", "body weight", "bodyweight") and not external_exercises:
        # 如果指定了器械但调用方没传外部池，尝试从 DB 加载
        try:
            from tools.fitai_database import get_db
            from fitai.knowledge import query_exercises as _qe
            db = get_db()
            exercise_pool = _build_exercise_pool_from_db(db, equipment)
        except Exception:
            pass  # 静默退化到硬编码池

    # ── 确定哪些天是训练日 ──
    training_days: list[int]  # 0-indexed day indices
    if frequency == 2:
        training_days = [0, 3]  # 周一、周四
    elif frequency == 3:
        training_days = [0, 2, 4]  # 周一、三、五
    elif frequency == 4:
        training_days = [0, 1, 3, 4]  # 周一、二、四、五
    else:
        training_days = [0, 1, 2, 3, 4]  # 周一至五

    rest_days = [d for d in range(7) if d not in training_days]

    # ── 根据 pain_point 确定全局策略 ──
    safety_first = pain_point == "怕受伤"
    variety_focus = pain_point == "没动力"
    progression_focus = pain_point == "没效果"

    # ── 根据 goal 确定动作池偏好 ──
    if goal == "减脂":
        cardio_bias = 2   # 每天至少 1-2 个有氧动作
        strength_body_parts = ["下肢", "上肢推", "上肢拉", "核心"]
        explanation = "减脂计划以「高消耗复合动作 + 有氧间歇」为核心，每天搭配力量训练保持肌肉量，提升基础代谢"
    elif goal == "增肌":
        cardio_bias = 0
        strength_body_parts = ["下肢", "上肢推", "上肢拉", "核心"]
        explanation = "增肌计划以「渐进式力量训练」为核心，按推/拉/腿分化，给每个肌群足够的刺激和恢复时间"
    elif goal == "缓解疼痛":
        cardio_bias = 0
        strength_body_parts = ["康复", "核心", "下肢"]
        explanation = "康复计划以「低冲击安全动作为主」，重点改善体态、强化核心稳定性、缓解常见慢性疼痛"
    else:  # 更健康
        cardio_bias = 1
        strength_body_parts = ["下肢", "上肢推", "上肢拉", "核心"]
        explanation = "综合健康计划均衡分配力量和有氧，目标是建立可持续的运动习惯"

    # V20: 伤病感知说明
    injury_contra = None
    if pain_point == "怕受伤":
        explanation += "。因为你提到担心受伤，所有动作均为自重型安全动作，每个动作都附带安全提示"
    elif pain_point == "没动力":
        explanation += "。每天安排不同的动作组合，保持新鲜感，还附带小挑战目标"
    elif pain_point == "没效果":
        explanation += "。计划包含渐进式超载提示，每次训练都比上次更进一步"

    # ── V35: 行为心理学的个性化解释 ──
    behavior_notes = []
    if ttm_stage in ("precontemplation", "preparation"):
        behavior_notes.append("因为你是刚起步，这一周的训练日不多，重点是让你不费力地养成习惯")
    if self_efficacy > 0 and self_efficacy <= 3:
        behavior_notes.append("每个训练日都只有最核心的动作，不贪多。做完了就是进步")
    if implementation_intent == "evening":
        behavior_notes.append("因为你在晚上练，我把高强度内容安排在了前面，最后以拉伸放松结束")
    elif implementation_intent == "morning":
        behavior_notes.append("因为你是晨练，每天的训练都包含了充分的热身环节")
    elif implementation_intent == "flexible":
        behavior_notes.append("你还没有固定的训练时间——没关系，试试看这周哪个时间段最舒服，下周再调整")
    if not has_autonomous_motivation:
        behavior_notes.append("我会在每天的训练里加一些小目标和即时反馈，让你更快看到变化")
    if behavior_notes:
        explanation += "。" + "；".join(behavior_notes)
    elif _KG_AVAILABLE and pain_point in PAIN_TO_INJURY and PAIN_TO_INJURY[pain_point]:
        injury_contra = get_contraindications(pain_point)
        if injury_contra:
            explanation += f"。考虑到你的{pain_point}情况，{injury_contra.get('tip', '已自动调整计划以避免风险动作')}"

    # ── 生成 7 天计划 ──
    days = []
    train_day_idx = 0  # 这是第几个训练日（用于轮转动作）

    for d in range(7):
        if d in rest_days:
            # 休息日
            if goal == "减脂":
                rest_activity = "散步 30 分钟或轻度拉伸"
            elif goal == "缓解疼痛":
                rest_activity = "泡沫轴放松 + 猫牛式 5 分钟"
            else:
                rest_activity = "休息或散步 20 分钟"

            days.append({
                "day": d + 1,
                "day_name": _DAY_NAMES[d],
                "focus": "休息恢复",
                "is_rest": True,
                "rest_activity": rest_activity,
                "tip": "休息日是肌肉修复和生长的关键时间" if goal == "增肌" else "恢复同样重要，别跳过休息日",
                "warmup": [],
                "main": [],
                "cooldown": [],
                "total_time": "休息日",
            })
            continue

        # ── 训练日 ──
        if frequency >= 4:
            split_cycle = [
                ("下肢力量", ["下肢"], 4, "约35分钟"),
                ("上肢推力", ["上肢推"], 3, "约25分钟"),
                ("上肢拉力", ["上肢拉"], 3, "约25分钟"),
                ("下肢 + 核心", ["下肢", "核心"], 4, "约30分钟"),
                ("全身循环", ["下肢", "上肢推", "上肢拉", "核心"], 5, "约35分钟"),
            ]
            si = train_day_idx % len(split_cycle)
            focus, body_parts, n_exercises, total_time = split_cycle[si]
        elif frequency == 3:
            split_cycle = [
                ("下肢主导", ["下肢"], 4, "约30分钟"),
                ("推力（胸/肩/三头）", ["上肢推"], 3, "约25分钟"),
                ("拉力（背/二头）", ["上肢拉"], 3, "约25分钟"),
            ]
            si = train_day_idx % len(split_cycle)
            focus, body_parts, n_exercises, total_time = split_cycle[si]
        else:
            focus = "全身训练"
            body_parts = ["下肢", "上肢推", "上肢拉", "核心"]
            n_exercises = 5
            total_time = "约35分钟"

        # V34: 时长调整动作数
        n_exercises = max(2, round(n_exercises * time_adjust["n_exercises_mult"]))
        total_time = time_adjust["label"] if time_adjust.get("label") else total_time

        # V20: 伤病过滤
        if injury_contra:
            body_parts = _filter_by_injury(body_parts, pain_point)

        # ── V34: 从动作池（DB 或硬编码）中选动作 ──
        main_exercises = _pick_by_type(exercise_pool, body_parts, n_exercises, train_day_idx * 2)
        if cardio_bias > 0 and train_day_idx < 7:
            cardio_pool = exercise_pool.get("有氧", _BODYWEIGHT_EXERCISES.get("有氧", []))
            if cardio_pool:
                cardio_exs = _pick(cardio_pool, cardio_bias, train_day_idx)
                for ce in cardio_exs:
                    main_exercises.append({**ce, "body_part": "有氧"})

        if goal == "缓解疼痛":
            rehab_pool = exercise_pool.get("康复", _BODYWEIGHT_EXERCISES.get("康复", []))
            if rehab_pool:
                rehab_exs = _pick(rehab_pool, 2, train_day_idx)
                for re in rehab_exs:
                    if len(main_exercises) > 4:
                        main_exercises[3] = {**re, "body_part": "康复"}
                    else:
                        main_exercises.append({**re, "body_part": "康复"})

        # ── V34: 经验级别 + 伤痛感知 → 组数/次数 ──
        exercises = []
        max_sets = exp_adjust["max_sets"]
        for i, ex in enumerate(main_exercises):
            if safety_first:
                base_sets = 3 if ex["difficulty"] <= 1 else 2
            elif progression_focus:
                base_sets = 3
            else:
                base_sets = 3

            # 应用经验调整
            sets = max(1, min(max_sets, round(base_sets * exp_adjust["set_mult"])))

            if ex["type"] == "cardio":
                reps = "30秒" if goal == "减脂" else "20秒"
            elif ex.get("difficulty", 2) >= 2:
                if exp_adjust["rep_bias"] == "high":
                    reps = "12-15"  # 新手高次数轻重量
                elif exp_adjust["rep_bias"] == "low":
                    reps = "6-10"   # 老手低次数大重量
                else:
                    reps = "8-12"
            else:
                reps = "12-15"

            exercises.append(_make_exercise(ex, sets, reps))

        # ── V35: 行为心理学驱动的每日鼓励语 ──
        if safety_first or injury_contra:
            daily_tip = _get_safety_tip(pain_point)
        elif progression_focus:
            daily_tip = "尝试比上次训练每个动作多做 1 个，或在最后一组做到力竭"
        elif variety_focus:
            daily_tip = "今日挑战：完成所有组数后，额外做 1 组平板支撑至力竭"
        else:
            daily_tip = "保持动作规范，感受目标肌群的发力"

        # V35: 自我效能低 → 更温和的鼓励
        if self_efficacy > 0 and self_efficacy <= 3:
            daily_tip = "今天的目标很简单：动起来就赢了。做不完也没关系——你已经在路上了 💚"
        # V35: 控制型动机 + 第1天 → 强调短期可见收益
        if not has_autonomous_motivation and train_day_idx == 0:
            daily_tip = "第一天！做完你会感觉整个人都不一样。先别想太远，把今天做好就行 💪"
        # V35: 晨练型 → 强调热身
        if implementation_intent == "morning" and not daily_tip:
            daily_tip = "早上身体刚醒，热身多花 2 分钟，效果会好很多 🌅"

        days.append(_build_day(
            d,
            focus,
            exercises,
            total_time,
            tip=daily_tip,
            warmup_offset=train_day_idx,
            cooldown_offset=train_day_idx + 1,
            warmup_n=time_adjust["warmup_ex"],
            cooldown_n=time_adjust["cooldown_ex"],
        ))
        train_day_idx += 1

    future = get_future_projection(goal, pain_point)

    return {
        "goal": goal,
        "frequency": frequency,
        "pain_point": pain_point,
        "days": days,
        "explanation": explanation,
        "future_projection": future,
    }


def adjust_plan(prev_plan: dict, feedbacks: list[dict], user_id: int | None = None) -> dict:
    """V33: 根据训练反馈 + RPE + 恢复状态 + 过度训练检测调整计划强度。

    Args:
        prev_plan: 上周 plan_data（generate_daily_plan 的返回值）
        feedbacks: training_feedback 行列表，每条含 {day_key, difficulty, soreness, sore_areas, rpe}
        user_id: 可选，用于查询恢复数据和过度训练检测

    Returns:
        调整后的 plan_data，可直接存入 training_plans.plan_data
    """
    import json
    import copy

    if not feedbacks:
        return _apply_progression(copy.deepcopy(prev_plan), factor=1.05)

    # ── 汇总反馈 ──
    difficulties = [f.get("difficulty", "") for f in feedbacks if f.get("difficulty")]
    rpes = [f.get("rpe") for f in feedbacks if f.get("rpe") and isinstance(f.get("rpe"), (int, float))]
    sore_areas_all = []
    for f in feedbacks:
        areas = f.get("sore_areas", "")
        if areas:
            try:
                parsed = json.loads(areas) if isinstance(areas, str) else areas
                sore_areas_all.extend(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    too_easy_count = difficulties.count("too_easy")
    too_hard_count = difficulties.count("too_hard")
    just_right_count = difficulties.count("just_right")

    from collections import Counter
    area_counter = Counter(sore_areas_all)

    adjusted = copy.deepcopy(prev_plan)
    notes = []

    # ── V33: 策略 0 — RPE 数据驱动的强度基准 ──
    avg_rpe = sum(rpes) / len(rpes) if rpes else 0
    rpe_factor = 1.0
    if avg_rpe > 0:
        if avg_rpe >= 8:
            rpe_factor = 0.75
            notes.append(f"平均 RPE {avg_rpe:.1f}/10 偏高，自动降低强度")
        elif avg_rpe <= 4:
            rpe_factor = 1.25
            notes.append(f"平均 RPE {avg_rpe:.1f}/10 偏低，可以加负荷了")
        elif 5 <= avg_rpe <= 7:
            rpe_factor = 1.05
            notes.append(f"平均 RPE {avg_rpe:.1f}/10 在合理区间")

    # ── V33: 策略 0.5 — 恢复评分门槛 ──
    recovery_score = None
    if user_id is not None:
        try:
            from fitai.analysis.recovery import compute_recovery_score
            from tools.fitai_database import get_db
            db = get_db()
            # 读取最近 7 天健康数据
            health_rows = db.execute(
                "SELECT date, data_type, value FROM health_data WHERE user_id=? AND date >= date('now', '-7 days') ORDER BY date",
                (user_id,),
            ).fetchall()
            from collections import defaultdict as _dd
            daily = _dd(dict)
            for r in health_rows:
                daily[r["date"]][r["data_type"]] = r["value"]
            if daily:
                recovery_score = compute_recovery_score(
                    [{"date": d, **m} for d, m in sorted(daily.items())]
                )
                if recovery_score < 35:
                    rpe_factor = min(rpe_factor, 0.6) if rpe_factor > 0 else 0.6
                    notes.append(f"恢复评分 {recovery_score}/100 — 需要减载周")
                elif recovery_score < 50:
                    rpe_factor = min(rpe_factor, 0.85) if rpe_factor > 0 else 0.85
                    notes.append(f"恢复评分 {recovery_score}/100 — 保持强度，注意休息")
        except Exception:
            pass  # 恢复数据不可用时静默跳过

    # ── V33: 策略 0.8 — 过度训练检测 ──
    if user_id is not None:
        try:
            from fitai.analysis.advanced import cross_metric_anomaly
            from tools.fitai_database import get_db
            db2 = get_db() if 'db' not in dir() else db
            rows = db2.execute(
                "SELECT date, data_type, value FROM health_data WHERE user_id=? AND date >= date('now', '-14 days') ORDER BY date",
                (user_id,),
            ).fetchall()
            from collections import defaultdict as _dd2
            daily2 = _dd2(dict)
            for r in rows:
                daily2[r["date"]][r["data_type"]] = r["value"]
            if daily2:
                signals = cross_metric_anomaly(dict(daily2))
                high_signals = [s for s in signals if s.get("severity") == "high"]
                if high_signals:
                    rpe_factor = min(rpe_factor, 0.5) if rpe_factor > 0 else 0.5
                    notes.append(f"⚠️ 检测到 {len(high_signals)} 个隐性过度训练信号，强制减载")
                    # 插入额外休息日
                    for day in adjusted.get("days", []):
                        if not day.get("is_rest") and day.get("day", 0) % 3 == 0:
                            day["main"] = day.get("main", [])[:1]  # 只保留 1 个动作
                            day["tip"] = "过度训练风险 — 今日轻量激活即可"
        except Exception:
            pass

    # ── 策略 1：难度 + RPE 综合调整 ──
    total = len(difficulties)
    base_factor = 1.05

    if total > 0:
        if too_easy_count > total * 0.5:
            base_factor = 1.3
            notes.append("根据你的反馈，这周的难度已提升")
        elif too_hard_count > total * 0.5:
            base_factor = 0.7
            notes.append("上周强度偏高，本周已调整")
        elif just_right_count >= total * 0.6:
            base_factor = 1.08
            notes.append("上周强度刚好，本周小幅增加")

    # 融合 RPE 因子：取 RPE 和反馈的加权平均
    if rpe_factor > 0 and rpe_factor != 1.0:
        final_factor = (base_factor * 0.4) + (rpe_factor * 0.6)  # RPE 权重大于主观反馈
    else:
        final_factor = base_factor

    # 用户明确要求的话，尊重用户请求
    if prev_plan.get("_user_request", ""):
        notes.append(f"根据你的要求「{prev_plan['_user_request']}」调整了计划")

    adjusted = _apply_progression(adjusted, factor=final_factor,
                                  adjustment_note="; ".join(notes) if notes else "")

    # ── 策略 2：针对特定酸痛部位减少该肌群 + 加拮抗肌群 ──
    if area_counter:
        most_sore = area_counter.most_common(3)
        for area_name, count in most_sore:
            if area_name in ("膝", "膝盖"):
                _reduce_bodypart(adjusted, "下肢", reason="上周膝盖酸痛较多")
                _boost_bodypart(adjusted, "上肢推", "增加上肢推力训练作为替代")
            elif area_name in ("腰", "背"):
                _reduce_bodypart(adjusted, "核心", reason="上周腰部酸痛较多")
                _boost_bodypart(adjusted, "下肢", "增加下肢训练作为替代，给核心更多恢复时间")
            elif area_name in ("肩"):
                _reduce_bodypart(adjusted, "上肢推", reason="上周肩部酸痛较多")
                _boost_bodypart(adjusted, "下肢", "增加下肢训练作为替代")

    # 清除内部标记
    prev_plan.pop("_user_request", None)
    return adjusted


def _apply_progression(plan: dict, factor: float, adjustment_note: str = "") -> dict:
    """对计划中的组数和次数应用缩放因子。"""
    for day in plan.get("days", []):
        if day.get("is_rest"):
            continue
        for ex in day.get("main", []):
            old_sets = ex.get("sets", 3)
            new_sets = max(1, min(5, round(old_sets * factor)))
            ex["sets"] = new_sets

            reps = ex.get("reps", "12-15")
            if reps not in ("20秒", "30秒", "1分钟"):
                try:
                    parts = reps.split("-")
                    lo, hi = int(parts[0]), int(parts[1])
                    lo = max(6, round(lo * factor))
                    hi = max(lo + 2, round(hi * factor))
                    ex["reps"] = f"{lo}-{hi}"
                except (ValueError, IndexError):
                    pass

        # 替代 tip 为调整说明
        if adjustment_note and day.get("tip"):
            day["tip"] = adjustment_note

    # 添加调整标记
    plan["_adjusted"] = True
    plan["_adjustment_factor"] = factor
    if adjustment_note:
        plan["_adjustment_note"] = adjustment_note
    return plan


def _reduce_bodypart(plan: dict, body_part_zh: str, reason: str = ""):
    """减少某身体部位的动作数量或组数。"""
    for day in plan.get("days", []):
        if day.get("is_rest"):
            continue
        reduced = 0
        for ex in day.get("main", []):
            if not reduced and body_part_zh in ex.get("why", ""):
                ex["sets"] = max(1, ex.get("sets", 3) - 1)
                ex["why"] = f"（减量：{reason}）" + ex["why"]
                reduced += 1


def _boost_bodypart(plan: dict, body_part_zh: str, note: str = ""):
    """增加某身体部位的动作。"""
    for day in plan.get("days", []):
        if day.get("is_rest"):
            continue
        has = False
        for ex in day.get("main", []):
            if body_part_zh in ex.get("why", ""):
                has = True
                break
        if not has and _BODYWEIGHT_EXERCISES.get(body_part_zh):
            extra = _pick(_BODYWEIGHT_EXERCISES[body_part_zh], 1)
            if extra:
                day["main"].append(_make_exercise(extra[0], 2, "10-12"))


def get_future_projection(goal: str, pain_point: str) -> str:
    """V19: 根据目标和痛点生成未来投射文案（心理学钩子 2）。"""
    projections = {
        "减脂": "如果你坚持这个计划：\n\n• 第 1 周：你会开始习惯「运动」不是痛苦，是日常\n• 第 2 周：爬楼梯不再喘，你会第一次感觉「好像瘦了」\n• 1 个月后：衣服开始变松，镜子里的线条在变化\n• 3 个月后：身边的人会问「你最近是不是在运动？」\n\n不要相信第一周的感觉。相信第三周的数据。",
        "增肌": "如果你坚持这个计划：\n\n• 第 1 周：你会学会每个动作的正确姿势，这是地基\n• 第 2 周：你的力量在悄然增长——不是感觉，是数字\n• 1 个月后：推、拉、蹲的负重会上一个台阶\n• 3 个月后：你会看到镜子里的自己开始「有型」\n\n肌肉不会在你想练的那天长出来。它在每一次你不想练但依然练了的那天长出来。",
        "更健康": "如果你坚持这个计划：\n\n• 第 1 周：你会睡得更踏实，醒来更清醒\n• 第 2 周：日常的疲劳感在减少，精力在回升\n• 1 个月后：「健康」不再是一个词，是你每天的状态\n• 3 个月后：体检报告里的数字会给你最好的反馈\n\n最好的投资不是基金，不是房产。是每天 30 分钟给自己的时间。",
        "缓解疼痛": "如果你坚持这个计划：\n\n• 第 1 周：疼痛不会马上消失，但你会开始理解它的来源\n• 第 2 周：核心稳定性和关节活动度在改善——你可能感觉不到，但你的身体知道\n• 1 个月后：弯腰、转头、下蹲——这些动作不再让你紧张\n• 3 个月后：你会重新信任自己的身体\n\n康复不是比赛。慢，就是快。",
    }
    base = projections.get(goal, projections["更健康"])

    if pain_point == "怕受伤":
        base += "\n\n安全永远是第一位的。我们宁可你进步慢一点，也不要你受伤停训。"
    elif pain_point == "没动力":
        base += "\n\n你不需要每天都充满动力。你只需要今天出现。动力会在你行动之后来找你，不是在之前。"
    elif pain_point == "没效果":
        base += "\n\n效果不是线性的。你可能前两周什么变化都看不到，然后在第三周突然发现——所有数字都在变好。"

    return base
