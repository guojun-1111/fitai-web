var API = require('../../utils/api.js');
var planUtils = require('../../utils/plan-utils.js');

function getGreeting() {
  var h = new Date().getHours();
  if (h < 5) return '夜深了';
  if (h < 9) return '早上好';
  if (h < 12) return '上午好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

// Apple Health ring: start at 7:30 (0.75π), sweep 270° clockwise
var START_ANGLE = Math.PI * 0.75;
var END_ANGLE = Math.PI * 2.25;
var SWEEP = END_ANGLE - START_ANGLE; // 1.5π = 270°

function drawRingArc(ctx, cx, cy, radius, pct, color, trackColor, lineWidth) {
  // Track (full background arc)
  ctx.beginPath();
  ctx.arc(cx, cy, radius, START_ANGLE, END_ANGLE);
  ctx.strokeStyle = trackColor;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = 'round';
  ctx.stroke();

  if (pct > 0) {
    var endAngle = START_ANGLE + (pct / 100) * SWEEP;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, START_ANGLE, endAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();
  }
}

Page({
  data: {
    _theme: 'dark',
    loggedIn: false,
    showRegister: false, confirmPassword: '',
    username: '', password: '', loading: false, error: '',
    greeting: getGreeting(),
    userName: '',
    todayPlan: null,
    todayIdx: (new Date().getDay() + 6) % 7,
    hasPlan: false,
    ringsData: {
      steps: { value: null, target: 10000, pct: 0, display: '--' },
      calories: { value: null, target: 500, pct: 0, display: '--' },
      sleep: { value: null, target: 8, pct: 0, display: '--' },
      separate: [
        { key: 'steps', color: '#3dd68c', value: null, target: 10000, pct: 0, display: '--', label: '今日步数' },
        { key: 'calories', color: '#f59e4b', value: null, target: 500, pct: 0, display: '--', label: '今日消耗' },
        { key: 'sleep', color: '#5e9eff', value: null, target: 8, pct: 0, display: '--', label: '昨晚睡眠' }
      ]
    },
    ringMode: 'combined',
    streak: 0, missedDays: 0, statusText: '',
    weeklySummary: null,
    showQuickRecord: false, quickType: '', quickLabel: '', quickUnit: '', quickValue: '',
    quickTypes: [
      { type: 'water', label: '喝水', unit: '杯' },
      { type: 'weight', label: '体重', unit: 'kg' },
      { type: 'sleep', label: '睡眠', unit: '小时' }
    ]
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    var token = wx.getStorageSync('fitai_token');
    if (token) { this.setData({ loggedIn: true }); this.loadDashboard(); }
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    if (typeof this.getTabBar === 'function' && this.getTabBar()) { this.getTabBar().setData({ selected: 0 }); this.getTabBar().updateTheme(getApp().globalData.theme); }
    if (getApp().globalData.token) {
      this.setData({ loggedIn: true });
      this.loadDashboard();
      this.syncWeRunData();
    }
  },

  loadDashboard: function () {
    var that = this;
    this.setData({ greeting: getGreeting() });
    API.get('/api/training/plan').then(function (res) {
      if (res.statusCode === 200 && res.data) {
        var plan = planUtils.unwrapPlanData(res.data);
        if (plan && plan.weeks && plan.weeks.length > 0) {
          var todayIdx = (new Date().getDay() + 6) % 7;
          var activeWeek = plan.weeks[0];
          for (var w = 0; w < plan.weeks.length; w++) {
            var allDone = true;
            (plan.weeks[w].days || []).forEach(function (d) { if (!d.is_rest && !d.completed) allDone = false; });
            if (!allDone) { activeWeek = plan.weeks[w]; break; }
          }
          var today = (activeWeek.days || [])[todayIdx];
          if (today) {
            today.day_name = ['周一','周二','周三','周四','周五','周六','周日'][todayIdx];
            if (!today.exercises && today.main) today.exercises = today.main;
            var streak = plan.streak || 0;
            var missed = plan.missedDays || 0;
            var statusText = '';
            if (today.is_rest) {
              statusText = '今天是休息日，好好恢复，肌肉在休息时才会生长';
            } else if (streak > 0) {
              statusText = '连续训练 ' + streak + ' 天，你比大多数人都能坚持！';
            } else if (missed > 0) {
              statusText = '你已经有 ' + missed + ' 个训练日没打卡了，今天就练吧';
            } else {
              statusText = '新计划刚开始，加油！';
            }
            that.setData({ todayPlan: today, hasPlan: true, streak: streak, missedDays: missed, statusText: statusText });
          } else {
            that.setData({ hasPlan: true, streak: plan.streak || 0, missedDays: plan.missedDays || 0 });
          }
        }
      }
    }).catch(function () {});

    this.loadHealthData();

    API.get('/api/weekly-summary').then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.summary) {
        that.setData({ weeklySummary: res.data.summary });
      }
    }).catch(function () {});

    var profile = wx.getStorageSync('fitai_profile');
    if (profile && profile.name) this.setData({ userName: profile.name });
  },

  syncWeRunData: function () {
    wx.getSetting({
      success: function (res) {
        if (res.authSetting['scope.werun']) {
          wx.getWeRunData({
            success: function (dataRes) {
              API.post('/api/health/wechat/werun', {
                encryptedData: dataRes.encryptedData,
                iv: dataRes.iv
              }).then(function () {
                var pages = getCurrentPages();
                var page = pages[pages.length - 1];
                if (page && page.loadHealthData) {
                  setTimeout(function () { page.loadHealthData(); }, 500);
                }
              }).catch(function () {});
            },
            fail: function () {
              console.log('WeRun data not available (expected in dev tools)');
            }
          });
        }
      },
      fail: function () {}
    });
  },

  onQuickTap: function (e) {
    var qt = this.data.quickTypes[e.currentTarget.dataset.idx];
    this.setData({ showQuickRecord: true, quickType: qt.type, quickLabel: qt.label, quickUnit: qt.unit, quickValue: '' });
  },
  onQuickValue: function (e) { this.setData({ quickValue: e.detail.value }); },
  submitQuickRecord: function () {
    var that = this;
    var v = parseFloat(this.data.quickValue);
    if (isNaN(v) || v <= 0) { wx.showToast({ title: '请输入有效数值', icon: 'none' }); return; }
    var dataTypeMap = { water: 'water', weight: 'weight', sleep: 'sleep' };
    var sendValue = v;
    if (this.data.quickType === 'sleep') sendValue = v * 60;
    API.post('/api/health/record', {
      data_type: dataTypeMap[this.data.quickType] || this.data.quickType,
      value: sendValue, unit: this.data.quickUnit
    }).then(function () {
      wx.showToast({ title: '已记录', icon: 'success' });
      that.setData({ showQuickRecord: false });
      setTimeout(function () { that.loadHealthData(); }, 500);
    }).catch(function () { wx.showToast({ title: '记录失败', icon: 'none' }); });
  },
  closeQuickRecord: function () { this.setData({ showQuickRecord: false }); },

  loadHealthData: function () {
    var that = this;
    API.get('/api/health/analysis-summary?days=1').then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.summary) {
        var s = res.data.summary;
        if (!s.steps && !s.calories && !s.sleep) return;

        var stepsVal = s.steps ? s.steps.latest : null;
        var calVal = s.calories ? s.calories.latest : null;
        var sleepVal = s.sleep ? s.sleep.latest : null;

        var stepsPct = stepsVal != null ? Math.min(100, Math.round(stepsVal / 10000 * 100)) : 0;
        var calPct = calVal != null ? Math.min(100, Math.round(calVal / 500 * 100)) : 0;
        var sleepPct = sleepVal != null ? Math.min(100, Math.round(sleepVal / 8 * 100)) : 0;

        function fmt(val, type) {
          if (val == null) return '--';
          if (type === 'steps') return val >= 10000 ? (val / 1000).toFixed(1) + 'k' : String(Math.round(val));
          if (type === 'sleep') return parseFloat(val).toFixed(1);
          return String(Math.round(val));
        }

        that.setData({
          ringsData: {
            steps: { value: stepsVal, target: 10000, pct: stepsPct, display: fmt(stepsVal, 'steps') },
            calories: { value: calVal, target: 500, pct: calPct, display: fmt(calVal, 'calories') },
            sleep: { value: sleepVal, target: 8, pct: sleepPct, display: fmt(sleepVal, 'sleep') },
            separate: [
              { key: 'steps', color: '#3dd68c', value: stepsVal, target: 10000, pct: stepsPct, display: fmt(stepsVal, 'steps'), label: '今日步数' },
              { key: 'calories', color: '#f59e4b', value: calVal, target: 500, pct: calPct, display: fmt(calVal, 'calories'), label: '今日消耗' },
              { key: 'sleep', color: '#5e9eff', value: sleepVal, target: 8, pct: sleepPct, display: fmt(sleepVal, 'sleep'), label: '昨晚睡眠' }
            ]
          }
        });

        // Draw rings after DOM renders (Canvas nodes always mounted, no wx:if destroy)
        setTimeout(function () { that.drawRings(); }, 300);
      }
    }).catch(function () {});
  },

  // ═══ Canvas 2D Ring Drawing (Apple Health style, with animation) ═══
  _prevPcts: null,
  _prevSepPcts: null,

  drawRings: function () {
    var that = this;
    var isDark = this.data._theme === 'dark';
    var trackColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    var rd = this.data.ringsData;

    if (this.data.ringMode === 'combined') {
      var query = wx.createSelectorQuery().in(this);
      query.select('#ringsCombinedCanvas').fields({ node: true, size: true }).exec(function (res) {
        if (!res || !res[0] || !res[0].node) return;
        var canvas = res[0].node;
        var ctx = canvas.getContext('2d');
        var dpr = (wx.getWindowInfo && wx.getWindowInfo().pixelRatio) || wx.getSystemInfoSync().pixelRatio;
        var w = res[0].width;
        var h = res[0].height;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        var cx = w / 2;
        var cy = h * 0.47;
        var radii = [104, 80, 56];
        var colors = ['#3dd68c', '#f59e4b', '#5e9eff'];
        var targetPcts = [rd.steps.pct, rd.calories.pct, rd.sleep.pct];
        var lw = 18;

        var prev = that._prevPcts || [0, 0, 0];
        var startTime = Date.now();
        var duration = 800;
        function animFrame() {
          var elapsed = Date.now() - startTime;
          var t = Math.min(1, elapsed / duration);
          var ease = 1 - Math.pow(1 - t, 3);
          ctx.clearRect(0, 0, w, h);
          for (var i = 0; i < 3; i++) {
            var cur = prev[i] + (targetPcts[i] - prev[i]) * ease;
            drawRingArc(ctx, cx, cy, radii[i], cur, colors[i], trackColor, lw);
          }
          if (t < 1) { setTimeout(animFrame, 16); }
        }
        animFrame();
        that._prevPcts = targetPcts;
      });
    } else {
      // Separate mode: 3 canvases, init once then animate
      var query2 = wx.createSelectorQuery().in(this);
      query2.select('#sepRingCanvas0').fields({ node: true, size: true });
      query2.select('#sepRingCanvas1').fields({ node: true, size: true });
      query2.select('#sepRingCanvas2').fields({ node: true, size: true });
      query2.exec(function (res) {
        if (!res || !res[0] || !res[0].node) return;
        var dpr = (wx.getWindowInfo && wx.getWindowInfo().pixelRatio) || wx.getSystemInfoSync().pixelRatio;
        var colors = ['#3dd68c', '#f59e4b', '#5e9eff'];
        var targetPcts = [rd.separate[0].pct, rd.separate[1].pct, rd.separate[2].pct];
        var prev = that._prevSepPcts || [0, 0, 0];

        // Init all 3 canvases once
        var ctxs = [];
        var dims = [];
        for (var j = 0; j < 3; j++) {
          var info = res[j];
          if (!info || !info.node) { ctxs.push(null); dims.push(null); continue; }
          var c = info.node;
          c.width = info.width * dpr;
          c.height = info.height * dpr;
          var ct = c.getContext('2d');
          ct.scale(dpr, dpr);
          ctxs.push(ct);
          dims.push({ w: info.width, h: info.height });
        }

        var startTime = Date.now();
        var duration = 800;
        function animFrame() {
          var elapsed = Date.now() - startTime;
          var t = Math.min(1, elapsed / duration);
          var ease = 1 - Math.pow(1 - t, 3);
          for (var i = 0; i < 3; i++) {
            if (!ctxs[i]) continue;
            var dm = dims[i];
            ctxs[i].clearRect(0, 0, dm.w, dm.h);
            var cur = prev[i] + (targetPcts[i] - prev[i]) * ease;
            var cx = dm.w / 2;
            var cy = dm.h * 0.44;
            var radius = Math.min(dm.w, dm.h) * 0.38;
            drawRingArc(ctxs[i], cx, cy, radius, cur, colors[i], trackColor, 16);
          }
          if (t < 1) { setTimeout(animFrame, 16); }
        }
        animFrame();
        that._prevSepPcts = targetPcts;
      });
    }
  },

  toggleRingMode: function () {
    var mode = this.data.ringMode === 'combined' ? 'separate' : 'combined';
    this.setData({ ringMode: mode }, function () {
      // Canvas nodes switch via display:none/block — still in DOM, query works
      setTimeout(this.drawRings.bind(this), 350);
    }.bind(this));
  },

  onUsername: function (e) { this.setData({ username: e.detail.value }); },
  onPassword: function (e) { this.setData({ password: e.detail.value }); },
  onConfirmPassword: function (e) { this.setData({ confirmPassword: e.detail.value }); },
  toggleAuthMode: function () {
    this.setData({ showRegister: !this.data.showRegister, error: '', confirmPassword: '' });
  },
  doRegister: function () {
    var that = this;
    var u = (this.data.username || '').trim();
    var p = this.data.password || '';
    var cp = this.data.confirmPassword || '';
    if (!u) { this.setData({ error: '请输入用户名' }); return; }
    if (p.length < 8) { this.setData({ error: '密码至少8位' }); return; }
    if (p !== cp) { this.setData({ error: '两次密码不一致' }); return; }
    this.setData({ loading: true, error: '' });
    API.register(u, p).then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.success) {
        that.setData({ loggedIn: true, loading: false });
        that.loadDashboard(); that.syncWeRunData();
      } else {
        that.setData({ error: (res.data && res.data.detail) || '注册失败', loading: false });
      }
    }).catch(function () { that.setData({ error: '网络错误', loading: false }); });
  },
  doLogin: function () {
    var that = this;
    this.setData({ loading: true, error: '' });
    API.login(this.data.username, this.data.password).then(function (res) {
      if (res.statusCode === 200 && res.data && res.data.success) {
        getApp().setToken(res.data.token || '');
        that.setData({ loggedIn: true, loading: false });
        that.loadDashboard(); that.syncWeRunData();
      } else { that.setData({ error: (res.data && res.data.detail) || '登录失败', loading: false }); }
    }).catch(function () { that.setData({ error: '网络错误', loading: false }); });
  },
  doWechatLogin: function () {
    var that = this;
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) { wx.showToast({ title: '微信登录失败', icon: 'none' }); return; }
        that.setData({ loading: true, error: '' });
        API.post('/api/auth/wechat-login', { code: loginRes.code }).then(function (res) {
          if (res.statusCode === 200 && res.data && res.data.success) {
            getApp().setToken(res.data.token || '');
            that.setData({ loggedIn: true, loading: false });
            that.loadDashboard(); that.syncWeRunData();
          } else { that.setData({ error: (res.data && res.data.detail) || '微信登录失败', loading: false }); }
        }).catch(function () { that.setData({ error: '网络错误', loading: false }); });
      },
      fail: function () { wx.showToast({ title: '微信登录失败', icon: 'none' }); }
    });
  },

  goChat: function () { wx.switchTab({ url: '/pages/chat/chat' }); },
  goPlanChat: function () { wx.navigateTo({ url: '/pages/plan-wizard/plan-wizard' }); },
  goHealth: function () { wx.switchTab({ url: '/pages/health/health' }); },
  goProfile: function () { wx.switchTab({ url: '/pages/profile/profile' }); },
  goPlan: function () { wx.navigateTo({ url: '/pages/plan/plan' }); },
  goExerciseLib: function () { wx.navigateTo({ url: '/pages/exercise-library/exercise-library' }); },
  goPose: function () { wx.navigateTo({ url: '/pages/pose/pose' }); }
});
