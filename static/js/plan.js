export function initPlan() {
  // Nothing to init on page load; plan is loaded on demand
}

export function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function errorStateHtml(id) {
  return '<div class="empty-state"><div class="empty-icon">⚠️</div><p>加载失败</p><button class="btn btn-outline btn-sm" onclick="import(\'./plan.js\').then(m=>m.loadPlan())">重试</button></div>';
}

export async function loadPlan() {
  var container = document.getElementById('plan-content');
  if (!container) return;
  container.innerHTML = '<div class="skeleton-pulse" style="height:200px;border-radius:12px;margin:8px 0"></div><div class="skeleton-pulse" style="height:160px;border-radius:12px;margin:8px 0"></div>';

  try {
    var resp = await fetch('/api/training/plan');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    if (!data.plan || !data.plan.plan_data) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">📅</div><p>还没有训练计划</p><p style="font-size:13px;color:var(--text3);margin-top:4px">3 个简单问题，马上生成 7 天可执行方案</p><button class="btn btn-primary" style="margin-top:16px" onclick="localStorage.removeItem(\'fitai-onboarded\');location.reload()">🎯 生成专属计划</button></div>';
      return;
    }

    var plan = data.plan.plan_data;
    var progress = data.plan.day_progress || {};
    renderPlan(container, plan, progress, data.plan.id);
  } catch (e) {
    console.error('plan: loadPlan', e);
    container.innerHTML = errorStateHtml('plan');
  }
}

function renderPlan(container, plan, progress, planId) {
  if (!plan.days) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">📅</div><p>计划格式不支持</p></div>';
    return;
  }

  var todayIdx = (new Date().getDay() + 6) % 7;
  var html = '';

  // Header
  html += '<div class="plan-header" style="margin-bottom:16px;padding:0 4px">';
  if (plan.goal) html += '<span class="plan-badge">' + escapeHtml(plan.goal) + '</span>';
  if (plan.frequency) html += '<span class="plan-badge" style="background:rgba(148,148,168,0.12);color:var(--text2)">每周 ' + plan.frequency + ' 天</span>';
  html += '</div>';

  // V19: Future projection (psychological hook #2)
  if (plan.future_projection) {
    html += '<div class="plan-future" style="background:linear-gradient(135deg,rgba(61,214,140,0.06),rgba(61,214,140,0.01));border:1px solid rgba(61,214,140,0.12);border-radius:12px;padding:16px;margin-bottom:16px;font-size:13px;color:var(--text2);line-height:1.8;white-space:pre-line">' + escapeHtml(plan.future_projection) + '</div>';
  }

  // Explanation
  if (plan.explanation) {
    html += '<div class="plan-explain" style="font-size:13px;color:var(--text3);margin-bottom:16px;line-height:1.5;padding:0 4px">' + escapeHtml(plan.explanation) + '</div>';
  }

  // Day cards
  for (var d = 0; d < plan.days.length; d++) {
    var day = plan.days[d];
    var isToday = d === todayIdx;
    var dayKey = 'day-' + (d + 1);
    var done = progress[dayKey] === true;

    html += '<div class="plan-day-card' + (isToday ? ' today' : '') + (done ? ' done' : '') + '" data-day="' + (d + 1) + '">';
    html += '<div class="plan-day-head" onclick="var b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\'">';
    html += '<span class="plan-day-icon">' + (day.is_rest ? '😴' : '🏋️') + '</span>';
    html += '<span class="plan-day-name">' + escapeHtml(day.day_name) + '</span>';
    html += '<span class="plan-day-focus' + (day.is_rest ? ' rest' : '') + '">' + escapeHtml(day.focus || (day.is_rest ? '休息' : '训练')) + '</span>';
    if (!day.is_rest) html += '<span class="plan-day-time">' + escapeHtml(day.total_time || '') + '</span>';
    if (done) html += '<span class="plan-day-check">✅</span>';
    html += '<span class="plan-day-toggle">▼</span>';
    html += '</div>';

    // Expanded body (hidden by default for non-today days)
    var bodyStyle = isToday ? '' : 'display:none';
    html += '<div class="plan-day-body" style="' + bodyStyle + '">';

    if (day.is_rest) {
      html += '<div class="plan-rest">' + escapeHtml(day.rest_activity || '好好休息') + '</div>';
    } else {
      // Warmup
      if (day.warmup && day.warmup.length > 0) {
        html += '<div class="plan-section-label">🔥 热身</div>';
        for (var w = 0; w < day.warmup.length; w++) {
          var wu = day.warmup[w];
          html += '<div class="plan-ex-row"><span class="plan-ex-name">' + escapeHtml(wu.name) + '</span><span class="plan-ex-dur">' + escapeHtml(wu.duration) + '</span></div>';
        }
      }

      // Main exercises
      html += '<div class="plan-section-label">💪 训练动作</div>';
      if (day.main && day.main.length > 0) {
        for (var e = 0; e < day.main.length; e++) {
          var ex = day.main[e];
          html += '<div class="plan-ex-row main">';
          html += '<div class="plan-ex-info"><span class="plan-ex-name">' + escapeHtml(ex.name) + '</span>';
          html += '<span class="plan-ex-spec">' + ex.sets + '组 × ' + escapeHtml(String(ex.reps)) + '</span>';
          html += '<span class="plan-ex-why">' + escapeHtml(ex.why || '') + '</span></div>';
          if (ex.tip) html += '<span class="plan-ex-tip">💡 ' + escapeHtml(ex.tip) + '</span>';
          html += '</div>';
        }
      } else {
        html += '<div class="plan-ex-row" style="color:var(--text3)">暂无动作详情</div>';
      }

      // Cooldown
      if (day.cooldown && day.cooldown.length > 0) {
        html += '<div class="plan-section-label">🧘 拉伸</div>';
        for (var c = 0; c < day.cooldown.length; c++) {
          var cd = day.cooldown[c];
          html += '<div class="plan-ex-row"><span class="plan-ex-name">' + escapeHtml(cd.name) + '</span><span class="plan-ex-dur">' + escapeHtml(cd.duration) + '</span></div>';
        }
      }
    }

    if (day.tip) {
      html += '<div class="plan-day-tip">💡 ' + escapeHtml(day.tip) + '</div>';
    }

    // Complete button for today's training days
    if (!day.is_rest && !done && isToday) {
      html += '<button class="plan-complete-btn" onclick="import(\'./plan.js\').then(function(m){m.markComplete(' + planId + ',\'day-' + (d + 1) + '\',' + d + ')})">✅ 标记完成</button>';
    }

    html += '</div>'; // plan-day-body
    html += '</div>'; // plan-day-card
  }

  container.innerHTML = html;
}

export async function markComplete(planId, dayKey, dayIdx) {
  try {
    var resp = await fetch('/api/training/plan/complete-day', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId, day: dayKey })
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    // V20: Show feedback panel after completion
    showFeedbackPanel(planId, dayKey);
    loadPlan();
  } catch (e) {
    console.error('plan: markComplete', e);
  }
}

// V20: Inline feedback panel after completing a training day
function showFeedbackPanel(planId, dayKey) {
  var container = document.getElementById('plan-content');
  if (!container) return;

  var fbHtml = '<div class="feedback-panel" id="feedback-panel">';
  fbHtml += '<div class="fb-title">训练感受如何？</div>';

  // Difficulty
  fbHtml += '<div class="fb-row"><span class="fb-label">难度</span>';
  fbHtml += '<span class="fb-chip" data-fb="difficulty" data-val="too_easy" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">太简单</span>';
  fbHtml += '<span class="fb-chip" data-fb="difficulty" data-val="just_right" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">刚好</span>';
  fbHtml += '<span class="fb-chip" data-fb="difficulty" data-val="too_hard" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">太难</span>';
  fbHtml += '</div>';

  // Soreness
  fbHtml += '<div class="fb-row"><span class="fb-label">酸痛</span>';
  fbHtml += '<span class="fb-chip" data-fb="soreness" data-val="none" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">无</span>';
  fbHtml += '<span class="fb-chip" data-fb="soreness" data-val="mild" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">轻微</span>';
  fbHtml += '<span class="fb-chip" data-fb="soreness" data-val="moderate" onclick="import(\'./plan.js\').then(function(m){m._fbSelect(this)})">明显</span>';
  fbHtml += '</div>';

  // Sore areas (multi-select)
  fbHtml += '<div class="fb-row"><span class="fb-label">哪里酸？（可多选）</span></div>';
  fbHtml += '<div class="fb-row fb-areas">';
  var areas = ['肩', '背', '腰', '膝', '臂', '腿', '无'];
  areas.forEach(function(a) {
    fbHtml += '<span class="fb-chip fb-area" data-area="' + a + '" onclick="import(\'./plan.js\').then(function(m){m._fbToggleArea(this)})">' + a + '</span>';
  });
  fbHtml += '</div>';

  // Submit + Skip
  fbHtml += '<div class="fb-actions">';
  fbHtml += '<button class="btn btn-primary btn-sm" onclick="import(\'./plan.js\').then(function(m){m._fbSubmit(' + planId + ',\'' + dayKey + '\')})">提交反馈</button>';
  fbHtml += '<button class="btn btn-outline btn-sm" onclick="var el=document.getElementById(\'feedback-panel\');if(el)el.remove()">跳过</button>';
  fbHtml += '</div>';
  fbHtml += '</div>';

  // Remove existing feedback panel if any
  var existing = document.getElementById('feedback-panel');
  if (existing) existing.remove();

  // Insert after the first day card that's today
  var todayCard = container.querySelector('.plan-day-card.today');
  if (todayCard) {
    todayCard.insertAdjacentHTML('afterend', fbHtml);
  } else {
    container.insertAdjacentHTML('beforeend', fbHtml);
  }
}

// Feedback state
var _feedbackData = { difficulty: '', soreness: '', sore_areas: [] };

export function _fbSelect(el) {
  var field = el.dataset.fb;
  var val = el.dataset.val;
  _feedbackData[field] = val;
  // Toggle active state on siblings
  var parent = el.parentElement;
  var chips = parent.querySelectorAll('.fb-chip');
  chips.forEach(function(c) { c.classList.remove('active'); });
  el.classList.add('active');
}

export function _fbToggleArea(el) {
  var area = el.dataset.area;
  var idx = _feedbackData.sore_areas.indexOf(area);
  if (idx >= 0) {
    _feedbackData.sore_areas.splice(idx, 1);
    el.classList.remove('active');
  } else {
    // If selecting a body part, remove '无' if present
    if (area !== '无') {
      var noneIdx = _feedbackData.sore_areas.indexOf('无');
      if (noneIdx >= 0) _feedbackData.sore_areas.splice(noneIdx, 1);
    } else {
      _feedbackData.sore_areas = ['无'];
    }
    _feedbackData.sore_areas.push(area);
    el.classList.add('active');
  }
}

export async function _fbSubmit(planId, dayKey) {
  try {
    await fetch('/api/training/plan/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_id: planId, day: dayKey,
        difficulty: _feedbackData.difficulty,
        soreness: _feedbackData.soreness,
        sore_areas: _feedbackData.sore_areas
      })
    });
  } catch (e) {
    console.error('plan: feedback submit', e);
  }
  var el = document.getElementById('feedback-panel');
  if (el) {
    el.innerHTML = '<div class="fb-thanks">感谢反馈！明天继续加油 💪</div>';
    setTimeout(function() { if (el) el.remove(); }, 2000);
  }
  _feedbackData = { difficulty: '', soreness: '', sore_areas: [] };
}
