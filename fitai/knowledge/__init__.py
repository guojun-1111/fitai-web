# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI Knowledge Graph — structured exercise science knowledge for plan generation."""
from fitai.knowledge.fitkg import (
    query_exercises,
    get_exercise_detail,
    get_muscle_info,
    get_contraindications,
    get_alternatives,
    get_category_info,
    get_exercise_zh,
    CATEGORY_INFO,
    EQUIPMENT_ALTERNATIVES,
    INJURY_CONTRAS,
    PAIN_TO_INJURY,
)
