// ec-canvas: ECharts wrapper for WeChat Mini-Program
var echarts = require('./echarts.js');

function wrapTouch(evt) {
  if (!evt || !evt.touches) return [];
  var touches = [];
  for (var i = 0; i < evt.touches.length; i++) {
    var t = evt.touches[i];
    touches.push({ x: t.x, y: t.y });
  }
  return touches;
}

Component({
  properties: {
    canvasId: { type: String, value: 'ec-canvas' },
    width: { type: Number, value: 680 },
    height: { type: Number, value: 400 },
    ec: { type: Object, value: {} }
  },

  data: {
    _chart: null,
    _inited: false
  },

  lifetimes: {
    ready: function () {
      // Defer to give parent page time to set ec.onInit
      var that = this;
      setTimeout(function () {
        that._initChart();
      }, 100);
    },

    detached: function () {
      if (this.data._chart) {
        this.data._chart.dispose();
        this.data._chart = null;
      }
    }
  },

  methods: {
    _initChart: function () {
      var that = this;
      if (this.data._inited) return;
      if (!this.data.ec || typeof this.data.ec.onInit !== 'function') return;

      var query = wx.createSelectorQuery().in(this);
      query.select('#' + this.data.canvasId)
        .fields({ node: true, size: true })
        .exec(function (res) {
          if (!res || !res[0] || !res[0].node) {
            // Retry once after a delay (canvas might not be ready)
            setTimeout(function () { that._initChart(); }, 200);
            return;
          }

          var canvasNode = res[0].node;
          var canvasWidth = res[0].width;
          var canvasHeight = res[0].height;
          var dpr = wx.getSystemInfoSync().pixelRatio || 2;

          canvasNode.width = canvasWidth * dpr;
          canvasNode.height = canvasHeight * dpr;

          that.data._inited = true;

          var chart = that.data.ec.onInit(canvasNode, canvasWidth, canvasHeight, dpr);
          that.data._chart = chart;

          // Set initial option if provided
          if (that.data.ec.options && chart) {
            chart.setOption(that.data.ec.options);
          }
        });
    },

    // Proxy setOption calls from parent page
    setOption: function (options, opts) {
      if (this.data._chart) {
        this.data._chart.setOption(options, opts || {});
      } else {
        // Chart not ready yet, store options for later
        var ec = this.data.ec;
        ec.options = options;
        this.setData({ ec: ec });
        if (!this.data._inited) {
          this._initChart();
        }
      }
    },

    // Allow page to get chart instance directly
    getChart: function () {
      return this.data._chart;
    }
  }
});
