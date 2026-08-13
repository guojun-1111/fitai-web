var API = require('../../utils/api.js');

var PROMPTS = [
  { text: '今天练什么？', icon: '💪' },
  { text: '分析我的训练数据', icon: '📊' },
  { text: '推荐减脂饮食', icon: '🥗' },
  { text: '记录今天的运动', icon: '✍️' },
  { text: '改善睡眠建议', icon: '🌙' },
  { text: '教学视频推荐', icon: '🎬' }
];

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function parseInline(s) {
  var out = '';
  var parts = s.split(/(\[.*?\]\(.*?\))/g);
  for (var i = 0; i < parts.length; i++) {
    var m = parts[i].match(/^\[(.*)\]\((.*)\)$/);
    if (m) {
      out += '<a href="' + escHtml(m[2]) + '" style="color:var(--green);text-decoration:underline;">' + escHtml(m[1]) + '</a>';
    } else {
      var bolds = parts[i].split(/(\*\*.*?\*\*)/g);
      for (var j = 0; j < bolds.length; j++) {
        if (bolds[j].indexOf('**') === 0 && bolds[j].lastIndexOf('**') === bolds[j].length - 2) {
          out += '<strong>' + escHtml(bolds[j].slice(2, -2)) + '</strong>';
        } else {
          out += escHtml(bolds[j]);
        }
      }
    }
  }
  return out;
}

function parseMarkdown(text) {
  if (!text) return '';
  var suggestionIdx = text.indexOf('[SUGGESTIONS]');
  if (suggestionIdx > -1) text = text.substring(0, suggestionIdx).trim();
  if (!text) return '';
  var lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  var html = '';
  var inList = '';
  function closeList() {
    if (inList === 'ul') { html += '</ul>'; }
    else if (inList === 'ol') { html += '</ol>'; }
    inList = '';
  }
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (!line.trim()) { closeList(); continue; }
    var h = line.match(/^###\s+(.+)/);
    if (h) { closeList(); html += '<h3 style="font-size:30rpx;font-weight:bold;color:var(--text);margin:16rpx 0 8rpx;">' + parseInline(h[1]) + '</h3>'; continue; }
    var ul = line.match(/^[\-\*]\s+(.+)/);
    if (ul) { if (inList !== 'ul') { closeList(); html += '<ul style="padding-left:32rpx;margin:4rpx 0;">'; inList = 'ul'; } html += '<li style="margin-bottom:4rpx;">' + parseInline(ul[1]) + '</li>'; continue; }
    var ol = line.match(/^\d+\.\s+(.+)/);
    if (ol) { if (inList !== 'ol') { closeList(); html += '<ol style="padding-left:32rpx;margin:4rpx 0;">'; inList = 'ol'; } html += '<li style="margin-bottom:4rpx;">' + parseInline(ol[1]) + '</li>'; continue; }
    closeList();
    html += '<p style="margin:4rpx 0;line-height:1.65;">' + parseInline(line) + '</p>';
  }
  closeList();
  return html;
}

Page({
  data: {
    _theme: 'dark', messages: [], input: '', typing: false, lastFailed: false,
    showPrompts: true, recording: false, scrollToId: ''
  },

  onLoad: function () {
    var that = this;
    this.setData({ _theme: getApp().globalData.theme || 'dark', showPrompts: true });
    this._recorder = wx.getRecorderManager();
    this._recorder.onStop(function (res) {
      that.setData({ recording: false });
      if (res.tempFilePath) { that.setData({ input: '[语音消息]' }); that.send('[语音消息]'); }
    });
    this._recorder.onError(function () { that.setData({ recording: false }); wx.showToast({ title: '录音失败', icon: 'none' }); });
  },

  onShow: function () {
    this.setData({ _theme: getApp().globalData.theme || 'dark' });
    if (typeof this.getTabBar === 'function' && this.getTabBar()) { this.getTabBar().setData({ selected: 1 }); this.getTabBar().updateTheme(getApp().globalData.theme); }
  },

  onHide: function () { this._cleanup(); },
  onUnload: function () { this._cleanup(); },

  _cleanup: function () {
    if (this._pingTimer) { clearInterval(this._pingTimer); this._pingTimer = null; }
    if (this._respTimeout) { clearTimeout(this._respTimeout); this._respTimeout = null; }
    if (this._socketTask) { try { this._socketTask.close({ code: 1000, reason: 'page hide' }); } catch (e) {} this._socketTask = null; }
  },

  onInput: function (e) { this.setData({ input: e.detail.value }); },

  send: function (e) {
    var text = '';
    if (typeof e === 'string') { text = e; }
    else if (e && e.currentTarget && e.currentTarget.dataset.text) { text = e.currentTarget.dataset.text; }
    else { text = this.data.input.trim(); }
    if (!text) return;

    var userMsg = { role: 'user', content: text, id: Date.now(), mdHtml: parseMarkdown(text) };
    var msgs = this.data.messages.concat([userMsg]);
    var aiMsgId = Date.now() + 1;
    var aiMsg = { role: 'assistant', content: '', id: aiMsgId, streaming: true, steps: [], stepsCollapsed: true, mdHtml: '', planCard: null };
    msgs.push(aiMsg);
    this.setData({ messages: msgs, input: '', typing: true, showPrompts: false, lastFailed: false });
    this.scrollToBottom();

    var that = this;
    var token = getApp().globalData.token || wx.getStorageSync('fitai_token') || '';
    this._cleanup();

    if (!token) {
      msgs[msgs.length - 1] = { role: 'assistant', content: '请先在首页完成登录，然后才能使用 AI 教练。', id: Date.now(), mdHtml: '', streaming: false, error: true };
      this.setData({ messages: msgs, typing: false }); this.scrollToBottom(); return;
    }

    var respTimeout = setTimeout(function () {
      if (that.data.typing) {
        that._cleanup();
        var m = that.data.messages;
        if (m[m.length - 1] && m[m.length - 1].streaming) {
          m[m.length - 1] = { role: 'assistant', content: 'AI 响应超时，请检查网络后重试。', id: Date.now(), mdHtml: '', streaming: false, error: true };
          that.setData({ messages: m, typing: false, lastFailed: true });
        }
      }
    }, 20000);
    this._respTimeout = respTimeout;

    var wsUrl = 'wss://fitmate.top/ws/chat?token=' + encodeURIComponent(token);
    var socketTask = wx.connectSocket({
      url: wsUrl,
      fail: function (err) { console.error('[FitAI] connectSocket failed:', JSON.stringify(err)); that._fallbackSend(text); }
    });

    socketTask.onOpen(function () {
      that._pingTimer = setInterval(function () { try { socketTask.send({ data: JSON.stringify({ type: 'ping' }) }); } catch (e) {} }, 30000);
      socketTask.send({ data: JSON.stringify({ type: 'query', content: text, model: 'deepseek-v4-flash' }) });
    });

    var streamContent = '';
    socketTask.onMessage(function (res) {
      var d;
      if (typeof res.data === 'string') { try { d = JSON.parse(res.data); } catch (e) { return; } }
      else { d = res.data; }
      if (!d || !d.type) return;

      var msgs = that.data.messages;
      var last = msgs[msgs.length - 1];
      if (!last || last.role !== 'assistant') return;
      var lastIdx = msgs.length - 1;

      if (d.type === 'chunk' && d.content) {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        streamContent += d.content;
        var up = {};
        up['messages[' + lastIdx + '].content'] = streamContent;
        up['messages[' + lastIdx + '].mdHtml'] = parseMarkdown(streamContent);
        that.setData(up);

      } else if (d.type === 'thought' || d.type === 'action' || d.type === 'observation') {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        var steps = (last.steps || []).concat([{ stepType: d.type, title: d.title || d.type, content: d.content || '' }]);
        var su = {};
        su['messages[' + lastIdx + '].steps'] = steps;
        su['messages[' + lastIdx + '].stepsCollapsed'] = true;
        that.setData(su);

      } else if (d.type === 'step') {
        var steps2 = (last.steps || []).concat([{ stepType: 'thought', title: d.title || d.content || '', content: d.content || '' }]);
        var su2 = {};
        su2['messages[' + lastIdx + '].steps'] = steps2;
        su2['messages[' + lastIdx + '].stepsCollapsed'] = true;
        that.setData(su2);

      } else if (d.type === 'plan_card') {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        var pu = {};
        pu['messages[' + lastIdx + '].planCard'] = { action: d.action || 'propose', plan: d.plan || null, confirmed: false };
        that.setData(pu);

      } else if (d.type === 'finish') {
        var fc = streamContent || d.answer || d.content || '';
        var fu = {};
        fu['messages[' + lastIdx + '].content'] = fc;
        fu['messages[' + lastIdx + '].mdHtml'] = parseMarkdown(fc);
        fu['messages[' + lastIdx + '].streaming'] = false;
        fu['messages[' + lastIdx + '].stepsCollapsed'] = true;
        fu['typing'] = false;
        // Extract suggestions from [SUGGESTIONS] tag
        var sugMatch = fc.match(/\[SUGGESTIONS\]([\s\S]*?)\[\/SUGGESTIONS\]/);
        if (sugMatch) {
          fu['messages[' + lastIdx + '].suggestions'] = sugMatch[1].split('\n').filter(function (s) { return s.trim(); }).slice(0, 4);
        }
        that.setData(fu); that._cleanup(); that.scrollToBottom();

      } else if (d.type === 'error') {
        var eu = {};
        eu['messages[' + lastIdx + '].content'] = d.content || 'AI 服务出错了，请重试';
        eu['messages[' + lastIdx + '].streaming'] = false;
        eu['messages[' + lastIdx + '].error'] = true;
        eu['typing'] = false;
        that.setData(eu); that._cleanup();

      } else if (d.type === 'greeting') {
        var gm = { role: 'assistant', content: d.content || '', id: Date.now(), mdHtml: parseMarkdown(d.content || ''), streaming: false, stepsCollapsed: true };
        that.setData({ messages: [gm], showPrompts: false }); that.scrollToBottom();
      }
    });

    socketTask.onClose(function (res) {
      clearInterval(that._pingTimer); that._pingTimer = null;
      var msgs = that.data.messages;
      var last = msgs[msgs.length - 1];
      if (last && last.streaming && !last.content) { that._fallbackSend(text); }
      else if (last && last.streaming) { var cu = {}; cu['messages[' + (msgs.length - 1) + '].streaming'] = false; cu['typing'] = false; that.setData(cu); }
    });

    socketTask.onError(function (err) { console.error('[FitAI] WS error:', JSON.stringify(err)); that._cleanup(); that._fallbackSend(text); });
    this._socketTask = socketTask;
  },

  _fallbackSend: function (text) {
    var that = this;
    var msgs = this.data.messages;
    API.chat(text).then(function (res) {
      var reply = '';
      if (res.data && res.data.reply) { reply = res.data.reply; }
      else if (typeof res.data === 'string') {
        var matches = res.data.match(/data:\s*(\{.*\})/g);
        if (matches) { var chunks = []; matches.forEach(function (m) { try { var p = JSON.parse(m.replace('data: ', '')); if (p.content) chunks.push(p.content); } catch (e) {} }); reply = chunks.join(''); }
      }
      if (!reply) { reply = (getApp().globalData.token || wx.getStorageSync('fitai_token')) ? 'AI 服务连接失败，请检查网络后重试。' : '请先在首页完成登录。'; }
      msgs[msgs.length - 1] = { role: 'assistant', content: reply, id: Date.now(), mdHtml: parseMarkdown(reply), streaming: false, stepsCollapsed: true, error: reply.indexOf('失败') > -1 || reply.indexOf('登录') > -1 };
      that.setData({ messages: msgs, typing: false }); that.scrollToBottom();
    }).catch(function () {
      msgs[msgs.length - 1] = { role: 'assistant', content: '网络连接失败，请检查网络后重试。', error: true, id: Date.now(), mdHtml: '', streaming: false };
      that.setData({ messages: msgs, typing: false, lastFailed: true });
    });
  },

  confirmPlan: function (e) {
    var idx = parseInt(e.currentTarget.dataset.msgIdx);
    if (isNaN(idx)) return;
    var card = this.data.messages[idx].planCard;
    if (!card || !card.plan) return;
    var that = this;
    var pu = {};
    pu['messages[' + idx + '].planCard.confirmed'] = true;
    pu['messages[' + idx + '].planCard.action'] = 'confirmed';
    this.setData(pu);
    API.post('/api/training/plan', { name: card.plan.name || '训练计划', goal: card.plan.goal || '综合提升', weeks: 1, plan_data: card.plan }).then(function () {
      wx.showToast({ title: '计划已生效', icon: 'success' });
    }).catch(function () { wx.showToast({ title: '已确认（离线）', icon: 'none' }); });
  },

  adjustPlan: function (e) {
    var idx = parseInt(e.currentTarget.dataset.msgIdx);
    if (isNaN(idx)) return;
    this.send('帮我看看我现在的训练计划，根据我的训练反馈帮我调整一下');
  },

  openCamera: function () {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera'],
      sizeType: ['compressed'],
      success: function (res) {
        var tempPath = res.tempFiles[0].tempFilePath;
        wx.getFileSystemManager().readFile({
          filePath: tempPath,
          encoding: 'base64',
          success: function (readRes) {
            var base64 = 'data:image/jpeg;base64,' + (readRes.data || '');
            that.setData({ showPrompts: false });
            that.sendWithImage('这是什么食物？帮我分析营养成分', base64);
          },
          fail: function () { wx.showToast({ title: '图片读取失败', icon: 'none' }); }
        });
      },
      fail: function (err) {
        if (err.errMsg.indexOf('cancel') === -1) wx.showToast({ title: '拍照失败', icon: 'none' });
      }
    });
  },

  sendWithImage: function (text, base64) {
    if (!text && !base64) return;
    var userMsg = { role: 'user', content: text || '[图片]', id: Date.now(), mdHtml: parseMarkdown(text || '') };
    var msgs = this.data.messages.concat([userMsg]);
    var aiMsgId = Date.now() + 1;
    var aiMsg = { role: 'assistant', content: '', id: aiMsgId, streaming: true, steps: [], stepsCollapsed: true, mdHtml: '', planCard: null };
    msgs.push(aiMsg);
    this.setData({ messages: msgs, input: '', typing: true, showPrompts: false, lastFailed: false });
    this.scrollToBottom();

    var that = this;
    var token = getApp().globalData.token || wx.getStorageSync('fitai_token') || '';
    this._cleanup();
    if (!token) {
      msgs[msgs.length - 1] = { role: 'assistant', content: '请先登录', id: Date.now(), mdHtml: '', streaming: false, error: true };
      this.setData({ messages: msgs, typing: false }); return;
    }

    var respTimeout = setTimeout(function () {
      if (that.data.typing) {
        that._cleanup();
        var m = that.data.messages;
        if (m[m.length - 1] && m[m.length - 1].streaming) {
          m[m.length - 1] = { role: 'assistant', content: 'AI 响应超时', id: Date.now(), mdHtml: '', streaming: false, error: true };
          that.setData({ messages: m, typing: false, lastFailed: true });
        }
      }
    }, 25000);
    this._respTimeout = respTimeout;
    this._setupSocket(token, text, base64);
  },

  _setupSocket: function (token, text, imageBase64) {
    var that = this;
    var wsUrl = 'wss://fitmate.top/ws/chat?token=' + encodeURIComponent(token || '');
    var socketTask = wx.connectSocket({ url: wsUrl, fail: function () { that._fallbackSend(text); } });

    socketTask.onOpen(function () {
      that._pingTimer = setInterval(function () { try { socketTask.send({ data: JSON.stringify({ type: 'ping' }) }); } catch (e) {} }, 30000);
      var payload = { type: 'query', content: text || '识别食物', model: 'deepseek-v4-flash' };
      if (imageBase64) payload.image = imageBase64;
      socketTask.send({ data: JSON.stringify(payload) });
    });

    var streamContent = '';
    socketTask.onMessage(function (res) {
      var d;
      if (typeof res.data === 'string') { try { d = JSON.parse(res.data); } catch (e) { return; } }
      else { d = res.data; }
      if (!d || !d.type) return;
      var msgs = that.data.messages, last = msgs[msgs.length - 1];
      if (!last || last.role !== 'assistant') return;
      var lastIdx = msgs.length - 1;

      if (d.type === 'chunk' && d.content) {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        streamContent += d.content;
        that.setData(['messages[' + lastIdx + '].content'], streamContent);
        that.setData(['messages[' + lastIdx + '].mdHtml'], parseMarkdown(streamContent));
      } else if (d.type === 'thought' || d.type === 'action' || d.type === 'observation') {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        var steps = (last.steps || []).concat([{ stepType: d.type, title: d.title || d.type, content: d.content || '' }]);
        that.setData(['messages[' + lastIdx + '].steps'], steps);
        that.setData(['messages[' + lastIdx + '].stepsCollapsed'], true);
      } else if (d.type === 'step') {
        var steps2 = (last.steps || []).concat([{ stepType: 'thought', title: d.title || d.content || '', content: d.content || '' }]);
        that.setData(['messages[' + lastIdx + '].steps'], steps2);
        that.setData(['messages[' + lastIdx + '].stepsCollapsed'], true);
      } else if (d.type === 'plan_card') {
        if (that._respTimeout) { clearTimeout(that._respTimeout); that._respTimeout = null; }
        that.setData(['messages[' + lastIdx + '].planCard'], { action: d.action || 'propose', plan: d.plan || null, confirmed: false });
      } else if (d.type === 'finish') {
        var fc = streamContent || d.answer || d.content || '';
        that.setData(['messages[' + lastIdx + '].content'], fc);
        that.setData(['messages[' + lastIdx + '].mdHtml'], parseMarkdown(fc));
        that.setData(['messages[' + lastIdx + '].streaming'], false);
        that.setData(['messages[' + lastIdx + '].stepsCollapsed'], true);
        that.setData({ typing: false });
        var sugMatch = fc.match(/\[SUGGESTIONS\]([\s\S]*?)\[\/SUGGESTIONS\]/);
        if (sugMatch) {
          that.setData(['messages[' + lastIdx + '].suggestions'], sugMatch[1].split('\n').filter(function (s) { return s.trim(); }).slice(0, 4));
        }
        that._cleanup(); that.scrollToBottom();
      } else if (d.type === 'error') {
        that.setData(['messages[' + lastIdx + '].content'], d.content || 'AI 出错了');
        that.setData(['messages[' + lastIdx + '].streaming'], false);
        that.setData(['messages[' + lastIdx + '].error'], true);
        that.setData({ typing: false }); that._cleanup();
      } else if (d.type === 'greeting') {
        that.setData({ messages: [{ role: 'assistant', content: d.content || '', id: Date.now(), mdHtml: parseMarkdown(d.content || ''), streaming: false, stepsCollapsed: true }], showPrompts: false });
      }
    });

    socketTask.onClose(function () {
      clearInterval(that._pingTimer); that._pingTimer = null;
      var m = that.data.messages, last = m[m.length - 1];
      if (last && last.streaming && !last.content) { that._fallbackSend(text); }
      else if (last && last.streaming) { that.setData(['messages[' + (m.length - 1) + '].streaming'], false); that.setData({ typing: false }); }
    });
    socketTask.onError(function () { that._cleanup(); that._fallbackSend(text); });
    this._socketTask = socketTask;
  },

  onWelcomeCard: function (e) {
    var action = e.currentTarget.dataset.action;
    if (action === 'plan') {
      wx.navigateTo({ url: '/pages/plan-wizard/plan-wizard' });
    } else if (action === 'analyze') {
      this.send('帮我分析一下我最近的训练数据');
    } else if (action === 'ask') {
      this.send('我刚开始健身，你能给我一些建议吗？');
    }
  },

  toggleSteps: function (e) {
    var idx = parseInt(e.currentTarget.dataset.msgIdx);
    if (isNaN(idx)) return;
    var msg = this.data.messages[idx] || {};
    this.setData(['messages[' + idx + '].stepsCollapsed'], !msg.stepsCollapsed);
  },

  retry: function () {
    var msgs = this.data.messages;
    if (msgs.length < 2) return;
    msgs.pop(); var lastUser = msgs.pop();
    this.setData({ messages: msgs, lastFailed: false });
    if (lastUser && lastUser.role === 'user') this.send(lastUser.content);
  },

  scrollToBottom: function () {
    var that = this;
    var msgs = this.data.messages;
    if (msgs.length === 0) return;
    var lastId = msgs[msgs.length - 1].id;
    this.setData({ scrollToId: '' }, function () { that.setData({ scrollToId: 'msg-' + lastId }); });
  },

  startVoice: function () {
    var that = this;
    wx.authorize({ scope: 'scope.record', success: function () { that.setData({ recording: true }); that._recorder.start({ format: 'mp3', duration: 60000 }); }, fail: function () { wx.showToast({ title: '请授权录音权限', icon: 'none' }); } });
  },

  stopVoice: function () { if (this.data.recording) this._recorder.stop(); }
});
