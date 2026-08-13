// FitAI 微信小程序 — App 入口
var API = require('./utils/api.js');

App({
  globalData: {
    token: '',
    userId: 0,
    username: '',
    isAdmin: false,
    theme: 'dark',
  },

  onLaunch: function() {
    var token = wx.getStorageSync('fitai_token');
    if (token) {
      this.globalData.token = token;
      this.checkAuth();
    }
    // 恢复主题
    var theme = wx.getStorageSync('fitai_theme') || 'dark';
    this.globalData.theme = theme;
    this.applyTheme(theme);
  },

  checkAuth: function() {
    var that = this;
    API.get('/api/auth/status').then(function(res) {
      if (res.data && res.data.authenticated) {
        that.globalData.userId = res.data.user_id || 0;
        that.globalData.isAdmin = res.data.is_admin || false;
      } else {
        wx.removeStorageSync('fitai_token');
        that.globalData.token = '';
      }
    }).catch(function() {});
  },

  setToken: function(token) {
    this.globalData.token = token;
    wx.setStorageSync('fitai_token', token);
  },

  setTheme: function(theme) {
    this.globalData.theme = theme;
    wx.setStorageSync('fitai_theme', theme);
    this.applyTheme(theme);
  },

  applyTheme: function(theme) {
    // 通过 setData 更新 page 元素上的 data-theme 属性
    var pages = getCurrentPages();
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].setData) {
        pages[i].setData({ _theme: theme });
      }
    }
  },

  logout: function() {
    wx.removeStorageSync('fitai_token');
    this.globalData.token = '';
    this.globalData.userId = 0;
  }
});
