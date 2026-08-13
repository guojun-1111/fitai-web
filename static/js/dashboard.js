// ========== Dashboard Panel ==========
import { animateCounter, exEmoji, hexToRgba, emptyStateHtml, showPanelError, clearPanelError } from './utils.js';
import { loadSidebarStats } from './sidebar.js';
import { adaptivePointRadius, chartMinWidth, createChartOptions, chartTheme, setChartEmpty, setChartSkeleton } from './chart-utils.js';

let weightChart = null, workoutChart = null;
export let dashDays = 7;

// Period buttons
export function initDashboard() {
  document.querySelectorAll('#panel-dashboard .period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#panel-dashboard .period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      dashDays = parseInt(btn.dataset.days);
      loadDashboard(dashDays);
    });
  });
}

export async function loadDashboard(days) {
  dashDays = days;
  setChartSkeleton(document.getElementById('chart-weight'));
  setChartSkeleton(document.getElementById('chart-workout'));
  try {
    const [wRes, mRes, nRes, sRes] = await Promise.all([
      fetch('/api/dashboard/workout?days=' + days),
      fetch('/api/dashboard/metrics?days=' + Math.max(days, 90)),
      fetch('/api/dashboard/nutrition?days=' + days),
      fetch('/api/stats?days=0'),
    ]);
    const wJson = await wRes.json();
    const workouts = wJson.data || [];
    const metrics = (await mRes.json()).data || [];
    const nutritions = (await nRes.json()).data || [];
    const stats = (await sRes.json()) || {};

    clearPanelError('panel-dashboard');

    renderStatCards(workouts, metrics, nutritions, days, wJson.streak || 0);
    renderAchievements(stats.achievements || []);
    renderExerciseStats(stats.exercises || []);
    renderWeightChart(metrics);
    renderWorkoutChart(workouts, days);
    loadSidebarStats();
    import('./videos.js').then(m => m.loadVideoGrid());

    // V10: What-If 因果洞察
    try { renderWhatIfCard(); } catch(e) { console.error('dashboard: renderWhatIfCard', e); }

    // V11: 浏览器本地计算健康分（Web Worker）
    try {
      const latest = metrics[metrics.length - 1];
      if (latest && (latest.weight_kg || nutritions.length > 0)) {
        computeLocalHealthScore({
          steps: nutritions.length > 0 ? null : null,
          sleep: null,
          heart_rate: null,
          weight: latest.weight_kg || undefined,
        });
      }
    } catch(e) { console.error('dashboard: computeHealthScore', e); }
  } catch (e) {
    console.error('Dashboard load error:', e);
    const cw = document.getElementById('chart-weight');
    const ck = document.getElementById('chart-workout');
    if (cw) setChartEmpty(cw, false);
    if (ck) setChartEmpty(ck, false);
    showPanelError('panel-dashboard', 'dashboard');
  }
}

// ── V11: 使用 Web Worker 本地计算健康分 ──
let _analysisWorker = null;
function getAnalysisWorker() {
  if (!_analysisWorker) {
    _analysisWorker = new Worker('/js/analysis-worker.js');
  }
  return _analysisWorker;
}

async function computeLocalHealthScore(metrics) {
  const worker = getAnalysisWorker();
  return new Promise((resolve) => {
    const id = Date.now();
    worker.onmessage = function handler(e) {
      if (e.data.id === id) {
        worker.removeEventListener('message', handler);
        resolve(e.data.result);
      }
    };
    worker.postMessage({ id, fn: 'computeHealthScore', args: [metrics] });
  });
}

function renderStatCards(workouts, metrics, nutritions, days, streak) {
  const recent = new Date(Date.now() - days * 86400000);
  const wkCount = workouts.filter(w => new Date(w.date) >= recent).length;
  const lastM = metrics[metrics.length - 1];
  const weight = lastM?.weight_kg ? lastM.weight_kg + '' : '--';
  const bf = lastM?.body_fat_pct ? lastM.body_fat_pct + '' : '--';

  animateCounter(document.getElementById('stat-streak'), streak, 600);
  animateCounter(document.getElementById('stat-workouts'), wkCount, 600);
  document.getElementById('stat-weight').textContent = weight;
  document.getElementById('stat-bodyfat').textContent = bf;
}

function renderWeightChart(data) {
  const canvas = document.getElementById('chart-weight');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (weightChart) weightChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('⚖️', '还没有体重记录，记录后这里会出现趋势图', '去记录', 'home'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const labels = data.map(d => d.date);
  const values = data.map(d => d.weight_kg);
  const pointCount = values.length;
  const pointR = adaptivePointRadius(pointCount);

  // Scrollable if >14 points
  const card = canvas.closest('.chart-card');
  if (card && pointCount > 14) {
    card.querySelector('.chart-wrap').classList.add('chart-wrap-scrollable');
    canvas.style.minWidth = chartMinWidth(pointCount) + 'px';
  }

  weightChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '体重 (kg)', data: values,
        borderColor: t.green, backgroundColor: hexToRgba(t.green, 0.08),
        fill: true, tension: 0.35, pointRadius: pointR,
        pointBackgroundColor: t.green, borderWidth: 2,
      }],
    },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 12) } }, y: { beginAtZero: false } },
    }),
  });
}

function renderWorkoutChart(data, days) {
  const canvas = document.getElementById('chart-workout');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (workoutChart) workoutChart.destroy();
  const t = chartTheme();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('🏋️', '近 ' + days + ' 天没有训练记录', '去练一组', 'home'));
    return;
  }
  setChartEmpty(canvas, false);
  const counts = {};
  for (let i = 0; i < days; i++) {
    const d = new Date(Date.now() - (days - 1 - i) * 86400000);
    counts[d.toISOString().slice(0,10)] = 0;
  }
  data.forEach(d => { counts[d.date] = (counts[d.date] || 0) + 1; });
  const labels = Object.keys(counts).sort();
  const values = labels.map(d => counts[d]);
  const pointCount = values.length;

  workoutChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '训练动作数', data: values,
        backgroundColor: hexToRgba(t.green, 0.35), borderColor: t.green,
        borderWidth: 1, borderRadius: 4,
      }],
    },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 12) } }, y: { stepSize: 1, beginAtZero: true } },
    }),
  });
}

function renderAchievements(achievements) {
  const row = document.getElementById('achievements-row');
  if (!row) return;
  row.innerHTML = achievements.map(a =>
    '<div class="achievement-badge ' + (a.earned ? 'earned' : 'locked') + '"><span class="badge-icon">' + a.icon + '</span><span>' + a.name + '</span></div>'
  ).join('');
}

function renderExerciseStats(exercises) {
  const container = document.getElementById('exercise-stats');
  if (!container) return;
  if (!exercises.length) {
    container.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:0 28px">暂无训练数据</div>';
    return;
  }
  container.innerHTML = exercises.map(e =>
    '<div class="exercise-chip"><span class="ex-icon">' + exEmoji(e.exercise_name) + '</span><span>' + e.exercise_name + '</span><span class="ex-count">x' + e.cnt + '</span>' + (e.max_w ? '<span class="ex-max"> max ' + e.max_w + 'kg</span>' : '') + '</div>'
  ).join('');
}

// ── V10: What-If 因果洞察 ──
const _WHATIF_RANGES = {
  sleep: [120, 720, 420, '分钟'], steps: [1000, 30000, 8000, '步'],
  calories: [500, 5000, 2000, '千卡'], heart_rate: [45, 100, 70, 'bpm'],
  weight: [40, 150, 70, 'kg'],
};

async function fetchWhatIf(scenario, resDiv) {
  resDiv.innerHTML = '<div style="color:#8b8b9e;font-size:0.85rem">推演中...</div>';
  try {
    const resp = await fetch('/api/insights/what-if', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, days: 30 }),
    });
    const data = await resp.json();
    if (!data.predictions || data.predictions.length === 0) {
      resDiv.innerHTML = '<div style="color:#8b8b9e;font-size:0.85rem">数据不足，记录更多健康数据后即可推演</div>';
      return;
    }
    resDiv.innerHTML = data.predictions.map(p => {
      const cls = p.change > 0 ? 'pos' : 'neg';
      const sign = p.change > 0 ? '+' : '';
      return '<div class="whatif-result-item"><span>' + p.metric + ' → ' + p.counterfactual + '</span><span><span class="wf-change ' + cls + '">' + sign + p.change + '</span><span class="wf-ci"> [' + p.ci_lower + ', ' + p.ci_upper + ']</span></span></div>';
    }).join('');
  } catch (e) {
    resDiv.innerHTML = '<div style="color:#f87171;font-size:0.85rem">推演出错了，请稍后重试</div>';
  }
}

function renderWhatIfCard() {
  const card = document.getElementById('whatif-card');
  if (!card) return;
  card.style.display = 'block';

  const slider = document.getElementById('whatif-slider');
  const valSpan = document.getElementById('whatif-value');
  const metricSel = document.getElementById('whatif-metric');

  // Scenario B elements
  const sliderB = document.getElementById('whatif-slider-b');
  const valSpanB = document.getElementById('whatif-value-b');
  const metricSelB = document.getElementById('whatif-metric-b');
  const scenarioBRow = document.getElementById('whatif-scenario-b');
  let compareMode = false;

  // Dynamic metric loading from causal graph
  fetch('/api/insights/causal?days=30')
    .then(r => r.json())
    .then(data => {
      if (data.causal_graph) {
        const vars = Object.keys(data.causal_graph);
        const newOpts = vars.map(v => '<option value="' + v + '">' + v + '</option>').join('');
        if (newOpts) { metricSel.innerHTML = newOpts; metricSelB.innerHTML = newOpts; }
      }
    }).catch((err) => { console.error('dashboard: causalGraph fetch', err); });

  function updateSlider(sel, sld, spn) {
    const r = _WHATIF_RANGES[sel.value] || [0, 1000, 100, ''];
    sld.min = r[0]; sld.max = r[1]; sld.value = r[2];
    spn.textContent = r[2] + (r[3] ? r[3] : '');
  }

  metricSel.onchange = () => updateSlider(metricSel, slider, valSpan);
  slider.oninput = () => { valSpan.textContent = slider.value + (_WHATIF_RANGES[metricSel.value] ? _WHATIF_RANGES[metricSel.value][3] : ''); };
  metricSelB.onchange = () => updateSlider(metricSelB, sliderB, valSpanB);
  sliderB.oninput = () => { valSpanB.textContent = sliderB.value + (_WHATIF_RANGES[metricSelB.value] ? _WHATIF_RANGES[metricSelB.value][3] : ''); };
  updateSlider(metricSel, slider, valSpan);
  updateSlider(metricSelB, sliderB, valSpanB);

  // Compare mode toggle
  document.getElementById('whatif-compare-btn').onclick = () => {
    compareMode = !compareMode;
    scenarioBRow.style.display = compareMode ? 'flex' : 'none';
    document.getElementById('whatif-results-b').innerHTML = '';
    document.getElementById('whatif-compare-btn').textContent = compareMode ? '📊 关闭对比' : '📊 对比';
  };

  // Main push-button handler
  document.getElementById('whatif-btn').onclick = async () => {
    const scenario = { [metricSel.value]: parseInt(slider.value) };
    document.getElementById('whatif-results-b').innerHTML = '';
    await fetchWhatIf(scenario, document.getElementById('whatif-results'));
    if (compareMode) {
      const scenarioB = { [metricSelB.value]: parseInt(sliderB.value) };
      await fetchWhatIf(scenarioB, document.getElementById('whatif-results-b'));
    }
  };
}

export { loadSidebarStats };
