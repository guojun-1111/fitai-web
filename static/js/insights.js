// ========== Insights Panel — V15 ==========
// Causal graph, interventions, changepoints, predictions

import { chartTheme } from './chart-utils.js';

export async function loadInsights() {
  loadCausalGraph();
  loadInterventions();
  loadChangepoints();
  loadPredictions();
}

async function loadCausalGraph() {
  const el = document.getElementById('insights-causal-graph');
  if (!el) return;
  el.innerHTML = '<span style="color:var(--text3)">分析中...</span>';
  try {
    const res = await fetch('/api/insights/causal?days=30');
    const data = await res.json();
    if (!data.causal_graph || Object.keys(data.causal_graph).length === 0) {
      el.innerHTML = '<span style="color:var(--text3)">数据不足（需要至少 14 天数据），继续记录后因果图会自动出现</span>';
      return;
    }
    const vars = Object.keys(data.causal_graph);
    const edges = [];
    for (const v of vars) {
      for (const target of (data.causal_graph[v] || [])) {
        edges.push({ from: v, to: target });
      }
    }
    // Simple text-based causal graph with colored nodes
    const t = chartTheme();
    const nodeSet = new Set();
    edges.forEach(function(e) { nodeSet.add(e.from); nodeSet.add(e.to); });
    const nodes = Array.from(nodeSet);
    const colors = [t.blue, t.green, t.orange, t.red, t.purple, '#e879f9'];
    const nodeHtml = nodes.map(function(n, i) {
      return '<span style="display:inline-block;padding:4px 10px;margin:4px;border-radius:6px;background:' + colors[i % colors.length] + '20;border:1px solid ' + colors[i % colors.length] + ';color:' + colors[i % colors.length] + ';font-size:12px">' + n + '</span>';
    }).join(' ');

    const edgeHtml = edges.map(function(e) {
      return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin:4px 0">' +
        '<span style="color:' + t.blue + '">' + e.from + '</span>' +
        '<span style="color:' + t.tick + '">→</span>' +
        '<span style="color:' + t.green + '">' + e.to + '</span>' +
        '</div>';
    }).join('');

    el.innerHTML =
      '<div style="margin-bottom:10px;font-size:12px;color:var(--text2)">发现 <b>' + edges.length + '</b> 条因果关系（' + data.n_days + ' 天数据）</div>' +
      '<div style="margin-bottom:12px">' + nodeHtml + '</div>' +
      '<div style="max-height:180px;overflow-y:auto">' + edgeHtml + '</div>';

    // Show significant effects if any
    if (data.n_significant > 0 && data.causal_effects) {
      const sigEffects = data.causal_effects.filter(function(e) { return e.significant; });
      if (sigEffects.length > 0) {
        const topEffects = sigEffects.slice(0, 3).map(function(e) {
          var dir = e.effect_size > 0 ? '↑' : '↓';
          return '<div style="font-size:11px;margin:2px 0;color:var(--text2)">' + dir + ' ' + e.cause + '→' + e.effect + ': ' + (e.interpretation || '') + '</div>';
        }).join('');
        el.innerHTML += '<div style="margin-top:8px;padding:8px;background:rgba(61,214,140,0.06);border-radius:8px;border:1px solid rgba(61,214,140,0.15)">' +
          '<div style="font-size:12px;color:var(--green);margin-bottom:4px">显著因果效应</div>' + topEffects + '</div>';
      }
    }
  } catch(e) {
    el.innerHTML = '<span style="color:var(--text3)">加载失败，请稍后重试</span>';
  }
}

async function loadInterventions() {
  const el = document.getElementById('insights-interventions');
  if (!el) return;
  el.innerHTML = '<span style="color:var(--text3)">计算中...</span>';
  try {
    // Try multiple target metrics
    var targets = ['sleep', 'steps', 'heart_rate'];
    var allResults = [];
    for (var t = 0; t < targets.length; t++) {
      try {
        var res = await fetch('/api/insights/best-intervention', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: targets[t], days: 30 }),
        });
        var data = await res.json();
        if (data.interventions && data.interventions.length > 0) {
          allResults.push({ target: targets[t], interventions: data.interventions });
        }
      } catch(e) { console.error('insights: loadInterventions target=' + targets[t], e); }
    }

    if (allResults.length === 0) {
      el.innerHTML = '<span style="color:var(--text3)">数据不足，继续记录更多数据后即可获得干预建议</span>';
      return;
    }

    var html = '';
    for (var r = 0; r < allResults.length; r++) {
      var result = allResults[r];
      html += '<div style="font-size:12px;color:var(--green);margin-bottom:6px">🎯 ' + result.target + '</div>';
      for (var i = 0; i < Math.min(result.interventions.length, 2); i++) {
        var inv = result.interventions[i];
        var color = (inv.expected_change || 0) > 0 ? 'var(--green)' : 'var(--red)';
        html += '<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid #1e1e28">' +
          '<span>' + inv.intervention + '</span>' +
          '<span style="color:' + color + '">' + (inv.expected_change > 0 ? '+' : '') + (inv.expected_change || 0) + '</span>' +
          '</div>';
      }
    }
    el.innerHTML = html || '<span style="color:var(--text3)">暂无推荐</span>';
  } catch(e) {
    el.innerHTML = '<span style="color:var(--text3)">加载失败</span>';
  }
}

async function loadChangepoints() {
  var el = document.getElementById('insights-changepoints');
  if (!el) return;
  el.innerHTML = '<span style="color:var(--text3)">检测中...</span>';
  try {
    var res = await fetch('/api/insights/changepoints?days=60');
    var data = await res.json();
    if (!data.changepoints || data.changepoints.length === 0) {
      el.innerHTML = '<span style="color:var(--text3)">未检测到显著生理变化，数据稳定</span>';
      return;
    }
    var html = data.changepoints.map(function(cp) {
      var icon = cp.type === 'overtraining_onset' ? '⚠️' : '💪';
      return '<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid #1e1e28;font-size:12px">' +
        '<span style="font-size:16px">' + icon + '</span>' +
        '<div><div style="color:var(--text)">' + (cp.message || cp.date || '检测到变化') + '</div>' +
        '<div style="color:var(--text3);font-size:11px">' + (cp.date || '') + '</div></div></div>';
    }).join('');
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<span style="color:var(--text3)">加载失败</span>';
  }
}

async function loadPredictions() {
  var el = document.getElementById('insights-predictions');
  if (!el) return;
  el.innerHTML = '<span style="color:var(--text3)">预测中...</span>';
  try {
    var res = await fetch('/api/insights/predictions?metric=steps&days_ahead=7');
    var data = await res.json();
    if (!data.predictions || data.predictions.length === 0) {
      el.innerHTML = '<span style="color:var(--text3)">数据不足（需要至少 14 天）</span>';
      return;
    }
    var direction = data.trend_direction === 'up' ? '↑ 上升' : '↓ 下降';
    var html = '<div style="font-size:12px;color:var(--text2);margin-bottom:8px">未来7天步数预测：<b style="color:' + (data.trend_direction === 'up' ? 'var(--green)' : 'var(--red)') + '">' + direction + '</b></div>';
    for (var i = 0; i < data.predictions.length; i++) {
      var p = data.predictions[i];
      html += '<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid #1e1e28">' +
        '<span>' + p.date + '</span>' +
        '<span>' + p.predicted.toLocaleString() + ' <span style="font-size:10px;color:var(--text3)">[' + p.ci_lower.toLocaleString() + '-' + p.ci_upper.toLocaleString() + ']</span></span>' +
        '</div>';
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<span style="color:var(--text3)">加载失败</span>';
  }
}
