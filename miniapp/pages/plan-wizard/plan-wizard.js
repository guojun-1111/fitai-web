// V35: 7-Step Evidence-Based Onboarding
// Step 1: TTM Stage | Step 2: SDT Motivation | Step 3: Self-Efficacy
// Step 4: Implementation Intention | Step 5: Equipment | Step 6: Frequency+Time
// Step 7: Goal + Pain Point | Then: Generate → Preview → Confirm
var API = require('../../utils/api.js');

Page({
  data: {
    _theme: 'dark',
    step: 1,
    totalSteps: 7,

    // Step 1: TTM Stage (Transtheoretical Model — Prochaska & DiClemente, 1983)
    ttmStage: '',
    ttmStages: [
      { value: 'precontemplation', label: '基本没动', desc: '最近没怎么运动过', emoji: '🌱' },
      { value: 'preparation', label: '偶尔动一下', desc: '有时候会运动但不规律', emoji: '🌿' },
      { value: 'action_early', label: '每周 1-2 次', desc: '已经有在练，在养成习惯', emoji: '🪴' },
      { value: 'action_maintenance', label: '每周 3 次以上', desc: '规律练习一段时间了', emoji: '🌳' }
    ],

    // Step 2: SDT Motivation Types (Self-Determination Theory — Ryan & Deci, 2000)
    selectedMotivations: {},
    motivationStr: '',
    hasMotivation: false,
    motivations: [
      { value: 'health_energy', label: '想更健康、更有精力', type: 'autonomous', emoji: '💪' },
      { value: 'feel_good', label: '运动让我感觉很棒', type: 'autonomous', emoji: '😊' },
      { value: 'get_stronger', label: '想变得更强、挑战自己', type: 'autonomous', emoji: '🎯' },
      { value: 'lose_weight', label: '想减重、看起来更好', type: 'controlled', emoji: '⚖️' },
      { value: 'doctor_family', label: '医生或家人建议我运动', type: 'controlled', emoji: '🩺' },
      { value: 'stress_relief', label: '想减压、改善情绪', type: 'autonomous', emoji: '🧘' }
    ],

    // Step 3: Self-Efficacy (Bandura, 1977) — 1-10 scale
    selfEfficacy: 0,
    efficacyLevels: [
      { value: 1, label: '完全没信心' },
      { value: 2, label: '' }, { value: 3, label: '' },
      { value: 4, label: '' }, { value: 5, label: '一半一半' },
      { value: 6, label: '' }, { value: 7, label: '' },
      { value: 8, label: '' }, { value: 9, label: '' },
      { value: 10, label: '非常有信心' }
    ],

    // Step 4: Implementation Intention (Gollwitzer & Sheeran, 2006)
    implIntent: '',
    implIntents: [
      { value: 'morning', label: '早上起床后', desc: '上班前练完，一整天都精神', emoji: '🌅' },
      { value: 'lunch', label: '午休时间', desc: '利用午休，不占用早晚', emoji: '☀️' },
      { value: 'evening', label: '下班后 / 晚上', desc: '一天忙完后的放松时刻', emoji: '🌙' },
      { value: 'weekend', label: '周末集中练', desc: '平时太忙，周末爆发', emoji: '📅' },
      { value: 'flexible', label: '还没固定时间', desc: '我会帮你找一个最合适的节奏', emoji: '🔄' }
    ],

    // Step 5: Equipment (multi-select) — from V34
    selectedEquip: {},
    equipmentStr: '',
    hasEquipment: false,
    equipmentOptions: [
      { value: 'body weight', label: '无器械（自重）', emoji: '🧘' },
      { value: 'dumbbell', label: '哑铃', emoji: '🏋️' },
      { value: 'band', label: '弹力带', emoji: '🎗️' },
      { value: 'barbell', label: '杠铃', emoji: '🏋️‍♂️' },
      { value: 'cable', label: '龙门架/绳索', emoji: '🔗' },
      { value: 'machine', label: '健身房器械', emoji: '🏢' }
    ],

    // Step 6: Frequency + Time per session
    frequency: '',
    timePerSession: '',
    frequencies: [
      { value: '2', label: '每周 1-2 天', desc: '轻松起步' },
      { value: '3', label: '每周 3-4 天', desc: '规律训练' },
      { value: '5', label: '每周 5 天以上', desc: '全力以赴' }
    ],
    times: [
      { value: '15', label: '15 分钟', desc: '短时高效' },
      { value: '30', label: '30 分钟', desc: '标准训练' },
      { value: '45', label: '45 分钟', desc: '充分训练' },
      { value: '60', label: '60 分钟+', desc: '深度训练' }
    ],

    // Step 7: Goal + Pain point
    goal: '',
    goals: ['减脂', '增肌', '更健康', '缓解疼痛'],
    painPoint: '',
    painPoints: [
      { value: '不知道练什么', label: '不知道练什么', desc: '需要专业的训练方向指导' },
      { value: '怕受伤', label: '怕受伤', desc: '希望安全第一，循序渐进' },
      { value: '没动力', label: '没动力', desc: '需要有人督促和鼓励' },
      { value: '没效果', label: '没效果', desc: '练了很久但看不到变化' }
    ],

    // Safety screening (implicit ACSM PAR-Q+ lite)
    safetyFlags: {
      heart: false, chest_pain: false, bone_joint: false,
      medication: false, over45_inactive: false
    },

    // Result
    generating: false,
    planData: null,
    planConfirmed: false,
    expandedDay: -1
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  // ── Step 1: TTM Stage ──
  selectTTM: function (e) { this.setData({ ttmStage: e.currentTarget.dataset.value }); },

  // ── Step 2: Motivation (multi-select) ──
  toggleMotivation: function (e) {
    var v = e.currentTarget.dataset.value;
    var sel = this.data.selectedMotivations;
    sel[v] = !sel[v];
    var items = [];
    for (var k in sel) { if (sel[k]) items.push(k); }
    this.setData({ selectedMotivations: sel, motivationStr: items.join(','), hasMotivation: items.length > 0 });
  },

  // ── Step 3: Self-Efficacy ──
  selectEfficacy: function (e) { this.setData({ selfEfficacy: parseInt(e.currentTarget.dataset.value) }); },

  // ── Step 4: Implementation Intention ──
  selectImplIntent: function (e) { this.setData({ implIntent: e.currentTarget.dataset.value }); },

  // ── Step 5: Equipment ──
  toggleEquipment: function (e) {
    var v = e.currentTarget.dataset.value;
    var sel = this.data.selectedEquip;
    sel[v] = !sel[v];
    var items = [];
    for (var k in sel) { if (sel[k]) items.push(k); }
    this.setData({ selectedEquip: sel, equipmentStr: items.join(','), hasEquipment: items.length > 0 });
  },

  // ── Step 6: Frequency + Time ──
  selectFrequency: function (e) { this.setData({ frequency: e.currentTarget.dataset.value }); },
  selectTime: function (e) { this.setData({ timePerSession: e.currentTarget.dataset.value }); },

  // ── Step 7: Goal + Pain Point ──
  selectGoal: function (e) { this.setData({ goal: e.currentTarget.dataset.value }); },
  selectPainPoint: function (e) { this.setData({ painPoint: e.currentTarget.dataset.value }); },

  // ── Navigation ──
  nextStep: function () {
    var s = this.data.step;
    if (s === 1 && !this.data.ttmStage) { wx.showToast({ title: '请选择一个最接近的', icon: 'none' }); return; }
    if (s === 2 && !this.data.hasMotivation) { wx.showToast({ title: '请至少选一个', icon: 'none' }); return; }
    if (s === 3 && !this.data.selfEfficacy) { wx.showToast({ title: '请给一个分数', icon: 'none' }); return; }
    if (s === 4 && !this.data.implIntent) { wx.showToast({ title: '请选一个最接近的', icon: 'none' }); return; }
    if (s === 5 && !this.data.hasEquipment) { wx.showToast({ title: '请至少选一种器械', icon: 'none' }); return; }
    if (s === 6 && (!this.data.frequency || !this.data.timePerSession)) { wx.showToast({ title: '请选择频率和时长', icon: 'none' }); return; }
    if (s === 7 && (!this.data.goal || !this.data.painPoint)) { wx.showToast({ title: '请选择目标和困扰', icon: 'none' }); return; }

    if (s === this.data.totalSteps) { this.generatePlan(); return; }
    this.setData({ step: s + 1 });
  },

  prevStep: function () {
    if (this.data.step > 1) this.setData({ step: this.data.step - 1 });
  },

  // ── Auto-adjust frequency based on TTM + Efficacy ──
  getSuggestedFrequency: function () {
    var freq = parseInt(this.data.frequency) || 3;
    // TTM for beginners: cap at 2
    if (this.data.ttmStage === 'precontemplation') freq = Math.min(freq, 2);
    // Low self-efficacy: reduce by 1
    if (this.data.selfEfficacy > 0 && this.data.selfEfficacy <= 3) freq = Math.max(1, freq - 1);
    // High self-efficacy + advanced stage: keep as-is
    return freq;
  },

  generatePlan: function () {
    var that = this;
    this.setData({ generating: true, step: this.data.totalSteps + 1 });

    var suggestedFreq = this.getSuggestedFrequency();
    var hasAutonomous = this.data.motivationStr.indexOf('health_energy') >= 0 ||
                        this.data.motivationStr.indexOf('feel_good') >= 0 ||
                        this.data.motivationStr.indexOf('get_stronger') >= 0 ||
                        this.data.motivationStr.indexOf('stress_relief') >= 0;

    API.post('/api/training/onboarding/quick-start', {
      goal: this.data.goal,
      frequency: suggestedFreq,
      pain_point: this.data.painPoint,
      equipment: this.data.equipmentStr,
      experience_level: this.data.ttmStage,
      time_per_session: this.data.timePerSession,
      // V35: behavioral psychology params
      ttm_stage: this.data.ttmStage,
      motivation_types: this.data.motivationStr,
      self_efficacy: this.data.selfEfficacy,
      implementation_intent: this.data.implIntent,
      has_autonomous_motivation: hasAutonomous,
      // age_group is derived from profile or defaults
      age_group: 'unknown'
    }).then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.plan) {
        var plan = res.data.plan;
        (plan.days || []).forEach(function (d) {
          if (d.main) d.exercises = d.main;
        });
        that.setData({ planData: plan, generating: false });
      } else {
        wx.showToast({ title: '生成失败，请重试', icon: 'none' });
        that.setData({ generating: false, step: that.data.totalSteps });
      }
    }).catch(function () {
      wx.showToast({ title: '网络错误，请重试', icon: 'none' });
      that.setData({ generating: false, step: that.data.totalSteps });
    });
  },

  toggleDay: function (e) {
    var idx = parseInt(e.currentTarget.dataset.index);
    this.setData({ expandedDay: this.data.expandedDay === idx ? -1 : idx });
  },

  confirmPlan: function () {
    this.setData({ planConfirmed: true });
    wx.showToast({ title: '计划已生效', icon: 'success' });
    setTimeout(function () { wx.redirectTo({ url: '/pages/plan/plan' }); }, 800);
  },

  adjustWithAI: function () { wx.switchTab({ url: '/pages/chat/chat' }); }
});
