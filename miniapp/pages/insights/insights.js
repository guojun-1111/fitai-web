var API = require('../../utils/api.js');

Page({
  data: {
    _theme: 'dark',
    causalGraph: null,
    interventions: [],
    changepoints: [],
    predictions: [],
    loading: true,
    activeTab: 'causal'
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadInsights();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  loadInsights: function () {
    var that = this;
    this.setData({ loading: true });

    API.get('/api/insights/summary').then(function (res) {
      var data = res.data || {};
      that.setData({
        causalGraph: data.causal_graph || null,
        interventions: data.interventions || data.best_interventions || [],
        changepoints: data.changepoints || data.physiological_changepoints || [],
        predictions: data.predictions || data.forecasts || [],
        loading: false
      });
    }).catch(function () {
      that.setData({ loading: false });
      wx.showToast({ title: '加载洞察失败', icon: 'none' });
    });
  },

  onTabTap: function (e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  }
});
