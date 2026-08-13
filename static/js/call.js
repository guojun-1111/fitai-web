// ========== Call Mode (Phone Call Overlay) ==========
import { onWsMessage } from './ws.js';

export let callActive = false;
let callRecognition = null;
let callAnswerText = '';

function startCallListen() {
  if (!callActive) return;
  document.getElementById('call-status').textContent = '正在听...';
  document.getElementById('call-transcript').textContent = '';
  if (callRecognition) {
    try { callRecognition.start(); } catch(e) { setTimeout(startCallListen, 500); }
  }
}

function hangupCall() {
  callActive = false;
  callAnswerText = '';
  if (callRecognition) { try { callRecognition.abort(); } catch(e) { console.error('call: abort', e); } }
  document.getElementById('call-overlay').style.display = 'none';
  const callBtn = document.getElementById('call-btn');
  if (callBtn) callBtn.style.color = '';
  document.getElementById('call-status').textContent = '正在听...';
  document.getElementById('call-transcript').textContent = '';
  if (window.speechSynthesis) speechSynthesis.cancel();
}

export function initCallMode() {
  const callBtn = document.getElementById('call-btn');
  if (!callBtn) return;

  callBtn.onclick = function() {
    if (callActive) {
      hangupCall();
      return;
    }
    if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
      alert('您的浏览器不支持语音，请使用 Chrome 或 Edge'); return;
    }
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      alert('语音功能需要 HTTPS 连接'); return;
    }

    callActive = true;
    window._speakEnabled = true;
    callAnswerText = '';
    window._switchModelSilent('deepseek-v4-flash');
    const speakerBtn = document.getElementById('speaker-btn');
    if (speakerBtn) speakerBtn.style.color = 'var(--green)';
    document.getElementById('call-overlay').style.display = 'flex';
    callBtn.style.color = 'var(--red)';

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    callRecognition = new SR();
    callRecognition.lang = 'zh-CN';
    callRecognition.continuous = false;
    callRecognition.interimResults = false;
    callRecognition.onresult = function(e) {
      const text = e.results[0][0].transcript;
      document.getElementById('call-transcript').textContent = '"' + text + '"';
      document.getElementById('call-status').textContent = '思考中...';
      const chatInput = document.getElementById('chat-input');
      if (chatInput) { chatInput.value = text; window._sendMessage(); }
    };
    callRecognition.onerror = function(e) {
      document.getElementById('call-status').textContent = '没听清，重试...';
      setTimeout(startCallListen, 1000);
    };
    callRecognition.onend = function() { /* handled by TTS finish */ };

    startCallListen();
  };

  const hangupBtn = document.getElementById('call-hangup');
  if (hangupBtn) hangupBtn.onclick = hangupCall;

  // Register call-mode WS message handler
  onWsMessage(function(d, req) {
    if (!callActive) return;
    if (d.type === 'chunk') {
      callAnswerText += (d.content || '');
      document.getElementById('call-status').textContent = '回复中...';
      document.getElementById('call-transcript').textContent = callAnswerText.slice(-200);
    } else if (d.type === 'finish') {
      document.getElementById('call-status').textContent = '回复中 🔊';
      let clean = callAnswerText || (d.answer || '');
      clean = clean.replace(/\[SUGGESTIONS\][\s\S]*?\[\/SUGGESTIONS\]/gi, '').replace(/[#*`\[\]]/g, '').replace(/\n+/g, ' ').trim();
      document.getElementById('call-transcript').textContent = clean.slice(0, 300);

      if (clean.length > 10 && window.speechSynthesis) {
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(clean);
        u.lang = 'zh-CN'; u.rate = 1.1;
        u.onend = function() { startCallListen(); };
        u.onerror = function() { startCallListen(); };
        speechSynthesis.speak(u);
      } else {
        setTimeout(startCallListen, 500);
      }
      callAnswerText = '';
    }
  });
}
