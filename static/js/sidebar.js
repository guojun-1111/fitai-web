// ========== Sidebar Stats ==========
export async function loadSidebarStats() {
  try {
    const [wRes, mRes] = await Promise.all([
      fetch('/api/dashboard/workout?days=7'),
      fetch('/api/dashboard/metrics?days=90'),
    ]);
    const workouts = (await wRes.json()).data || [];
    const metrics = (await mRes.json()).data || [];
    const wkCount = workouts.length;
    const lastM = metrics[metrics.length - 1];
    const weight = lastM?.weight_kg ? lastM.weight_kg + 'kg' : '--';
    const vals = document.querySelectorAll('.stat-mini-val');
    if (vals[0]) vals[0].textContent = wkCount;
    if (vals[1]) vals[1].textContent = weight;
  } catch (_) { console.error('sidebar: loadSessions', _); }
}

// Make it globally accessible for ws.js
window._loadSidebarStats = loadSidebarStats;
