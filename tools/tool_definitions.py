# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI 工具定义 — OpenAI function calling 格式"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索运动健康知识，获取文字技巧和建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如'深蹲正确姿势'、'跑步膝盖保护'"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_url",
            "description": "获取B站教学视频链接。当用户问到某个动作怎么做、想学某项运动、想看教学视频时，调用此工具",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string", "description": "运动名称，如'深蹲'、'俯卧撑'、'跑步姿势'"}
                },
                "required": ["exercise_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_workout",
            "description": "记录用户的训练数据。RPE 是自觉用力程度（1-10 量表），用于计算训练负荷 sRPE = RPE × 时长",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string", "description": "训练动作名称"},
                    "sets": {"type": "integer", "description": "组数"},
                    "reps": {"type": "integer", "description": "每组次数"},
                    "weight_kg": {"type": "number", "description": "重量(kg)"},
                    "duration_minutes": {"type": "integer", "description": "持续时间(分钟)"},
                    "rpe": {"type": "integer", "description": "自觉用力程度(RPE), 1-10量表", "minimum": 1, "maximum": 10},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": ["exercise_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_body_metric",
            "description": "记录用户的身体测量数据（体重、体脂率等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number", "description": "体重(kg)"},
                    "body_fat_pct": {"type": "number", "description": "体脂率(%)"},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_nutrition",
            "description": "记录用户的饮食数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "description": "餐食类型：早餐/午餐/晚餐/加餐"},
                    "food_name": {"type": "string", "description": "食物名称"},
                    "calories": {"type": "number", "description": "热量(千卡)"},
                    "protein_g": {"type": "number", "description": "蛋白质(克)"},
                    "carbs_g": {"type": "number", "description": "碳水(克)"},
                    "fat_g": {"type": "number", "description": "脂肪(克)"}
                },
                "required": ["food_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_workout_history",
            "description": "查询用户的训练历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "查询最近多少天，默认30"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_body_metrics",
            "description": "查询用户的身体测量历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "查询最近多少天，默认30"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_nutrition_history",
            "description": "查询用户的饮食历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "查询最近多少天，默认30"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_health_data",
            "description": "查询用户的健康数据（步数、心率、睡眠、卡路里等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_type": {"type": "string", "description": "数据类型：steps, heart_rate, sleep, calories, spo2, weight, body_fat, blood_pressure_sys, blood_glucose, hydration, exercise"},
                    "days": {"type": "integer", "description": "查询最近多少天，默认30"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_health_now",
            "description": "同步设备健康数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "平台：google_fit, huawei_health, health_connect"}
                },
                "required": ["platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compute_daily_score",
            "description": "计算今日综合健康分(0-100)。用户问'今天状态怎么样''健康分多少'时使用。融合步数、睡眠、心率等指标",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询城市天气。用户问天气、户外运动建议、今天适合跑步吗时使用",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如北京、上海、广州"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "predict_trends",
            "description": "预测用户各项健康指标的未来趋势。用户问'我会瘦吗''趋势怎么样''预测一下'时使用。基于线性回归外推",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "分析最近多少天的数据，默认60"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_correlations",
            "description": "分析用户健康数据之间的关联模式（如睡眠 vs 步数），发现隐藏规律。用户问'我的数据有什么规律'或'它们有关联吗'时使用",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "分析最近多少天，默认60"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {"name": "recovery_score", "description": "计算今日恢复评分(0-100)。用户问'今天该练吗''恢复得怎么样'时使用。综合训练强度、睡眠、心率", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "recommend_workouts", "description": "基于训练历史推荐动作。用户问'推荐练什么''有什么新动作'时使用", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "training_plan", "description": "生成4周渐进训练计划。用户问'帮我制定计划''怎么安排训练'时使用", "parameters": {"type": "object", "properties": {"goal": {"type": "string", "description": "目标：减脂/增肌/综合"}}}}
    },
    {
        "type": "function",
        "function": {"name": "advanced_health_score", "description": "计算指数加权健康综合评分，近期数据权重更高，自动识别数据陈旧并扣分。用户问'我整体健康水平怎么样''最近状态如何'时使用", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "cross_anomaly_check", "description": "跨指标组合异常检测。识别隐性风险（如睡眠正常+心率升高+步数骤降=潜在过度训练）。用户说'我感觉不对劲''最近很累'时使用", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "adaptive_training_plan", "description": "基于历史数据自适应调整的训练计划，根据完成率动态调整强度。比 training_plan 更个性化", "parameters": {"type": "object", "properties": {"goal": {"type": "string", "description": "目标：减脂/增肌/综合"}}}}
    },
    {
        "type": "function",
        "function": {"name": "analyze_food_photo", "description": "识别食物照片并返回营养数据。用户上传了食物图片时使用此工具。", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "search_exercises", "description": "搜索标准健身动作库（1,324个动作，含中文指导和演示动图）。注意：动作名是英文的，请将用户的中文动作名翻译成英文关键词再搜索。如'卧推'→'bench press'，'深蹲'→'squat'，'俯卧撑'→'push up'", "parameters": {"type": "object", "properties": {"body_part": {"type": "string", "description": "身体部位（英文：chest/back/legs/shoulders/arms/waist）"}, "equipment": {"type": "string", "description": "器材（英文：dumbbell/barbell/body weight/cable）"}, "keyword": {"type": "string", "description": "搜索关键词（英文）"}}}}
    },
    {
        "type": "function",
        "function": {"name": "get_exercise_instructions", "description": "获取某个健身动作的详细中文指导步骤和演示动图链接。注意：参数用英文动作名（如bench press、squat、push up）。", "parameters": {"type": "object", "properties": {"exercise_name": {"type": "string", "description": "英文动作名称"}}, "required": ["exercise_name"]}}
    },
    {
        "type": "function",
        "function": {"name": "causal_insight", "description": "因果洞察分析：发现用户健康指标间的因果关系（非相关性），回答'为什么'类问题。如'为什么我的恢复分这么低'、'睡眠和心率有什么关系'、'如果我多睡1小时会怎样'。这是FitAI的核心差异化功能——基于Pearl因果推断（不是简单相关分析）", "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "用户想了解的因果问题，如'what_affects_recovery'、'sleep_effect_on_hr'、'what_if_more_sleep'"}}}}
    },
    {
        "type": "function",
        "function": {"name": "get_current_plan", "description": "读取用户当前的训练计划和进度。在用户询问「我的计划是什么」「练到哪了」「这周还有几天」或需要调整计划时，先调用此工具了解现状", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "adjust_training_plan", "description": "基于当前计划和训练反馈调整训练计划。用户说「引体向上做不了」「太累了想换一下」「周三没时间」「能不能换个动作」时使用。会自动读取用户的当前计划和历史反馈，结合用户的要求生成调整后的新计划", "parameters": {"type": "object", "properties": {"changes": {"type": "string", "description": "用户想调整什么，例如'引体向上做不了，换个动作'、'太累了，降强度'、'周三没时间'、'想把跑步换成游泳'"}}}}
    }
]
