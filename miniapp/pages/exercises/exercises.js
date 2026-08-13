var API = require('../../utils/api.js');
var echarts = require('../../components/ec-canvas/echarts.js');
var chartTheme = require('../../utils/chart-theme.js');

var PIE_COLORS = ['#3dd68c', '#5e9eff', '#f59e4b', '#f87171', '#a78bfa', '#fbbf24', '#34d399', '#fb923c', '#f472b6', '#818cf8'];

Page({
  data: {
    _theme: 'dark',
    stats: { total_workouts: '--', total_minutes: '--', total_calories: '--', type_count: '--' },
    typeRanking: [],
    loading: true,
    ecPie: null
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
    this.setData({ loading: true, ecPie: null });

    Promise.all([
      API.get('/api/dashboard/stats'),
      API.get('/api/exercises/ranking')
    ]).then(function (results) {
      var statsRes = results[0];
      var rankRes = results[1];

      var stats = {};
      if (statsRes.data && statsRes.data.data) {
        var d = statsRes.data.data;
        stats = {
          total_workouts: d.total_workouts || '--',
          total_minutes: d.total_minutes || '--',
          total_calories: d.total_calories || '--',
          type_count: d.type_count || d.exercise_type_count || '--'
        };
      }

      var typeRanking = [];
      if (rankRes.data) {
        typeRanking = (rankRes.data.data || rankRes.data.ranking || rankRes.data || []).slice(0, 15);
      }

      that.setData({
        stats: stats,
        typeRanking: typeRanking,
        loading: false
      });

      if (typeRanking.length > 0) {
        that._initPieChart(typeRanking);
      }
    }).catch(function () {
      that.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    });
  },

  _initPieChart: function (ranking) {
    var that = this;
    var topItems = ranking.slice(0, 8);
    var others = ranking.slice(8);
    var othersTotal = 0;
    others.forEach(function (r) {
      othersTotal += (r.count || r.total_sets || 0);
    });

    var pieData = topItems.map(function (r, i) {
      return {
        name: r.name || r.exercise_type || r.type || '',
        value: r.count || r.total_sets || 0,
        itemStyle: { color: PIE_COLORS[i % PIE_COLORS.length] }
      };
    });

    if (othersTotal > 0) {
      pieData.push({
        name: '其他',
        value: othersTotal,
        itemStyle: { color: '#6b6358' }
      });
    }

    this.setData({
      ecPie: {
        onInit: function (canvas, width, height, dpr) {
          var chart = echarts.init(canvas, null, {
            width: width, height: height, devicePixelRatio: dpr
          });
          var opts = chartTheme.buildPieChart(pieData);
          chart.setOption(opts);
          that._pieChart = chart;
          return chart;
        }
      }
    });
  }
});
