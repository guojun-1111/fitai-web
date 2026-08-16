// ========== Privacy & Data Management ==========

export async function exportData() {
  const status = document.getElementById('privacy-status');
  if (status) status.textContent = '正在导出...';
  try {
    const resp = await fetch('/api/privacy/export');
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      if (status) status.textContent = '导出失败: ' + (err.detail || resp.status);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fitai_export.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (status) status.textContent = '导出成功，已开始下载。';
  } catch (e) {
    if (status) status.textContent = '网络错误';
  }
}

export async function deleteAccount() {
  if (!confirm('确定要注销账户吗？此操作将永久删除你的全部数据，无法撤销。')) return;
  if (!confirm('再次确认：删除后所有健康数据、对话记录、训练计划都将永久丢失。确定继续？')) return;
  try {
    const resp = await fetch('/api/privacy/account', { method: 'DELETE' });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      alert('账户已注销。');
      window.location.href = '/login';
    } else {
      alert(data.detail || '删除失败');
    }
  } catch (e) {
    alert('网络错误');
  }
}

window.exportData = exportData;
window.deleteAccount = deleteAccount;
