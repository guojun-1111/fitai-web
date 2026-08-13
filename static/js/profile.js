// ========== Profile & Model Settings ==========
export function initProfile() {
  const saveBtn = document.getElementById('save-profile-btn');
  if (saveBtn) saveBtn.addEventListener('click', saveProfile);
  loadProfile();
  loadModelSetting();
}

export async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    const p = await res.json();
    document.getElementById('profile-name').value = p.name || '';
    document.getElementById('profile-gender').value = p.gender || '';
    document.getElementById('profile-birth').value = p.birth_year || '';
    document.getElementById('profile-height').value = p.height_cm || '';
    document.getElementById('profile-weight').value = p.weight_kg || '';
    document.getElementById('profile-goal').value = p.fitness_goal || '';
    document.getElementById('profile-level').value = p.activity_level || '';
    document.getElementById('profile-notes').value = p.notes || '';
    updateBrandName(p.name);
  } catch (e) { console.error('Profile load error:', e); }
}

export async function saveProfile() {
  const data = {
    name: document.getElementById('profile-name').value.trim(),
    gender: document.getElementById('profile-gender').value,
    birth_year: parseInt(document.getElementById('profile-birth').value) || null,
    height_cm: parseFloat(document.getElementById('profile-height').value) || null,
    weight_kg: parseFloat(document.getElementById('profile-weight').value) || null,
    fitness_goal: document.getElementById('profile-goal').value.trim(),
    activity_level: document.getElementById('profile-level').value,
    notes: document.getElementById('profile-notes').value.trim(),
  };
  try {
    const res = await fetch('/api/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const result = await res.json();
    if (result.ok) {
      const badge = document.getElementById('profile-saved');
      if (badge) { badge.style.display = 'inline'; setTimeout(() => { badge.style.display = 'none'; }, 2000); }
      updateBrandName(data.name);
    }
  } catch (e) { alert('保存失败: ' + e); }
}

export async function switchModel(modelId) {
  try {
    const res = await fetch('/api/settings/model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: modelId }) });
    const data = await res.json();
    const status = document.getElementById('model-status');
    if (data.ok) {
      document.querySelectorAll('.model-option').forEach(opt => opt.classList.toggle('active', opt.dataset.model === modelId));
      if (status) { status.textContent = '已切换，下次对话生效'; status.style.color = 'var(--green)'; status.style.display = 'block'; setTimeout(() => { status.style.display = 'none'; }, 2000); }
    } else {
      if (status) { status.textContent = '切换失败: ' + (data.error || '未知错误'); status.style.color = 'var(--red)'; status.style.display = 'block'; setTimeout(() => { status.style.display = 'none'; }, 3000); }
    }
  } catch (e) {
    const status = document.getElementById('model-status');
    if (status) { status.textContent = '切换失败，请重试'; status.style.color = 'var(--red)'; status.style.display = 'block'; }
  }
}

export async function switchModelSilent(modelId) {
  try { await fetch('/api/settings/model', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({model: modelId}) }); } catch(e) { console.error('profile: switchModel', e); }
}

export async function setReplyStyle(style) {
  try {
    const res = await fetch('/api/settings/reply-style', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ style }) });
    const data = await res.json();
    if (data.ok) {
      document.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.querySelector('.style-btn[data-style="' + style + '"]');
      if (activeBtn) activeBtn.classList.add('active');
    }
  } catch(e) { console.error('profile: setReplyStyle', e); }
}
export async function loadModelSetting() {
  try {
    const res = await fetch('/api/settings/model');
    const data = await res.json();
    const current = data.model || '';
    document.querySelectorAll('.model-option').forEach(opt => opt.classList.toggle('active', opt.dataset.model === current));
  } catch (e) { console.error('Load model setting error:', e); }
}

function updateBrandName(name) {
  const sub = document.getElementById('brand-sub');
  if (sub) sub.textContent = name ? name + '的私人助手' : '智能健身助手';
}

// Export for HTML onclick
window.switchModel = switchModel;
window.setReplyStyle = setReplyStyle;
window._switchModelSilent = switchModelSilent;
