var API = require('../../utils/api.js');

var SUPPORTED_EXTS = ['.xml', '.csv', '.json', '.zip', '.tcx', '.gpx'];
var EXT_LABELS = 'XML / CSV / JSON / ZIP / TCX / GPX';

Page({
  data: {
    _theme: 'dark',
    uploading: false,
    uploadProgress: 0,
    jobId: '',
    jobStatus: '',
    jobResult: null,
    fileName: '',
    fileSize: '',
    error: ''
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    if (!getApp().globalData.token) {
      wx.showToast({ title: '请先登录', icon: 'none' });
    }
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  chooseFile: function () {
    var that = this;
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      success: function (res) {
        var file = res.tempFiles[0];
        var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (SUPPORTED_EXTS.indexOf(ext) === -1) {
          wx.showToast({ title: '不支持的文件类型，支持: ' + EXT_LABELS, icon: 'none', duration: 3000 });
          return;
        }
        if (file.size > 50 * 1024 * 1024) {
          wx.showToast({ title: '文件不能超过 50MB', icon: 'none' });
          return;
        }
        that.setData({
          fileName: file.name,
          fileSize: (file.size / 1024 / 1024).toFixed(1) + ' MB',
          error: ''
        });
        that.uploadFile(file.path, file.name);
      }
    });
  },

  uploadFile: function (filePath, fileName) {
    var that = this;
    var token = getApp().globalData.token;

    this.setData({ uploading: true, uploadProgress: 0, jobStatus: '上传中...' });

    var uploadTask = wx.uploadFile({
      url: 'https://fitmate.top/api/health/import-file',
      filePath: filePath,
      name: 'file',
      header: {
        'Authorization': token ? 'Bearer ' + token : ''
      },
      success: function (res) {
        if (res.statusCode === 200 || res.statusCode === 201) {
          try {
            var data = JSON.parse(res.data);
            that.setData({ jobId: data.job_id || '', jobStatus: '解析中...' });
            that.pollStatus(data.job_id);
          } catch (e) {
            that.setData({ uploading: false, error: '响应解析失败' });
          }
        } else if (res.statusCode === 401) {
          that.setData({ uploading: false, error: '登录已过期，请重新登录' });
        } else {
          var detail = '';
          try { detail = JSON.parse(res.data).detail || ''; } catch (e) {}
          that.setData({ uploading: false, error: detail || '上传失败 (' + res.statusCode + ')' });
        }
      },
      fail: function (err) {
        that.setData({ uploading: false, error: '网络错误: ' + (err.errMsg || '') });
      }
    });

    uploadTask.onProgressUpdate(function (res) {
      that.setData({ uploadProgress: res.progress });
    });
  },

  pollStatus: function (jobId) {
    var that = this;
    var attempts = 0;
    var maxAttempts = 60; // 2 minutes max

    var timer = setInterval(function () {
      attempts++;
      API.get('/api/health/import-status?job_id=' + jobId).then(function (res) {
        if (!res.data) return;
        var status = res.data.status;
        that.setData({ jobStatus: status === 'running' ? '解析数据中...' : status });

        if (status === 'done') {
          clearInterval(timer);
          that.setData({
            uploading: false,
            jobStatus: '完成',
            jobResult: res.data.result
          });
          wx.showToast({ title: '导入成功！', icon: 'success' });
        } else if (status === 'error') {
          clearInterval(timer);
          that.setData({
            uploading: false,
            jobStatus: '失败',
            error: res.data.error_msg || '导入失败'
          });
        }
      }).catch(function () {
        // keep polling
      });

      if (attempts >= maxAttempts) {
        clearInterval(timer);
        that.setData({ uploading: false, error: '导入超时，请稍后查看是否完成' });
      }
    }, 2000);
  },

  goBack: function () {
    wx.navigateBack({ delta: 1 });
  }
});
