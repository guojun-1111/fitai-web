# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""工具注册表 — 适配 AgentLoop"""
import asyncio
import json
from typing import Any, Dict, Optional

from tools import fitai_tools
from tools.tool_definitions import TOOL_DEFINITIONS


class ToolRegistry:
    def __init__(self, user_id: int):
        self._user_id = user_id
        self._handlers: Dict[str, callable] = {
            "search": lambda args: fitai_tools.search(args.get("query", "")),
            "get_video_url": lambda args: fitai_tools.get_video_url(args.get("exercise_name", "")),
            "log_workout": lambda args: fitai_tools.log_workout(
                self._user_id,
                exercise_name=args.get("exercise_name", ""),
                sets=args.get("sets"),
                reps=args.get("reps"),
                weight_kg=args.get("weight_kg"),
                duration_minutes=args.get("duration_minutes"),
                notes=args.get("notes"),
            ),
            "log_body_metric": lambda args: fitai_tools.log_body_metric(
                self._user_id,
                weight_kg=args.get("weight_kg"),
                body_fat_pct=args.get("body_fat_pct"),
                notes=args.get("notes"),
            ),
            "log_nutrition": lambda args: fitai_tools.log_nutrition(
                self._user_id,
                meal_type=args.get("meal_type"),
                food_name=args.get("food_name", ""),
                calories=args.get("calories"),
                protein_g=args.get("protein_g"),
                carbs_g=args.get("carbs_g"),
                fat_g=args.get("fat_g"),
            ),
            "query_workout_history": lambda args: fitai_tools.query_workout_history(
                self._user_id,
                days=args.get("days", 30),
            ),
            "query_body_metrics": lambda args: fitai_tools.query_body_metrics(
                self._user_id,
                days=args.get("days", 30),
            ),
            "query_nutrition_history": lambda args: fitai_tools.query_nutrition_history(
                self._user_id,
                days=args.get("days", 30),
            ),
            "query_health_data": lambda args: fitai_tools.query_health_data(
                self._user_id,
                data_type=args.get("data_type", ""),
                days=args.get("days", 30),
            ),
            "sync_health_now": lambda args: fitai_tools.sync_health_now(
                self._user_id,
                platform=args.get("platform", "google_fit"),
            ),
            "compute_daily_score": lambda args: fitai_tools.compute_daily_score(self._user_id),
            "recovery_score": lambda args: fitai_tools.recovery_score(self._user_id),
            "recommend_workouts": lambda args: fitai_tools.recommend_workouts(self._user_id),
            "training_plan": lambda args: fitai_tools.training_plan(args.get("goal", "综合")),
            "get_weather": lambda args: fitai_tools.get_weather(
                city=args.get("city", "北京"),
            ),
            "predict_trends": lambda args: fitai_tools.predict_trends(
                self._user_id,
                days=args.get("days", 60),
            ),
            "analyze_correlations": lambda args: fitai_tools.analyze_correlations(
                self._user_id,
                days=args.get("days", 60),
            ),
            "advanced_health_score": lambda args: fitai_tools.advanced_health_score(self._user_id),
            "cross_anomaly_check": lambda args: fitai_tools.cross_anomaly_check(self._user_id),
            "adaptive_training_plan": lambda args: fitai_tools.adaptive_training_plan(
                self._user_id,
                goal=args.get("goal", "综合"),
            ),
            "analyze_food_photo": lambda args: fitai_tools.analyze_food_photo(self._user_id),
            "search_exercises": lambda args: fitai_tools.search_exercises(
                body_part=args.get("body_part", ""),
                equipment=args.get("equipment", ""),
                keyword=args.get("keyword", ""),
            ),
            "get_exercise_instructions": lambda args: fitai_tools.get_exercise_instructions(
                exercise_name=args.get("exercise_name", ""),
            ),
            "causal_insight": lambda args: fitai_tools.causal_insight(
                self._user_id,
                question=args.get("question", "what_affects_recovery"),
            ),
            "get_current_plan": lambda args: fitai_tools.get_current_plan(self._user_id),
            "adjust_training_plan": lambda args: fitai_tools.adjust_training_plan(
                self._user_id,
                changes=args.get("changes", ""),
            ),
        }

    def get_definitions(self):
        return TOOL_DEFINITIONS

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return f"Unknown tool: {tool_name}"
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, handler, arguments)
            if result is None:
                return "Tool executed successfully"
            return str(result)
        except Exception as e:
            return f"Tool error: {e}"
