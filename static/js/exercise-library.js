// FitAI Exercise Library — browse 1,324 standard exercises with GIFs
let currentCategory = '', currentEquipment = '', currentDifficulty = '', currentKeyword = '';
let searchTimer = null;

export async function loadExerciseLibrary(category, equipment, difficulty, keyword) {
  currentCategory = category || '';
  currentEquipment = equipment || '';
  currentDifficulty = difficulty || '';
  currentKeyword = keyword || '';

  const grid = document.getElementById('exlib-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="loading-msg"><div class="dot-wave"><span></span><span></span><span></span></div> 加载中...</div>';

  try {
    const params = new URLSearchParams();
    if (currentCategory) params.set('category', currentCategory);
    if (currentEquipment) params.set('equipment', currentEquipment);
    if (currentKeyword) params.set('keyword', currentKeyword);
    params.set('limit', '500');
    const res = await fetch(`/api/exercises/library?${params}`);
    const data = await res.json();
    let exercises = data.exercises || [];

    // Client-side difficulty filter (API doesn't support it yet)
    if (currentDifficulty) {
      const diff = parseInt(currentDifficulty);
      exercises = exercises.filter(e => e.difficulty_level === diff);
    }

    if (!exercises.length) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><p>没有找到匹配的动作</p></div>';
      return;
    }

    grid.innerHTML = exercises.map(e => {
      const gifUrl = (e.image_url || '').replace('/exercise-images/', '/exercise-gifs/').replace('.jpg', '.gif');
      const diffStars = '⭐'.repeat(e.difficulty_level || 3);
      return `<div class="exlib-card" onclick="window._showExlibDetail('${e.id}')" title="${e.name}">
        <div class="exlib-gif-wrap">
          <img src="${gifUrl}" alt="${e.name}" loading="lazy" onerror="this.style.display='none'">
          <span class="exlib-equip-tag">${e.equipment}</span>
        </div>
        <div class="exlib-info">
          <div class="exlib-name">${e.name}</div>
          <div class="exlib-meta">${e.body_part} · ${diffStars}</div>
        </div>
      </div>`;
    }).join('');

  } catch (e) {
    grid.innerHTML = '<div class="empty-state"><p>加载失败</p></div>';
  }
}

export function showExerciseDetail(exerciseId) {
  fetch(`/api/exercises/${exerciseId}`).then(r => r.json()).then(e => {
    if (e.error) return;
    const gifUrl = (e.image_url || '').replace('/exercise-images/', '/exercise-gifs/').replace('.jpg', '.gif');
    const modal = document.getElementById('exlib-modal');
    if (!modal) return;
    modal.innerHTML = `
      <div class="exlib-modal-bg" onclick="this.parentElement.style.display='none'"></div>
      <div class="exlib-modal-content">
        <button class="exlib-modal-close" onclick="document.getElementById('exlib-modal').style.display='none'">✕</button>
        <div class="exlib-modal-gif"><img src="${gifUrl}" alt="${e.name}" style="max-width:100%;max-height:300px;border-radius:8px;object-fit:contain"></div>
        <h2>${e.name}</h2>
        <div class="exlib-modal-tags">
          <span class="exlib-tag">${e.body_part}</span>
          <span class="exlib-tag">${e.equipment}</span>
          <span class="exlib-tag">难度 ${e.difficulty_level}/5</span>
        </div>
        <div class="exlib-modal-instructions">${(e.instructions_zh || e.instructions_en || '暂无指导').replace(/\n/g, '<br>')}</div>
      </div>`;
    modal.style.display = 'flex';
  });
}

export function initExerciseLibrary() {
  // Search input with debounce
  const searchInput = document.getElementById('exlib-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        loadExerciseLibrary(currentCategory, currentEquipment, currentDifficulty, searchInput.value.trim());
      }, 300);
    });
  }

  // Category filter
  document.getElementById('exlib-category-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.exlib-filter-btn');
    if (!btn) return;
    document.querySelectorAll('#exlib-category-list .exlib-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadExerciseLibrary(btn.dataset.value || '', currentEquipment, currentDifficulty, currentKeyword);
  });

  // Equipment filter
  document.getElementById('exlib-equipment-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.exlib-filter-btn');
    if (!btn) return;
    document.querySelectorAll('#exlib-equipment-list .exlib-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadExerciseLibrary(currentCategory, btn.dataset.value || '', currentDifficulty, currentKeyword);
  });

  // Difficulty filter
  document.getElementById('exlib-difficulty-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.exlib-filter-btn');
    if (!btn) return;
    document.querySelectorAll('#exlib-difficulty-list .exlib-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadExerciseLibrary(currentCategory, currentEquipment, btn.dataset.value || '', currentKeyword);
  });

  // Modal
  if (!document.getElementById('exlib-modal')) {
    const modal = document.createElement('div');
    modal.id = 'exlib-modal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:10001;align-items:center;justify-content:center';
    document.body.appendChild(modal);
  }
}

window._showExlibDetail = showExerciseDetail;
