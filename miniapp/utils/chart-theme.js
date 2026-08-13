// Shared ECharts theme utility for miniapp pages
var echarts = require('../components/ec-canvas/echarts.js');

var THEME_COLORS = {
  dark: {
    text: '#a09888', axis: '#6b6358', grid: 'rgba(255,255,255,0.06)',
    green: '#3dd68c', blue: '#5e9eff', orange: '#f59e4b', red: '#f87171',
    purple: '#a78bfa', yellow: '#fbbf24', bg: '#1a1714'
  },
  light: {
    text: '#6e6e73', axis: '#86868b', grid: 'rgba(0,0,0,0.06)',
    green: '#22c55e', blue: '#3b82f6', orange: '#f59e4b', red: '#ef4444',
    purple: '#8b5cf6', yellow: '#f59e0b', bg: '#f5f5f7'
  },
  morning: {
    text: '#92400e', axis: '#a16207', grid: 'rgba(0,0,0,0.08)',
    green: '#16a34a', blue: '#2563eb', orange: '#d97706', red: '#dc2626',
    purple: '#7c3aed', yellow: '#d97706', bg: '#fef9ef'
  }
};

function getTheme() {
  var app = getApp();
  return (app && app.globalData && app.globalData.theme) || 'dark';
}

function getColors() {
  return THEME_COLORS[getTheme()] || THEME_COLORS.dark;
}

// Get responsive chart dimensions based on screen width
function getChartSize(dataCount) {
  var sys = wx.getSystemInfoSync();
  var w = sys.windowWidth;
  // Chart takes full available width minus page padding (24rpx*2 ≈ 48rpx)
  var chartW = w - 24;  // in px (roughly 48rpx converted)
  // For many data points, make chart wider (scrollable)
  var minW = Math.max(chartW, dataCount * 28);
  return { width: minW, height: 200 };  // in px (400rpx ≈ 200px)
}

// Shared base config: tooltip, dataZoom, animation
function _baseGrid() {
  var cols = getColors();
  return {
    top: 12, right: 16, bottom: dataZoomEnabled() ? 44 : 28, left: 44
  };
}

function _baseTooltip() {
  var cols = getColors();
  return {
    trigger: 'axis',
    confine: true,
    backgroundColor: 'rgba(30,28,26,0.92)',
    borderColor: cols.green,
    borderWidth: 1,
    textStyle: { color: '#e8e4dc', fontSize: 12 },
    formatter: function (params) {
      if (!params || !params.length) return '';
      var p = params[0];
      return p.axisValue + '<br/>' + p.marker + ' ' + p.seriesName + ': <b>' + p.value + '</b>';
    }
  };
}

function _baseDataZoom(dataCount) {
  if (dataCount < 8) return [];
  return [{
    type: 'inside',
    start: 0,
    end: dataCount > 30 ? 30 : 100,
    minSpan: 5
  }, {
    type: 'slider',
    start: 0,
    end: dataCount > 30 ? 30 : 100,
    height: 16,
    bottom: 4,
    borderColor: 'transparent',
    backgroundColor: 'rgba(128,128,128,0.08)',
    fillerColor: 'rgba(61,214,140,0.15)',
    handleStyle: { color: getColors().green, width: 20 },
    textStyle: { color: getColors().axis, fontSize: 9 }
  }];
}

function dataZoomEnabled() {
  return true;
}

// Line chart builder
function buildLineChart(values, labels, lineColor, areaColor, opts) {
  var cols = getColors();
  var minVal = Math.min.apply(null, values);
  var maxVal = Math.max.apply(null, values);
  if (minVal === maxVal) { minVal = minVal - 1; maxVal = maxVal + 1; }
  var range = maxVal - minVal;
  var name = (opts && opts.seriesName) || '';

  var series = [{
    name: name,
    type: 'line',
    data: values,
    smooth: true,
    symbol: 'circle',
    symbolSize: values.length > 60 ? 0 : 3,
    lineStyle: { color: lineColor || cols.green, width: 2 },
    itemStyle: { color: lineColor || cols.green },
    areaStyle: areaColor ? { color: areaColor, opacity: 0.12 } : undefined
  }];

  // Optional moving average overlay
  if (opts && opts.maValues && opts.maValues.length > 0) {
    series.push({
      name: '7日均线',
      type: 'line',
      data: opts.maValues,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: cols.orange, width: 1.5, type: 'dashed' },
      itemStyle: { color: cols.orange }
    });
  }

  return {
    animation: true,
    animationDuration: 600,
    grid: _baseGrid(),
    tooltip: _baseTooltip(),
    dataZoom: _baseDataZoom(values.length),
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: cols.grid } },
      axisTick: { show: false },
      axisLabel: { color: cols.axis, fontSize: 10, interval: Math.max(0, Math.floor(labels.length / 6) - 1) }
    },
    yAxis: {
      type: 'value',
      name: (opts && opts.yLabel) || '',
      min: minVal - range * 0.1,
      max: maxVal + range * 0.1,
      splitLine: { lineStyle: { color: cols.grid } },
      axisLabel: { color: cols.axis, fontSize: 10 }
    },
    series: series
  };
}

// Bar chart builder
function buildBarChart(values, labels, barColor, opts) {
  var cols = getColors();
  var name = (opts && opts.seriesName) || '';
  return {
    animation: true,
    animationDuration: 500,
    grid: _baseGrid(),
    tooltip: _baseTooltip(),
    dataZoom: labels.length > 10 ? _baseDataZoom(labels.length) : [],
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: cols.grid } },
      axisTick: { show: false },
      axisLabel: { color: cols.axis, fontSize: 10, interval: 0, rotate: labels.length > 7 ? 45 : 0 }
    },
    yAxis: {
      type: 'value',
      name: (opts && opts.yLabel) || '',
      splitLine: { lineStyle: { color: cols.grid } },
      axisLabel: { color: cols.axis, fontSize: 10 }
    },
    series: [{
      name: name,
      type: 'bar',
      data: values,
      barWidth: '50%',
      itemStyle: {
        color: barColor || cols.green,
        borderRadius: [3, 3, 0, 0]
      }
    }]
  };
}

// Pie chart builder
function buildPieChart(data, radius) {
  var cols = getColors();
  return {
    animation: true,
    animationDuration: 500,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(30,28,26,0.92)',
      borderColor: cols.green,
      borderWidth: 1,
      textStyle: { color: '#e8e4dc', fontSize: 12 },
      formatter: '{b}: {c} ({d}%)'
    },
    series: [{
      type: 'pie',
      radius: radius || ['45%', '72%'],
      center: ['50%', '50%'],
      data: data,
      label: { color: cols.text, fontSize: 10 },
      emphasis: {
        label: { fontSize: 14, fontWeight: 'bold' },
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' }
      },
      itemStyle: {
        borderRadius: 4,
        borderColor: cols.bg,
        borderWidth: 2
      }
    }]
  };
}

// Create ec config object for page data — wires touch events to ECharts
function initEc(onInitFn) {
  var chartInstance = null;

  function _dispatch(action, evt) {
    if (!chartInstance) return;
    chartInstance.dispatchAction({
      type: action,
      x: evt.touches && evt.touches[0] ? evt.touches[0].x : (evt.x || 0),
      y: evt.touches && evt.touches[0] ? evt.touches[0].y : (evt.y || 0)
    });
  }

  return {
    onInit: function (canvasNode, width, height, dpr) {
      chartInstance = echarts.init(canvasNode, null, {
        width: width, height: height, devicePixelRatio: dpr
      });
      if (typeof onInitFn === 'function') {
        onInitFn(chartInstance, canvasNode, width, height, dpr);
      }
      return chartInstance;
    },
    touchStart: function (evt) { _dispatch('showTip', evt); },
    touchMove: function (evt) { _dispatch('showTip', evt); },
    touchEnd: function (evt) { _dispatch('hideTip', evt); if (chartInstance) chartInstance.dispatchAction({ type: 'takeGlobalCursor', key: 'dataZoomSelect', dataZoomSelectActive: false }); }
  };
}

module.exports = {
  getTheme: getTheme,
  getColors: getColors,
  buildLineChart: buildLineChart,
  buildBarChart: buildBarChart,
  buildPieChart: buildPieChart,
  initEc: initEc,
  getChartSize: getChartSize,
  THEME_COLORS: THEME_COLORS
};
