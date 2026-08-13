var API = require('../../utils/api.js');
var echarts = require('../../components/ec-canvas/echarts.js');
var chartTheme = require('../../utils/chart-theme.js');

var METRICS = [
  { key: 'steps', label: '步数', unit: '步', icon: '🚶', color: '#5e9eff' },
  { key: 'heart_rate', label: '心率', unit: 'bpm', icon: '💓', color: '#f87171' },
  { key: 'sleep', label: '睡眠', unit: '小时', icon: '🌙', color: '#a78bfa' },
  { key: 'calories', label: '卡路里', unit: 'kcal', icon: '🔥', color: '#fb923c' },
  { key: 'weight', label: '体重', unit: 'kg', icon: '⚖️', color: '#34d399' },
  { key: 'body_fat', label: '体脂', unit: '%', icon: '📊', color: '#fbbf24' },
  { key: 'blood_pressure_systolic', label: '收缩压', unit: 'mmHg', icon: '🩺', color: '#f472b6' },
  { key: 'blood_glucose', label: '血糖', unit: 'mmol/L', icon: '🩸', color: '#818cf8' }
];

Page({
  data: {
    _theme: 'dark',
    period: 7,
    periods: [
      { label: '7天', value: 7 },
      { label: '30天', value: 30 },
      { label: '90天', value: 90 }
    ],
    cards: [],
    loading: true,
    showDetail: false,
    detailMetric: null,
    detailData: [],
    detailPeriod: 30,
    ecDetail: null
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    this.loadData();
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 2 });
      this.getTabBar().updateTheme(getApp().globalData.theme);
    }
  },

  onPullDownRefresh: function () {
    this.loadData().then(function () { wx.stopPullDownRefresh(); });
  },

  loadData: function () {
    var that = this;
    var types = METRICS.map(function (m) { return m.key; }).join(',');
    this.setData({ loading: true });

    return API.get('/api/dashboard/health-batch?types=' + types + '&days=' + this.data.period)
      .then(function (res) {
        var raw = (res.data && res.data.data) ? res.data.data : {};
        var cards = METRICS.map(function (m) {
          var arr = raw[m.key] || [];
          var latestVal = arr.length > 0 ? arr[arr.length - 1].value : null;
          var latestUnit = arr.length > 0 ? (arr[arr.length - 1].unit || m.unit) : m.unit;
          var prevVal = arr.length > 1 ? arr[arr.length - 2].value : null;
          var trend = null;
          if (latestVal !== null && prevVal !== null) {
            trend = latestVal > prevVal ? 'up' : (latestVal < prevVal ? 'down' : 'flat');
          }
          var displayVal = '--';
          if (latestVal !== null) {
            if (m.key === 'sleep' || m.key === 'weight' || m.key === 'body_fat' || m.key === 'blood_glucose') {
              displayVal = parseFloat(latestVal).toFixed(1);
            } else {
              displayVal = Math.round(latestVal);
            }
          }
          return {
            key: m.key,
            label: m.label,
            icon: m.icon,
            color: m.color,
            value: displayVal,
            unit: latestUnit,
            trend: trend,
            count: arr.length
          };
        });
        that.setData({ cards: cards, loading: false });
      })
      .catch(function () {
        that.setData({ loading: false });
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  onPeriodTap: function (e) {
    var p = parseInt(e.currentTarget.dataset.period);
    if (p === this.data.period) return;
    this.setData({ period: p });
    this.loadData();
  },

  onCardTap: function (e) {
    var key = e.currentTarget.dataset.key;
    var cards = this.data.cards;
    var metric = null;
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].key === key) { metric = cards[i]; break; }
    }
    if (!metric) return;
    this.setData({ showDetail: true, detailMetric: metric, detailPeriod: 30, ecDetail: null });
    this.loadDetail(key);
  },

  closeDetail: function () {
    this._detailChart = null;
    this.setData({ showDetail: false, detailMetric: null, detailData: [], ecDetail: null });
  },

  onDetailPeriodTap: function (e) {
    var p = parseInt(e.currentTarget.dataset.period);
    if (p === this.data.detailPeriod) return;
    this.setData({ detailPeriod: p });
    this.loadDetail(this.data.detailMetric.key);
  },

  loadDetail: function (type) {
    var that = this;
    wx.showLoading({ title: '加载中' });
    API.get('/api/dashboard/health?type=' + type + '&days=' + this.data.detailPeriod)
      .then(function (res) {
        var arr = (res.data && res.data.data) ? res.data.data : [];
        var values = arr.map(function (r) { return parseFloat(r.value) || 0; });
        var labels = arr.map(function (r) { return r.date ? r.date.substring(5) : ''; });
        var avg = values.length ? (values.reduce(function (a, b) { return a + b; }, 0) / values.length).toFixed(1) : 0;
        var max = values.length ? Math.max.apply(null, values).toFixed(1) : 0;
        var min = values.length ? Math.min.apply(null, values).toFixed(1) : 0;

        that._chartValues = values;
        that._chartLabels = labels;

        that.setData({
          detailData: arr,
          detailAvg: avg, detailMax: max, detailMin: min
        });

        wx.hideLoading();

        if (values.length > 1) {
          that._initDetailChart();
        }
      })
      .catch(function () {
        wx.hideLoading();
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  _initDetailChart: function () {
    var that = this;
    var metric = this.data.detailMetric;
    var values = this._chartValues;
    var labels = this._chartLabels;

    if (!values || values.length < 2 || !metric) return;

    this.setData({
      ecDetail: {
        onInit: function (canvas, width, height, dpr) {
          var chart = echarts.init(canvas, null, {
            width: width, height: height, devicePixelRatio: dpr
          });
          var opts = chartTheme.buildLineChart(values, labels, metric.color);
          chart.setOption(opts);
          that._detailChart = chart;
          return chart;
        }
      }
    });
  }
});
