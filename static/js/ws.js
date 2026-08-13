// ========== WebSocket Core ==========
import { state } from './state.js';
import { escapeHtml, _toolLabelEvent, enhanceAnswer } from './utils.js';
import { iconSVG, TOOL_ICONS } from './icons.js';

function _toolIcon(funcName) {
  const iconName = TOOL_ICONS[funcName] || 'wrench';
  return iconSVG(iconName, 18);
}

const msgHandlers = [];

export function onWsMessage(fn) { msgHandlers.push(fn); }
export function offWsMessage(fn) {
  const idx = msgHandlers.indexOf(fn);
  if (idx >= 0) msgHandlers.splice(idx, 1);
}

export function resetActiveReq() {
  state.thinking = false;
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = false;
  updateConnStatus(state.wsConnected);
  state.activeReq = null;
}

export function updateConnStatus(ok) {
  const dot = document.querySelector('.status-dot');
  const label = document.querySelector('.connection-status span:last-child');
  if (!dot || !label) return;
  if (state.thinking) {
    dot.className = 'status-dot thinking';
    label.textContent = '思考中...';
  } else if (ok) {
    dot.className = 'status-dot connected';
    label.textContent = '已连接';
  } else {
    dot.className = 'status-dot disconnected';
    label.textContent = '未连接·重试中';
  }
}

export function getModelId() {
  const m = document.querySelector('.model-option.active');
  return m ? m.dataset.model : 'deepseek-v4-flash';
}

function renderSteps(req) {
  const content = req.div.querySelector('.msg-content');
  content.innerHTML = '';
  const statusDiv = document.createElement('div');
  statusDiv.className = 'agent-live-status';
  const items = req.steps.map(s =>
    '<div class="live-step ' + s.type + '">' +
    '<span class="live-step-icon">' + (s.icon || '') + '</span>' +
    '<span class="live-step-text">' + escapeHtml(s.summary || s.type) + '</span>' +
    '</div>'
  ).join('');
  statusDiv.innerHTML = items;
  content.appendChild(statusDiv);
  const chatMessages = document.getElementById('chat-messages');
  if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
}

export function handleWsMessage(e) {
  let d;
  try { d = JSON.parse(e.data); } catch (_) { return; }

  // V17: handle pong — clear heartbeat timeout
  if (d.type === 'pong') {
    clearTimeout(state._pongTimeout);
    return;
  }

  // V21: Real-time pose insights from server
  if (d.type === 'pose_insight') {
    var insight = d.data || {};
    if (insight.message) {
      import('./pose.js').then(function(m) {
        var cueEl = document.getElementById('pose-cue');
        if (cueEl && insight.message) {
          cueEl.textContent = insight.message;
          cueEl.className = 'pose-cue warn';
        }
      }).catch(function(){});
    }
    return;
  }

  if (!state.activeReq) return;

  const req = state.activeReq;

  try {
    if (d.type === 'step') {
      req.currentStep = d.step;
    }
    if (d.type === 'thought') {
      req.thought = d.content;
      if (req.steps.filter(s => s.type !== 'thought').length === 0) {
        req.steps = [{type: 'thought', content: d.content || '分析中...', summary: '思考', icon: iconSVG('brain', 16)}];
        renderSteps(req);
      }
    }
    if (d.type === 'action' && d.action_type === 'call') {
      const steps = req.steps.filter(s => s.type !== 'thought');
      if (req.thought) steps.push({type: 'thought', content: req.thought, summary: '思考', icon: iconSVG('brain', 16)});
      steps.push({
        type: 'action',
        content: d.func_name + '(' + (d.args ? JSON.stringify(d.args) : '') + ')',
        summary: _toolLabelEvent(d.func_name, d.args || {}),
        icon: _toolIcon(d.func_name),
        func: d.func_name,
      });
      req.steps = steps;
      renderSteps(req);
    }
    if (d.type === 'observation') {
      const obsPreview = (d.content || '').replace(/\n/g, ' ').slice(0, 80);
      req.steps.push({
        type: 'observation', content: d.content,
        summary: obsPreview + ((d.content || '').length > 80 ? '...' : ''),
        icon: iconSVG('list-checks', 16),
      });
      renderSteps(req);
    }
    if (d.type === 'chunk') {
      const content = req.div.querySelector('.msg-content');
      if (!req._hasChunks) {
        req._hasChunks = true;
        content.innerHTML = '';
        req._textBuffer = '';
      }
      req._textBuffer += (d.content || '');
      try {
        if (typeof marked !== 'undefined' && marked.parse) {
          content.innerHTML = marked.parse(enhanceAnswer(req._textBuffer));
        } else {
          content.textContent = req._textBuffer;
        }
      } catch (er) {
        content.innerHTML = escapeHtml(req._textBuffer).replace(/\n/g, '<br>');
      }
      const chatMessages = document.getElementById('chat-messages');
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    if (d.type === 'finish') {
      const content = req.div.querySelector('.msg-content');
      if (!req._hasChunks) {
        if (req.steps.length === 0) content.innerHTML = '';
        if (req.steps.length > 0) {
          const summaryDiv = document.createElement('div');
          summaryDiv.className = 'agent-summary';
          summaryDiv.innerHTML = '<details><summary>Agent 工作过程 <span style="color:var(--text3);font-size:11px">(' + req.steps.length + ' 步)</span></summary>' +
            req.steps.map(s => '<div class="agent-step-row"><span class="agent-step-icon">' + (s.icon || '') + '</span><span>' + escapeHtml(s.summary || '') + '</span></div>').join('') +
            '</details>';
          content.appendChild(summaryDiv);
        }
        const answerDiv = document.createElement('div');
        answerDiv.className = 'answer';
        try {
          if (typeof marked !== 'undefined' && marked.parse) {
            answerDiv.innerHTML = marked.parse(enhanceAnswer(d.answer));
          } else {
            answerDiv.innerHTML = escapeHtml(d.answer).replace(/\n/g, '<br>');
          }
        } catch (er) {
          answerDiv.innerHTML = escapeHtml(d.answer).replace(/\n/g, '<br>');
        }
        content.appendChild(answerDiv);
      } else {
        if (req.steps.length > 0) {
          const summaryDiv = document.createElement('div');
          summaryDiv.className = 'agent-summary';
          summaryDiv.innerHTML = '<details><summary>Agent 工作过程 <span style="color:var(--text3);font-size:11px">(' + req.steps.length + ' 步)</span></summary>' +
            req.steps.map(s => '<div class="agent-step-row"><span class="agent-step-icon">' + (s.icon || '') + '</span><span>' + escapeHtml(s.summary || '') + '</span></div>').join('') +
            '</details>';
          content.appendChild(summaryDiv);
        }
      }

      // Suggestions
      const answer = req._textBuffer || d.answer;
      const suggMatch = answer.match(/\[SUGGESTIONS\]([\s\S]*?)\[\/SUGGESTIONS\]/i);
      const suggestions = [];
      if (suggMatch) {
        suggMatch[1].split(/\|\||\n/).forEach(function(s) {
          const clean = s.replace(/^[\s\d\.\-\*\•]+/, '').trim();
          if (clean.length > 1 && clean.length <= 30) suggestions.push(clean);
        });
      }

      if (suggestions.length > 0) {
        const suggDiv = document.createElement('div');
        suggDiv.className = 'suggestions-row';
        suggDiv.innerHTML = '<div class="suggestions-label">💡 继续探索</div>';
        suggestions.forEach(function(s) {
          const chip = document.createElement('button');
          chip.className = 'suggestion-chip';
          chip.textContent = s;
          chip.onclick = function() { window.quickSend(s); };
          suggDiv.appendChild(chip);
        });
        content.appendChild(suggDiv);
      }

      // TTS
      if (state.speakEnabled && answer && window.speechSynthesis) {
        let cleanForSpeech = answer.replace(/\[SUGGESTIONS\][\s\S]*?\[\/SUGGESTIONS\]/gi, '').replace(/[#*`\[\]]/g, '').trim();
        if (cleanForSpeech.length > 50) {
          const u = new SpeechSynthesisUtterance(cleanForSpeech);
          u.lang = 'zh-CN'; u.rate = 1.0; u.pitch = 1.0;
          speechSynthesis.speak(u);
        }
      }

      const chatMessages = document.getElementById('chat-messages');
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;

      window._loadSidebarStats();
      setTimeout(function() { window._loadSidebarSessions(); }, 500);
      resetActiveReq();
    }
    if (d.type === 'error') {
      req.div.querySelector('.msg-content').innerHTML =
        '<div style="color:var(--red)">Error: ' + escapeHtml(d.content) + '</div>';
      resetActiveReq();
    }
    if (d.type === 'humanizing') {
      req.div.querySelector('.msg-content').innerHTML =
        '<div class="loading-msg"><div class="dot-wave"><span></span><span></span><span></span></div> 正在优化回答...</div>';
    }
  } catch (err) {
    console.error('WS handler error:', err);
    resetActiveReq();
  }

  for (const h of msgHandlers) {
    try { h(d, req); } catch (e) { console.error('ws: msgHandler', e); }
  }
}

export function connectWS() {
  if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
  state.ws.addEventListener('message', handleWsMessage);

  state.ws.onopen = () => {
    state.wsConnected = true;
    state.reconnectDelay = 1000;
    updateConnStatus(true);
    // V17: heartbeat — 30s ping, 10s pong timeout
    clearInterval(state._pingTimer);
    state._pingTimer = setInterval(() => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'ping' }));
        state._pongTimeout = setTimeout(() => {
          if (state.ws) state.ws.close();
        }, 10000);
      }
    }, 30000);
    if (state.pendingMessages.length) {
      const mid = getModelId();
      state.pendingMessages.forEach(m => {
        const payload = {type: 'query', model: mid};
        if (typeof m === 'string') {
          payload.content = m;
        } else {
          payload.content = m.text;
          if (m.image) payload.image = m.image;
        }
        state.ws.send(JSON.stringify(payload));
      });
      state.pendingMessages = [];
    }
  };

  state.ws.onclose = () => {
    state.wsConnected = false;
    state.thinking = false;
    state.activeReq = null;
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = false;
    updateConnStatus(false);
    clearInterval(state._pingTimer);
    clearTimeout(state._pongTimeout);
    clearTimeout(state._reconnectTimer);
    state.reconnectDelay = Math.min(state.reconnectDelay * 1.5, 30000);
    if (!state._pageHidden) {
      state._reconnectTimer = setTimeout(connectWS, state.reconnectDelay);
    }
  };

  state.ws.onerror = () => { state.ws.close(); };
}

export function queueMessage(msg, image) {
  state.pendingMessages.push(image ? {text: msg, image} : msg);
  connectWS();
}

export function isWsReady() {
  return state.wsConnected && state.ws && state.ws.readyState === WebSocket.OPEN;
}

export function sendWsMessage(obj) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(obj));
  }
}
