// ========== Bilibili Video Grid ==========
import { escapeHtml } from './utils.js';

export async function loadVideoGrid(exercise) {
  const grid = document.getElementById('video-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="empty-state"><div class="empty-icon">🎬</div><p>搜索中...</p></div>';
  try {
    const params = exercise ? '?exercise=' + encodeURIComponent(exercise) + '&limit=6' : '?limit=6';
    const res = await fetch('/api/videos' + params);
    const data = (await res.json()).data || [];
    if (!data.length) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">🎬</div><p>暂无相关视频</p></div>';
      return;
    }
    grid.innerHTML = data.map(v => {
      const bvUrl = 'https://www.bilibili.com/video/' + v.bvid;
      let thumbnailUrl = '';
      if (v.thumbnail) {
        const base = v.thumbnail.startsWith('//') ? 'https:' + v.thumbnail : v.thumbnail;
        thumbnailUrl = base + '@672w_378h_1c.avif';
      }
      const playCount = v.play ? (v.play >= 10000 ? (v.play/10000).toFixed(1) + '万' : v.play) : '';
      return '<div class="video-card" onclick="window.open(\'' + bvUrl + '\', \'_blank\')">' +
        '<div class="video-thumb">' +
        (thumbnailUrl
          ? '<img src="' + thumbnailUrl + '" alt="' + escapeHtml(v.title) + '" class="video-thumb-img" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'video-thumb-fallback\\\'><span>🎬</span><span>B站健身</span></div>\'">'
          : '<div class="video-thumb-fallback"><span>🎬</span><span>B站健身</span></div>') +
        '<div class="video-play-overlay">▶</div>' +
        (v.duration ? '<div class="video-duration-tag">' + v.duration + '</div>' : '') +
        '</div>' +
        '<div class="video-info">' +
        '<div class="video-title" title="' + escapeHtml(v.title) + '">' + v.title + '</div>' +
        '<div class="video-meta">' +
        (v.author ? '<span class="video-author">' + escapeHtml(v.author) + '</span>' : '') +
        (playCount ? '<span class="video-plays">▶ ' + playCount + '</span>' : '') +
        '</div></div></div>';
    }).join('');
  } catch (_) {
    grid.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><p>加载失败</p></div>';
  }
}
