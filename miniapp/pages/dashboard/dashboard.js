var API = require('../../utils/api.js');
var echarts = require('../../components/ec-canvas/echarts.js');
var chartTheme = require('../../utils/chart-theme.js');

Page({
  data: {
    _theme: 'dark',
    period: 7,
    periods: [
      { label: '7天', value: 7 },
      { label: '30天', value: 30 },
      { label: '90天', value: 90 }
    ],
    stats: { streak: 0, workouts: 0, latest_weight: '--', latest_bodyfat: '--' },
    achievements: [],
    exerciseTypes: [],
    videos: [],
    loading: true,
    ecWeight: null
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadData();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  loadData: function () {
    var that = this;
    this.setData({ loading: true, ecWeight: null });

    var days = this.data.period;
    Promise.all([
      API.get('/api/dashboard/stats?days=' + days),
      API.get('/api/dashboard/exercise-stats?days=' + days),
      API.get('/api/videos/recommend?limit=4'),
      API.get('/api/dashboard/health?type=weight&days=30')
    ]).then(function (results) {
      var statsRes = results[0];
      var exRes = results[1];
      var videoRes = results[2];
      var weightRes = results[3];

      var stats = {};
      if (statsRes.data && statsRes.data.data) {
        var d = statsRes.data.data;
        stats = {
          streak: d.streak || 0,
          workouts: d.total_workouts || 0,
          latest_weight: d.latest_weight ? d.latest_weight.toFixed(1) + ' kg' : '--',
          latest_bodyfat: d.latest_bodyfat ? d.latest_bodyfat.toFixed(1) + '%' : '--'
        };
      }

      var exerciseTypes = [];
      if (exRes.data && exRes.data.data) {
        exerciseTypes = (exRes.data.data || []).slice(0, 8);
      }

      var videos = [];
      if (videoRes.data) {
        videos = (videoRes.data.videos || videoRes.data || []).slice(0, 4);
      }

      that.setData({
        stats: stats,
        exerciseTypes: exerciseTypes,
        videos: videos,
        loading: false
      });

      // Init weight chart if data available
      var weightData = (weightRes.data && weightRes.data.data) ? weightRes.data.data : [];
      if (weightData.length > 1) {
        that._initWeightChart(weightData);
      }
    }).catch(function () {
      that.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    });
  },

  _initWeightChart: function (rawData) {
    var that = this;
    var values = rawData.map(function (r) { return parseFloat(r.value) || 0; });
    var labels = rawData.map(function (r) { return (r.date || '').substring(5); });

    this.setData({
      ecWeight: {
        onInit: function (canvas, width, height, dpr) {
          var chart = echarts.init(canvas, null, {
            width: width, height: height, devicePixelRatio: dpr
          });
          var opts = chartTheme.buildLineChart(values, labels, '#34d399');
          chart.setOption(opts);
          that._weightChart = chart;
          return chart;
        }
      }
    });
  },

  onPeriodTap: function (e) {
    var p = parseInt(e.currentTarget.dataset.period);
    if (p === this.data.period) return;
    this.setData({ period: p });
    this.loadData();
  }
});
