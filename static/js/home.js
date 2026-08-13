// ========== Home Panel ==========
import { state } from './state.js';
import { escapeHtml, emptyStateHtml, errorStateHtml } from './utils.js';
import { chartTheme } from './chart-utils.js';

// ===== Ring Drawing (V19: adaptive to canvas size) =====
function drawRing(canvasId, progress, color, valueText, unitText) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const cs = getComputedStyle(document.documentElement);
  const trackColor = cs.getPropertyValue("--ring-track").trim() || "#1e1e28";
  const valueColor = cs.getPropertyValue("--text").trim() || "#e8e8ed";
  const subColor = cs.getPropertyValue("--text3").trim() || "#63637a";
  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2;
  const isMini = w < 100;
  const radius = isMini ? 28 : 72, lineWidth = isMini ? 6 : 16;

  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.strokeStyle = trackColor;
  ctx.lineWidth = lineWidth;
  ctx.stroke();

  const startAngle = -Math.PI / 2;
  const minArc = progress > 0 && progress < 0.03 ? 0.2 : 0;
  const endAngle = startAngle + Math.max(Math.PI * 2 * Math.min(progress, 1), minArc);
  ctx.beginPath();
  ctx.arc(cx, cy, radius, startAngle, endAngle);
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = "round";
  ctx.stroke();

  if (progress > 1) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.globalAlpha = 0.4;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  ctx.fillStyle = valueColor;
  ctx.font = (isMini ? "bold 16px " : "bold 28px ") + getComputedStyle(document.body).fontFamily;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(isMini ? valueText : valueText, cx, isMini ? cy : cy - 8);
  if (!isMini) {
    ctx.fillStyle = subColor;
    ctx.font = "13px " + getComputedStyle(document.body).fontFamily;
    ctx.textBaseline = "middle";
    ctx.fillText(unitText, cx, cy + 18);
  }

  const pct = Math.round(Math.min(progress, 1) * 100);
  if (!isMini) {
    ctx.fillStyle = color;
    ctx.font = "bold 14px " + getComputedStyle(document.body).fontFamily;
    ctx.fillText(pct + "%", cx, cy + 42);
  }
}

function animateRing(canvasId, targetProgress, color, valueText, unitText, duration) {
  duration = duration || 1000;
  const startTime = performance.now();
  function step(now) {
    const elapsed = now - startTime;
    const t = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    const current = eased * targetProgress;
    drawRing(canvasId, current, color, valueText, unitText);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function drawRingsFromData(data, animate) {
  const t = chartTheme();
  const stepsData = data.summary.steps;
  if (stepsData && stepsData.has_data) {
    const stepsVal = stepsData.latest;
    const stepsProgress = stepsVal / 10000;
    if (animate) {
      animateRing("ring-steps", stepsProgress, t.blue, stepsVal.toLocaleString(), "/ 10,000步");
    } else {
      drawRing("ring-steps", stepsProgress, t.blue, stepsVal.toLocaleString(), "/ 10,000步");
    }
  } else {
    drawRing("ring-steps", 0, t.blue, "--", "步");
  }

  const calData = data.summary.calories;
  if (calData && calData.has_data) {
    const calVal = calData.latest;
    const calProgress = calVal / 500;
    if (animate) {
      animateRing("ring-calories", calProgress, t.orange, calVal.toLocaleString(), "/ 500千卡");
    } else {
      drawRing("ring-calories", calProgress, t.orange, calVal.toLocaleString(), "/ 500千卡");
    }
  } else {
    drawRing("ring-calories", 0, t.orange, "--", "千卡");
  }

  const sleepData = data.summary.sleep;
  if (sleepData && sleepData.has_data) {
    const sleepMin = sleepData.latest;
    const sleepHours = (sleepMin / 60).toFixed(1);
    const sleepProgress = sleepMin / 480;
    if (animate) {
      animateRing("ring-sleep", sleepProgress, t.purple, sleepHours, "/ 8小时");
    } else {
      drawRing("ring-sleep", sleepProgress, t.purple, sleepHours, "/ 8小时");
    }
  } else {
    drawRing("ring-sleep", 0, t.purple, "--", "小时");
  }
}

// ===== Main Load =====
export async function loadHomePanel(forceAnimate) {
  const sleepInput = document.getElementById('input-sleep');
  const weightInput = document.getElementById('quick-weight');
  if (sleepInput) sleepInput.value = '';
  if (weightInput) weightInput.value = '';

  if (state._homeDataLoaded && !forceAnimate && state._lastHomeData) {
    drawRingsFromData(state._lastHomeData, false);
    return;
  }

  const hour = new Date().getHours();
  let greeting;
  if (hour < 6) greeting = "夜深了 🌙";
  else if (hour < 9) greeting = "早上好 ☀️";
  else if (hour < 12) greeting = "上午好 🌤️";
  else if (hour < 14) greeting = "中午好 ☀️";
  else if (hour < 18) greeting = "下午好 🌈";
  else if (hour < 21) greeting = "晚上好 🌅";
  else greeting = "夜深了 🌙";

  const dayNames = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const now = new Date();
  const dateStr = now.getFullYear() + "年" + (now.getMonth()+1) + "月" + now.getDate() + "日 " + dayNames[now.getDay()];

  const greetingEl = document.getElementById("home-greeting");
  const dateEl = document.getElementById("home-date");
  if (greetingEl) greetingEl.textContent = greeting;
  if (dateEl) dateEl.textContent = dateStr;

  // 数据到达前先画占位环，避免面板空白
  const t0 = chartTheme();
  drawRing("ring-steps", 0, t0.blue, "…", "步");
  drawRing("ring-calories", 0, t0.orange, "…", "千卡");
  drawRing("ring-sleep", 0, t0.purple, "…", "小时");

  try {
    const res = await fetch("/api/health/analysis-summary?days=1");
    const data = await res.json();
    state._lastHomeData = data;
    state._homeDataLoaded = true;
    drawRingsFromData(data, true);
    loadWaterToday();
  } catch (e) {
    console.error("Home panel load error:", e);
    const t = chartTheme();
    drawRing("ring-steps", 0, t.blue, "?", "步");
    drawRing("ring-calories", 0, t.orange, "?", "千卡");
    drawRing("ring-sleep", 0, t.purple, "?", "小时");
  }

  loadTrainingStatus();
  updateHomeCards();
  loadWeeklySummary();
  renderHomeHero();
}

// V19: Hero status bar — one-sentence summary based on user state
async function renderHomeHero() {
  var heroEl = document.getElementById('home-hero-status');
  var textEl = document.getElementById('hero-status-text');
  var ctaEl = document.getElementById('hero-cta-btn');
  if (!heroEl || !textEl || !ctaEl) return;

  try {
    // Fetch plan and health summary in parallel
    var _a = await Promise.all([
      fetch('/api/training/plan').then(function(r) { return r.ok ? r.json() : null; }),
      fetch('/api/health/analysis-summary?days=1').then(function(r) { return r.ok ? r.json() : null; })
    ]);
    var planJson = _a[0], healthData = _a[1];

    var hasPlan = planJson && planJson.plan && planJson.plan.plan_data && planJson.plan.plan_data.days;
    var hasData = healthData && (healthData.steps_total > 0 || healthData.sleep_avg > 0 || healthData.calories_total > 0);

    if (hasPlan) {
      var plan = planJson.plan.plan_data;
      var todayIdx = (new Date().getDay() + 6) % 7;
      var todayPlan = plan.days[todayIdx];
      var progress = planJson.plan.day_progress || {};
      var dayKey = 'day-' + (todayIdx + 1);
      var done = progress[dayKey] === true;
      var streak = planJson.streak || 0;
      var missed = planJson.missed_days || 0;

      if (todayPlan && todayPlan.is_rest) {
        textEl.innerHTML = '😴 <b>今天是休息日</b><br><span style="font-size:13px;color:var(--text2)">' + escapeHtml(todayPlan.rest_activity || '好好恢复') + '</span>';
        ctaEl.textContent = '查看完整计划 →';
        ctaEl.style.display = '';
        ctaEl.onclick = function() {
          document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
          document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
          var pp = document.getElementById('panel-plan');
          if (pp) pp.classList.add('active');
          import('./plan.js').then(function(m) { m.loadPlan(); });
        };
      } else if (done) {
        var tomorrowIdx = (todayIdx + 1) % 7;
        var tomorrowPlan = plan.days[tomorrowIdx];
        textEl.innerHTML = '✅ <b>今天完成了！</b><br><span style="font-size:13px;color:var(--text2)">明天是「' + escapeHtml(tomorrowPlan.focus || '训练') + '」日</span>' + (streak >= 3 ? '<br><span style="font-size:12px;color:var(--accent)">连续 ' + streak + ' 天了，保持下去！</span>' : '');
        ctaEl.textContent = '预览明天 →';
        ctaEl.style.display = '';
        ctaEl.onclick = function() {
          document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
          document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
          var pp = document.getElementById('panel-plan');
          if (pp) pp.classList.add('active');
          import('./plan.js').then(function(m) { m.loadPlan(); });
        };
      } else {
        var lossMsg = '';
        if (missed >= 2) {
          lossMsg = '<br><span style="font-size:12px;color:#f87171">你已经 ' + missed + ' 天没训练了。今天就练，别等到明天</span>';
        } else if (missed === 1) {
          lossMsg = '<br><span style="font-size:12px;color:var(--text3)">昨天没练——没关系，今天回来就行</span>';
        }
        textEl.innerHTML = '🏋️ <b>今天是「' + escapeHtml(todayPlan.focus || '训练') + '」日</b><br><span style="font-size:13px;color:var(--text2)">' + escapeHtml(todayPlan.total_time || '') + (todayPlan.main ? ' · ' + todayPlan.main.length + ' 个动作' : '') + '</span>' + (streak >= 5 ? '<br><span style="font-size:12px;color:#f59e0b">连续 ' + streak + ' 天训练！中断会倒退 30%</span>' : '') + lossMsg;
        ctaEl.textContent = '查看今日训练 →';
        ctaEl.style.display = '';
        ctaEl.onclick = function() {
          document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
          document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
          var pp = document.getElementById('panel-plan');
          if (pp) pp.classList.add('active');
          import('./plan.js').then(function(m) { m.loadPlan(); });
        };
      }
    } else if (hasData) {
      textEl.innerHTML = '👋 <b>数据已就绪</b><br><span style="font-size:13px;color:var(--text2)">生成专属计划，让数据变得有意义</span>';
      ctaEl.textContent = '生成训练计划 →';
      ctaEl.style.display = '';
      ctaEl.onclick = function() {
        localStorage.removeItem('fitai-onboarded');
        location.reload();
      };
    } else {
      textEl.innerHTML = '👋 <b>准备好让身体变好了吗？</b><br><span style="font-size:13px;color:var(--text2)">3 个简单问题，马上得到你的专属 7 天方案</span>';
      ctaEl.textContent = '🎯 生成专属计划';
      ctaEl.style.display = '';
      ctaEl.onclick = function() {
        localStorage.removeItem('fitai-onboarded');
        location.reload();
      };
    }
    heroEl.style.display = '';
  } catch (e) {
    console.error('home: renderHero', e);
    // Fallback: show simple message
    textEl.innerHTML = '👋 <b>欢迎回来</b>';
    heroEl.style.display = '';
  }
}

// ===== Quick Record =====
export async function recordHealth(dataType, inputId, unit, multiplier) {
  const input = document.getElementById(inputId);
  const msgEl = document.getElementById("msg-" + dataType);
  if (!input) return;
  const val = parseFloat(input.value);
  if (!val || val <= 0) {
    if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = "请输入有效数值"; }
    return;
  }

  const finalVal = Math.round(val * multiplier * 10) / 10;
  try {
    const res = await fetch("/api/health/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_type: dataType, value: finalVal, unit: unit }),
      credentials: "same-origin",
    });
    if (res.status === 401) {
      if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = "请先登录"; }
      return;
    }
    const data = await res.json();
    if (data.error) {
      if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = data.error; }
    } else {
      if (msgEl) { msgEl.style.color = "var(--green)"; msgEl.textContent = "已记录 ✓"; }
      input.value = "";
      setTimeout(() => { if (msgEl) msgEl.textContent = ""; }, 2000);
      loadHomePanel(true);
      updateHomeCards();
    }
  } catch (e) {
    if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = "网络错误"; }
  }
}

export async function recordWater() {
  const msgEl = document.getElementById("msg-water");
  try {
    const res = await fetch("/api/health/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_type: "water", value: 1, unit: "杯" }),
      credentials: "same-origin",
    });
    if (res.status === 401) {
      if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = "请先登录"; }
      return;
    }
    const data = await res.json();
    if (data.error && msgEl) {
      msgEl.style.color = "var(--red)";
      msgEl.textContent = data.error;
    } else {
      if (msgEl) { msgEl.style.color = "var(--green)"; msgEl.textContent = "已记录 ✓"; }
      setTimeout(() => { if (msgEl) msgEl.textContent = ""; }, 1500);
      loadWaterToday();
    }
  } catch (e) {
    if (msgEl) { msgEl.style.color = "var(--red)"; msgEl.textContent = "网络错误"; }
  }
}

export async function loadWaterToday() {
  try {
    const res = await fetch("/api/health/water-today");
    const data = await res.json();
    const el = document.getElementById("water-today");
    if (el) el.textContent = "今日: " + data.total + " 杯 (" + (data.total * 250) + "ml)";
  } catch (e) {
    console.error("Water load error:", e);
  }
}

async function loadTrainingStatus() {
  const badge = document.getElementById('home-training-status');
  if (!badge) return;
  try {
    const res = await fetch('/api/dashboard/workout?days=1');
    const data = (await res.json()).data || [];
    if (data.length > 0) {
      badge.className = 'status-badge trained';
      badge.innerHTML = '🏋️ 今日已训练 ' + data.length + ' 项';
    } else {
      badge.className = 'status-badge idle';
      badge.innerHTML = '🏃 今天还没动，来一组？';
    }
    badge.style.display = 'inline-flex';
  } catch (e) {
    badge.style.display = 'none';
  }
}

export async function loadWeeklySummary() {
  const el = document.getElementById('weekly-summary');
  if (!el) return;
  el.innerHTML = '<div class="weekly-stats-row">' +
    '<span class="skeleton" style="width:110px;height:26px;display:inline-block"></span>'.repeat(3) + '</div>';
  try {
    const res = await fetch('/api/weekly-summary', { credentials: 'same-origin' });
    const data = await res.json();
    const s = data.summary;
    if (!s || Object.keys(s).length <= 2) { el.innerHTML = emptyStateHtml('📭', '暂无本周数据，导入或开始记录后自动生成周摘要', '去导入数据', 'settings', true); return; }

    const parts = [];
    if (s.workout_count) parts.push('<b>' + s.workout_count + '</b> 次训练');
    if (s.steps) parts.push('日均 <b>' + Math.round(s.steps.avg).toLocaleString() + '</b> 步');
    if (s.sleep) parts.push('睡眠均 <b>' + (s.sleep.avg / 60).toFixed(1) + '</b> 小时');
    if (s.calories) parts.push('消耗 <b>' + Math.round(s.calories.total).toLocaleString() + '</b> 千卡');
    if (s.water) parts.push('喝水 <b>' + Math.round(s.water.total) + '</b> 杯');
    if (typeof s.weight_change === 'number') {
      const wc = s.weight_change;
      parts.push('体重 <b style="color:' + (wc <= 0 ? 'var(--green)' : 'var(--orange)') + '">' + (wc > 0 ? '+' : '') + wc.toFixed(1) + 'kg</b>');
    }
    el.innerHTML = '<div class="weekly-stats-row">' + parts.map(function(p) { return '<span class="weekly-stat-chip">' + p + '</span>'; }).join('') + '</div>';
  } catch (e) {
    el.innerHTML = errorStateHtml('home');
  }
}

export async function updateHomeCards() {
  try {
    // V18: fetch training plan first for today's workout
    var planData = null;
    try {
      var pRes = await fetch('/api/training/plan');
      if (pRes.ok) {
        var pJson = await pRes.json();
        if (pJson.plan && pJson.plan.plan_data && pJson.plan.plan_data.days) {
          planData = pJson.plan.plan_data;
        }
      }
    } catch(e) { console.error('home: fetch plan', e); }

    const [wRes, mRes, sRes] = await Promise.all([
      fetch('/api/dashboard/workout?days=7'),
      fetch('/api/dashboard/metrics?days=90'),
      fetch('/api/stats?days=7'),
    ]);
    const workouts = (await wRes.json()).data || [];
    const metrics = (await mRes.json()).data || [];
    const stats = (await sRes.json()) || {};

    // V18: Today's training card — plan first, fall back to stats
    const recCard = document.getElementById('home-card-recommend');
    const recDesc = document.getElementById('rec-desc');
    if (planData && planData.days) {
      var todayIdx = (new Date().getDay() + 6) % 7;
      var todayPlan = planData.days[todayIdx];
      if (todayPlan && !todayPlan.is_rest && todayPlan.main && todayPlan.main.length > 0) {
        var exNames = todayPlan.main.slice(0, 3).map(function(e) { return e.name; }).join('、');
        if (recDesc) recDesc.innerHTML = '<span class="rec-highlight">' + todayPlan.day_name + '</span>：' + escapeHtml(exNames) + (todayPlan.main.length > 3 ? ' 等' + todayPlan.main.length + '个动作' : '');
        if (recCard) {
          recCard.onclick = function() {
            document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
            document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
            var pp = document.getElementById('panel-plan');
            if (pp) pp.classList.add('active');
            import('./plan.js').then(function(m) { m.loadPlan(); });
          };
          recCard.style.cursor = 'pointer';
        }
        // Update weekly stats with plan goal
        const recWeekly = document.getElementById('rec-weekly');
        if (recWeekly && planData.goal) {
          recWeekly.innerHTML = '目标：<span class="rec-highlight">' + escapeHtml(planData.goal) + '</span> · 每周 <span class="rec-highlight">' + planData.frequency + '</span> 天';
        }
      } else if (todayPlan && todayPlan.is_rest) {
        if (recDesc) recDesc.innerHTML = '今天是<span class="rec-highlight">休息日</span>，' + (todayPlan.rest_activity || '好好恢复');
      }
    } else if (recDesc) {
      // Fallback: current behavior
      if (stats.exercises && stats.exercises.length > 0) {
        const topEx = stats.exercises[0];
        recDesc.innerHTML = '你最常练 <span class="rec-highlight">' + escapeHtml(topEx.exercise_name) + '</span>（' + topEx.cnt + '次），保持节奏！';
      } else {
        recDesc.textContent = '开始你的第一次训练，AI 教练来指导';
      }
    }

    const recWeekly = document.getElementById('rec-weekly');
    if (recWeekly && !planData) {
      const wkCount = workouts.length;
      const streak = stats.streak || 0;
      if (wkCount > 0) {
        recWeekly.innerHTML = '本周 <span class="rec-highlight">' + wkCount + '</span> 次训练' + (streak > 1 ? ' · 连续 <span class="rec-highlight">' + streak + '</span> 天' : '');
      } else {
        recWeekly.textContent = '本周暂无训练记录';
      }
    }

    const recTrend = document.getElementById('rec-trend');
    if (recTrend) {
      if (metrics.length >= 2) {
        const latest = metrics[metrics.length - 1];
        const prev = metrics[metrics.length - 2];
        if (latest.weight_kg && prev.weight_kg) {
          const diff = (latest.weight_kg - prev.weight_kg).toFixed(1);
          const arrow = diff > 0 ? '↑' : (diff < 0 ? '↓' : '→');
          const color = diff < 0 ? 'var(--green)' : (diff > 0 ? 'var(--orange)' : 'var(--text2)');
          recTrend.innerHTML = '最新 <span class="rec-highlight">' + latest.weight_kg + 'kg</span> · 较上次 <span style="color:' + color + ';font-weight:700">' + arrow + Math.abs(diff) + 'kg</span>';
        } else if (latest.weight_kg) {
          recTrend.innerHTML = '最新体重 <span class="rec-highlight">' + latest.weight_kg + 'kg</span>';
        } else {
          recTrend.textContent = '记录体重数据以追踪变化';
        }
      } else {
        recTrend.textContent = '记录体重数据以追踪变化';
      }
    }
  } catch (e) {
    console.error('Update home cards error:', e);
  }
}

export function ringClick(metric, name, icon, color, unit, chartType) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const healthBtn = document.querySelector('.nav-btn[data-panel="health"]');
  if (healthBtn) healthBtn.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const healthPanel = document.getElementById('panel-health');
  if (healthPanel) healthPanel.classList.add('active');
  import('./health.js').then(m => {
    m.loadHealthDashboard(7);
    setTimeout(function() { m.openHealthDetail(metric, name, icon, color, unit, chartType); }, 200);
  });
}

export async function triggerAIRecommend() {
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  const chatBtn = document.querySelector('.nav-btn[data-panel="chat"]');
  if (chatBtn) chatBtn.classList.add("active");
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const chatPanel = document.getElementById("panel-chat");
  if (chatPanel) chatPanel.classList.add("active");

  try {
    const res = await fetch("/api/health/analysis-summary?days=7");
    const data = await res.json();
    let summary = "";
    if (data.summary.steps && data.summary.steps.has_data) {
      summary += "步数: 日均" + data.summary.steps.stats_7d.avg + "步, 趋势" + (data.weekly_trends.steps ? data.weekly_trends.steps.direction : "稳定") + "。";
    }
    if (data.summary.heart_rate && data.summary.heart_rate.has_data) {
      summary += "心率: 日均" + data.summary.heart_rate.stats_7d.avg + "bpm。";
    }
    if (data.summary.sleep && data.summary.sleep.has_data) {
      summary += "睡眠: 日均" + data.summary.sleep.stats_7d.avg + "分钟。";
    }
    if (data.summary.calories && data.summary.calories.has_data) {
      summary += "卡路里: 日均" + data.summary.calories.stats_7d.avg + "千卡。";
    }
    const chatInput = document.getElementById('chat-input');
    if (chatInput) chatInput.value = "根据以下健康数据摘要，给我个性化的运动、饮食和生活建议（要具体可操作）：" + summary;
  } catch (e) {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) chatInput.value = "请根据我的健康数据给我个性化的运动和饮食建议";
  }
  const { sendMessage } = await import('./chat.js');
  sendMessage();
}

export function triggerAIAnalysis() {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const chatBtn = document.querySelector('.nav-btn[data-panel="chat"]');
  if (chatBtn) chatBtn.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-chat').classList.add('active');
  const chatInput = document.getElementById('chat-input');
  if (chatInput) chatInput.value = '请根据我近期的健康数据（步数、心率、睡眠、卡路里）做一次综合分析';
  import('./chat.js').then(m => m.sendMessage());
}
