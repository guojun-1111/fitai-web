var API = require('../../utils/api.js');
var planUtils = require('../../utils/plan-utils.js');

Page({
  data: {
    _theme: 'dark',
    loading: true,
    error: '',
    plan: null,
    weeks: [],
    currentWeek: 1,
    currentWeekLabel: '',
    currentDays: [],
    completedDays: 0,
    remainingDays: 0,
    planId: null,
    expandedDayIndex: -1
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadPlan();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  loadPlan: function () {
    var that = this;
    this.setData({ loading: true, error: '' });

    API.get('/api/training/plan')
      .then(function (res) {
        if (res.statusCode === 200 && res.data) {
          var plan = planUtils.unwrapPlanData(res.data);
          if (plan) {
            that._processPlan(plan);
          } else {
            that.setData({ loading: false, plan: null });
          }
        } else {
          that.setData({ loading: false, plan: null });
        }
      })
      .catch(function () {
        that.setData({ loading: false, error: '加载失败，请检查网络连接' });
      });
  },

  _processPlan: function (plan) {
    var weeks = plan.weeks || [];
    var completedDays = 0;
    var totalDays = 0;

    weeks.forEach(function (w) {
      (w.days || []).forEach(function (d) {
        if (!d.is_rest) totalDays++;
        if (d.completed) completedDays++;
      });
    });

    var todayIdx = (new Date().getDay() + 6) % 7;
    var activeWeek = weeks.length > 0 ? weeks[0].week : 1;
    for (var i = 0; i < weeks.length; i++) {
      var allDone = true;
      (weeks[i].days || []).forEach(function (d) {
        if (!d.is_rest && !d.completed) allDone = false;
      });
      if (!allDone) { activeWeek = weeks[i].week; break; }
    }

    this.setData({
      plan: plan,
      planId: plan.id,
      weeks: weeks,
      currentWeek: activeWeek,
      completedDays: completedDays,
      totalDays: totalDays,
      remainingDays: totalDays - completedDays,
      loading: false,
      error: ''
    });

    this._updateWeekView();
  },

  _updateWeekView: function () {
    var weeks = this.data.weeks;
    var cw = this.data.currentWeek;
    var currentWeekData = null;

    for (var i = 0; i < weeks.length; i++) {
      if (weeks[i].week === cw) { currentWeekData = weeks[i]; break; }
    }

    if (!currentWeekData) {
      this.setData({ currentDays: [] });
      return;
    }

    var days = (currentWeekData.days || []).map(function (d, idx) {
      d.day_name = d.day_name || planUtils.DAY_NAMES[idx] || ('Day ' + (idx + 1));
      return d;
    });

    this.setData({
      currentWeekLabel: '第' + cw + '周',
      currentDays: days
    });
  },

  onWeekTap: function (e) {
    var w = parseInt(e.currentTarget.dataset.week);
    if (w === this.data.currentWeek) return;
    this.setData({ currentWeek: w });
    this._updateWeekView();
  },

  toggleDayExpand: function (e) {
    var idx = parseInt(e.currentTarget.dataset.index);
    this.setData({ expandedDayIndex: this.data.expandedDayIndex === idx ? -1 : idx });
  },

  goRegenerate: function () {
    wx.navigateTo({ url: '/pages/plan-wizard/plan-wizard' });
  },

  markComplete: function (e) {
    var idx = parseInt(e.currentTarget.dataset.index);
    var days = this.data.currentDays;
    if (idx < 0 || idx >= days.length) return;

    var day = days[idx];
    var that = this;

    API.post('/api/training/plan/complete-day', {
      plan_id: this.data.planId,
      day: 'day-' + day.day
    }).then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.success) {
        days[idx].completed = true;
        var completed = 0;
        var remaining = 0;
        days.forEach(function (d) {
          if (!d.is_rest) { if (d.completed) completed++; else remaining++; }
        });
        that.setData({
          currentDays: days,
          completedDays: that.data.completedDays + 1,
          remainingDays: Math.max(0, that.data.remainingDays - 1)
        });
        wx.showToast({ title: '已完成！', icon: 'success' });
      } else {
        wx.showToast({ title: '标记失败', icon: 'none' });
      }
    }).catch(function () {
      wx.showToast({ title: '网络错误', icon: 'none' });
    });
  }
});
