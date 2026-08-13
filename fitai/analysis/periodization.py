# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""智能周期化：根据用户目标自动生成渐进式训练计划。"""

WEEKLY_TEMPLATES = {
    "减脂": [
        {"focus": "建立基础", "intensity": "中低", "cardio": "3次×30min", "strength": "全身2次", "note": "重点培养运动习惯，动作规范优先"},
        {"focus": "增加消耗", "intensity": "中等", "cardio": "4次×35min", "strength": "上肢+下肢各1次", "note": "加入间歇训练(HIIT)，提高燃脂效率"},
        {"focus": "强度提升", "intensity": "中高", "cardio": "4次×40min", "strength": "推拉腿分化3次", "note": "增加负重，缩短组间休息到 60 秒"},
        {"focus": "突破平台", "intensity": "高", "cardio": "5次×30min", "strength": "推拉腿分化4次", "note": "挑战自我，尝试新动作打破适应"},
    ],
    "增肌": [
        {"focus": "动作学习", "intensity": "中等", "cardio": "1次×20min", "strength": "全身3次", "note": "重点掌握深蹲、卧推、硬拉三大项"},
        {"focus": "肌耐力", "intensity": "中高", "cardio": "1次×20min", "strength": "上下分化4次", "note": "每组 10-12 次，组间休息 90 秒"},
        {"focus": "肌肉增长", "intensity": "高", "cardio": "0-1次×15min", "strength": "推拉腿分化5次", "note": "每组 8-10 次至力竭，确保每天蛋白质 >1.6g/kg"},
        {"focus": "力量峰值", "intensity": "极高", "cardio": "0次", "strength": "推拉腿分化5次", "note": "每组 5-8 次大重量，组间休息 2-3 分钟"},
    ],
    "综合": [
        {"focus": "适应期", "intensity": "中低", "cardio": "2次×25min", "strength": "全身2次", "note": "平衡有氧和力量，建立运动节奏"},
        {"focus": "提升期", "intensity": "中等", "cardio": "3次×30min", "strength": "上下分化3次", "note": "逐步增加训练频率和时长"},
        {"focus": "强化期", "intensity": "中高", "cardio": "3次×35min", "strength": "推拉腿分化4次", "note": "提升每组的训练质量"},
        {"focus": "维持期", "intensity": "高", "cardio": "3次×30min", "strength": "推拉腿分化4次", "note": "维持成果，适当加入新刺激"},
    ],
}


def generate_plan(goal: str, weeks: int = 4) -> dict:
    """根据目标生成 N 周训练计划。goal: 减脂/增肌/综合"""
    template = WEEKLY_TEMPLATES.get(goal, WEEKLY_TEMPLATES["综合"])
    plan = []
    for i, week in enumerate(template[:weeks]):
        plan.append({
            "week": i + 1,
            "focus": week["focus"],
            "intensity": week["intensity"],
            "cardio": week["cardio"],
            "strength": week["strength"],
            "note": week["note"],
        })
    return {
        "goal": goal,
        "weeks": len(plan),
        "plan": plan,
        "summary": f"{weeks}周{goal}计划：从{plan[0]['focus']}逐步过渡到{plan[-1]['focus']}"
    }
