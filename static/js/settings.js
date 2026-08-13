// ========== Settings (OAuth + Platform Connect) ==========
import { loadHealthDashboard, healthDays } from './health.js';

export function connectPlatform(platformName) {
  const btn = document.getElementById('connect-' + platformName);
  if (btn) { btn.textContent = '⏳ 连接中...'; btn.disabled = true; }
  fetch('/api/health/' + platformName + '/auth-url')
    .then(r => r.json())
    .then(data => {
      if (btn) { btn.textContent = '连接'; btn.disabled = false; }
      if (data.connected) { alert('已成功连接到 ' + platformName + '!\n' + (data.detail || '')); loadSettings(); loadHealthDashboard(healthDays); return; }
      if (data.error) { alert(data.error); return; }
      if (!data.url) { alert('获取授权链接失败，请检查凭据是否正确配置'); return; }
      const width = 600, height = 700;
      const left = (screen.width - width) / 2;
      const top = (screen.height - height) / 2;
      const authWindow = window.open(data.url, 'OAuth_' + platformName, 'width=' + width + ',height=' + height + ',left=' + left + ',top=' + top);
      if (!authWindow) {
        const confirmed = confirm('浏览器拦截了弹窗。\n\n点击「确定」将复制授权链接，请在浏览器地址栏粘贴打开。');
        if (confirmed) {
          navigator.clipboard.writeText(data.url).then(() => alert('授权链接已复制！请在新标签页中粘贴打开，授权完成后关闭标签页即可。')).catch(() => prompt('请手动复制以下链接并在浏览器中打开:', data.url));
        }
        return;
      }
      const pollTimer = setInterval(() => { if (authWindow.closed) { clearInterval(pollTimer); loadSettings(); loadHealthDashboard(healthDays); } }, 500);
    })
    .catch(err => { if (btn) { btn.textContent = '连接'; btn.disabled = false; } alert('获取授权链接失败: ' + err + '\n请确认凭据已正确配置。'); });
}

export async function loadSettings() {
  try {
    const res = await fetch('/api/health/platforms');
    const data = await res.json();
    for (const p of (data.platforms || [])) {
      const btn = document.getElementById('connect-' + p.name);
      const badge = document.getElementById('badge-' + p.name);
      const cfgBadge = document.getElementById('config-badge-' + p.name);
      const cfgBtn = document.getElementById('config-cred-btn-' + p.name);
      const credForm = document.getElementById('cred-form-' + p.name);
      if (!btn || !badge) continue;

      let credConfigured = false;
      try { const cfgRes = await fetch('/api/health/' + p.name + '/config-status'); const cfgData = await cfgRes.json(); credConfigured = cfgData.configured; } catch (_) { console.error('settings: platformConfig ' + p.name, _); }

      if (p.connected) {
        btn.style.display = 'none'; badge.style.display = 'inline';
        if (cfgBadge) cfgBadge.style.display = 'none'; if (cfgBtn) cfgBtn.style.display = 'none'; if (credForm) credForm.style.display = 'none';
      } else if (credConfigured) {
        btn.style.display = 'inline'; badge.style.display = 'none';
        if (cfgBadge) cfgBadge.style.display = 'inline'; if (cfgBtn) cfgBtn.style.display = 'none'; if (credForm) credForm.style.display = 'none';
      } else {
        btn.style.display = 'none'; badge.style.display = 'none';
        if (cfgBadge) cfgBadge.style.display = 'none'; if (cfgBtn) cfgBtn.style.display = 'inline';
      }
    }
  } catch (e) { console.error('Settings load error:', e); }
}

export function showCredForm(platform) {
  const form = document.getElementById('cred-form-' + platform);
  const cfgBtn = document.getElementById('config-cred-btn-' + platform);
  if (form) form.style.display = 'block';
  if (cfgBtn) cfgBtn.style.display = 'none';
}

export async function savePlatformConfig(platform) {
  const clientId = document.getElementById('client-id-' + platform).value.trim();
  const clientSecret = document.getElementById('client-secret-' + platform).value.trim();
  if (!clientId || !clientSecret) { alert('请填写 Client ID 和 Client Secret'); return; }
  try {
    const res = await fetch('/api/health/' + platform + '/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }) });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('cred-form-' + platform).style.display = 'none';
    alert(data.message || '凭据已保存');
    loadSettings();
  } catch (e) { alert('保存失败: ' + e); }
}

