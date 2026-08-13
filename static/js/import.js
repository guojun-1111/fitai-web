// ========== File Import ==========
import { state } from './state.js';
import { triggerConfetti } from './utils.js';

export function initImport() {
  const area = document.getElementById('import-area');
  if (!area) return;

  area.addEventListener('click', () => {
    const fileInput = document.getElementById('import-file-input');
    if (fileInput) fileInput.click();
  });

  area.addEventListener('dragover', (e) => {
    e.preventDefault();
    area.style.borderColor = 'var(--green)';
    area.style.background = 'var(--green-dim)';
  });

  area.addEventListener('dragleave', () => {
    area.style.borderColor = 'var(--border)';
    area.style.background = 'var(--surface)';
  });

  area.addEventListener('drop', (e) => {
    e.preventDefault();
    area.style.borderColor = 'var(--border)';
    area.style.background = 'var(--surface)';
    const file = e.dataTransfer.files[0];
    if (file) processImportFile(file);
  });
}

export function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) processImportFile(file);
  event.target.value = '';
}

export async function processImportFile(file) {
  const resultDiv = document.getElementById('import-result');
  const sizeMB = (file.size / (1024 * 1024)).toFixed(1);

  if (file.size > 200 * 1024 * 1024) {
    if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 文件过大 (' + sizeMB + ' MB)，请拆分后分批导入</span>';
    return;
  }

  if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⏳ 正在解析 ' + file.name + ' (' + sizeMB + ' MB)...<br><span style="font-size:11px">大文件可能需要几十秒，请耐心等待</span></span>';

  try {
    if (window.Worker) {
      const buffer = await file.arrayBuffer();
      const worker = new Worker('/import-worker.js');
      let workerDone = false;

      worker.onmessage = async function(e) {
        if (e.data.type === 'progress') {
          if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⏳ 正在解析 ' + file.name + '... ' + (e.data.percent || 0) + '%</span>';
          return;
        }
        if (e.data.type === 'done') {
          workerDone = true;
          worker.terminate();
          const r = e.data.result || {};
          const records = r.records || [];
          const workouts = r.workouts || [];
          const total = records.length + workouts.length;

          if (total === 0) {
            if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⏳ 浏览器解析未找到数据，已自动切换服务端处理...</span>';
            fallbackServerImport(file, resultDiv);
            return;
          }

          if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">📤 正在上传 ' + total + ' 条记录...</span>';

          const upRes = await fetch('/api/health/import-batch', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ records, workouts }), credentials: 'same-origin',
          });
          if (upRes.status === 401) { if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 请先登录后再导入数据</span>'; return; }
          const upData = await upRes.json();
          const msg = '✅ 导入完成：成功 ' + (upData.count || total) + ' 条';
          if (resultDiv) resultDiv.innerHTML = upData.message ? '✅ ' + upData.message : msg;

          // Refresh panels
          state._homeDataLoaded = false;
          const panelHealthActive = document.getElementById('panel-health').classList.contains('active');
          const panelDashboardActive = document.getElementById('panel-dashboard').classList.contains('active');
          const panelExercisesActive = document.getElementById('panel-exercises').classList.contains('active');
          const panelHistoryActive = document.getElementById('panel-history').classList.contains('active');

          if (panelHealthActive) import('./health.js').then(m => m.loadHealthDashboard(7));
          if (panelDashboardActive) import('./dashboard.js').then(m => m.loadDashboard(7));
          if (panelExercisesActive) import('./exercises.js').then(m => m.loadExerciseAnalysis());
          if (panelHistoryActive) {
            const activeBtn = document.querySelector('.subnav-btn.active');
            if (activeBtn) import('./history.js').then(m => m.loadHistory(activeBtn.dataset.type));
          }
          import('./home.js').then(m => m.loadHomePanel(true));
          window._loadSidebarStats();
          if (window._loadSidebarSessions) window._loadSidebarSessions();
          if (total > 10) triggerConfetti();
          return;
        }
        if (e.data.type === 'error') {
          workerDone = true;
          worker.terminate();
          if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⚠️ 浏览器解析失败（' + e.data.message + '），转为服务端导入...</span>';
          await fallbackServerImport(file, resultDiv);
        }
      };

      worker.onerror = function(err) { worker.terminate(); fallbackServerImport(file, resultDiv); };
      worker.postMessage({ buffer, filename: file.name, platform: 'local_import' }, [buffer]);

      setTimeout(function() {
        if (!workerDone) { worker.terminate(); workerDone = true; fallbackServerImport(file, resultDiv); }
      }, 60000);
      return;
    }

    await fallbackServerImport(file, resultDiv);
  } catch (e) {
    if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 导入失败: ' + e + '</span>';
  }
}

async function fallbackServerImport(file, resultDiv) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('platform', 'local_import');
  try {
    const res = await fetch('/api/health/import-file', { method: 'POST', body: formData, credentials: 'same-origin' });
    if (res.status === 401) { if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 请先登录后再导入数据</span>'; return; }
    if (!res.ok) {
      // Try to read error as JSON first, fallback to text
      let errMsg = 'HTTP ' + res.status;
      try {
        const errData = await res.json();
        errMsg = errData.detail || errData.error || errMsg;
      } catch (jsonErr) {
        const text = await res.text().catch(() => '');
        errMsg = text.slice(0, 100) || errMsg;
      }
      if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 上传失败（' + errMsg + '），请刷新页面后重试</span>';
      return;
    }
    let data;
    try {
      data = await res.json();
    } catch (jsonErr) {
      if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 服务器返回异常，请刷新页面后重试</span>';
      return;
    }
    if (data.job_id) {
      const ahead = data.queue_ahead || 0;
      if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⏳ 已加入处理队列（前方 ' + ahead + ' 人），正在处理...</span>';
      // Poll for job completion
      const jobId = data.job_id;
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch('/api/health/import-status?job_id=' + jobId, { credentials: 'same-origin' });
          const statusData = await statusRes.json();
          if (statusData.status === 'done') {
            clearInterval(pollInterval);
            if (resultDiv) {
              const result = statusData.result || {};
              resultDiv.innerHTML = '<span style="color:var(--green)">✅ ' + (result.message || '导入完成') + '</span>';
            }
          } else if (statusData.status === 'error') {
            clearInterval(pollInterval);
            if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 导入失败: ' + (statusData.error || '未知错误') + '</span>';
          } else {
            if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--text2)">⏳ 正在处理中...（' + (statusData.status || 'queued') + '）</span>';
          }
        } catch (e) {
          // Polling error, keep trying
        }
      }, 3000);
      // Stop polling after 10 minutes
      setTimeout(() => clearInterval(pollInterval), 600000);
    } else if (data.error || data.detail) {
      if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ ' + (data.error || data.detail) + '</span>';
    } else {
      if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--green)">✅ ' + (data.message || '已提交处理') + '</span>';
    }
  } catch (e) {
    if (resultDiv) resultDiv.innerHTML = '<span style="color:var(--red)">❌ 服务端导入失败: ' + e + '</span>';
  }
}

// Export for HTML onclick
window.handleFileSelect = handleFileSelect;
