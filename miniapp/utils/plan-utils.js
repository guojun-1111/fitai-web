// 统一训练计划数据解包
// 兼容两种格式：
//   Shape A: daily_planner 产出 → { goal, frequency, days: [...], explanation, future_projection }
//   Shape B: periodization 产出 → { goal, plan: [...], summary }

var DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

function unwrapPlanData(apiData) {
  var plan = (apiData && apiData.plan) ? apiData.plan : (apiData || null);
  if (!plan) return null;

  var planData = plan.plan_data;
  if (!planData) return null;

  // 已经是 JSON 对象（后端已 parse），如果是字符串再 parse 一次
  if (typeof planData === 'string') {
    try { planData = JSON.parse(planData); } catch (e) { return null; }
  }

  var weeks = [];
  var frequency = planData.frequency || 0;
  var explanation = planData.explanation || '';
  var futureProjection = planData.future_projection || '';
  var totalDays = 0, completedDays = 0;

  if (planData.days && planData.days.length > 0) {
    // Shape A: 单周日计划
    var days = planData.days.map(function (d, idx) {
      d.day_name = d.day_name || DAY_NAMES[idx] || ('Day ' + (idx + 1));
      d.completed = !!(plan.day_progress && plan.day_progress['day-' + d.day]);
      if (!d.is_rest) totalDays++;
      if (d.completed) completedDays++;
      return d;
    });
    weeks = [{ week: 1, days: days }];
    frequency = planData.frequency || days.filter(function (d) { return !d.is_rest; }).length;
  } else if (planData.plan && planData.plan.length > 0) {
    // Shape B: 多周期化计划（高层级，无每日详情）
    weeks = planData.plan.map(function (w) {
      return { week: w.week, focus: w.focus, intensity: w.intensity, note: w.note, days: [] };
    });
  }

  var streak = (apiData && apiData.streak) ? apiData.streak : 0;
  var missedDays = (apiData && apiData.missed_days) ? apiData.missed_days : 0;
  var createdAt = plan.created_at || '';

  return {
    id: plan.id,
    name: plan.name || (planData.goal + '训练计划'),
    goal: planData.goal || plan.goal || '',
    frequency: frequency,
    weeks: weeks,
    totalWeeks: weeks.length,
    totalDays: totalDays,
    completedDays: completedDays,
    explanation: explanation,
    futureProjection: futureProjection,
    dayProgress: plan.day_progress || {},
    status: plan.status || 'active',
    createdAt: createdAt,
    streak: streak,
    missedDays: missedDays
  };
}

module.exports = {
  unwrapPlanData: unwrapPlanData,
  DAY_NAMES: DAY_NAMES
};
