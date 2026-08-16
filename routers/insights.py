# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""因果洞察聚合路由：按子域拆分后统一 include。"""
from fastapi import APIRouter

from routers.insights_causal import router as _causal
from routers.insights_recovery import router as _recovery
from routers.insights_physiology import router as _physiology
from routers.insights_forecast import router as _forecast

router = APIRouter(prefix="/api/insights", tags=["insights"])

router.include_router(_causal)
router.include_router(_recovery)
router.include_router(_physiology)
router.include_router(_forecast)
