var app = getApp();

Component({
  options: { styleIsolation: 'apply-shared' },
  data: {
    _theme: 'dark',
    selected: 0,
    list: [
      { pagePath: "/pages/index/index", text: "首页" },
      { pagePath: "/pages/chat/chat", text: "AI教练" },
      { pagePath: "/pages/health/health", text: "健康" },
      { pagePath: "/pages/profile/profile", text: "我的" }
    ]
  },

  attached: function () {
    var theme = (app && app.globalData && app.globalData.theme) || wx.getStorageSync('fitai_theme') || 'dark';
    this.setData({ _theme: theme });
  },

  methods: {
    updateTheme: function (theme) {
      if (theme) this.setData({ _theme: theme });
    },

    switchTab: function (e) {
      var index = e.currentTarget.dataset.index;
      var item = this.data.list[index];
      if (this.data.selected === index) return;
      wx.switchTab({ url: item.pagePath });
    }
  }
});
