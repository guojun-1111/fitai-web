// ========== V21: Algorithm-Woven Pose Correction Engine ==========
// MediaPipe Pose + Bayesian Changepoint (fatigue) + Conformal Prediction (confidence).
// Browser-side real-time squat form analysis with Web Speech API cues.

import { ChangepointDetector } from './changepoint.js';
import { AdaptiveConformalPredictor } from './conformal.js';
import { sendWsMessage } from './ws.js';

let _poseLandmarker = null;
let _isRunning = false;
let _animationId = null;
let _repState = 'up'; // 'up' | 'down'
let _repCount = 0;
let _lastRepTime = 0;
let _feedbackTimer = 0;
let _lastSpokenCue = '';
let _lastSpeakTime = 0;
let _videoEl = null;
let _canvasEl = null;
let _ctx = null;
let _indicatorsEl = null;
let _repEl = null;
let _cueEl = null;
let _fatigueBarEl = null;
let _speechEnabled = true;
let _currentExercise = 'squat';   // 'squat' | 'pushup' | 'plank' | 'lunge' | 'ytw'

// ── V21: Algorithm state ──
let _changepoint = new ChangepointDetector({ threshold: 3.0, drift: 0.5, warmup: 5 });
let _conformalKnee = new AdaptiveConformalPredictor({ alpha: 0.1, gamma: 0.005 });
let _conformalHip = new AdaptiveConformalPredictor({ alpha: 0.1, gamma: 0.005 });
let _repMetrics = [];          // per-rep data for server analysis
let _qualityScores = [];       // last 20 rep quality scores for mini chart
let _currentRepMinKnee = 180;  // tracking min knee angle during current rep
let _currentRepMinHip = 180;
let _currentRepMaxBack = 0;
let _currentRepMaxValgus = 0;
let _currentRepStartTime = 0;
let _lastFeedbackConfidence = 50;

// ── V23: Personal baseline calibration ──
let _personalBaseline = null;
try {
  var saved = localStorage.getItem('fitai_pose_baseline');
  if (saved) _personalBaseline = JSON.parse(saved);
} catch (e) { _personalBaseline = null; }
if (!_personalBaseline) {
  _personalBaseline = { squat_knee: 90, squat_hip: 70, pushup_elbow: 90, lunge_knee: 90 };
}

export function getBaseline() { return _personalBaseline; }

export function saveBaseline(exId, values) {
  if (!_personalBaseline) _personalBaseline = {};
  if (exId === 'squat') { _personalBaseline.squat_knee = values.knee; _personalBaseline.squat_hip = values.hip; }
  else if (exId === 'pushup') { _personalBaseline.pushup_elbow = values.elbow; }
  else if (exId === 'lunge') { _personalBaseline.lunge_knee = values.knee; }
  try { localStorage.setItem('fitai_pose_baseline', JSON.stringify(_personalBaseline)); } catch (e) {}
}

export function startCalibration(exId) {
  // Switch to the exercise and enter calibration mode
  switchExercise(exId);
  _isCalibrating = exId;
  _calibrationSamples = [];
  _calibrationReps = 3;
  if (_cueEl) { _cueEl.textContent = '标定模式：请做 ' + _calibrationReps + ' 个标准动作'; _cueEl.className = 'pose-cue'; }
  speak('请做' + _calibrationReps + '个你认为最标准的' + (_EX_NAMES[exId] || exId));
  startPoseSession();
}

let _isCalibrating = null;
let _calibrationSamples = [];
let _calibrationReps = 3;

// ── MediaPipe keypoint indices ──
const KP = {
  LEFT_SHOULDER: 11, RIGHT_SHOULDER: 12,
  LEFT_HIP: 23, RIGHT_HIP: 24,
  LEFT_KNEE: 25, RIGHT_KNEE: 26,
  LEFT_ANKLE: 27, RIGHT_ANKLE: 28,
  LEFT_EAR: 7, RIGHT_EAR: 8,
  NOSE: 0,
};

// ── Initialize ──

var _EX_NAMES = {squat:'深蹲',pushup:'俯卧撑',plank:'平板支撑',lunge:'箭步蹲',ytw:'肩部 YTW'};

export function switchExercise(exId) {
  if (_currentExercise === exId) return;
  stopPoseSession();
  _currentExercise = exId;
  document.querySelectorAll('.ex-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.ex === exId);
  });
  var btn = document.getElementById('pose-start-btn');
  if (btn) btn.textContent = '开始' + (_EX_NAMES[exId] || exId) + '检测';
}

export async function initPose() {
  // Model is loaded on demand in startPoseSession()
}

function getMidpoint(lm, i1, i2) {
  return { x: (lm[i1].x + lm[i2].x) / 2, y: (lm[i1].y + lm[i2].y) / 2, z: (lm[i1].z + lm[i2].z) / 2 };
}

function calcAngle(a, b, c) {
  // 3D distance using MediaPipe's z-coordinate for better accuracy
  var ab = Math.sqrt(Math.pow(b.x - a.x, 2) + Math.pow(b.y - a.y, 2) + Math.pow((b.z||0) - (a.z||0), 2));
  var bc = Math.sqrt(Math.pow(c.x - b.x, 2) + Math.pow(c.y - b.y, 2) + Math.pow((c.z||0) - (b.z||0), 2));
  var ac = Math.sqrt(Math.pow(c.x - a.x, 2) + Math.pow(c.y - a.y, 2) + Math.pow((c.z||0) - (a.z||0), 2));
  if (ab === 0 || bc === 0) return 180;
  var cosAngle = (ab * ab + bc * bc - ac * ac) / (2 * ab * bc);
  cosAngle = Math.max(-1, Math.min(1, cosAngle));
  return Math.round(Math.acos(cosAngle) * 180 / Math.PI);
}

function calcVerticalAngle(a, b) {
  var dx = b.x - a.x;
  var dy = b.y - a.y;
  var angle = Math.atan2(Math.abs(dx), Math.abs(dy)) * 180 / Math.PI;
  return Math.round(angle);
}

// ── V23: Form quality score with green zone (±10° no penalty) ──

// Green zone helper: deviation beyond margin is penalized
function _greenDev(actual, ideal, margin) {
  return Math.max(0, Math.abs(actual - ideal) - margin);
}

function computeQuality(kneeAngle, hipAngle, backAngle, kneeValgus) {
  return _computeSquatQuality(kneeAngle, hipAngle, backAngle, kneeValgus);
}

function _computeSquatQuality(kneeAngle, hipAngle, backAngle, kneeValgus) {
  var idealKnee = (_personalBaseline && _personalBaseline.squat_knee) || 90;
  var idealHip = (_personalBaseline && _personalBaseline.squat_hip) || 70;
  // Green zone: ±10° knee, ±10° hip, ±5° back, ±3 valgus — no penalty
  var kneeDev = _greenDev(kneeAngle, idealKnee, 10);
  var hipDev = _greenDev(hipAngle, idealHip, 10);
  var backDev = _greenDev(backAngle, 0, 5);
  var valgusDev = _greenDev(kneeValgus, 0, 3);
  var kneeQ = Math.max(0, 100 - kneeDev * 2.0);
  var hipQ = Math.max(0, 100 - hipDev * 2.0);
  var backQ = Math.max(0, 100 - backDev * 3.0);
  var valgusQ = Math.max(0, 100 - valgusDev * 10);
  return Math.round(kneeQ * 0.35 + hipQ * 0.25 + backQ * 0.25 + valgusQ * 0.15);
}

function computePushupQuality(elbowAngle, bodyLine) {
  var idealElbow = (_personalBaseline && _personalBaseline.pushup_elbow) || 90;
  var elbowDev = _greenDev(elbowAngle, idealElbow, 10);
  var bodyDev = _greenDev(bodyLine, 0, 3);
  var elbowQ = Math.max(0, 100 - elbowDev * 2.0);
  var bodyQ = Math.max(0, 100 - bodyDev * 10);
  return Math.round(elbowQ * 0.5 + bodyQ * 0.5);
}

function computeLungeQuality(frontKneeAngle, torsoAngle) {
  var idealKnee = (_personalBaseline && _personalBaseline.lunge_knee) || 90;
  var kneeDev = _greenDev(frontKneeAngle, idealKnee, 10);
  var torsoDev = _greenDev(torsoAngle, 0, 5);
  var kneeQ = Math.max(0, 100 - kneeDev * 2.0);
  var torsoQ = Math.max(0, 100 - torsoDev * 4);
  return Math.round(kneeQ * 0.6 + torsoQ * 0.4);
}

function computePlankQuality(bodyAngle, hipSag) {
  var bodyDev = _greenDev(bodyAngle, 180, 5);
  var sagDev = _greenDev(hipSag, 0, 0.02);
  var bodyQ = Math.max(0, 100 - bodyDev * 3);
  var sagQ = Math.max(0, 100 - sagDev * 200);
  return Math.round(bodyQ * 0.5 + sagQ * 0.5);
}

// ── Startup ──

export async function startPoseSession() {
  if (_isRunning) return;
  var container = document.getElementById('panel-pose');
  if (!container) return;

  _videoEl = container.querySelector('#pose-video');
  _canvasEl = container.querySelector('#pose-canvas');
  _indicatorsEl = container.querySelector('#pose-indicators');
  _repEl = container.querySelector('#pose-rep-count');
  _cueEl = container.querySelector('#pose-cue');
  _fatigueBarEl = container.querySelector('#pose-fatigue-bar');
  _ctx = _canvasEl ? _canvasEl.getContext('2d') : null;

  if (!_videoEl || !_canvasEl) return;

  try {
    var stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 480, height: 360, facingMode: 'user' }
    });
    _videoEl.srcObject = stream;
    await _videoEl.play();

    if (!_poseLandmarker) {
      console.log('pose: loading vision bundle...');
      var Vision = await import('/mediapipe/vision_bundle.mjs?v=121364');
      console.log('pose: bundle loaded, init FilesetResolver...');
      var fileset = await Vision.FilesetResolver.forVisionTasks('/mediapipe/wasm');
      console.log('pose: FilesetResolver ready, creating PoseLandmarker...');

      // Try GPU first, then CPU fallback
      var delegates = ['GPU', 'CPU'];
      var lastErr = null;
      for (var d = 0; d < delegates.length; d++) {
        try {
          _poseLandmarker = await Vision.PoseLandmarker.createFromOptions(fileset, {
            baseOptions: {
              modelAssetPath: '/mediapipe/pose_landmarker_full.task?v=121364',
              delegate: delegates[d]
            },
            runningMode: 'VIDEO',
            numPoses: 1,
            minPoseDetectionConfidence: 0.5,
            minPosePresenceConfidence: 0.5,
            minTrackingConfidence: 0.4,
          });
          console.log('pose: PoseLandmarker OK, delegate=' + delegates[d]);
          break;
        } catch (e) {
          lastErr = e;
          console.warn('pose: delegate ' + delegates[d] + ' failed:', e.message || e);
        }
      }
      if (!_poseLandmarker) {
        throw lastErr || new Error('Failed to create PoseLandmarker');
      }
    }

    _isRunning = true;
    _repCount = 0;
    _repState = 'up';
    _repMetrics = [];
    _qualityScores = [];
    _currentRepMinKnee = 180;
    _currentRepMinHip = 180;
    _currentRepMaxBack = 0;
    _currentRepMaxValgus = 0;
    _currentRepStartTime = Date.now();
    _changepoint.reset();
    _conformalKnee.reset();
    _conformalHip.reset();
    _lastFeedbackConfidence = 50;
    _lastSpokenCue = '';
    _lastSpeakTime = 0;
    _plankStartTime = 0;
    _ytwPhaseTimer = 0;
    _visibilityChecked = false;
    _bodyVisible = { full: true, lower: true };
    if (_poseLandmarker) _poseLandmarker._warnedVisibility = false;
    var ld2 = document.getElementById('pose-live-diag');
    if (ld2) ld2.style.display = 'none';

    // Show video feed immediately even before model loads
    if (_videoEl) _videoEl.style.display = '';
    drawMirrorFallback();

    var sb = document.getElementById('pose-start-btn');
    var tb = document.getElementById('pose-stop-btn');
    if (sb) sb.style.display = 'none';
    if (tb) tb.style.display = '';
    hideFatigueWarning();
    hideDiagnosisCard();
    updateUI();
    detectLoop();
  } catch (e) {
    console.error('pose: camera or model load failed', e);
    if (_cueEl) _cueEl.textContent = '摄像头或模型加载失败，请检查权限和设备';
  }
}

export function stopPoseSession() {
  _isRunning = false;
  if (_animationId) { cancelAnimationFrame(_animationId); _animationId = null; }
  if (_videoEl && _videoEl.srcObject) {
    _videoEl.srcObject.getTracks().forEach(function(t) { t.stop(); });
    _videoEl.srcObject = null;
  }
  // Send rep data for server-side causal analysis
  if (_repMetrics.length >= 3) {
    sendRepDataForAnalysis();
  }
  var sb = document.getElementById('pose-start-btn');
  var tb = document.getElementById('pose-stop-btn');
  if (sb) sb.style.display = '';
  if (tb) tb.style.display = 'none';
  if (_cueEl) { _cueEl.textContent = '点击开始'; _cueEl.className = 'pose-cue'; }
  hideFatigueWarning();
  var ld3 = document.getElementById('pose-live-diag');
  if (ld3) ld3.style.display = 'none';
}

// ── V21: Live inline diagnosis (every N reps during exercise) ──

function requestLiveDiagnosis() {
  if (_repMetrics.length < 5 || _repMetrics.length % 5 !== 0) return;
  var payload = {
    exercise: _currentExercise,
    reps: _repMetrics.slice(-10),
    changepoint_state: _changepoint.getState()
  };
  fetch('/api/pose/analyze-set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(r) { return r.json(); })
  .then(function(data) {
    if (data && data.diagnosis && data.confidence > 0.4) {
      showLiveDiagnosis(data);
    }
  }).catch(function() {});
}

function showLiveDiagnosis(data) {
  var el = document.getElementById('pose-live-diag');
  if (!el) {
    el = document.createElement('div');
    el.id = 'pose-live-diag';
    el.className = 'pose-live-diag';
    var container = document.getElementById('panel-pose');
    if (container) container.appendChild(el);
  }
  var confPct = Math.round((data.confidence || 0.5) * 100);
  el.innerHTML = '<span class="pld-icon">🔍</span><span class="pld-text">' + (data.diagnosis || '').slice(0, 60) + '</span><span class="pld-conf">' + confPct + '%</span>';
  el.style.display = '';
  clearTimeout(el._hideTimer);
  el._hideTimer = setTimeout(function() { el.style.opacity = '0.5'; }, 8000);
}

// ── Send rep data to server for causal diagnosis (full, on stop) ──

function sendRepDataForAnalysis() {
  var payload = {
    exercise: _currentExercise,
    reps: _repMetrics.slice(),
    changepoint_state: _changepoint.getState()
  };
  fetch('/api/pose/analyze-set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(r) { return r.json(); })
  .then(function(data) {
    if (data && data.diagnosis) {
      showDiagnosisCard(data);
    }
  }).catch(function(e) {
    console.warn('pose: analysis request failed (endpoint may not exist yet)', e);
  });
}

// ── Mirror fallback (show camera feed on canvas before model loads) ──

function drawMirrorFallback() {
  if (!_ctx || !_canvasEl || !_videoEl) return;
  function _mirror() {
    if (!_poseLandmarker && _isRunning && _videoEl && _videoEl.readyState >= 2) {
      var w = _canvasEl.width, h = _canvasEl.height;
      _ctx.save();
      _ctx.scale(-1, 1);
      _ctx.drawImage(_videoEl, -w, 0, w, h);
      _ctx.restore();
      requestAnimationFrame(_mirror);
    }
  }
  requestAnimationFrame(_mirror);
}

// ── Detection Loop ──

var _frameSkip = 0;
function detectLoop() {
  if (!_isRunning) return;

  _frameSkip++;
  var now = performance.now();
  // Skip every other frame to reduce GPU/CPU load on slower devices
  if (_poseLandmarker && _videoEl && _videoEl.readyState >= 3 && _frameSkip % 2 === 0) {
    try {
      var results = _poseLandmarker.detectForVideo(_videoEl, now);
      if (results && results.landmarks && results.landmarks.length > 0) {
        if (!_poseLandmarker._loggedDetect) {
          console.log('pose: FIRST DETECTION! landmarks=' + results.landmarks[0].length);
          _poseLandmarker._loggedDetect = true;
        }
        processLandmarks(results.landmarks[0]);
      }
    } catch (e) {
      // Model not ready yet or frame skipped, keep trying
    }
  }
  _animationId = requestAnimationFrame(detectLoop);
}

// ── Core Analysis (multi-exercise dispatcher) ──

var _bodyVisible = { full: true, lower: true };
var _visibilityChecked = false;

function checkBodyVisibility(lm) {
  // Check if knees are actually visible (not just extrapolated)
  // Visible knees have reasonable y > hip.y and < ankle.y
  var hipY = (lm[KP.LEFT_HIP].y + lm[KP.RIGHT_HIP].y) / 2;
  var kneeY = (lm[KP.LEFT_KNEE].y + lm[KP.RIGHT_KNEE].y) / 2;
  var ankleY = (lm[KP.LEFT_ANKLE].y + lm[KP.RIGHT_ANKLE].y) / 2;
  var kneeVisibility = lm[KP.LEFT_KNEE].visibility || 0;
  // MediaPipe visibility < 0.5 means the joint is likely occluded/guessed
  var lkV = lm[KP.LEFT_KNEE].visibility;
  var rkV = lm[KP.RIGHT_KNEE].visibility;
  _bodyVisible.lower = (typeof lkV === 'undefined' || lkV > 0.5) && (typeof rkV === 'undefined' || rkV > 0.5);
  _bodyVisible.full = _bodyVisible.lower && kneeY > hipY && hipY > 0.1;
  if (!_visibilityChecked && !_bodyVisible.lower) {
    _visibilityChecked = true;
    return false;
  }
  _visibilityChecked = true;
  return _bodyVisible.lower;
}

function processLandmarks(lm) {
  checkBodyVisibility(lm);
  switch (_currentExercise) {
    case 'pushup': return processPushup(lm);
    case 'plank': return processPlank(lm);
    case 'lunge': return processLunge(lm);
    case 'ytw': return processYtw(lm);
    default: return processSquat(lm);
  }
}

// ── Squat Analysis ──

function processSquat(lm) {
  var shoulder = getMidpoint(lm, KP.LEFT_SHOULDER, KP.RIGHT_SHOULDER);
  var hip = getMidpoint(lm, KP.LEFT_HIP, KP.RIGHT_HIP);
  var knee = getMidpoint(lm, KP.LEFT_KNEE, KP.RIGHT_KNEE);
  var ankle = getMidpoint(lm, KP.LEFT_ANKLE, KP.RIGHT_ANKLE);

  var kneeAngle = calcAngle(hip, knee, ankle);
  var hipAngle = calcAngle(shoulder, hip, knee);
  var backAngle = calcVerticalAngle(shoulder, hip);
  var kneeValgus = Math.abs(knee.x - ankle.x) * 100;

  var kneeStatus = kneeAngle < 70 ? 'too_deep' : kneeAngle > 120 ? 'shallow' : kneeAngle < 80 ? 'deep' : 'good';
  var hipStatus = hipAngle > 110 ? 'shallow' : 'good';
  var backStatus = backAngle > 40 ? 'rounded' : 'good';
  var valgusStatus = kneeValgus > 8 ? 'caving' : 'good';

  // Track per-rep extremes
  if (kneeAngle < 105) {
    // Bottom position: track min/max values
    if (kneeAngle < _currentRepMinKnee) _currentRepMinKnee = kneeAngle;
    if (hipAngle < _currentRepMinHip) _currentRepMinHip = hipAngle;
    if (backAngle > _currentRepMaxBack) _currentRepMaxBack = backAngle;
    if (kneeValgus > _currentRepMaxValgus) _currentRepMaxValgus = kneeValgus;
  }

  // ── V23: Hard block if lower body invisible for squat ──
  if (!_bodyVisible.lower) {
    if (_cueEl) { _cueEl.textContent = '⛔ 摄像头看不到膝盖，无法检测深蹲'; _cueEl.className = 'pose-cue low-conf'; }
    if (_indicatorsEl) _indicatorsEl.innerHTML = '<div style="color:#f87171;text-align:center;padding:12rpx;">请调整摄像头位置，确保全身可见<br>或切换到上半身动作（俯卧撑/平板/YTW）</div>';
    drawMirrorFallback(lm);
    return;
  }
  // Standing verification: hip must be well above knee to prevent false reps when sitting
  var hipAboveKnee = (knee.y - hip.y) > 0.08;
  var isBottom = kneeAngle < 115 && hipAboveKnee;
  var isTop = kneeAngle > 135 && hipAboveKnee;

  // Rep counting state machine
  if (_repState === 'up' && isBottom) {
    _repState = 'down';
  } else if (_repState === 'down' && isTop) {
    _repState = 'up';
    var now = Date.now();
    if (now - _lastRepTime > 500) {
      _repCount++;
      _lastRepTime = now;

      // ── V21: Record rep metrics ──
      var repDuration = now - _currentRepStartTime;
      var quality = computeQuality(_currentRepMinKnee, _currentRepMinHip, _currentRepMaxBack, _currentRepMaxValgus);

      _repMetrics.push({
        rep: _repCount,
        kneeAngle_min: Math.round(_currentRepMinKnee),
        hipAngle_min: Math.round(_currentRepMinHip),
        backAngle_max: Math.round(_currentRepMaxBack),
        kneeValgus_max: Math.round(_currentRepMaxValgus * 10) / 10,
        quality: quality,
        duration_ms: repDuration
      });

      _qualityScores.push(quality);
      if (_qualityScores.length > 20) _qualityScores.shift();

      // ── V21: Feed to changepoint detector ──
      var cpResult = _changepoint.update(quality);
      if (cpResult.alarm && cpResult.state === 'critical') {
        showFatigueWarning('critical', cpResult.score);
      } else if (cpResult.alarm && cpResult.state === 'warning') {
        showFatigueWarning('warning', cpResult.score);
      }

      // ── V21: Update conformal predictors with actual errors ──
      // Use the difference between raw metric and ideal as "error"
      var kneeError = Math.abs(_currentRepMinKnee - 90);
      var hipError = Math.abs(_currentRepMinHip - 70);
      _conformalKnee.updateAndPredict(_currentRepMinKnee, kneeError);
      _conformalHip.updateAndPredict(_currentRepMinHip, hipError);

      // Reset rep tracking
      _currentRepMinKnee = 180;
      _currentRepMinHip = 180;
      _currentRepMaxBack = 0;
      _currentRepMaxValgus = 0;
      _currentRepStartTime = now;

      // V21: Send rep data to server via WebSocket for real-time trend analysis
      try {
        sendWsMessage({
          type: 'pose_rep',
          data: {
            rep: _repCount,
            kneeAngle_min: Math.round(_currentRepMinKnee),
            hipAngle_min: Math.round(_currentRepMinHip),
            backAngle_max: Math.round(_currentRepMaxBack),
            kneeValgus_max: Math.round(_currentRepMaxValgus * 10) / 10,
            quality: quality
          }
        });
      } catch(e) {}

      updateUI();
      if (_speechEnabled) {
        speak(_repCount + '个');
      }
      requestLiveDiagnosis();
    }
  }

  // ── V21: Confidence-aware feedback cues ──
  var cue = '';
  var cueClass = '';

  // Use conformal confidence to modulate cue language
  var kneeConf = _conformalKnee.getConfidence(kneeAngle);
  var hipConf = _conformalHip.getConfidence(hipAngle);
  _lastFeedbackConfidence = Math.min(kneeConf, hipConf);

  if (kneeStatus === 'shallow') {
    cue = _lastFeedbackConfidence >= 70 ? '再蹲低一点' : '膝盖可能还要再弯一点';
    cueClass = 'warn';
  } else if (kneeStatus === 'too_deep') {
    cue = '不用蹲太深';
    cueClass = 'warn';
  } else if (backStatus === 'rounded') {
    cue = _lastFeedbackConfidence >= 70 ? '挺胸，背部挺直' : '背部注意不要弯';
    cueClass = 'warn';
  } else if (valgusStatus === 'caving') {
    cue = _lastFeedbackConfidence >= 70 ? '膝盖不要内扣' : '膝盖可能有点内扣，注意一下';
    cueClass = 'warn';
  } else if (hipStatus === 'shallow') {
    cue = '臀部再往下坐';
    cueClass = 'warn';
  } else if (isBottom) {
    cue = '深度够了！';
    cueClass = 'good';
  } else if (isTop) {
    cue = '准备好了';
    cueClass = 'good';
  }

  if (cue && Date.now() - _feedbackTimer > 1500) {
    _feedbackTimer = Date.now();
    if (_cueEl) {
      _cueEl.textContent = cue;
      var cls = 'pose-cue ' + cueClass;
      if (_lastFeedbackConfidence < 60 && cueClass === 'warn') cls += ' low-conf';
      _cueEl.className = cls;
    }
    // Only speak when cue CHANGES and at least 3s since last speech
    if (_speechEnabled && cue !== _lastSpokenCue && Date.now() - _lastSpeakTime > 3000) {
      _lastSpokenCue = cue;
      _lastSpeakTime = Date.now();
      speak(cue);
    }
  }

  updateIndicators(kneeAngle, hipAngle, backAngle, kneeValgus, kneeStatus, hipStatus, backStatus, valgusStatus);
  drawOverlay(lm);
}

// ── V21: Fatigue Warning ──

function showFatigueWarning(level, score) {
  if (!_fatigueBarEl) return;
  _fatigueBarEl.style.display = '';
  _fatigueBarEl.className = 'pose-fatigue-bar ' + level;
  if (level === 'critical') {
    _fatigueBarEl.textContent = '🛑 动作质量明显下降（' + score + '分），建议休息30秒';
    speak('动作质量下降，建议休息一下');
  } else {
    _fatigueBarEl.textContent = '⚠️ 动作质量有下降趋势（' + score + '分），注意控制';
  }
}

function hideFatigueWarning() {
  if (_fatigueBarEl) _fatigueBarEl.style.display = 'none';
}

// ── V21: Diagnosis Card ──

function showDiagnosisCard(data) {
  var container = document.getElementById('panel-pose');
  if (!container) return;
  var existing = container.querySelector('.pose-diagnosis-card');
  if (existing) existing.remove();

  var card = document.createElement('div');
  card.className = 'pose-diagnosis-card';
  var confPct = Math.round((data.confidence || 0.5) * 100);
  card.innerHTML =
    '<div class="pd-header">🔍 动作分析完成</div>' +
    '<div class="pd-body">' +
      '<div class="pd-diag">' + (data.diagnosis || '') + '</div>' +
      (data.causal_path ? '<div class="pd-path">因果链：' + data.causal_path + '</div>' : '') +
      '<div class="pd-conf">置信度：' + confPct + '%</div>' +
      (data.correction ? '<div class="pd-corr">💡 ' + data.correction + '</div>' : '') +
    '</div>' +
    '<button class="pd-dismiss" onclick="this.parentElement.remove()">已了解</button>';
  container.appendChild(card);
}

function hideDiagnosisCard() {
  var cards = document.querySelectorAll('.pose-diagnosis-card');
  cards.forEach(function(c) { c.remove(); });
}

// ── Indicators ──

function updateIndicators(kneeAngle, hipAngle, backAngle, kneeValgus, kneeStatus, hipStatus, backStatus, valgusStatus) {
  if (!_indicatorsEl) return;

  // V21: Add confidence level to knee indicator
  var kneeConfNote = '';
  var kc = _conformalKnee.getConfidence(kneeAngle);
  if (kc < 50) kneeConfNote = ' <span class="pi-conf-low">?</span>';
  else if (kc >= 80) kneeConfNote = ' <span class="pi-conf-high">✓</span>';

  _indicatorsEl.innerHTML =
    '<div class="pi-row ' + kneeStatus + '"><span class="pi-label">膝角</span><span class="pi-val">' + kneeAngle + '°' + kneeConfNote + '</span></div>' +
    '<div class="pi-row ' + hipStatus + '"><span class="pi-label">髋角</span><span class="pi-val">' + hipAngle + '°</span></div>' +
    '<div class="pi-row ' + backStatus + '"><span class="pi-label">背角</span><span class="pi-val">' + backAngle + '°</span></div>' +
    '<div class="pi-row ' + valgusStatus + '"><span class="pi-label">膝距</span><span class="pi-val">' + kneeValgus.toFixed(1) + '</span></div>';
}

function updateUI() {
  if (_repEl) _repEl.textContent = _repCount;
}

// ── Canvas Overlay ──

function drawOverlay(lm) {
  if (!_ctx || !_canvasEl) return;
  var w = _canvasEl.width, h = _canvasEl.height;
  _ctx.clearRect(0, 0, w, h);

  // Mirror for front-facing camera (natural mirror UX)
  _ctx.save();
  _ctx.scale(-1, 1);
  _ctx.translate(-w, 0);

  // Draw skeleton
  var bones = [
    [11,12], [11,23], [12,24], [23,24],
    [23,25], [24,26], [25,27], [26,28],
    [11,13], [13,15], [12,14], [14,16],
  ];

  _ctx.strokeStyle = 'rgba(61,214,140,0.6)';
  _ctx.lineWidth = 2;
  _ctx.beginPath();
  bones.forEach(function(pair) {
    var a = lm[pair[0]], b = lm[pair[1]];
    _ctx.moveTo(a.x * w, a.y * h);
    _ctx.lineTo(b.x * w, b.y * h);
  });
  _ctx.stroke();

  // Draw key joints
  var keyJoints = [11,12,23,24,25,26,27,28];
  keyJoints.forEach(function(i) {
    var p = lm[i];
    _ctx.beginPath();
    _ctx.arc(p.x * w, p.y * h, 4, 0, Math.PI * 2);
    _ctx.fillStyle = 'rgba(61,214,140,0.9)';
    _ctx.fill();
  });

  // Draw angle arc at knee
  var hip = getMidpoint(lm, KP.LEFT_HIP, KP.RIGHT_HIP);
  var knee = getMidpoint(lm, KP.LEFT_KNEE, KP.RIGHT_KNEE);
  var ankle = getMidpoint(lm, KP.LEFT_ANKLE, KP.RIGHT_ANKLE);

  _ctx.strokeStyle = 'rgba(251,146,60,0.8)';
  _ctx.lineWidth = 2;
  _ctx.beginPath();
  _ctx.moveTo(hip.x * w, hip.y * h);
  _ctx.lineTo(knee.x * w, knee.y * h);
  _ctx.lineTo(ankle.x * w, ankle.y * h);
  _ctx.stroke();

  // Restore from mirror transform before drawing UI overlays
  _ctx.restore();

  // ── V21: Draw quality trend mini chart (bottom-right) ──
  drawQualityChart(w, h);
}

// ── V21: Mini quality trend chart ──

function drawQualityChart(w, h) {
  if (_qualityScores.length < 2) return;

  var chartW = 80, chartH = 40;
  var cx = w - chartW - 10, cy = h - chartH - 10;

  // Background
  _ctx.fillStyle = 'rgba(0,0,0,0.45)';
  _ctx.fillRect(cx - 4, cy - 12, chartW + 8, chartH + 16);

  // Label
  _ctx.fillStyle = 'rgba(255,255,255,0.7)';
  _ctx.font = '9px sans-serif';
  _ctx.fillText('质量分', cx, cy - 2);

  // Grid lines
  _ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  _ctx.lineWidth = 0.5;
  [25, 50, 75].forEach(function(level) {
    var gy = cy + chartH - (level / 100) * chartH;
    _ctx.beginPath();
    _ctx.moveTo(cx, gy);
    _ctx.lineTo(cx + chartW, gy);
    _ctx.stroke();
  });

  // Trend line
  var maxPts = chartW / 3; // fit ~1 point per 3px
  var scores = _qualityScores;
  if (scores.length > maxPts) {
    scores = scores.slice(scores.length - maxPts);
  }
  var xStep = chartW / Math.max(scores.length - 1, 1);

  _ctx.strokeStyle = 'rgba(251,191,36,0.9)';
  _ctx.lineWidth = 1.5;
  _ctx.beginPath();
  scores.forEach(function(s, i) {
    var px = cx + i * xStep;
    var py = cy + chartH - (s / 100) * chartH;
    if (i === 0) _ctx.moveTo(px, py);
    else _ctx.lineTo(px, py);
  });
  _ctx.stroke();

  // V22: Fatigue warning threshold (red dashed line at quality=60)
  if (_changepoint.getState().state !== 'normal') {
    var warnY = cy + chartH - 0.6 * chartH;  // 60% quality = warning zone
    _ctx.strokeStyle = 'rgba(248,113,113,0.7)';
    _ctx.lineWidth = 1;
    _ctx.setLineDash([3, 3]);
    _ctx.beginPath();
    _ctx.moveTo(cx, warnY);
    _ctx.lineTo(cx + chartW, warnY);
    _ctx.stroke();
    _ctx.setLineDash([]);
    // Label
    _ctx.fillStyle = 'rgba(248,113,113,0.8)';
    _ctx.font = '7px sans-serif';
    _ctx.fillText('⚠', cx + chartW + 2, warnY + 3);
  }

  // Latest value
  var lastScore = _qualityScores[_qualityScores.length - 1];
  var lx = cx + (scores.length - 1) * xStep;
  var ly = cy + chartH - (lastScore / 100) * chartH;
  _ctx.beginPath();
  _ctx.arc(lx, ly, 3, 0, Math.PI * 2);
  _ctx.fillStyle = lastScore >= 70 ? '#3dd68c' : lastScore >= 50 ? '#fbbf24' : '#f87171';
  _ctx.fill();
}

// ── Push-up Analysis (V22) ──

function processPushup(lm) {
  var shoulder = getMidpoint(lm, KP.LEFT_SHOULDER, KP.RIGHT_SHOULDER);
  var hip = getMidpoint(lm, KP.LEFT_HIP, KP.RIGHT_HIP);
  var elbowMid = {x: (lm[13].x + lm[14].x) / 2, y: (lm[13].y + lm[14].y) / 2, z: 0};
  var wristMid = {x: (lm[15].x + lm[16].x) / 2, y: (lm[15].y + lm[16].y) / 2, z: 0};
  var elbowAngle = calcAngle(shoulder, elbowMid, wristMid);
  var bodyLine = Math.abs(shoulder.y - hip.y) * 100;

  var isDown = elbowAngle < 100;
  var isUp = elbowAngle > 150;

  if (_repState === 'up' && isDown) { _repState = 'down'; }
  else if (_repState === 'down' && isUp) {
    _repState = 'up';
    var now = Date.now();
    if (now - _lastRepTime > 500) {
      _repCount++;
      _lastRepTime = now;
      var quality = computePushupQuality(elbowAngle, bodyLine);
      _repMetrics.push({rep:_repCount, elbowAngle_min:Math.round(elbowAngle), bodyLine_max:Math.round(bodyLine*10)/10, quality:quality, duration_ms:now-_currentRepStartTime});
      _qualityScores.push(quality); if (_qualityScores.length > 20) _qualityScores.shift();
      var cpResult = _changepoint.update(quality);
      if (cpResult.alarm && cpResult.state === 'critical') showFatigueWarning('critical', cpResult.score);
      else if (cpResult.alarm && cpResult.state === 'warning') showFatigueWarning('warning', cpResult.score);
      _currentRepStartTime = now;
      try { sendWsMessage({type:'pose_rep',data:{rep:_repCount,elbowAngle_min:Math.round(elbowAngle),bodyLine_max:Math.round(bodyLine*10)/10,quality:quality}}); } catch(e) {}
      updateUI();
      if (_speechEnabled) speak(_repCount + '个');
      requestLiveDiagnosis();
    }
  }

  var cue = '';
  if (elbowAngle < 70) cue = '不用下那么低';
  else if (elbowAngle > 100 && _repState === 'down') cue = '再往下一点';
  else if (bodyLine > 5) cue = '身体不要塌腰，收紧核心';
  else if (isDown) cue = '深度够了！';
  else if (isUp) cue = '准备好了';

  if (cue && Date.now() - _feedbackTimer > 1500) {
    _feedbackTimer = Date.now();
    if (_cueEl) { _cueEl.textContent = cue; _cueEl.className = 'pose-cue ' + (cue.indexOf('够了') > -1 ? 'good' : 'warn'); }
    if (_speechEnabled && cue.indexOf('核心') > -1) speak(cue);
  }

  updateIndicators(elbowAngle, 0, bodyLine, 0, elbowAngle < 70 ? 'too_deep' : elbowAngle > 120 ? 'shallow' : 'good', 'good', bodyLine > 5 ? 'rounded' : 'good', 'good');
  drawOverlay(lm);
}

// ── Plank Analysis (V22, timer-based) ──

var _plankStartTime = 0;
function processPlank(lm) {
  var shoulder = getMidpoint(lm, KP.LEFT_SHOULDER, KP.RIGHT_SHOULDER);
  var hip = getMidpoint(lm, KP.LEFT_HIP, KP.RIGHT_HIP);
  var ankle = getMidpoint(lm, KP.LEFT_ANKLE, KP.RIGHT_ANKLE);
  var bodyAngle = calcAngle(shoulder, hip, ankle);
  var hipSag = (shoulder.y + ankle.y) / 2 - hip.y;

  if (!_plankStartTime) _plankStartTime = Date.now();
  var elapsed = Math.floor((Date.now() - _plankStartTime) / 1000);

  var cue = '';
  if (Math.abs(180 - bodyAngle) > 5 && hipSag > 0.03) cue = '臀部不要塌，收紧核心';
  else if (Math.abs(180 - bodyAngle) > 5 && hipSag < -0.03) cue = '臀部不要翘';
  else if (elapsed > 0) cue = elapsed + ' 秒';

  if (cue && Date.now() - _feedbackTimer > 2000) {
    _feedbackTimer = Date.now();
    if (_cueEl) { _cueEl.textContent = cue; _cueEl.className = 'pose-cue good'; }
    if (_speechEnabled && elapsed > 0 && elapsed % 15 === 0 && elapsed < 120) speak(elapsed + '秒');
  }

  if (_repEl) _repEl.textContent = elapsed;

  updateIndicators(bodyAngle, 0, Math.abs(180 - bodyAngle), 0, Math.abs(180 - bodyAngle) > 8 ? 'shallow' : 'good', 'good', Math.abs(hipSag) > 0.03 ? 'rounded' : 'good', 'good');
  drawOverlay(lm);
}

// ── Lunge Analysis (V22) ──

function processLunge(lm) {
  if (!_bodyVisible.lower) {
    if (_cueEl) { _cueEl.textContent = '⛔ 摄像头看不到膝盖，无法检测箭步蹲'; _cueEl.className = 'pose-cue low-conf'; }
    drawMirrorFallback(lm);
    return;
  }
  var shoulder = getMidpoint(lm, KP.LEFT_SHOULDER, KP.RIGHT_SHOULDER);
  var hip = getMidpoint(lm, KP.LEFT_HIP, KP.RIGHT_HIP);
  var frontKnee = lm[KP.LEFT_KNEE];
  var frontHip = lm[KP.LEFT_HIP];
  var frontAnkle = lm[KP.LEFT_ANKLE];
  var backKnee = lm[KP.RIGHT_KNEE];

  var frontKneeAngle = calcAngle(frontHip, frontKnee, frontAnkle);
  var torsoAngle = calcVerticalAngle(shoulder, hip);

  var isDown = frontKneeAngle < 100;
  var isUp = frontKneeAngle > 160;

  if (_repState === 'up' && isDown) { _repState = 'down'; }
  else if (_repState === 'down' && isUp) {
    _repState = 'up';
    var now = Date.now();
    if (now - _lastRepTime > 800) {
      _repCount++;
      _lastRepTime = now;
      var quality = computeLungeQuality(frontKneeAngle, torsoAngle);
      _repMetrics.push({rep:_repCount, frontKneeAngle_min:Math.round(frontKneeAngle), torsoAngle_max:Math.round(torsoAngle), quality:quality, duration_ms:now-_currentRepStartTime});
      _qualityScores.push(quality); if (_qualityScores.length > 20) _qualityScores.shift();
      var cpResult = _changepoint.update(quality);
      if (cpResult.alarm && cpResult.state === 'critical') showFatigueWarning('critical', cpResult.score);
      else if (cpResult.alarm && cpResult.state === 'warning') showFatigueWarning('warning', cpResult.score);
      _currentRepStartTime = now;
      try { sendWsMessage({type:'pose_rep',data:{rep:_repCount,frontKneeAngle_min:Math.round(frontKneeAngle),torsoAngle_max:Math.round(torsoAngle),quality:quality}}); } catch(e) {}
      updateUI();
      if (_speechEnabled) speak(_repCount + '个');
      requestLiveDiagnosis();
    }
  }

  var cue = '';
  if (frontKneeAngle < 80) cue = '前膝弯太多了';
  else if (frontKneeAngle > 110 && _repState === 'down') cue = '再往下蹲一点';
  else if (torsoAngle > 25) cue = '身体保持直立';
  else if (backKnee.y > 0.85) cue = '后膝快要触地了';

  if (cue && Date.now() - _feedbackTimer > 1500) {
    _feedbackTimer = Date.now();
    if (_cueEl) { _cueEl.textContent = cue; _cueEl.className = 'pose-cue warn'; }
    if (_speechEnabled && (cue.indexOf('不') > -1 || cue.indexOf('再') > -1)) speak(cue);
  }

  updateIndicators(frontKneeAngle, 0, torsoAngle, 0, frontKneeAngle < 80 ? 'too_deep' : frontKneeAngle > 120 ? 'shallow' : 'good', 'good', torsoAngle > 25 ? 'rounded' : 'good', 'good');
  drawOverlay(lm);
}

// ── YTW Shoulder Analysis (V22) ──

var _ytwPhase = 0;
var _ytwPhaseTimer = 0;
function processYtw(lm) {
  var shoulderL = lm[KP.LEFT_SHOULDER];
  var wristL = lm[15];
  var wristR = lm[16];
  var armAngleL = calcVerticalAngle(shoulderL, wristL);
  var armAngleR = calcVerticalAngle({x: lm[KP.RIGHT_SHOULDER].x, y: lm[KP.RIGHT_SHOULDER].y, z: 0}, wristR);
  var avgArmAngle = (armAngleL + armAngleR) / 2;

  var phaseNames = ['Y', 'T', 'W'];
  var now = Date.now();

  if (avgArmAngle < 55) _ytwPhase = 0;
  else if (avgArmAngle >= 55 && avgArmAngle < 100) _ytwPhase = 1;
  else _ytwPhase = 2;

  if (_ytwPhaseTimer && now - _ytwPhaseTimer > 3000 && _ytwPhase === 0) {
    _repCount++;
    var quality = Math.max(0, 100 - Math.abs(avgArmAngle - 45) * 1.5);
    _repMetrics.push({rep:_repCount, avgArmAngle:Math.round(avgArmAngle), quality:quality});
    _qualityScores.push(quality); if (_qualityScores.length > 20) _qualityScores.shift();
    _ytwPhaseTimer = 0;
    try { sendWsMessage({type:'pose_rep',data:{rep:_repCount,avgArmAngle:Math.round(avgArmAngle),quality:quality}}); } catch(e) {}
    updateUI();
    if (_speechEnabled) speak(_repCount + '组');
    requestLiveDiagnosis();
  }
  if (!_ytwPhaseTimer && _ytwPhase === 0) _ytwPhaseTimer = now;

  var cue = '';
  if (_ytwPhase === 0) cue = 'Y — 手臂上举，不要耸肩';
  else if (_ytwPhase === 1) cue = 'T — 手臂侧平举';
  else cue = 'W — 屈肘下拉';

  if (cue && Date.now() - _feedbackTimer > 2000) {
    _feedbackTimer = Date.now();
    if (_cueEl) { _cueEl.textContent = cue; _cueEl.className = 'pose-cue good'; }
  }

  updateIndicators(avgArmAngle, 0, 0, 0, 'good', 'good', 'good', 'good');
  drawOverlay(lm);
}

// ── Voice Cues ──

function speak(text) {
  try {
    if (!('speechSynthesis' in window)) return;
    var u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN';
    u.rate = 0.85;    // Slower = clearer
    u.volume = 0.6;
    u.pitch = 1.0;

    // Try to pick a better Chinese voice
    var voices = speechSynthesis.getVoices();
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].lang === 'zh-CN' && voices[i].name.indexOf('Yun') > -1) {
        u.voice = voices[i]; break;  // Microsoft Yunyang/Yunxi
      }
    }
    if (!u.voice) {
      for (var j = 0; j < voices.length; j++) {
        if (voices[j].lang.indexOf('zh') === 0) { u.voice = voices[j]; break; }
      }
    }

    // Don't cancel previous speech — let it finish naturally
    if (!speechSynthesis.speaking) {
      speechSynthesis.speak(u);
    }
  } catch (e) {}
}

export function toggleSpeech() {
  _speechEnabled = !_speechEnabled;
  return _speechEnabled;
}

export function getRepCount() {
  return _repCount;
}

export function resetReps() {
  _repCount = 0;
  _repMetrics = [];
  _qualityScores = [];
  _changepoint.reset();
  _conformalKnee.reset();
  _conformalHip.reset();
  _currentRepMinKnee = 180;
  _currentRepMinHip = 180;
  _currentRepMaxBack = 0;
  _currentRepMaxValgus = 0;
  _currentRepStartTime = Date.now();
  hideFatigueWarning();
  hideDiagnosisCard();
  updateUI();
}

// ── V21: Export for external access ──

export function getRepMetrics() {
  return _repMetrics.slice();
}

export function getChangepointState() {
  return _changepoint.getState();
}

export function getConformalState() {
  return { knee: _conformalKnee.getState(), hip: _conformalHip.getState() };
}
