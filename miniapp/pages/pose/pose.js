var API = require('../../utils/api.js');

// Biomechanical checkpoints per exercise type
var CHECKPOINTS = {
  squat: [
    '双脚与肩同宽，脚尖微微朝外',
    '下蹲时膝盖不要超过脚尖',
    '保持背部挺直，核心收紧',
    '膝盖不要内扣，向外打开',
    '蹲到大腿与地面平行即可',
  ],
  pushup: [
    '双手与肩同宽或略宽',
    '身体成一条直线，核心收紧',
    '下降时肘部与身体呈45度',
    '不要塌腰或撅臀',
    '下巴、胸部、腹部同时触地',
  ],
  plank: [
    '肘部在肩膀正下方',
    '身体从脚跟到头部成一条直线',
    '收紧臀部和腹肌',
    '不要塌腰',
    '保持正常呼吸，不要憋气',
  ],
  lunge: [
    '前脚和后脚在一条直线上',
    '前膝不要超过脚尖',
    '躯干保持直立',
    '后膝轻轻触地但不支撑重量',
    '核心收紧保持平衡',
  ],
  ytw: [
    '俯卧在垫子上，额头贴地',
    '双臂分别举成 Y、T、W 形',
    '用背部肌肉发力带动手臂',
    '不要耸肩',
    '每个位置保持2秒',
  ],
};

var EXERCISE_LIST = [
  { id: 'squat', name: '深蹲', target: '股四头肌 · 臀肌 · 核心', color: '#3dd68c' },
  { id: 'pushup', name: '俯卧撑', target: '胸肌 · 三角肌 · 肱三头肌', color: '#5e9eff' },
  { id: 'plank', name: '平板支撑', target: '核心 · 腹肌 · 竖脊肌', color: '#f59e4b' },
  { id: 'lunge', name: '弓步蹲', target: '股四头肌 · 臀肌 · 腿后肌', color: '#a78bfa' },
  { id: 'ytw', name: 'YTW 肩背', target: '菱形肌 · 斜方肌下束 · 肩袖', color: '#f87171' },
];

Page({
  data: {
    _theme: 'dark',
    step: 'select',       // select | ready | analyzing | result
    exercises: EXERCISE_LIST,
    selectedExercise: null,
    currentCheckpoints: [],
    videoPath: '',
    analysisProgress: 0,
    analysisMessage: '上传视频中...',
    diagnosis: null,
    errorMsg: '',
    progressTimer: null,
  },

  onLoad: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
  },

  onUnload: function () {
    if (this.data.progressTimer) clearInterval(this.data.progressTimer);
  },

  // ═══ Exercise Selection ═══
  selectExercise: function (e) {
    var id = e.currentTarget.dataset.id;
    var name = e.currentTarget.dataset.name;
    var checkpoints = CHECKPOINTS[id] || [];
    var ex = EXERCISE_LIST.find(function (item) { return item.id === id; });
    this.setData({
      selectedExercise: ex || { id: id, name: name },
      currentCheckpoints: checkpoints,
      step: 'ready',
      diagnosis: null,
      errorMsg: '',
    });
  },

  backToSelect: function () {
    this.setData({ step: 'select', selectedExercise: null, currentCheckpoints: [] });
  },

  retryPose: function () {
    this.setData({ step: 'select', selectedExercise: null, currentCheckpoints: [], diagnosis: null, errorMsg: '', videoPath: '' });
  },

  // ═══ Recording ═══
  startRecord: function () {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['video'],
      sourceType: ['camera'],
      maxDuration: 30,
      camera: 'back',
      success: function (res) {
        var tempFilePath = res.tempFiles[0].tempFilePath;
        var duration = res.tempFiles[0].duration || 0;
        if (duration < 2) {
          wx.showToast({ title: '视频太短，至少2秒', icon: 'none' });
          return;
        }
        that.setData({ videoPath: tempFilePath });
        that.uploadAndAnalyze(tempFilePath);
      },
      fail: function (err) {
        if (err.errMsg && err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '录制失败，请重试', icon: 'none' });
        }
      }
    });
  },

  chooseFromAlbum: function () {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['video'],
      sourceType: ['album'],
      maxDuration: 30,
      success: function (res) {
        var tempFilePath = res.tempFiles[0].tempFilePath;
        that.setData({ videoPath: tempFilePath });
        that.uploadAndAnalyze(tempFilePath);
      },
      fail: function (err) {
        if (err.errMsg && err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '选择失败，请重试', icon: 'none' });
        }
      }
    });
  },

  // ═══ Upload & Analyze ═══
  uploadAndAnalyze: function (filePath) {
    var that = this;
    this.setData({ step: 'analyzing', analysisProgress: 0, analysisMessage: '上传视频中...' });

    // Simulate progress
    var timer = setInterval(function () {
      var p = that.data.analysisProgress;
      if (p < 85) {
        var newP = p + Math.random() * 15;
        if (newP > 85) newP = 85;
        var msg = newP < 30 ? '上传视频中...' : (newP < 60 ? '提取视频帧...' : '分析动作姿态...');
        that.setData({ analysisProgress: Math.round(newP), analysisMessage: msg });
      }
    }, 800);
    this.setData({ progressTimer: timer });

    var token = (getApp().globalData && getApp().globalData.token) || wx.getStorageSync('fitai_token') || '';

    wx.uploadFile({
      url: 'https://fitmate.top/api/pose/analyze-video',
      filePath: filePath,
      name: 'video',
      header: {
        'Authorization': token ? 'Bearer ' + token : '',
      },
      formData: {
        exercise: this.data.selectedExercise.id || 'squat',
      },
      success: function (res) {
        clearInterval(timer);
        that.setData({ analysisProgress: 100, analysisMessage: '分析完成' });

        try {
          var data = JSON.parse(res.data);
          if (data && data.success) {
            setTimeout(function () {
              that.setData({ step: 'result', diagnosis: data });
            }, 600);
          } else {
            that.setData({
              step: 'result',
              diagnosis: null,
              errorMsg: (data && data.message) || '分析失败，请重试',
            });
          }
        } catch (e) {
          that.setData({
            step: 'result',
            diagnosis: null,
            errorMsg: '服务器返回格式异常',
          });
        }
      },
      fail: function () {
        clearInterval(timer);
        that.setData({
          step: 'result',
          diagnosis: null,
          errorMsg: '网络错误，请检查网络后重试',
        });
      }
    });
  },

  // ═══ Navigation ═══
  goChat: function () {
    wx.switchTab({ url: '/pages/chat/chat' });
  },
});
