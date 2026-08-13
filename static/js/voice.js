// ========== Voice Chat (Web Speech API) ==========
import { state } from './state.js';
export let speakEnabled = false;
// Export for ws.js TTS — kept for backward compat
window._speakEnabled = false;

export function initVoice() {
  // Speech-to-Text — requires HTTPS or localhost
  let recognition = null;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hasSecureContext = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if (SR && hasSecureContext) {
    recognition = new SR();
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = function(e) {
      const transcript = e.results[0][0].transcript;
      const chatInput = document.getElementById('chat-input');
      if (chatInput) chatInput.value = transcript;
      const micBtn = document.getElementById('mic-btn');
      if (micBtn) micBtn.classList.remove('recording');
      setTimeout(function() { window._sendMessage(); }, 100);
    };
    recognition.onerror = function(e) {
      const micBtn = document.getElementById('mic-btn');
      if (micBtn) micBtn.classList.remove('recording');
    };
    recognition.onend = function() {
      const micBtn = document.getElementById('mic-btn');
      if (micBtn) micBtn.classList.remove('recording');
    };
  }

  const micBtn = document.getElementById('mic-btn');
  if (micBtn) {
    if (!recognition) {
      const hint = (!SR) ? '浏览器不支持语音' : '语音需要 HTTPS 连接';
      micBtn.title = hint;
      micBtn.style.opacity = '0.4';
      micBtn.style.cursor = 'not-allowed';
      micBtn.onclick = function() { alert(hint + '。请使用 HTTPS 访问或 Chrome/Edge 浏览器'); };
    } else {
      micBtn.onclick = function() {
        if (micBtn.classList.contains('recording')) {
          recognition.stop();
          micBtn.classList.remove('recording');
        } else {
          recognition.start();
          micBtn.classList.add('recording');
        }
      };
    }
  }

  // Text-to-Speech toggle — writes state.speakEnabled so ws.js can read it
  const speakerBtn = document.getElementById('speaker-btn');
  let ttsPrimed = false;
  if (speakerBtn) {
    speakerBtn.onclick = function() {
      state.speakEnabled = !state.speakEnabled;
      speakEnabled = state.speakEnabled;
      window._speakEnabled = state.speakEnabled;
      speakerBtn.style.color = state.speakEnabled ? 'var(--green)' : '';
      if (state.speakEnabled && !ttsPrimed && window.speechSynthesis) {
        ttsPrimed = true;
        const prime = new SpeechSynthesisUtterance('');
        prime.volume = 0; prime.rate = 2;
        speechSynthesis.speak(prime);
      }
    };
  }
}
