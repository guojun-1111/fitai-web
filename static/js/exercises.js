// ========== Exercise Analysis ==========
import { escapeHtml, exEmoji, hexToRgba, showPanelError, clearPanelError } from './utils.js';
import { createChartOptions, chartTheme } from './chart-utils.js';

let exFreqChart = null, exMonthlyChart = null, exCalChart = null, exPieChart = null;
let exTypeChart = null;

function _palette(t) {
  return [t.blue, t.green, t.orange, t.red, t.purple, '#e879f9', '#4dabf7', '#38d9a9'];
}

export async function loadExerciseAnalysis() {
  try {
    const res = await fetch('/api/exercises/analysis');
    const data = await res.json();
    document.getElementById('ex-total-workouts').textContent = data.total_workouts || 0;
    document.getElementById('ex-total-minutes').textContent = (data.total_exercise_minutes || 0).toLocaleString();
    const calTotal = data.calories_by_month.reduce((s, m) => s + m.calories, 0);
    document.getElementById('ex-total-calories').textContent = calTotal > 0 ? calTotal.toLocaleString() + ' 千卡' : '--';
    document.getElementById('ex-type-count').textContent = data.frequency.length;
    renderExFreqChart(data.frequency);
    renderExMonthlyChart(data.monthly_trend);
    renderExCalChart(data.calories_by_month);
    renderExPieChart(data.frequency);
    renderExTypeList(data.frequency);
    clearPanelError('panel-exercises');
  } catch (e) {
    console.error('Exercise analysis load error:', e);
    showPanelError('panel-exercises', 'exercises');
  }
}

function renderExFreqChart(freq) {
  const canvas = document.getElementById('chart-exercise-freq');
  if (!canvas || !freq.length) return;
  if (exFreqChart) exFreqChart.destroy();
  const colors = _palette(chartTheme());
  exFreqChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels: freq.map(f => f.name), datasets: [{ label: '次数', data: freq.map(f => f.count), backgroundColor: freq.map((_, i) => colors[i%8]), borderWidth: 1, borderRadius: 4 }] },
    options: createChartOptions({ indexAxis: 'y', scales: { x: { stepSize: 1 }, y: {} } }),
  });
}

function renderExMonthlyChart(monthly) {
  const canvas = document.getElementById('chart-exercise-monthly');
  if (!canvas || !monthly.length) return;
  if (exMonthlyChart) exMonthlyChart.destroy();
  const t = chartTheme();
  const pointR = monthly.length <= 12 ? 4 : 2;
  exMonthlyChart = new Chart(canvas.getContext('2d'), {
    type: 'line', data: { labels: monthly.map(m => m.month), datasets: [
      { label: '运动次数', data: monthly.map(m => m.count), borderColor: t.green, backgroundColor: hexToRgba(t.green, 0.08), fill: true, tension: 0.35, pointRadius: pointR, pointBackgroundColor: t.green, borderWidth: 2, yAxisID: 'y' },
      { label: '运动时长(分钟)', data: monthly.map(m => m.total_minutes), borderColor: t.blue, backgroundColor: hexToRgba(t.blue, 0.05), fill: false, tension: 0.35, pointRadius: pointR, pointBackgroundColor: t.blue, borderWidth: 2, yAxisID: 'y1' },
    ]},
    options: createChartOptions({
      plugins: { legend: { display: true, labels: { color: t.tick, font: { size: 10 } } } },
      scales: { x: { maxTicksLimit: 12 }, y: { type: 'linear', position: 'left', ticks: { color: t.green } }, y1: { type: 'linear', position: 'right', ticks: { color: t.blue }, grid: { display: false } } },
    }),
  });
}

function renderExCalChart(calByMonth) {
  const canvas = document.getElementById('chart-exercise-calories');
  if (!canvas || !calByMonth.length) return;
  if (exCalChart) exCalChart.destroy();
  const t = chartTheme();
  exCalChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels: calByMonth.map(c => c.month), datasets: [{ label: '千卡', data: calByMonth.map(c => c.calories), backgroundColor: hexToRgba(t.orange, 0.35), borderColor: t.orange, borderWidth: 1, borderRadius: 4 }] },
    options: createChartOptions({ scales: { x: { maxTicksLimit: 12 }, y: { beginAtZero: true } } }),
  });
}

function renderExPieChart(freq) {
  const canvas = document.getElementById('chart-exercise-pie');
  if (!canvas || !freq.length) return;
  if (exPieChart) exPieChart.destroy();
  const t = chartTheme();
  const colors = _palette(t);
  exPieChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut', data: { labels: freq.map(f => f.name), datasets: [{ data: freq.map(f => f.count), backgroundColor: freq.map((_, i) => colors[i % colors.length]), borderColor: t.surface, borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: t.tick, font: { size: 11 }, padding: 12 } } } },
  });
}

function renderExTypeList(freq) {
  const container = document.getElementById('ex-type-list');
  if (!container) return;
  if (!freq.length) { container.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:0 28px">暂无运动记录，请导入数据或开始记录</div>'; return; }
  const maxCount = freq[0].count;
  container.innerHTML = freq.map(f =>
    '<div class="ex-type-row" data-exname="' + escapeHtml(f.name) + '" onclick="openExDetail(\'' + escapeHtml(f.name).replace(/'/g, "\\'") + '\')" title="点击查看' + escapeHtml(f.name) + '详情">' +
    '<span class="ex-type-name">' + exEmoji(f.name) + ' ' + escapeHtml(f.name) + '</span>' +
    '<span class="ex-type-bar-wrap"><span class="ex-type-bar" style="width:' + (f.count/maxCount*100) + '%"></span></span>' +
    '<span class="ex-type-stats">' + f.count + '次 · ' + Math.round(f.total_minutes) + '分钟 · ' + f.days + '天</span>' +
    '<span class="ex-type-arrow">→</span></div>'
  ).join('');
}

export async function openExDetail(name) {
  const list = document.getElementById('ex-type-list');
  const detail = document.getElementById('ex-detail');
  const title = document.getElementById('ex-detail-title');
  if (!detail || !title) return;
  if (list) list.style.display = 'none';
  detail.style.display = 'block';
  title.textContent = exEmoji(name) + ' ' + name;

  try {
    const res = await fetch('/api/exercises/type/' + encodeURIComponent(name));
    const data = await res.json();
    const summary = document.getElementById('ex-detail-summary');
    if (summary) summary.innerHTML =
      '<div class="stat-card"><div class="stat-card-icon">🔢</div><div class="stat-card-info"><div class="stat-card-val">' + data.total_count + '</div><div class="stat-card-label">总次数</div></div></div>' +
      '<div class="stat-card"><div class="stat-card-icon">📅</div><div class="stat-card-info"><div class="stat-card-val">' + data.days + '</div><div class="stat-card-label">训练天数</div></div></div>' +
      '<div class="stat-card"><div class="stat-card-icon">⏱️</div><div class="stat-card-info"><div class="stat-card-val">' + data.total_minutes + '</div><div class="stat-card-label">总时长 (分钟)</div></div></div>' +
      (data.max_weight ? '<div class="stat-card"><div class="stat-card-icon">🏋️</div><div class="stat-card-info"><div class="stat-card-val">' + data.max_weight + 'kg</div><div class="stat-card-label">最大重量</div></div></div>' : '') +
      (data.total_volume ? '<div class="stat-card"><div class="stat-card-icon">📊</div><div class="stat-card-info"><div class="stat-card-val">' + data.total_volume.toLocaleString() + '</div><div class="stat-card-label">总容量 (组×次)</div></div></div>' : '');
    renderExTypeTrend(data.monthly_trend || []);
    const tbody = document.querySelector('#ex-history-table tbody');
    if (tbody) {
      if (data.history && data.history.length) {
        tbody.innerHTML = data.history.map(r => '<tr><td>' + r.date + '</td><td>' + (r.sets||'-') + '</td><td>' + (r.reps||'-') + '</td><td>' + (r.weight_kg?r.weight_kg+'kg':'-') + '</td><td>' + (r.duration_minutes?r.duration_minutes+'分钟':'-') + '</td><td>' + (r.notes||'') + '</td></tr>').join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text3);text-align:center;padding:20px">暂无详细记录</td></tr>';
      }
    }
  } catch (e) { console.error('load exercise detail error:', e); }
}

export function closeExDetail() {
  const list = document.getElementById('ex-type-list');
  const detail = document.getElementById('ex-detail');
  if (list) list.style.display = 'block';
  if (detail) detail.style.display = 'none';
  if (exTypeChart) { exTypeChart.destroy(); exTypeChart = null; }
}

function renderExTypeTrend(monthly) {
  const canvas = document.getElementById('chart-ex-type-trend');
  if (!canvas || !monthly.length) return;
  if (exTypeChart) exTypeChart.destroy();
  const t = chartTheme();
  exTypeChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels: monthly.map(m => m.month), datasets: [
      { label: '训练次数', data: monthly.map(m => m.cnt), backgroundColor: t.blue, borderRadius: 4, yAxisID: 'y' },
      { label: '总时长(分钟)', data: monthly.map(m => m.total_min), type: 'line', borderColor: t.green, backgroundColor: hexToRgba(t.green, 0.05), fill: true, tension: 0.35, pointRadius: 3, pointBackgroundColor: t.green, yAxisID: 'y1' },
    ]},
    options: createChartOptions({
      plugins: { legend: { display: true, labels: { color: t.tick, font: { size: 10 } } } },
      scales: { x: {}, y: { type: 'linear', position: 'left', ticks: { color: t.blue, stepSize: 1 } }, y1: { type: 'linear', position: 'right', ticks: { color: t.green }, grid: { display: false } } },
    }),
  });
}

// Export for HTML onclick
window.openExDetail = openExDetail;
window.closeExDetail = closeExDetail;
