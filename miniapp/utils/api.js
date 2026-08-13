// API 请求封装
var app = getApp();

function request(method, path, data) {
  return new Promise(function(resolve, reject) {
    var token = (app && app.globalData && app.globalData.token) || wx.getStorageSync('fitai_token') || '';
    wx.request({
      url: 'https://fitmate.top' + path,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : '',
      },
      success: function(res) {
        if (res.statusCode === 401) {
          wx.removeStorageSync('fitai_token');
          if (app && app.globalData) app.globalData.token = '';
        }
        resolve(res);
      },
      fail: reject,
    });
  });
}

// V17: WebSocket chat connection for streaming
function connectChatWS(token) {
  var wsUrl = 'wss://fitmate.top/ws/chat?token=' + encodeURIComponent(token || '');
  var socket = wx.connectSocket({
    url: wsUrl,
    header: { 'content-type': 'application/json' },
    fail: function(err) {
      console.error('WS connect failed:', err);
    }
  });
  return socket;
}

module.exports = {
  get: function(path) { return request('GET', path); },
  post: function(path, data) { return request('POST', path, data); },
  login: function(username, password) {
    return request('POST', '/api/auth/login', { username: username, password: password }).then(function(res) {
      if (res.statusCode === 200 && res.data && res.data.success) {
        var token = res.data.token || '';
        if (token) {
          getApp().setToken(token);
        }
      }
      return res;
    });
  },
  register: function(username, password) {
    return request('POST', '/api/auth/register', { username: username, password: password }).then(function(res) {
      if (res.statusCode === 200 && res.data && res.data.success) {
        var token = res.data.token || '';
        if (token) {
          getApp().setToken(token);
        }
      }
      return res;
    });
  },
  chat: function(message) {
    return request('POST', '/api/chat', { message: message });
  },
  connectChatWS: connectChatWS
};
