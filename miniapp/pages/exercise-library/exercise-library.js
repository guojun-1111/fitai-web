var API = require('../../utils/api.js');

var CATEGORIES = [
  { value: '', label: '全部' }, { value: 'chest', label: '胸' }, { value: 'back', label: '背' },
  { value: 'shoulders', label: '肩' }, { value: 'upper arms', label: '手臂' },
  { value: 'upper legs', label: '大腿' }, { value: 'lower legs', label: '小腿' },
  { value: 'waist', label: '腰腹' }, { value: 'cardio', label: '心肺' }
];

var EQUIPMENT = [
  { value: '', label: '全部' }, { value: 'body weight', label: '自重' },
  { value: 'dumbbell', label: '哑铃' }, { value: 'barbell', label: '杠铃' },
  { value: 'cable', label: '绳索' }, { value: 'machine', label: '器械' },
  { value: 'band', label: '弹力带' }, { value: 'kettlebell', label: '壶铃' }
];

var DIFFICULTIES = [
  { value: '', label: '全部难度' }, { value: '1', label: '⭐ 极易' },
  { value: '2', label: '⭐⭐ 简单' }, { value: '3', label: '⭐⭐⭐ 中等' },
  { value: '4', label: '⭐⭐⭐⭐ 较难' }, { value: '5', label: '⭐⭐⭐⭐⭐ 高难' }
];

var BODYPART_ICONS = {
  chest: '🏋️', back: '🔙', shoulders: '🙆', 'upper arms': '💪',
  'upper legs': '🦵', 'lower legs': '🦶', waist: '🧘', cardio: '🏃'
};

Page({
  data: {
    _theme: 'dark', search: '', category: '', equipment: '', difficulty: '',
    categories: CATEGORIES, equipments: EQUIPMENT, difficulties: DIFFICULTIES,
    exercises: [], page: 1, hasMore: true, loading: false, total: 0,
    // Detail popup
    showDetail: false, detailExercise: null
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadExercises();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  loadExercises: function () {
    var that = this;
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true });

    var params = '?page=' + this.data.page + '&limit=20';
    if (this.data.search) params += '&keyword=' + encodeURIComponent(this.data.search);
    if (this.data.category) params += '&body_part=' + encodeURIComponent(this.data.category);
    if (this.data.equipment) params += '&equipment=' + encodeURIComponent(this.data.equipment);

    API.get('/api/exercises/library' + params).then(function (res) {
      var data = res.data || {};
      var items = data.data || data.exercises || data || [];
      if (!Array.isArray(items)) items = [];

      if (that.data.difficulty) {
        var diffLevel = parseInt(that.data.difficulty);
        items = items.filter(function(ex) {
          return (ex.difficulty_level || ex.difficulty || 3) === diffLevel;
        });
      }

      // Post-process: ensure Chinese name
      items.forEach(function(ex) {
        if (!ex.name_zh || ex.name_zh === ex.name) {
          ex.name_zh = ex.name; // fallback
        }
      });

      var newList = that.data.page === 1 ? items : that.data.exercises.concat(items);
      that.setData({
        exercises: newList, page: that.data.page + 1,
        hasMore: items.length >= 20, loading: false,
        total: data.total || newList.length
      });
    }).catch(function () {
      that.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    });
  },

  onSearch: function (e) {
    this.setData({ search: e.detail.value, page: 1, hasMore: true, exercises: [] });
    this.loadExercises();
  },

  onFilterTap: function (e) {
    var type = e.currentTarget.dataset.type;
    var value = e.currentTarget.dataset.value;
    var update = {};
    update[type] = value;
    this.setData(update);
    this.setData({ page: 1, hasMore: true, exercises: [] });
    this.loadExercises();
  },

  loadMore: function () {
    if (this.data.hasMore) this.loadExercises();
  },

  // ── V36: 点击查看详情 ──
  onExerciseTap: function (e) {
    var idx = parseInt(e.currentTarget.dataset.index);
    var ex = this.data.exercises[idx];
    if (!ex) return;
    this.setData({ showDetail: true, detailExercise: ex });
  },

  closeDetail: function () {
    this.setData({ showDetail: false, detailExercise: null });
  },

  preventBubble: function () {},

  // ── V36: 图片加载失败用占位符 ──
  onImageError: function (e) {
    var idx = parseInt(e.currentTarget.dataset.index);
    if (isNaN(idx)) return;
    var key = 'exercises[' + idx + '].imgFailed';
    this.setData({ [key]: true });
  },

  getBodyPartIcon: function (bp) {
    return BODYPART_ICONS[bp] || '🏋️';
  }
});
