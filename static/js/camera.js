// FitAI Camera Module — food photo capture
let stream = null;
let capturedBase64 = null;

// Create camera overlay in DOM
function ensureOverlay() {
  if (document.getElementById('camera-overlay')) return;
  const ov = document.createElement('div');
  ov.id = 'camera-overlay';
  ov.innerHTML = `
    <div class="camera-bg">
      <video id="camera-video" autoplay playsinline></video>
      <canvas id="camera-canvas" style="display:none"></canvas>
      <div id="camera-preview" style="display:none"></div>
      <div class="camera-controls">
        <button class="camera-btn" id="camera-capture-btn">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/></svg>
        </button>
        <button class="camera-btn camera-close-btn" id="camera-close-btn">✕</button>
        <button class="camera-btn camera-send-btn" id="camera-send-btn" style="display:none">发送</button>
        <button class="camera-btn camera-retake-btn" id="camera-retake-btn" style="display:none">重拍</button>
      </div>
    </div>
  `;
  ov.style.cssText = 'position:fixed;inset:0;z-index:10001;background:#000;display:none;flex-direction:column;align-items:center;justify-content:center;';
  document.body.appendChild(ov);
}

export async function openCamera() {
  ensureOverlay();
  const overlay = document.getElementById('camera-overlay');
  const video = document.getElementById('camera-video');
  const canvas = document.getElementById('camera-canvas');
  const preview = document.getElementById('camera-preview');
  const captureBtn = document.getElementById('camera-capture-btn');
  const closeBtn = document.getElementById('camera-close-btn');
  const sendBtn = document.getElementById('camera-send-btn');
  const retakeBtn = document.getElementById('camera-retake-btn');

  capturedBase64 = null;
  overlay.style.display = 'flex';
  video.style.display = 'block';
  preview.style.display = 'none';
  captureBtn.style.display = '';
  sendBtn.style.display = 'none';
  retakeBtn.style.display = 'none';

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
  } catch (e) {
    closeCamera();
    // Fallback to file picker
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    input.onchange = (e) => {
      const file = e.target.files[0];
      if (file) processPickedFile(file);
    };
    input.click();
  }

  // Capture
  captureBtn.onclick = () => {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    capturedBase64 = canvas.toDataURL('image/jpeg', 0.7);
    // Show preview
    video.style.display = 'none';
    preview.style.display = 'block';
    preview.innerHTML = '<img src="' + capturedBase64 + '" style="max-width:100%;max-height:60vh;border-radius:12px">';
    captureBtn.style.display = 'none';
    sendBtn.style.display = '';
    retakeBtn.style.display = '';
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  };

  // Retake
  retakeBtn.onclick = () => { openCamera(); };

  // Close
  closeBtn.onclick = () => { closeCamera(); };

  // Send
  sendBtn.onclick = () => {
    if (capturedBase64 && window._onCameraCapture) {
      window._onCameraCapture(capturedBase64);
    }
    closeCamera();
  };
}

function closeCamera() {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  const overlay = document.getElementById('camera-overlay');
  if (overlay) overlay.style.display = 'none';
}

function processPickedFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    capturedBase64 = e.target.result;
    if (window._onCameraCapture) {
      window._onCameraCapture(capturedBase64);
    }
  };
  reader.readAsDataURL(file);
}

// Camera button styles
const style = document.createElement('style');
style.textContent = `
.camera-bg { text-align:center; width:100%; max-width:500px; }
#camera-video { width:100%; max-height:70vh; object-fit:cover; border-radius:12px; }
.camera-controls { display:flex; justify-content:center; gap:20px; margin-top:20px; flex-wrap:wrap; }
.camera-btn { padding:12px 24px; border-radius:24px; border:none; font-size:16px; cursor:pointer; background:rgba(255,255,255,0.15); color:#fff; min-height:44px; }
.camera-send-btn { background:#3dd68c; color:#000; font-weight:600; }
.camera-close-btn { position:fixed; top:16px; right:16px; font-size:24px; background:none; padding:8px 16px; }
.camera-retake-btn { background:rgba(255,255,255,0.1); }
`;
document.head.appendChild(style);
