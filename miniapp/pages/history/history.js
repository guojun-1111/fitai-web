var API = require('../../utils/api.js');

Page({
  data: {
    _theme: 'dark',
    type: 'workout',
    subnav: [
      { key: 'workout', label: '训练记录' },
      { key: 'metrics', label: '体测数据' },
      { key: 'nutrition', label: '饮食记录' }
    ],
    records: [],
    loading: true
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadHistory();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  onTypeTap: function (e) {
    var t = e.currentTarget.dataset.type;
    if (t === this.data.type) return;
    this.setData({ type: t });
    this.loadHistory();
  },

  loadHistory: function () {
    var that = this;
    this.setData({ loading: true });

    var paths = {
      workout: '/api/dashboard/workouts?limit=50',
      metrics: '/api/dashboard/metrics?limit=50',
      nutrition: '/api/dashboard/nutrition?limit=50'
    };

    API.get(paths[this.data.type] || paths.workout)
      .then(function (res) {
        var records = [];
        if (res.data && res.data.data) {
          records = res.data.data || [];
        }
        that.setData({ records: records, loading: false });
      })
      .catch(function () {
        that.setData({ loading: false });
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  }
});
