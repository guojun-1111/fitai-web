// V11.0: FitAI 浏览器端分析引擎（Web Worker）
// 将最常用的 5 个分析函数从服务器 Python 搬到浏览器 JS
// 与 fitai/analysis/trends.py 保持数值一致性
'use strict';

// ── 消息路由 ──
self.onmessage = function(e) {
  const { id, fn, args } = e.data;
  let result;
  try {
    switch (fn) {
      case 'detectTrend':       result = detectTrend(args[0]); break;
      case 'computeHealthScore': result = computeHealthScore(args[0]); break;
      case 'detectAnomalies':    result = detectAnomalies(args[0], args[1]); break;
      case 'ewmaSmooth':        result = ewmaSmooth(args[0], args[1]); break;
      case 'pearsonCorrelation': result = pearsonCorrelation(args[0], args[1]); break;
      case 'batchAnalyze':      result = batchAnalyze(args[0]); break;
      default: result = { error: 'Unknown function: ' + fn };
    }
  } catch (err) {
    result = { error: err.message };
  }
  self.postMessage({ id, result });
};

// ── 工具函数 ──
function mean(arr) {
  let s = 0; for (let i = 0; i < arr.length; i++) s += arr[i];
  return s / arr.length;
}

function variance(arr, m) {
  if (m === undefined) m = mean(arr);
  let s = 0; for (let i = 0; i < arr.length; i++) s += (arr[i] - m) * (arr[i] - m);
  return s / arr.length; // population std (matches Python)
}

// ── 1. 趋势检测（对照 trends.py:detect_trend）──
function detectTrend(values) {
  const n = values.length;
  if (n < 3) return { direction: 'stable', slope_per_day: 0, percent_change_per_week: 0, confidence: 0 };

  const mx = mean(values.map((_, i) => i));
  const my = mean(values);

  let num = 0, den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - mx) * (values[i] - my);
    den += (i - mx) * (i - mx);
  }
  const slope = den === 0 ? 0 : num / den;

  // R-squared
  let ssRes = 0, ssTot = 0;
  for (let i = 0; i < n; i++) {
    const yp = my + slope * (i - mx);
    ssRes += (values[i] - yp) * (values[i] - yp);
    ssTot += (values[i] - my) * (values[i] - my);
  }
  const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;
  const mval = my !== 0 ? my : 1;
  const pctPerWeek = (slope * 7 / mval) * 100;

  let direction = 'stable';
  if (Math.abs(pctPerWeek) >= 0.5) {
    direction = pctPerWeek > 0 ? 'improving' : 'declining';
  }
  return {
    direction, slope_per_day: Math.round(slope * 10000) / 10000,
    percent_change_per_week: Math.round(pctPerWeek * 100) / 100,
    confidence: Math.round(Math.max(0, Math.min(1, r2)) * 1000) / 1000,
  };
}

// ── 2. 单日健康分（对照 trends.py:_score_day）──
function scoreDay(metrics) {
  let score = 50;
  if (metrics.steps != null)   score += Math.min(metrics.steps / 10000 * 20, 25) - 10;
  if (metrics.sleep != null)   score += Math.min(metrics.sleep / 480 * 25, 30) - 12.5;
  if (metrics.calories != null) score += Math.min(metrics.calories / 500 * 15, 20) - 7.5;
  if (metrics.heart_rate != null) {
    const hr = metrics.heart_rate;
    score += (hr >= 55 && hr <= 75) ? 5 : (hr < 55 || hr > 85) ? -8 : 0;
  }
  if (metrics.weight != null && metrics.weight_prev != null) {
    score += metrics.weight <= metrics.weight_prev ? 5 : -3;
  }
  return Math.max(0, Math.min(100, score));
}

// ── 3. 综合健康分（对照 trends.py:compute_health_score）──
function computeHealthScore(metrics) {
  const raw = scoreDay(metrics);
  const score = Math.round(raw);
  let level = '需关注';
  if (score >= 80) level = '优秀';
  else if (score >= 65) level = '良好';
  else if (score >= 45) level = '一般';
  const details = [];
  if (metrics.steps != null)   details.push('步数 ' + metrics.steps + '步');
  if (metrics.sleep != null)   details.push('睡眠 ' + metrics.sleep + '分钟');
  if (metrics.heart_rate != null) details.push('心率 ' + metrics.heart_rate + 'bpm');
  return { score, level, details: details.join('; ') };
}

// ── 4. 异常检测（对照 trends.py:detect_anomalies）──
function detectAnomalies(values, dates, threshold) {
  if (threshold === undefined) threshold = 2.5;
  const n = values.length;
  if (n < 4) return [];
  const m = mean(values);
  const v = variance(values, m);
  const std = v > 0 ? Math.sqrt(v) : 1;
  const anomalies = [];
  for (let i = 0; i < n; i++) {
    const z = (values[i] - m) / (std || 1);
    if (Math.abs(z) > threshold) {
      anomalies.push({
        index: i,
        date: dates ? dates[i] : String(i),
        value: values[i],
        z_score: Math.round(z * 100) / 100,
        deviation: Math.round((values[i] - m) * 10) / 10,
        severity: Math.abs(z) > 3 ? 'high' : 'medium',
      });
    }
  }
  return anomalies;
}

// ── 5. EWMA 平滑 ──
function ewmaSmooth(values, span) {
  if (span === undefined) span = 7;
  const alpha = 2 / (span + 1);
  const out = [];
  let s = values[0] || 0;
  for (let i = 0; i < values.length; i++) {
    s = alpha * values[i] + (1 - alpha) * s;
    out.push(Math.round(s * 100) / 100);
  }
  return out;
}

// ── 6. Pearson 相关（对照 trends.py:compute_correlation）──
function pearsonCorrelation(x, y) {
  const n = x.length;
  if (n < 3 || y.length !== n) return { coefficient: 0, interpretation: 'insufficient data' };
  const mx = mean(x), my = mean(y);
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    const xd = x[i] - mx, yd = y[i] - my;
    num += xd * yd; dx += xd * xd; dy += yd * yd;
  }
  const den = Math.sqrt(dx) * Math.sqrt(dy);
  let r = den === 0 ? 0 : num / den;
  r = Math.max(-1, Math.min(1, r));
  const absR = Math.abs(r);
  let interp = '极弱相关';
  if (absR >= 0.8) interp = '强相关';
  else if (absR >= 0.6) interp = '中等相关';
  else if (absR >= 0.4) interp = '弱相关';
  return { coefficient: Math.round(r * 1000) / 1000, interpretation: interp };
}

// ── 7. 批量分析（一次计算全部）──
function batchAnalyze(healthData) {
  // healthData: [{date, steps, sleep, heart_rate, calories, weight, ...}, ...]
  const dates = healthData.map(d => d.date);
  const steps = healthData.map(d => d.steps || 0);
  const sleep = healthData.map(d => d.sleep || 0);
  const hr = healthData.map(d => d.heart_rate || 0).filter(v => v > 0);

  const latest = healthData[healthData.length - 1] || {};
  const healthScore = computeHealthScore({
    steps: latest.steps, sleep: latest.sleep,
    heart_rate: latest.heart_rate, calories: latest.calories,
    weight: latest.weight,
  });

  const stepsTrend = steps.length >= 3 ? detectTrend(steps) : null;
  const sleepTrend = sleep.length >= 3 ? detectTrend(sleep) : null;

  const anomalies = detectAnomalies(steps, dates);

  return { healthScore, stepsTrend, sleepTrend, anomalies, nDays: healthData.length };
}
