// ========== Auth & User Management ==========
import { escapeHtml } from './utils.js';

export async function deleteUser(userId) {
  if (!confirm('确定删除此用户？')) return;
  try {
    const resp = await fetch('/api/auth/users/' + userId, { method: 'DELETE' });
    const data = await resp.json();
    if (resp.ok) { alert('用户已删除'); location.reload(); }
    else { alert(data.detail || '删除失败'); }
  } catch(e) { alert('网络错误'); }
}

export function toggleRegistration(allowed) {
  fetch('/api/auth/registration', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({allowed}) })
    .then(r => r.json()).then(d => { if (d.success) alert('注册已' + (allowed ? '开启' : '关闭')); });
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

// Chat history sessions
export async function loadSidebarSessions() {
  try {
    const resp = await fetch('/api/chat/sessions');
    const data = await resp.json();
    const container = document.getElementById('sidebar-sessions');
    if (!container || !data.sessions || !data.sessions.length) {
      if (container) container.innerHTML = '<div style="font-size:11px;color:var(--text3)">暂无对话</div>';
      return;
    }
    container.innerHTML = data.sessions.slice(0, 10).map(function(s) {
      const d = new Date(s.created_at);
      const label = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
      return '<div class="sidebar-session-item" onclick="window._loadSession(\'' + s.session_id + '\')" title="' + label + '">' + label + '</div>';
    }).join('');
  } catch(e) { console.error('Failed to load sessions:', e); }
}

export async function loadSession(sid) {
  try {
    const resp = await fetch('/api/chat/sessions/' + sid);
    const data = await resp.json();
    if (!data.messages) return;
    const chatBody = document.getElementById('chat-messages');
    if (!chatBody) return;
    chatBody.innerHTML = '';
    data.messages.forEach(function(m) {
      const div = document.createElement('div');
      div.className = 'msg-row msg-' + m.role;
      div.innerHTML = '<div class="msg-bubble"><div class="msg-content">' + (m.content || '').replace(/\n/g, '<br>') + '</div></div>';
      chatBody.appendChild(div);
    });
    chatBody.scrollTop = chatBody.scrollHeight;
  } catch(e) { console.error('Load session error:', e); }
}

// Theme switcher
let currentTheme;
export function initTheme() {
  currentTheme = localStorage.getItem('fitai-theme') || 'light';
  document.documentElement.setAttribute('data-theme', currentTheme);
}

export function setTheme(t) {
  localStorage.setItem('fitai-theme', t);
  document.documentElement.setAttribute('data-theme', t);
}

// Export for HTML onclick
window.deleteUser = deleteUser;
window.toggleRegistration = toggleRegistration;
window.logout = logout;
window.setTheme = setTheme;
window._loadSession = loadSession;
window._loadSidebarSessions = loadSidebarSessions;
