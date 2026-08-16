// ========== FitAI Boot / Entry Point ==========
// V15: Global error handlers — prevent silent crashes
window.addEventListener('error', function(e) {
  if (e.target && e.target.tagName === 'SCRIPT' && e.target.src) {
    console.error('[FitAI] Script load failed:', e.target.src);
    _showErrorToast('部分功能加载失败，请刷新页面重试');
    return;
  }
  console.error('[FitAI] Unhandled error:', e.error || e.message);
  _showErrorToast('出了点问题，请刷新页面重试');
});

window.addEventListener('unhandledrejection', function(e) {
  console.error('[FitAI] Unhandled promise rejection:', e.reason);
  // Don't show toast for network errors (handled by individual modules)
  if (e.reason && e.reason.message && e.reason.message.includes('Failed to fetch')) return;
  _showErrorToast('网络请求失败，请检查网络后重试');
});

function _showErrorToast(msg) {
  const existing = document.getElementById('fitai-error-toast');
  if (existing) return;
  const toast = document.createElement('div');
  toast.id = 'fitai-error-toast';
  toast.textContent = msg;
  Object.assign(toast.style, {
    position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
    background: 'rgba(248,113,113,0.95)', color: '#fff', padding: '10px 24px',
    borderRadius: '8px', fontSize: '14px', zIndex: '99999',
    boxShadow: '0 4px 12px rgba(0,0,0,0.3)', animation: 'fadeIn 0.3s',
  });
  document.body.appendChild(toast);
  setTimeout(function() { if (toast.parentNode) toast.remove(); }, 5000);
}

import { connectWS } from './ws.js';
import { initChat, quickSend, sendMessage } from './chat.js';
import { initVoice } from './voice.js';
import { initCallMode } from './call.js';
import { replaceIcons } from './icons.js';
import { initNav } from './nav.js';
import { initDashboard } from './dashboard.js';
import { initHistory } from './history.js';
import { initHealth } from './health.js';
import { initProfile } from './profile.js';
import { initImport } from './import.js';
import { initTheme, loadSidebarSessions } from './auth.js';
import { loadHomePanel, recordHealth, recordWater, ringClick, triggerAIRecommend, triggerAIAnalysis } from './home.js';
import { loadDashboard } from './dashboard.js';
import { loadHistory } from './history.js';
import { loadHealthDashboard, openHealthDetail, closeHealthDetail } from './health.js';
import { loadExerciseAnalysis, openExDetail, closeExDetail } from './exercises.js';
import { loadSettings, connectPlatform, showCredForm, savePlatformConfig } from './settings.js';
import { loadProfile, saveProfile, switchModel, switchModelSilent, setReplyStyle, loadModelSetting } from './profile.js';
import { handleFileSelect } from './import.js';
import { openCamera } from './camera.js';
import { initExerciseLibrary, loadExerciseLibrary } from './exercise-library.js';
import { deleteUser, toggleRegistration, logout, setTheme, loadSession } from './auth.js';
import { exportData, deleteAccount } from './privacy.js';

// ── Expose for HTML onclick handlers ──
window.quickSend = quickSend;
window._sendMessage = sendMessage;
window.recordHealth = recordHealth;
window.recordWater = recordWater;
window.ringClick = ringClick;
window.triggerAIAnalysis = triggerAIAnalysis;
window.triggerAIRecommend = triggerAIRecommend;
window.switchModel = switchModel;
window.setReplyStyle = setReplyStyle;
window.setTheme = setTheme;
window.deleteUser = deleteUser;
window.toggleRegistration = toggleRegistration;
window.logout = logout;
window.handleFileSelect = handleFileSelect;
window.openExDetail = openExDetail;
window.closeExDetail = closeExDetail;
window.closeHealthDetail = closeHealthDetail;
window._switchModelSilent = switchModelSilent;
window.exportData = exportData;
window.deleteAccount = deleteAccount;

// ── iOS Safari viewport height fix ──
// iOS 的 100vh 包含地址栏高度，比实际可视区大，导致底部 tab bar 被挤出屏幕
function _setVH() {
  document.documentElement.style.setProperty('--vh', window.innerHeight * 0.01 + 'px');
}
_setVH();
window.addEventListener('resize', _setVH);
window.addEventListener('orientationchange', function () { setTimeout(_setVH, 100); });

// Splash — 提前绑定关闭逻辑，不等 authGate
const splash = document.getElementById('splash-screen');
if (splash) {
  splash.addEventListener('click', () => splash.classList.add('hidden'));
  setTimeout(() => splash.classList.add('hidden'), 2000);
}

// Auth gate
async function authGate() {
  try {
    let resp;
    try {
      resp = await fetch('/api/auth/status');
    } catch (netErr) {
      throw new Error('NetworkError: ' + netErr.message);
    }
    if (!resp.ok) throw new Error('ServerError: HTTP ' + resp.status);
    let authData;
    try {
      authData = await resp.json();
    } catch (jsonErr) {
      throw new Error('InvalidResponse: ' + jsonErr.message);
    }
    if (!authData.authenticated) {
      const setupParam = new URLSearchParams(window.location.search).get('setup') || '';
      window.location.href = '/login' + (authData.setup_allowed && setupParam ? '?setup=' + setupParam : '');
      return;
    }

    // Admin panel
    if (authData.is_admin) {
      const adminPanel = document.getElementById('admin-panel');
      if (adminPanel) adminPanel.style.display = 'block';
      const regToggle = document.getElementById('registration-toggle');
      if (regToggle) regToggle.checked = authData.registration_allowed;

      try {
        const userListResp = await fetch('/api/auth/users');
        if (userListResp.ok) {
          const userData = await userListResp.json();
          const userListDiv = document.getElementById('user-list');
          if (userListDiv && userData.users) {
            userListDiv.innerHTML = '<h4 style="margin-top:16px;color:var(--text)">用户列表 (' + userData.total + '人)</h4>' +
              userData.users.map(function(u) {
                return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">' +
                  '<span>' + u.username + (u.is_admin ? ' <span style="color:var(--green);font-size:11px">管理员</span>' : '') + '</span>' +
                  (u.is_admin ? '' : '<button onclick="deleteUser(' + u.id + ')" style="background:rgba(255,107,122,0.1);color:#ff6b7a;border:1px solid rgba(255,107,122,0.2);border-radius:4px;padding:4px 8px;cursor:pointer;font-size:12px">删除</button>') +
                  '</div>';
              }).join('');
          }
        }
      } catch(e) { console.error('Failed to load user list:', e); }
    }

    // Init all modules
    initTheme();
    replaceIcons();  // Convert [data-icon] elements to SVG
    connectWS();
    initChat();
    initVoice();
    // Camera button → food recognition
    const camBtn = document.getElementById('camera-chat-btn');
    if (camBtn) camBtn.onclick = () => {
      window._onCameraCapture = (base64) => {
        const chatInput = document.getElementById('chat-input');
        const text = chatInput ? chatInput.value.trim() || '这是什么食物？帮我分析营养成分' : '这是什么食物？帮我分析营养成分';
        sendMessage(text, base64);
        window._onCameraCapture = null;
      };
      openCamera();
    };

    initCallMode();
    initNav();
    initDashboard();
    initHistory();
    initHealth();
    initProfile();
    initExerciseLibrary();
    initImport();
    import('./plan.js').then(m => m.initPlan());
    loadHomePanel();
    setTimeout(loadSidebarSessions, 2000);

    // V10: 新人引导
    if (!localStorage.getItem('fitai-onboarded')) {
      setTimeout(() => {
        const overlay = document.getElementById('onboarding-overlay');
        if (overlay) overlay.style.display = 'flex';
      }, 1500);
      initOnboarding();
    }
  } catch(e) {
    // 认证失败也关闭 splash，但显示错误提示
    if (splash) splash.classList.add('hidden');
    console.error('Auth check failed:', e);
    // 渲染错误 UI 让用户知道出问题了
    const main = document.querySelector('.main-content');
    if (main) {
      main.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text2);padding:40px;text-align:center"><div style="font-size:48px;margin-bottom:16px">⚠️</div><h2 style="color:var(--text);margin-bottom:8px">连接服务器失败</h2><p style="margin-bottom:24px;line-height:1.6">无法连接到 FitAI 服务器，请检查网络连接后重试</p><button onclick="location.reload()" style="padding:10px 32px;background:var(--green);color:#fff;border:none;border-radius:10px;font-size:15px;cursor:pointer;font-weight:600">🔄 重新连接</button></div>';
    }
  }
}

// Register Service Worker for PWA (only in production, not localhost)
if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js?v=16').then((reg) => {
      console.log('SW registered:', reg.scope);
      // Force update check on every page load (Safari is lazy about this)
      reg.update();
      // Auto-reload when new SW takes over
      reg.addEventListener('updatefound', () => {
        const newWorker = reg.installing;
        if (newWorker) {
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              console.log('SW updated, reloading...');
              window.location.reload();
            }
          });
        }
      });
    }).catch((err) => {
      console.error('SW registration failed:', err);
    });
  });
}

// ── V18.1: 冷启动引导（含欢迎页）──
window._obShowStep = function(n) {
  for (var i = 1; i <= 6; i++) {
    var el = document.getElementById('ob-step-' + i);
    if (el) el.style.display = (i === n) ? 'block' : 'none';
  }
  // 4 dots for steps 2-5 (goal→freq→pain→loading). Step 1 (welcome) & step 6 (result) have no dot.
  for (var i = 1; i <= 4; i++) {
    var dot = document.getElementById('ob-dot-' + i);
    if (dot) { dot.className = 'ob-dot' + (i + 1 <= n ? ' active' : ''); }
  }
  var card = document.getElementById('ob-card');
  if (card) card.scrollTop = 0;
  window._obStep = n;
};

window._obGeneratePlan = function() {
  var goal = window._obGoal;
  var freq = window._obFreq;
  var pain = window._obPain;

  // Phase 2: Show diagnosis first (1.8s), then loading + API call
  var diagTexts = {
    '减脂|怕受伤': '你的担心是对的。大多数减脂失败不是因为不努力，是因为受伤被迫中断。接下来 7 天，每个动作都是低风险的，你的膝盖和腰椎会得到保护。这不是一个「变瘦」的计划——这是一个「安全变瘦」的计划。',
    '减脂|没动力': '你不是懒。你是没有看到过自己能坚持多久。这个计划每天只让你专注一件事，不是一堆。我们不需要你「努力」，只需要你「出现」。',
    '减脂|没效果': '不是所有汗水都有回报。之前的努力可能用错了方向。这个 7 天计划的核心不是「多做」，而是「做对」。',
    '减脂|不知道练什么': '迷茫是对的。健身行业有太多噪音。我们砍掉了所有废话，只给你最直接有效的动作——每天不超过 5 个。',
    '增肌|怕受伤': '安全比大重量重要。前 7 天全部是可控的自重动作，你的关节会先于肌肉变强。受伤的人无法增肌——我们先确保你不会成为那个人。',
    '增肌|没动力': '不是每个人都需要每天 2 小时在健身房。这个计划中的每个动作都有明确的目的。当你看到第一周的变化，动力会自己来。',
    '增肌|没效果': '平台期不是因为你不努力，是因为你没有换方法。接下来我们会用不同的刺激模式打破适应。',
    '增肌|不知道练什么': '信息过载是最大的敌人。我们把 1324 个动作缩减到了最适合你的几个。不是最多的，是最对的。',
    '更健康|怕受伤': '健康不是冲刺，是马拉松。我们用最温和的方式开始，你的身体会感谢你没有在一开始就过度消耗它。',
    '更健康|没动力': '最难的不是运动本身，是穿上运动鞋的那一刻。我们把这个计划设计得足够简单——简单到你没有理由不去做。',
    '更健康|没效果': '「更健康」不是一个模糊的目标。接下来 7 天，你会具体地感受到什么叫「状态变好了」。从睡眠到精力，数据会说真话。',
    '更健康|不知道练什么': '不需要成为健身专家才能拥有健康。我们帮你选了最均衡的组合——下半身、上半身、核心，轮着来。',
    '缓解疼痛|怕受伤': '你来找我们是对的。康复不是忍痛训练，是在保护中重建。每个动作都经过筛选——只做对恢复有帮助的，不做可能加重问题的。',
    '缓解疼痛|没动力': '疼痛让人沮丧。但你知道吗？正确的运动其实是疼痛的解药，不是原因。这个计划比你想象的温和，但比休息更有效。',
    '缓解疼痛|没效果': '如果之前的康复没效果，可能是因为没有找对根源。我们把重点放在核心稳定性和关节活动度——大多数慢性疼痛的根在这儿。',
    '缓解疼痛|不知道练什么': '不知道练什么没关系——你只需要知道「不去练什么」。我们帮你避开了所有高风险动作，只保留了安全的康复练习。'
  };
  var diagKey = goal + '|' + pain;
  var diagText = diagTexts[diagKey] || ('我们分析了你的「' + goal + '」目标和「' + pain + '」的困扰，为你量身定制了这个 7 天方案。每个动作都有明确的目的——没有一个是凑数的。');

  window._obShowStep(5);
  // Replace step 5 content with diagnosis
  var s5 = document.getElementById('ob-step-5');
  if (s5) {
    s5.innerHTML = '<div class="ob-icon">🔍</div><h2>我们听到了</h2><p style="font-size:14px;color:var(--text2);line-height:1.8;max-width:360px;margin:0 auto">' + diagText + '</p><div class="ob-loading-bar"><div class="ob-loading-fill"></div></div>';
  }

  // After 1.8s, transition to spinner + fire API
  setTimeout(function() {
    if (s5) {
      s5.innerHTML = '<div class="ob-icon" style="animation: pulse 1.5s ease-in-out infinite">⚙️</div><h2>正在为你定制专属计划...</h2><p>根据你的目标、频率和困扰，生成 7 天可执行训练方案</p><div class="ob-loading-bar"><div class="ob-loading-fill"></div></div>';
    }
    window._doFetchPlan(goal, freq, pain);
  }, 1800);
};

window._doFetchPlan = function(goal, freq, pain) {
  fetch('/api/training/onboarding/quick-start', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal: goal, frequency: parseInt(freq), pain_point: pain })
  }).then(function(resp) {
    if (resp.status === 401) throw new Error('AUTH_EXPIRED');
    if (!resp.ok) {
      // Try to read server error detail from response body
      return resp.text().then(function(body) {
        var detail = body;
        try { var j = JSON.parse(body); detail = j.error || j.detail || body; } catch(e) {}
        throw new Error('HTTP_' + resp.status + '|' + detail.substring(0, 200));
      });
    }
    return resp.json();
  }).then(function(data) {
    if (!data.success || !data.plan) throw new Error('No plan');
    window._obPlan = data.plan;
    window._obShowStep(6);  // result is now step 6
    window._obRenderPlan(data.plan);
  }).catch(function(err) {
    console.error('boot: quickStart', err);
    var msg, hint;
    if (err.message === 'AUTH_EXPIRED') {
      msg = '登录状态已过期';
      hint = '请刷新页面重新登录';
    } else if (err.message && err.message.indexOf('HTTP_') === 0) {
      var parts = err.message.split('|');
      msg = '服务器错误（状态码：' + parts[0].slice(5) + '）';
      hint = parts[1] || '请稍后重试';
    } else {
      msg = '无法连接服务器';
      hint = '请检查网络连接后重试';
    }
    var s5 = document.getElementById('ob-step-5');
    if (s5) {
      s5.innerHTML = '<div class="ob-icon">⚠️</div><h2>' + msg + '</h2><p style="font-size:12px;color:var(--text3);word-break:break-all;max-height:120px;overflow-y:auto">' + hint + '</p><div class="ob-buttons" style="margin-top:16px"><button class="btn btn-primary" onclick="window._obGeneratePlan()">🔄 重试</button><button class="ob-skip" onclick="window._obFinish()">跳过，先进去看看</button></div>';
    }
  });
};

window._obRenderPlan = function(plan) {
  var container = document.getElementById('ob-plan-scroll');
  if (!container) return;

  var explainEl = document.getElementById('ob-plan-explain');
  if (explainEl) explainEl.textContent = plan.explanation || '';

  var html = '';
  var todayIdx = (new Date().getDay() + 6) % 7;

  for (var d = 0; d < plan.days.length; d++) {
    var day = plan.days[d];
    var isToday = d === todayIdx;
    if (day.is_rest) {
      html += '<div class="ob-day-card' + (isToday ? ' today' : '') + '">' +
        '<div class="ob-day-header"><span class="ob-day-name">' + day.day_name + '</span><span class="ob-day-focus rest">休息</span></div>' +
        '<div class="ob-day-rest">' + (day.rest_activity || '好好休息') + '</div>' +
        '<div class="ob-day-tip">' + (day.tip || '') + '</div></div>';
    } else {
      html += '<div class="ob-day-card' + (isToday ? ' today' : '') + '">' +
        '<div class="ob-day-header"><span class="ob-day-name">' + day.day_name + '</span><span class="ob-day-focus">' + (day.focus || '训练') + '</span><span class="ob-day-time">' + (day.total_time || '') + '</span></div>';
      if (day.main && day.main.length > 0) {
        html += '<div class="ob-day-exercises">';
        for (var e = 0; e < day.main.length; e++) {
          var ex = day.main[e];
          html += '<div class="ob-ex-item"><span class="ob-ex-name">' + ex.name + '</span><span class="ob-ex-detail">' + ex.sets + '组 × ' + ex.reps + '</span><span class="ob-ex-why">' + (ex.why || '') + '</span></div>';
        }
        html += '</div>';
      }
      if (day.tip) html += '<div class="ob-day-tip">💡 ' + day.tip + '</div>';
      html += '</div>';
    }
  }

  container.innerHTML = html;

  setTimeout(function() {
    var todayCard = container.querySelector('.ob-day-card.today');
    if (todayCard) todayCard.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' });
  }, 300);
};

window._obFinish = function() {
  localStorage.setItem('fitai-onboarded', '1');
  var overlay = document.getElementById('onboarding-overlay');
  if (overlay) overlay.style.display = 'none';
  try { loadHomePanel(); } catch(e) {}
};

function initOnboarding() {
  window._obStep = 1;
  window._obGoal = '';
  window._obFreq = '3';
  window._obPain = '';
  window._obPlan = null;

  var indicator = document.getElementById('ob-steps-indicator');
  if (indicator) {
    indicator.innerHTML = '';
    // 4 dots for steps 2-5 (goal, freq, pain, loading)
    for (var i = 1; i <= 4; i++) {
      var dot = document.createElement('span');
      dot.className = 'ob-dot';
      dot.id = 'ob-dot-' + i;
      indicator.appendChild(dot);
    }
  }

  // Goal buttons → next button is ob-next-2
  var goalBtns = document.querySelectorAll('#ob-goal-btns .ob-goal-btn');
  for (var g = 0; g < goalBtns.length; g++) {
    goalBtns[g].onclick = function() {
      for (var j = 0; j < goalBtns.length; j++) { goalBtns[j].classList.remove('selected'); }
      this.classList.add('selected');
      window._obGoal = this.dataset.goal;
      var next = document.getElementById('ob-next-2');
      if (next) next.disabled = false;
    };
  }

  // Frequency buttons → next button is ob-next-3
  var freqBtns = document.querySelectorAll('#ob-freq-btns .ob-freq-btn');
  for (var f = 0; f < freqBtns.length; f++) {
    freqBtns[f].onclick = function() {
      for (var j = 0; j < freqBtns.length; j++) { freqBtns[j].classList.remove('selected'); }
      this.classList.add('selected');
      window._obFreq = this.dataset.freq;
      var next = document.getElementById('ob-next-3');
      if (next) next.disabled = false;
    };
  }

  // Pain point buttons → next button is ob-next-4
  var painBtns = document.querySelectorAll('#ob-pain-btns .ob-pain-btn');
  for (var p = 0; p < painBtns.length; p++) {
    painBtns[p].onclick = function() {
      for (var j = 0; j < painBtns.length; j++) { painBtns[j].classList.remove('selected'); }
      this.classList.add('selected');
      window._obPain = this.dataset.pain;
      var next = document.getElementById('ob-next-4');
      if (next) next.disabled = false;
    };
  }
}

// V17: Page visibility — pause/resume WS reconnect + timers on tab switch
document.addEventListener('visibilitychange', () => {
  const hidden = document.hidden;
  window._pageHidden = hidden;
  // Access state via dynamic import to avoid circular dep
  import('./state.js').then(m => {
    const s = m.state;
    s._pageHidden = hidden;
    if (hidden) {
      clearTimeout(s._reconnectTimer);
      clearInterval(s._pingTimer);
    } else if (!s.wsConnected) {
      // Tab back, try reconnect if disconnected
      import('./ws.js').then(ws => ws.connectWS());
    }
  }).catch(() => {});
});

// Run on DOM ready
document.addEventListener('DOMContentLoaded', authGate);

// Quick input cleanup
(function() {
  const w = document.getElementById('quick-weight');
  const s = document.getElementById('input-sleep');
  if (w) w.value = '';
  if (s) s.value = '';
  setTimeout(function() { if (w) w.value = ''; if (s) s.value = ''; }, 100);
  setTimeout(function() { if (w) w.value = ''; if (s) s.value = ''; }, 500);
})();
