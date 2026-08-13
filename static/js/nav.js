// ========== Navigation ==========
import { loadHomePanel } from './home.js';
import { loadDashboard } from './dashboard.js';
import { loadHistory } from './history.js';
import { loadHealthDashboard, closeHealthDetail } from './health.js';
import { loadExerciseAnalysis } from './exercises.js';
import { loadExerciseLibrary } from './exercise-library.js';
import { loadSettings } from './settings.js';
import { loadInsights } from './insights.js';
import { loadProfile, loadModelSetting } from './profile.js';

export function initNav() {
  // Brand logo click → home
  const brandEl = document.querySelector('.sidebar-brand');
  if (brandEl) {
    brandEl.style.cursor = 'pointer';
    brandEl.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      const homeBtn = document.querySelector('.nav-btn[data-panel="home"]');
      if (homeBtn) homeBtn.classList.add('active');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      const homePanel = document.getElementById('panel-home');
      if (homePanel) homePanel.classList.add('active');
      loadHomePanel();
    });
  }

  // Nav buttons
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const panel = btn.dataset.panel;
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + panel).classList.add('active');

      // Close health detail if switching away from health panel
      if (panel !== 'health') closeHealthDetail();

      if (panel === 'home') loadHomePanel();
      if (panel === 'dashboard') loadDashboard(7);
      if (panel === 'history') loadHistory('workout');
      if (panel === 'health') loadHealthDashboard(7);
      if (panel === 'settings') { loadSettings(); loadProfile(); loadModelSetting(); }
      if (panel === 'exercises') loadExerciseAnalysis();
      if (panel === 'exercise-library') loadExerciseLibrary();
      if (panel === 'insights') loadInsights();
      if (panel === 'plan') { import('./plan.js').then(m => m.loadPlan()); }
      if (panel === 'pose') {
        // Show start button, hide stop
        var sb = document.getElementById('pose-start-btn');
        var tb = document.getElementById('pose-stop-btn');
        if (sb) sb.style.display = '';
        if (tb) tb.style.display = 'none';
      }
      // V20: Stop pose session when switching away from pose panel
      if (panel !== 'pose') {
        import('./pose.js').then(function(m) { m.stopPoseSession(); }).catch(function() {});
        var sb2 = document.getElementById('pose-start-btn');
        var tb2 = document.getElementById('pose-stop-btn');
        if (sb2) sb2.style.display = '';
        if (tb2) tb2.style.display = 'none';
      }
    });
  });

  // Quick action + suggestion chip delegation
  document.addEventListener('click', (e) => {
    const goto = e.target.closest('.empty-cta[data-goto]');
    if (goto) {
      const target = document.querySelector('.nav-btn[data-panel="' + goto.dataset.goto + '"]');
      if (target) target.click();
      return;
    }
    const chip = e.target.closest('.quick-btn') || e.target.closest('.suggestion-chip');
    if (chip) {
      const msg = chip.dataset.msg;
      if (!msg) return;
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      const chatBtn = document.querySelector('.nav-btn[data-panel="chat"]');
      if (chatBtn) chatBtn.classList.add('active');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      const chatPanel = document.getElementById('panel-chat');
      if (chatPanel) chatPanel.classList.add('active');
      // Dynamic import to avoid circular dep
      import('./chat.js').then(m => m.sendMessage(msg));
    }
  });
}
