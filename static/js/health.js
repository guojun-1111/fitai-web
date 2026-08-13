// ========== Health Dashboard ==========
import { hexToRgba, _groupByDate, _groupByDateAvg, emptyStateHtml, showPanelError, clearPanelError } from './utils.js';
import { triggerAIAnalysis } from './home.js';
import { lttbDownsample, computeMovingAverage, adaptivePointRadius, chartMinWidth, createChartOptions, prepareChartData, chartTheme, setChartEmpty, setChartSkeleton } from './chart-utils.js';

let stepsChart = null, heartRateChart = null, sleepChart = null, caloriesBurnChart = null;
let weightHCChart = null, bodyFatChart = null, trendChart = null;
export let healthDays = 7;

// Detail view state
let healthDetailChart = null;
let healthDetailMetric = null;
let healthDetailDays = 7;

// ===== Init =====
export function initHealth() {
  // Period buttons in health panel
  document.querySelectorAll('#panel-health .period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#panel-health .period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadHealthDashboard(parseInt(btn.dataset.days));
    });
  });

  // Click delegation for health stat cards
  document.addEventListener('click', (e) => {
    if (e.target.closest('.empty-cta')) return; // let nav.js handle empty-state CTA
    const statCard = e.target.closest('.health-stat-clickable');
    const chartCard = e.target.closest('.health-chart-clickable');
    const target = statCard || chartCard;
    if (target && !e.target.closest('canvas')) {
      openHealthDetail(target.dataset.metric, target.dataset.name, target.dataset.icon, target.dataset.color, target.dataset.unit, target.dataset.chartType);
    }
    // Also handle clicks on canvas inside chart cards
    const canvasInChart = e.target.closest('.health-chart-clickable canvas');
    if (canvasInChart) {
      const cc = canvasInChart.closest('.health-chart-clickable');
      openHealthDetail(cc.dataset.metric, cc.dataset.name, cc.dataset.icon, cc.dataset.color, cc.dataset.unit, cc.dataset.chartType);
    }
  });

  // Detail period selector
  document.addEventListener('click', (e) => {
    if (e.target.closest('#detail-period-selector .period-btn')) {
      const btn = e.target.closest('.period-btn');
      document.querySelectorAll('#detail-period-selector .period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      healthDetailDays = parseInt(btn.dataset.days);
      if (healthDetailMetric) loadHealthDetail(healthDetailMetric.metric, healthDetailDays);
    }
  });

  // Sync button
  document.addEventListener('click', (e) => {
    if (e.target.id === 'sync-now-btn') {
      e.target.textContent = '⏳ 同步中...';
      e.target.disabled = true;
      fetch('/api/health/last-sync').then(() => {
        setTimeout(() => { loadHealthDashboard(healthDays); e.target.textContent = '🔄 立即同步'; e.target.disabled = false; }, 5000);
      }).catch(() => { e.target.textContent = '🔄 立即同步'; e.target.disabled = false; });
    }
  });
}

// ===== Main Load =====
export async function loadHealthDashboard(days) {
  healthDays = days;
  ['chart-steps', 'chart-heartrate', 'chart-sleep', 'chart-calories-burn', 'chart-weight-hc', 'chart-bodyfat']
    .forEach(id => setChartSkeleton(document.getElementById(id)));
  try {
    const typeList = 'steps,heart_rate,sleep,calories,weight,body_fat,blood_pressure_sys,blood_glucose';
    const [batchRes, platformsRes, syncRes] = await Promise.all([
      fetch(`/api/dashboard/health-batch?types=${typeList}&days=${days}`),
      fetch('/api/health/platforms'),
      fetch('/api/health/last-sync'),
    ]);
    const batchData = (await batchRes.json()).data || {};
    const platforms = (await platformsRes.json()).platforms || [];
    const syncInfo = (await syncRes.json()).last_sync || {};

    const stepsData = batchData.steps || [];
    const hrData = batchData.heart_rate || [];
    const sleepData = batchData.sleep || [];
    const calData = batchData.calories || [];
    const weightData = batchData.weight || [];
    const bfData = batchData.body_fat || [];
    const bpData = batchData.blood_pressure_sys || [];
    const bgData = batchData.blood_glucose || [];

    clearPanelError('panel-health');

    renderHealthStatCards(stepsData, hrData, sleepData, calData, weightData, bfData, bpData, bgData);
    renderStepsChart(stepsData);
    renderHeartRateChart(hrData);
    renderSleepChart(sleepData);
    renderCaloriesBurnChart(calData);
    renderWeightHCChart(weightData);
    renderBodyFatChart(bfData);
    renderPlatformConnections(platforms);
    renderLastSync(syncInfo);
    loadWeeklyAnalysis();
  } catch (e) {
    console.error('Health dashboard load error:', e);
    ['chart-steps', 'chart-heartrate', 'chart-sleep', 'chart-calories-burn', 'chart-weight-hc', 'chart-bodyfat']
      .forEach(id => { const c = document.getElementById(id); if (c) setChartEmpty(c, false); });
    showPanelError('panel-health', 'health');
  }
}

// ===== Detail View =====
export function openHealthDetail(metric, name, icon, color, unit, chartType) {
  healthDetailMetric = { metric, name, icon, color, unit, chartType };
  healthDetailDays = 7;
  document.getElementById('health-dashboard-content').style.display = 'none';
  const detailEl = document.getElementById('health-detail');
  if (!detailEl) return;
  detailEl.style.display = 'flex';
  detailEl.style.flexDirection = 'column';
  detailEl.style.flex = '1';
  const iconEl = document.getElementById('detail-icon');
  const titleEl = document.getElementById('detail-title');
  if (iconEl) iconEl.textContent = icon;
  if (titleEl) titleEl.textContent = name + '详情';
  const periodBtns = document.querySelectorAll('#detail-period-selector .period-btn');
  periodBtns.forEach(b => b.classList.remove('active'));
  if (periodBtns[0]) periodBtns[0].classList.add('active');
  loadHealthDetail(metric, 7);
}

export function closeHealthDetail() {
  const detailEl = document.getElementById('health-detail');
  if (detailEl) detailEl.style.display = 'none';
  document.getElementById('health-dashboard-content').style.display = '';
  healthDetailMetric = null;
  if (healthDetailChart) { healthDetailChart.destroy(); healthDetailChart = null; }
}

async function loadHealthDetail(metric, days) {
  if (!healthDetailMetric) return;
  try {
    const res = await fetch('/api/dashboard/health?data_type=' + metric + '&days=' + days);
    const data = (await res.json()).data || [];
    const isAvg = metric === 'heart_rate';
    const byDate = isAvg ? _groupByDateAvg(data) : _groupByDate(data);
    const sortedDates = Object.keys(byDate).sort();
    const values = sortedDates.map(d => byDate[d]);
    renderDetailStats(values, healthDetailMetric.unit);
    renderDetailChart(sortedDates, values);
    renderDetailTable(sortedDates, byDate, healthDetailMetric.unit);
  } catch (e) { console.error('Health detail load error:', e); }
}

function renderDetailStats(values, unit) {
  const container = document.getElementById('detail-stats');
  if (!container) return;
  if (!values.length) { container.innerHTML = '<div class="detail-stat-card"><div class="detail-stat-val">--</div></div>'.repeat(4); return; }
  const avg = Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  const max = Math.round(Math.max(...values));
  const min = Math.round(Math.min(...values));
  const total = Math.round(values.reduce((a, b) => a + b, 0));
  container.innerHTML =
    '<div class="detail-stat-card"><div class="detail-stat-label">平均值</div><div class="detail-stat-val">' + avg.toLocaleString() + ' <span style="font-size:14px;color:var(--text3)">' + unit + '</span></div></div>' +
    '<div class="detail-stat-card"><div class="detail-stat-label">最高值</div><div class="detail-stat-val">' + max.toLocaleString() + ' <span style="font-size:14px;color:var(--text3)">' + unit + '</span></div></div>' +
    '<div class="detail-stat-card"><div class="detail-stat-label">最低值</div><div class="detail-stat-val">' + min.toLocaleString() + ' <span style="font-size:14px;color:var(--text3)">' + unit + '</span></div></div>' +
    '<div class="detail-stat-card"><div class="detail-stat-label">总计</div><div class="detail-stat-val">' + total.toLocaleString() + ' <span style="font-size:14px;color:var(--text3)">' + unit + '</span></div></div>';
}

const _METRIC_THEME_KEY = {
  steps: 'blue', heart_rate: 'red', sleep: 'purple', calories: 'orange',
  weight: 'green', body_fat: 'orange', blood_pressure_sys: 'red', blood_glucose: 'purple',
};

function renderDetailChart(labels, values) {
  const canvas = document.getElementById('chart-health-detail');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (healthDetailChart) healthDetailChart.destroy();
  const t = chartTheme();
  const color = t[_METRIC_THEME_KEY[healthDetailMetric.metric]] || healthDetailMetric.color;
  const isLine = healthDetailMetric.chartType === 'line';
  const pointCount = values.length;
  const pointR = isLine ? adaptivePointRadius(pointCount) : 0;

  // LTTB downsampling for large detail datasets
  let chartLabels = labels, chartValues = values;
  if (pointCount > 50) {
    const downsampled = lttbDownsample(values.map((v, i) => ({ x: i, y: v })), 50);
    chartLabels = downsampled.map(p => labels[p.x]);
    chartValues = downsampled.map(p => p.y);
  }

  // Scrollable detail chart
  const wrap = canvas.closest('.detail-chart-wrap');
  if (wrap && pointCount > 14) {
    wrap.style.overflowX = 'auto';
    canvas.style.minWidth = chartMinWidth(pointCount) + 'px';
  } else if (wrap) {
    wrap.style.overflowX = '';
    canvas.style.minWidth = '';
  }

  const datasets = [{
    label: healthDetailMetric.name + ' (' + healthDetailMetric.unit + ')', data: chartValues,
    borderColor: color, backgroundColor: isLine ? hexToRgba(color, 0.08) : hexToRgba(color, 0.35),
    fill: isLine, tension: 0.35, pointRadius: pointR,
    pointBackgroundColor: color, borderWidth: 2, borderRadius: isLine ? 0 : 4,
  }];

  // Moving average for detail chart
  if (pointCount > 7 && isLine) {
    const maValues = computeMovingAverage(chartValues, 7);
    datasets.push({
      label: '7日均线', data: maValues,
      borderColor: hexToRgba(color, 0.5), backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  healthDetailChart = new Chart(ctx, {
    type: isLine ? 'line' : 'bar',
    data: { labels: chartLabels, datasets },
    options: createChartOptions({
      scales: {
        x: { ticks: { maxTicksLimit: Math.min(pointCount, 20) } },
        y: { beginAtZero: !isLine },
      },
    }),
  });
}

function renderDetailTable(dates, byDate, unit) {
  const tbody = document.querySelector('#detail-table tbody');
  if (!tbody) return;
  const reversedDates = [...dates].reverse();
  tbody.innerHTML = reversedDates.map(d =>
    '<tr><td class="table-date">' + d + '</td><td class="table-val">' + byDate[d].toLocaleString() + '</td><td class="table-unit">' + unit + '</td></tr>'
  ).join('');
}

// ===== Chart Renderers =====
function _shouldShowMA() {
  const cb = document.getElementById('ma-toggle');
  return cb ? cb.checked : true;
}

function _makeScrollable(canvas, count) {
  const card = canvas.closest('.chart-card');
  if (!card) return;
  const wrap = card.querySelector('.chart-wrap');
  if (!wrap) return;
  if (count > 14) {
    wrap.classList.add('chart-wrap-scrollable');
    canvas.style.minWidth = chartMinWidth(count) + 'px';
  } else {
    wrap.classList.remove('chart-wrap-scrollable');
    canvas.style.minWidth = '';
  }
}

function renderStepsChart(data) {
  const canvas = document.getElementById('chart-steps');
  if (!canvas) return;
  if (stepsChart) stepsChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('👣', '还没有步数数据，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDate, 50);
  const pointCount = values.length;
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '步数', data: values,
    backgroundColor: hexToRgba(t.blue, 0.35), borderColor: t.blue,
    borderWidth: 1, borderRadius: 4,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues, type: 'line',
      borderColor: t.tick, backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  stepsChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels, datasets },
    options: createChartOptions({
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: true } },
    }),
  });
}

function renderHeartRateChart(data) {
  const canvas = document.getElementById('chart-heartrate');
  if (!canvas) return;
  if (heartRateChart) heartRateChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('❤️', '还没有心率数据，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDateAvg, 50);
  const pointCount = values.length;
  const pointR = adaptivePointRadius(pointCount);
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '心率 (bpm)', data: values,
    borderColor: t.red, backgroundColor: hexToRgba(t.red, 0.08),
    fill: true, tension: 0.35, pointRadius: pointR, pointBackgroundColor: t.red, borderWidth: 2,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues,
      borderColor: hexToRgba(t.red, 0.6), backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  heartRateChart = new Chart(canvas.getContext('2d'), {
    type: 'line', data: { labels, datasets },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: false } },
    }),
  });
}

function renderSleepChart(data) {
  const canvas = document.getElementById('chart-sleep');
  if (!canvas) return;
  if (sleepChart) sleepChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('😴', '还没有睡眠数据，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDate, 50);
  const pointCount = values.length;
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '睡眠 (分钟)', data: values,
    backgroundColor: hexToRgba(t.purple, 0.35), borderColor: t.purple,
    borderWidth: 1, borderRadius: 4,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues, type: 'line',
      borderColor: t.tick, backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  sleepChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels, datasets },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: true } },
    }),
  });
}

function renderCaloriesBurnChart(data) {
  const canvas = document.getElementById('chart-calories-burn');
  if (!canvas) return;
  if (caloriesBurnChart) caloriesBurnChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('🔥', '还没有卡路里数据，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDate, 50);
  const pointCount = values.length;
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '卡路里 (kcal)', data: values,
    backgroundColor: hexToRgba(t.orange, 0.35), borderColor: t.orange,
    borderWidth: 1, borderRadius: 4,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues, type: 'line',
      borderColor: t.tick, backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  caloriesBurnChart = new Chart(canvas.getContext('2d'), {
    type: 'bar', data: { labels, datasets },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: true } },
    }),
  });
}

function renderWeightHCChart(data) {
  const canvas = document.getElementById('chart-weight-hc');
  if (!canvas) return;
  if (weightHCChart) weightHCChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('⚖️', '还没有体重记录，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDateAvg, 50);
  const pointCount = values.length;
  const pointR = adaptivePointRadius(pointCount);
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '体重 (kg)', data: values,
    borderColor: t.green, backgroundColor: hexToRgba(t.green, 0.08),
    fill: true, tension: 0.35, pointRadius: pointR, pointBackgroundColor: t.green, borderWidth: 2,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues,
      borderColor: hexToRgba(t.green, 0.6), backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  weightHCChart = new Chart(canvas.getContext('2d'), {
    type: 'line', data: { labels, datasets },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: false } },
    }),
  });
}

function renderBodyFatChart(data) {
  const canvas = document.getElementById('chart-bodyfat');
  if (!canvas) return;
  if (bodyFatChart) bodyFatChart.destroy();
  if (!data.length) {
    setChartEmpty(canvas, true, emptyStateHtml('📉', '还没有体脂记录，导入后自动展示', '去导入数据', 'settings'));
    return;
  }
  setChartEmpty(canvas, false);
  const t = chartTheme();
  const { labels, values, originalCount } = prepareChartData(data, _groupByDateAvg, 50);
  const pointCount = values.length;
  const pointR = adaptivePointRadius(pointCount);
  const showMA = _shouldShowMA() && pointCount > 7;
  const maValues = showMA ? computeMovingAverage(values, 7) : null;
  _makeScrollable(canvas, pointCount);

  const datasets = [{
    label: '体脂率 (%)', data: values,
    borderColor: t.orange, backgroundColor: hexToRgba(t.orange, 0.08),
    fill: true, tension: 0.35, pointRadius: pointR, pointBackgroundColor: t.orange, borderWidth: 2,
  }];
  if (showMA) {
    datasets.push({
      label: '7日均线', data: maValues,
      borderColor: hexToRgba(t.orange, 0.6), backgroundColor: 'transparent',
      borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0.4, fill: false,
    });
  }

  bodyFatChart = new Chart(canvas.getContext('2d'), {
    type: 'line', data: { labels, datasets },
    options: createChartOptions({
      scales: { x: { ticks: { maxTicksLimit: Math.min(pointCount, 14) } }, y: { beginAtZero: false } },
    }),
  });
}

function renderHealthStatCards(steps, hr, sleep, cal, weight, bf, bp, bg) {
  const allDates = [...new Set([...steps, ...hr, ...sleep, ...cal, ...weight, ...bf, ...bp, ...bg].map(d => d.date))].sort();
  const latestDate = allDates.length ? allDates[allDates.length - 1] : null;

  function latestVal(arr, fn) {
    const filtered = arr.filter(d => d.date === latestDate);
    return filtered.length ? fn(filtered) : 0;
  }

  const latestSteps = latestVal(steps, a => a.reduce((s, d) => s + (d.value || 0), 0));
  const latestAvgHr = latestVal(hr, a => Math.round(a.reduce((s, d) => s + (d.value || 0), 0) / a.length));
  const latestSleep = latestVal(sleep, a => Math.max(...a.map(d => d.value || 0)));
  const latestCal = latestVal(cal, a => a.reduce((s, d) => s + (d.value || 0), 0));
  const latestWeight = latestVal(weight, a => a.reduce((s, d) => s + (d.value || 0), 0) / a.length);
  const latestBf = latestVal(bf, a => a.reduce((s, d) => s + (d.value || 0), 0) / a.length);
  const latestBp = latestVal(bp, a => Math.max(...a.map(d => d.value || 0)));
  const latestBg = latestVal(bg, a => a.reduce((s, d) => s + (d.value || 0), 0) / a.length);

  const showSteps = latestSteps || (steps.length ? steps[steps.length-1].value : 0);
  const showHr = latestAvgHr || (hr.length ? Math.round(hr[hr.length-1].value) : 0);
  const showSleep = latestSleep || (sleep.length ? Math.round(sleep[sleep.length-1].value) : 0);
  const showCal = latestCal || (cal.length ? Math.round(cal[cal.length-1].value) : 0);
  const showWeight = latestWeight || (weight.length ? weight[weight.length-1].value : 0);
  const showBf = latestBf || (bf.length ? bf[bf.length-1].value : 0);
  const showBp = latestBp || (bp.length ? Math.round(bp[bp.length-1].value) : 0);
  const showBg = latestBg || (bg.length ? Math.round(bg[bg.length-1].value * 10) / 10 : 0);

  document.getElementById('stat-steps').textContent = showSteps > 0 ? showSteps.toLocaleString() : '--';
  document.getElementById('stat-hr').textContent = latestAvgHr > 0 ? latestAvgHr + ' bpm' : '--';
  document.getElementById('stat-sleep').textContent = showSleep > 0 ? Math.round(showSleep) + ' min' : '--';
  document.getElementById('stat-calories').textContent = showCal > 0 ? Math.round(showCal) + ' kcal' : '--';

  const elW = document.getElementById('stat-weight-hc'); if (elW) elW.textContent = showWeight > 0 ? showWeight.toLocaleString() + ' kg' : '--';
  const elBf = document.getElementById('stat-bodyfat-hc'); if (elBf) elBf.textContent = showBf > 0 ? Math.round(showBf * 10) / 10 + '%' : '--';
  const elBp = document.getElementById('stat-bp'); if (elBp) elBp.textContent = showBp > 0 ? Math.round(showBp) + ' mmHg' : '--';
  const elBg = document.getElementById('stat-glucose'); if (elBg) elBg.textContent = showBg > 0 ? showBg + ' mmol/L' : '--';

  const dateLabel = latestDate || '--';
  const labels = document.querySelectorAll('#health-stat-grid .stat-card-label');
  if (labels.length >= 4) {
    labels[0].textContent = '最新步数 (' + dateLabel + ')';
    labels[1].textContent = '平均心率 (' + dateLabel + ')';
    labels[2].textContent = '睡眠时长 (' + dateLabel + ')';
    labels[3].textContent = '消耗卡路里 (' + dateLabel + ')';
  }
}

// ===== Weekly Analysis =====
async function loadWeeklyAnalysis() {
  try {
    const [stepsW, hrW, sleepW, calW] = await Promise.all([
      fetch('/api/health/weekly?data_type=steps&weeks=12').then(r => r.json()),
      fetch('/api/health/weekly?data_type=heart_rate&weeks=12').then(r => r.json()),
      fetch('/api/health/weekly?data_type=sleep&weeks=12').then(r => r.json()),
      fetch('/api/health/weekly?data_type=calories&weeks=12').then(r => r.json()),
    ]);
    renderTrendChart(stepsW, hrW, sleepW);
    renderSummary(stepsW, hrW, sleepW, calW);
  } catch (e) { console.error('Weekly analysis error:', e); }
}

function renderTrendChart(stepsD, hrD, sleepD) {
  const canvas = document.getElementById('chart-trend');
  if (!canvas) return;
  if (trendChart) trendChart.destroy();
  const t = chartTheme();
  const weeks = (stepsD.weeks || []).map(w => w.week);
  trendChart = new Chart(canvas.getContext('2d'), {
    type: 'line', data: { labels: weeks, datasets: [
      { label: '步数(千)', data: (stepsD.weeks||[]).map(w => Math.round(w.avg/100)/10), borderColor: t.blue, backgroundColor: hexToRgba(t.blue, 0.05), fill: false, tension: 0.3, pointRadius: 4, pointBackgroundColor: t.blue, borderWidth: 2, yAxisID: 'y' },
      { label: '心率', data: (hrD.weeks||[]).map(w => Math.round(w.avg)), borderColor: t.red, backgroundColor: hexToRgba(t.red, 0.05), fill: false, tension: 0.3, pointRadius: 4, pointBackgroundColor: t.red, borderWidth: 2, yAxisID: 'y1' },
    ]},
    options: createChartOptions({
      plugins: { legend: { labels: { color: t.tick, font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: t.tick, maxTicksLimit: 8, font: { size: 10 } } },
        y: { type: 'linear', position: 'left', ticks: { color: t.blue, font: { size: 10 }, callback: v => v + 'k' } },
        y1: { type: 'linear', position: 'right', ticks: { color: t.red, font: { size: 10 }, callback: v => v + ' bpm' }, grid: { display: false } },
      },
    }),
  });
}

function renderSummary(stepsD, hrD, sleepD, calD) {
  const trendIcon = (d) => { if (!d.trend) return '—'; return d.trend.direction === 'up' ? '↑' + d.trend.pct + '%' : '↓' + d.trend.pct + '%'; };
  const trendColor = (d) => { if (!d.trend) return 'var(--text2)'; if (d.data_type === 'heart_rate') return d.trend.direction === 'up' ? 'var(--red)' : 'var(--green)'; return d.trend.direction === 'up' ? 'var(--green)' : 'var(--red)'; };
  const wSteps = (stepsD.weeks || []).slice(-1)[0];
  const wHr = (hrD.weeks || []).slice(-1)[0];
  const wSleep = (sleepD.weeks || []).slice(-1)[0];
  const elSteps = document.getElementById('sum-avg-steps'); if (elSteps) elSteps.textContent = wSteps ? Math.round(wSteps.avg).toLocaleString() + ' 步' : '--';
  const elHr = document.getElementById('sum-avg-hr'); if (elHr) elHr.textContent = wHr ? Math.round(wHr.avg) + ' bpm' : '--';
  const elSleep = document.getElementById('sum-avg-sleep'); if (elSleep) elSleep.textContent = wSleep ? Math.round(wSleep.avg) + ' 分' : '--';
  const elTrendSteps = document.getElementById('sum-trend-steps'); if (elTrendSteps) elTrendSteps.innerHTML = '<span style="color:' + trendColor(stepsD) + '">' + trendIcon(stepsD) + '</span>';
  const elTrendHr = document.getElementById('sum-trend-hr'); if (elTrendHr) elTrendHr.innerHTML = '<span style="color:' + trendColor(hrD) + '">' + trendIcon(hrD) + '</span>';
}

function renderPlatformConnections(platforms) {
  const container = document.getElementById('platform-connections');
  if (!container) return;
  if (!platforms.length) { container.innerHTML = '<div class="empty-state" style="padding:10px"><p style="font-size:12px">暂无已配置的平台。请在设置中连接设备。</p></div>'; return; }
  container.innerHTML = platforms.map(p => '<div class="platform-chip ' + (p.connected ? 'connected' : 'disconnected') + '"><span>' + (p.connected ? '✅' : '⬜') + '</span><span>' + p.display_name + '</span><span style="font-size:11px;color:var(--text3)">' + p.device_list + '</span></div>').join('');
}

function renderLastSync(syncInfo) {
  const el = document.getElementById('last-sync-text');
  if (!el) return;
  const times = Object.values(syncInfo).map(s => s.finished_at).filter(Boolean).sort().reverse();
  el.textContent = times.length ? '最后同步: ' + times[0].replace('T', ' ').slice(0, 16) : '最后同步: --';
}
