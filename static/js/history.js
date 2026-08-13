// ========== History Panel ==========
export function initHistory() {
  document.querySelectorAll('.subnav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.subnav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadHistory(btn.dataset.type);
    });
  });
}

export async function loadHistory(type) {
  const container = document.getElementById('history-content');
  if (!container) return;
  container.innerHTML = '<div class="loading-msg"><div class="dot-wave"><span></span><span></span><span></span></div> 加载中...</div>';
  try {
    let res, data;
    if (type === 'workout') {
      res = await fetch('/api/dashboard/workout?days=365');
      data = (await res.json()).data || [];
      renderWorkoutHistory(container, data);
    } else if (type === 'metrics') {
      res = await fetch('/api/dashboard/metrics?days=365');
      data = (await res.json()).data || [];
      renderMetricsHistory(container, data);
    } else {
      res = await fetch('/api/dashboard/nutrition?days=90');
      data = (await res.json()).data || [];
      renderNutritionHistory(container, data);
    }
  } catch (_) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><p>加载失败</p></div>';
  }
}

function renderWorkoutHistory(container, data) {
  if (!data.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">🏋️</div><p>暂无训练记录</p></div>';
    return;
  }
  const rows = [...data].reverse().map(r =>
    '<tr><td>' + r.date + '</td><td>' + r.exercise_name + '</td><td>' + (r.sets||'-') + '</td><td>' + (r.reps||'-') + '</td><td>' + (r.weight_kg?r.weight_kg+'kg':'-') + '</td><td>' + (r.duration_minutes?r.duration_minutes+'min':'-') + '</td><td style="color:var(--text3);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (r.notes||'-') + '</td></tr>'
  ).join('');
  container.innerHTML = '<table><thead><tr><th>日期</th><th>动作</th><th>组数</th><th>次数</th><th>重量</th><th>时长</th><th>备注</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function renderMetricsHistory(container, data) {
  if (!data.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">⚖️</div><p>暂无体测数据</p></div>';
    return;
  }
  const rows = [...data].reverse().map(r =>
    '<tr><td>' + r.date + '</td><td>' + (r.weight_kg?r.weight_kg+' kg':'-') + '</td><td>' + (r.body_fat_pct?r.body_fat_pct+'%':'-') + '</td><td style="color:var(--text3)">' + (r.notes||'-') + '</td></tr>'
  ).join('');
  container.innerHTML = '<table><thead><tr><th>日期</th><th>体重</th><th>体脂率</th><th>备注</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function renderNutritionHistory(container, data) {
  if (!data.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">🍽️</div><p>暂无饮食记录</p></div>';
    return;
  }
  const rows = [...data].reverse().map(r =>
    '<tr><td>' + r.date + '</td><td>' + (r.meal_type||'-') + '</td><td>' + r.food_name + '</td><td>' + (r.calories?r.calories+'千卡':'-') + '</td><td>' + (r.protein_g?r.protein_g+'g':'-') + '</td><td>' + (r.carbs_g?r.carbs_g+'g':'-') + '</td><td>' + (r.fat_g?r.fat_g+'g':'-') + '</td></tr>'
  ).join('');
  container.innerHTML = '<table><thead><tr><th>日期</th><th>餐类型</th><th>食物</th><th>热量</th><th>蛋白质</th><th>碳水</th><th>脂肪</th></tr></thead><tbody>' + rows + '</tbody></table>';
}
