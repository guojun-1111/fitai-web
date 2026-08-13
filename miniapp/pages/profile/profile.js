var app = getApp();
var API = require('../../utils/api.js');

Page({
  data: {
    _theme: 'dark',
    // User info
    username: '',
    isAdmin: false,
    authenticated: false,
    // Server status
    serverStatus: '检查中...',
    userCount: 0,
    registrationOpen: true,
    cacheSize: '',
    // Profile form
    profile: { name: '', gender: '', birth: '', height: '', weight: '', level: '', goal: '', notes: '' },
    profileSaved: false,
    // AI Model
    currentModel: 'deepseek-v4-flash',
    // Reply style
    replyStyle: 'casual',
    // Coach style — determines AI persona
    coachStyle: 'friend',
    // Theme
    currentTheme: 'dark',
    // Admin
    showAdmin: false
  },

  onShow: function () {
    this.setData({ _theme: app.globalData.theme || 'dark', currentTheme: app.globalData.theme || 'dark' });
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 3 });
    }
    this.loadProfile();
  },

  loadProfile: function () {
    var that = this;
    var g = app.globalData;
    this.setData({
      username: g.username || '未登录',
      isAdmin: g.isAdmin || false,
      authenticated: !!g.token
    });

    // Server status
    API.get('/api/auth/status').then(function (res) {
      if (res.data) {
        that.setData({
          serverStatus: res.data.auth_enabled ? '在线' : '初始化中',
          userCount: res.data.user_count || 0,
          authenticated: res.data.authenticated || false,
          isAdmin: res.data.is_admin || false,
          registrationOpen: res.data.registration_allowed
        });
      }
    }).catch(function () {
      that.setData({ serverStatus: '离线' });
    });

    // Cache size
    try {
      var info = wx.getStorageInfoSync();
      this.setData({ cacheSize: (info.currentSize || 0).toFixed(1) + ' KB / ' + (info.limitSize || 0).toFixed(0) + ' KB' });
    } catch (e) {}

    // Load saved profile & preferences
    var profile = wx.getStorageSync('fitai_profile') || {};
    this.setData({
      profile: profile,
      currentModel: wx.getStorageSync('fitai_model') || 'deepseek-v4-flash',
      replyStyle: wx.getStorageSync('fitai_reply_style') || 'casual',
      coachStyle: wx.getStorageSync('fitai_coach_style') || 'friend'
    });
  },

  // Profile form
  onProfileInput: function (e) {
    var field = e.currentTarget.dataset.field;
    var profile = this.data.profile;
    profile[field] = e.detail.value;
    this.setData({ profile: profile, profileSaved: false });
  },

  saveProfile: function () {
    var that = this;
    wx.setStorageSync('fitai_profile', this.data.profile);
    // Map mini-program field names to backend field names
    var p = this.data.profile;
    var serverProfile = {
      name: p.name || '',
      gender: p.gender || '',
      birth_year: p.birth ? parseInt(p.birth) : null,
      height_cm: p.height ? parseFloat(p.height) : null,
      weight_kg: p.weight ? parseFloat(p.weight) : null,
      fitness_goal: p.goal || '',
      activity_level: p.level || '',
      notes: p.notes || '',
      coach_style: this.data.coachStyle
    };
    API.post('/api/profile/update', serverProfile).then(function () {}).catch(function () {});
    this.setData({ profileSaved: true });
    wx.showToast({ title: '已保存', icon: 'success' });
    setTimeout(function () { that.setData({ profileSaved: false }); }, 2000);
  },

  // AI Model
  switchModel: function (e) {
    var model = e.currentTarget.dataset.model;
    this.setData({ currentModel: model });
    wx.setStorageSync('fitai_model', model);
    API.post('/api/settings/model', { model: model }).catch(function () {});
    wx.showToast({ title: '模型已切换', icon: 'success' });
  },

  // Reply style
  setStyle: function (e) {
    var style = e.currentTarget.dataset.style;
    this.setData({ replyStyle: style });
    wx.setStorageSync('fitai_reply_style', style);
    API.post('/api/settings/reply-style', { style: style }).catch(function () {});
  },

  // Coach style — determines AI persona (friend / coach / family)
  setCoachStyle: function (e) {
    var style = e.currentTarget.dataset.cs;
    this.setData({ coachStyle: style });
    wx.setStorageSync('fitai_coach_style', style);
    // Sync to server via profile update
    API.post('/api/profile/update', { coach_style: style }).catch(function () {});
    var labels = { friend: '像朋友', coach: '像教练', family: '像家人' };
    wx.showToast({ title: '教练风格：' + (labels[style] || style), icon: 'success' });
  },

  // Theme
  switchTheme: function (e) {
    var theme = e.currentTarget.dataset.theme;
    this.setData({ currentTheme: theme });
    app.setTheme(theme);
    if (typeof this.getTabBar === 'function' && this.getTabBar()) this.getTabBar().updateTheme(theme);
    wx.showToast({ title: '主题已切换', icon: 'success' });
  },

  // Registration toggle (admin)
  toggleRegistration: function (e) {
    var allowed = e.detail.value;
    API.post('/api/admin/toggle-registration', { allowed: allowed }).then(function () {
      wx.showToast({ title: allowed ? '注册已开启' : '注册已关闭', icon: 'success' });
    }).catch(function () {
      wx.showToast({ title: '操作失败', icon: 'none' });
    });
  },

  // Navigate
  goTrainingPlan: function () {
    wx.navigateTo({ url: '/pages/index/index' });  // training plan lives on index page
  },

  goImport: function () {
    wx.navigateTo({ url: '/pages/import/import' });
  },

  goDashboard: function () {
    wx.navigateTo({ url: '/pages/dashboard/dashboard' });
  },

  goHistory: function () {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goExercises: function () {
    wx.navigateTo({ url: '/pages/exercises/exercises' });
  },

  goExerciseLib: function () {
    wx.navigateTo({ url: '/pages/exercise-library/exercise-library' });
  },

  goInsights: function () {
    wx.navigateTo({ url: '/pages/insights/insights' });
  },

  // Cache & Logout
  clearCache: function () {
    var that = this;
    wx.showModal({
      title: '清除缓存',
      content: '将清除所有本地数据，需要重新登录',
      success: function (res) {
        if (res.confirm) {
          wx.clearStorageSync();
          app.globalData.token = '';
          app.globalData.userId = 0;
          that.loadProfile();
          wx.showToast({ title: '已清除', icon: 'success' });
        }
      }
    });
  },

  doLogout: function () {
    var that = this;
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: function (res) {
        if (res.confirm) {
          API.post('/api/auth/logout').catch(function () {});
          wx.removeStorageSync('fitai_token');
          app.globalData.token = '';
          app.logout();
          that.setData({ authenticated: false, username: '未登录', isAdmin: false });
          wx.reLaunch({ url: '/pages/index/index' });
        }
      }
    });
  }
});
