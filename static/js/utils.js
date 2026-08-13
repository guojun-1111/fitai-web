// ========== Utility Functions ==========

export function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Unified empty-state block. gotoPanel: nav panel name the CTA jumps to (via nav-btn click).
export function emptyStateHtml(icon, text, ctaLabel, gotoPanel, compact) {
  return '<div class="empty-state' + (compact ? ' compact' : '') + '"><div class="empty-icon">' + icon + '</div>' +
    '<div class="empty-text">' + text + '</div>' +
    (ctaLabel ? '<button class="empty-cta" data-goto="' + gotoPanel + '">' + ctaLabel + '</button>' : '') +
    '</div>';
}

// Error variant: retry re-triggers the panel's nav button (which re-runs its loader).
export function errorStateHtml(panel) {
  return '<div class="empty-state"><div class="empty-icon">⚠️</div>' +
    '<div class="empty-text">加载失败，请检查网络后重试</div>' +
    '<button class="empty-cta" data-goto="' + panel + '">点击重试</button></div>';
}

// Prepend a retryable error block to a panel; keeps existing DOM (canvases) intact for retry.
// On next successful load the caller should remove '.panel-error'.
export function showPanelError(panelId, panelName) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  let err = panel.querySelector('.panel-error');
  if (!err) {
    err = document.createElement('div');
    err.className = 'panel-error';
    panel.prepend(err);
  }
  err.innerHTML = errorStateHtml(panelName);
}

export function clearPanelError(panelId) {
  const panel = document.getElementById(panelId);
  const err = panel && panel.querySelector('.panel-error');
  if (err) err.remove();
}

// Exercise emoji map
const EXERCISE_EMOJI = {
  '卧推': '🏋️', '深蹲': '🦵', '硬拉': '💪', '弯举': '💪', '哑铃': '🏋️',
  '引体向上': '🔝', '俯卧撑': '🤸', '跑步': '🏃', '游泳': '🏊', '划船': '🚣',
  '推举': '⬆️', '飞鸟': '🕊️', '腹肌': '🔄', '平板支撑': '⏱️', '卷腹': '🔄',
  '弓步': '🚶', '臀推': '🍑', '面拉': '🔙', '侧平举': '🤷',
  '屈臂弯举': '💪', '哑铃屈臂弯举': '💪', '双手哑铃屈臂弯举': '💪',
};

export function exEmoji(name) {
  for (const [k, v] of Object.entries(EXERCISE_EMOJI)) {
    if (name.includes(k)) return v;
  }
  return '🏋️';
}

export function animateCounter(element, targetValue, duration, formatter) {
  duration = duration || 800;
  formatter = formatter || function(v) { return Math.round(v).toLocaleString(); };
  const startValue = 0;
  let startTime = null;

  function step(timestamp) {
    if (!startTime) startTime = timestamp;
    const elapsed = timestamp - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = startValue + (targetValue - startValue) * eased;
    element.textContent = formatter(current);
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }
  requestAnimationFrame(step);
}

export function triggerConfetti() {
  const colors = ['#3dd68c', '#5e9eff', '#f59e4b', '#f87171', '#8a2be2', '#e879f9'];
  for (let i = 0; i < 30; i++) {
    const particle = document.createElement('div');
    particle.style.cssText =
      'position:fixed;width:8px;height:8px;background:' + colors[Math.floor(Math.random()*colors.length)] +
      ';border-radius:2px;pointer-events:none;z-index:9999;left:' + (Math.random()*80+10) + '%;top:' + (Math.random()*60+10) + '%';
    document.body.appendChild(particle);

    const keyframes = [
      { transform: 'translate(0,0) rotate(0deg) scale(1)', opacity: 1 },
      { transform: 'translate(' + (Math.random()*200-100) + 'px,' + (Math.random()*300-100) + 'px) rotate(' + (Math.random()*360) + 'deg) scale(0)', opacity: 0 }
    ];
    const anim = particle.animate(keyframes, {
      duration: 800 + Math.random() * 600,
      easing: 'cubic-bezier(.25,.46,.45,.94)',
      fill: 'forwards'
    });
    anim.onfinish = function() { particle.remove(); };
  }
}

export function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

export function _groupByDate(data) {
  const result = {};
  data.forEach(d => { result[d.date] = (result[d.date] || 0) + (d.value || 0); });
  return result;
}

export function _groupByDateAvg(data) {
  const tmp = {};
  const cnt = {};
  data.forEach(d => {
    tmp[d.date] = (tmp[d.date] || 0) + (d.value || 0);
    cnt[d.date] = (cnt[d.date] || 0) + 1;
  });
  const result = {};
  Object.keys(tmp).forEach(d => { result[d] = Math.round(tmp[d] / cnt[d]); });
  return result;
}

// Tool icon/label helpers used by handleWsMessage
export function _toolIcon(funcName) {
  const map = {
    'search': '🔍', 'get_video_url': '🎬', 'query_workout_history': '🏋️',
    'query_body_metrics': '⚖️', 'query_nutrition_history': '🍽️',
    'query_health_data': '❤️', 'sync_health_now': '🔄',
    'log_workout': '📝', 'log_body_metric': '📏', 'log_nutrition': '🍎',
  };
  return map[funcName] || '🔧';
}

export function _toolLabelEvent(funcName, args) {
  const map = {
    'search': '搜索: ' + (args.query || ''),
    'get_video_url': '搜视频: ' + (args.exercise_name || ''),
    'query_workout_history': '查训练历史',
    'query_body_metrics': '查体测数据',
    'query_nutrition_history': '查饮食记录',
    'query_health_data': '查健康数据: ' + (args.data_type || '全部'),
    'sync_health_now': '同步设备: ' + (args.platform || '全部'),
    'log_workout': '记录训练: ' + (args.exercise_name || ''),
    'log_body_metric': '记录体测',
    'log_nutrition': '记录饮食: ' + (args.food_name || ''),
  };
  return map[funcName] || funcName;
}

// Enhance markdown answer (B站 video embeds + exercise GIF embeds)
export function enhanceAnswer(content) {
  // Convert local exercise GIF/JPG to responsive images
  content = content.replace(
    /!\[([^\]]*)\]\((\/exercise-gifs\/[^)]+\.gif)\)/gi,
    (match, alt, src) => '<div class="exercise-gif"><img src="' + src + '" alt="' + escapeHtml(alt) + '" loading="lazy" style="max-width:200px;border-radius:8px;margin:4px 0"></div>'
  );

  // Convert CDN exercise GIF links to inline images
  content = content.replace(
    /!\[([^\]]*)\]\((https:\/\/cdn\.jsdelivr\.net\/gh\/hasaneyldrm\/exercises-dataset[^)]+)\)/gi,
    (match, alt, url) => {
      return '<div class="exercise-gif"><img src="' + url + '" alt="' + escapeHtml(alt || '演示') + '" loading="lazy" style="max-width:180px;border-radius:8px;margin:4px 0" onerror="this.style.display=\'none\'"><br><small style=\'color:var(--text3)\'>' + escapeHtml(alt || '演示') + '</small></div>';
    }
  );
  content = content.replace(
    /(?:\[>>\s*点击观看视频\]\(([^)]+)\))|(?:https?:\/\/(?:www\.)?bilibili\.com\/video\/(BV[a-zA-Z0-9]+)\S*)/gi,
    (match, pageUrl, bvid) => {
      const bv = bvid || (pageUrl ? pageUrl.match(/BV[a-zA-Z0-9]+/)?.[0] : null);
      if (!bv) return match;
      const embedUrl = 'https://player.bilibili.com/player.html?bvid=' + bv + '&page=1&high_quality=1&autoplay=0';
      return '<div class="bili-embed"><iframe src="' + embedUrl + '" frameborder="0" allowfullscreen style="width:100%;height:200px;border-radius:8px;margin:8px 0"></iframe><a href="https://www.bilibili.com/video/' + bv + '" target="_blank" class="video-link">📺 在B站观看</a></div>';
    }
  );
  return content;
}
