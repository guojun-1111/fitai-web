// ========== Chat Panel ==========
import { state } from './state.js';
import { queueMessage, isWsReady, getModelId, sendWsMessage, updateConnStatus } from './ws.js';
import { escapeHtml } from './utils.js';
import { iconSVG } from './icons.js';

export function initChat() {
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');

  if (chatInput) {
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
  }

  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
}

export function sendMessage(fullMessage, imageBase64) {
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const text = chatInput ? chatInput.value.trim() : '';
  const sendText = typeof fullMessage === 'string' ? fullMessage : text;
  if (!sendText && !imageBase64) return;
  if (state.activeReq) return;

  // UI 初始化 — 无论 WS 是否就绪都要执行
  removeWelcome();
  addMessage('user', text || sendText.slice(0, 50) + '...');
  if (chatInput) {
    chatInput.value = '';
    chatInput.style.height = 'auto';
  }
  if (sendBtn) sendBtn.disabled = true;
  state.thinking = true;
  updateConnStatus(true);

  const div = addMessage('assistant', '');
  if (!div) return;
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'loading-msg';
  loadingDiv.innerHTML = '<div class="dot-wave"><span></span><span></span><span></span></div> 思考中...';
  div.querySelector('.msg-content').appendChild(loadingDiv);

  state.activeReq = { div: div, thought: '', steps: [] };

  // 发送 — 根据 WS 状态选择路径
  if (isWsReady()) {
    const payload = {type: 'query', content: sendText || '识别食物', model: getModelId()};
    if (imageBase64) payload.image = imageBase64;
    sendWsMessage(payload);
  } else {
    queueMessage(sendText, imageBase64);
  }
}

export function addMessage(role, text) {
  const chatMessages = document.getElementById('chat-messages');
  if (!chatMessages) return null;
  const div = document.createElement('div');
  div.className = 'message ' + role;
  const avatarIcon = role === 'user' ? 'user-icon' : 'bot';
  div.innerHTML = '<div class="msg-avatar">' + iconSVG(avatarIcon, 18) + '</div><div class="msg-content">' + escapeHtml(text) + '</div>';
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

export function removeWelcome() {
  const w = document.querySelector('.welcome-msg');
  if (w) w.style.display = 'none';
}

export function showWelcome() {
  const w = document.querySelector('.welcome-msg');
  if (w) w.style.display = '';
}

export function quickSend(msg) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const chatBtn = document.querySelector('.nav-btn[data-panel="chat"]');
  if (chatBtn) chatBtn.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const chatPanel = document.getElementById('panel-chat');
  if (chatPanel) chatPanel.classList.add('active');
  sendMessage(msg);
}
