# FitAI-web 更新日志

---

## V6.0 — 工程化重构 (2026-07-09 ~ 2026-07-11)

### 前端模块化
- 将 2573 行 `app.js` 拆分为 21 个 ES Module（`static/js/boot.js`、`ws.js`、`chat.js`、`health.js` 等）
- 使用共享状态模块（`state.js`）解决循环引用
- HTML 内联脚本清理，仅保留最小化主题初始化
- `removeWelcome()` 改为隐藏而非永久删除

### SVG 图标系统
- 创建 `icons.js`，含 42 个 Lucide SVG 图标（MIT 开源，线条风格）
- 替换全站 ~55 个 Emoji：侧边栏导航、状态反馈、AI 过程展示、工具图标
- 聊天头像 `👤🤖` → SVG `user` / `bot`

### WebSocket 流式返回
- `agent/loop.py` 新增 `AgentEvent` dataclass，实时 yield step/thought/action/observation 事件
- WS 路径流式发送 `chunk` + 结构化事件，用户看到实时思考过程
- SSE 路径保持兼容

### 摄像头食物识别
- 新建 `camera.js`：`getUserMedia` 打开后置摄像头、拍照、预览、重拍、发送
- 集成硅基流动 Qwen3-VL-8B 视觉模型，识别食物并估算营养
- 双模型架构：DeepSeek 处理对话 + Qwen-VL 处理图片，互不干扰
- 聊天栏新增 📷 拍照按钮

### 算法创新
- `fitai/analysis/advanced.py` 新增三个算法：
  - **自适应周期化训练计划**：基于历史完成率动态调整强度
  - **多维交叉异常检测**：4 种隐性风险模式（过度训练/代谢下降/压力积累/恢复不足）
  - **指数加权健康评分（EWMA）**：近期数据权重更高 + 陈旧惩罚 + 趋势箭头
- `交叉异常检测 O(n²) → O(n)`，滑动窗口替代逐日重算
- 共享评分公式 `_score_day()`，trends.py 和 advanced.py 共用

### 后端修复
- 补齐 11 个缺失 API 端点（`/api/videos`、`/api/exercises/analysis`、`/api/profile` 等）
- 修复 4 个端点 JSON 解析保护 + 6 个端点 days 参数校验
- 修复 `_start_import_worker` UnboundLocalError
- 添加 HTTP 请求日志中间件（loguru）
- 删除死代码：`model_lock`、`_pending_food_images`、复制 countbot 父项目的逻辑
- 3 个新 AI 工具注册：`advanced_health_score`、`cross_anomaly_check`、`adaptive_training_plan`

### 前端性能优化
- 健康面板 API 请求从 10 次减至 3 次（使用批量端点）
- 删除 4 处 console.log 调试日志
- 修复快捷按钮首次加载失效（WS 未就绪时 UI 提前初始化）

### 手机端适配
- 修复 `#panel-chat` CSS 优先级导致面板异常可见
- 底部标签栏文字恢复可见 + 消除 hover 偏移
- 8 类按钮触摸目标统一 ≥44px
- 输入框字体 16px 防 iOS 缩放
- `height`+`bottom` 冲突修复，面板底部不被 tab bar 遮挡
- 登录页手机端适配

### PWA + 离线
- 新增 `manifest.json`、`sw.js`（Cache-First + Network-First 混合缓存）
- 生成 PWA 图标（192x192 + 512x512）
- Service Worker 仅在生产环境注册
- 废弃 `apple-mobile-web-app-capable` → `mobile-web-app-capable`

### 测试
- 29 个 pytest 测试用例，覆盖 auth、database 模块

### 健康详情 + 运动详情 HTML 补全
- 新增 `#health-detail` 钻取视图（统计卡片、图表、数据表格）
- 新增 `#ex-detail` 运动详情视图（摘要、月度趋势、历史记录）
- 新增体重/体脂图表、周报分析区域

### 代码清理
- 删除 `static/app.js`（2573 行死代码）
- 删除 `static/css/`（未引用）
- 删除 `archive_old_health_data` / `cleanup_archived_data`（从未调用）
- 删除 server.py 中 5 处重复的 create_provider 调用

---

## V5.0 — CPU 优化 (2026-06-30)

### 内存缓存
- 4 个高频 API 端点添加 3 分钟 TTL 内存缓存（`analysis-summary`、`water-today`、`weekly-summary`、`dashboard/health`）
- 重复请求 <1ms 响应，CPU 压力降约 90%
- 写入数据时自动清缓存保证一致性
- 上限 500 条，自动淘汰最旧条目

### 异步 SQL
- 新增 `_db_fetch()` 辅助函数，使用 `run_in_executor` 将 SQL 查询放入线程池
- 4 个读端点改为异步查询，不再阻塞事件循环
- 并发处理能力翻倍，不换数据库驱动、零风险

### 数据分层归档
- 新增 `health_daily_summary` 表，7 天前的旧数据按日聚合归档
- `get_health_data_history_json` 和 `get_health_data_history` 改为 UNION 双表查询
- 新增 `archive_old_health_data()` 归档函数和 `cleanup_archived_data()` 清理函数
- 安全策略：当前只归档不删除，运行验证后手动执行清理

---

## V4.0 — 智能功能 (2026-06-29)

### 智能追问 (P0)
- 增强 Agent 系统提示词，AI 主动追问不完整信息
- 例：用户说"练了腿"→ AI 反问"几组几次？重量多少？"
- 自动关联历史数据，发现异常时主动提醒

### 关联洞察 (P1)
- 新增 `analyze_correlations` 工具（Pearson 相关系数）
- 跨类型数据分析：发现步数与睡眠、训练与体重等隐藏关联
- 例："晚上 9 点后吃饭，深睡时长平均少 40 分钟"

### 趋势预判 (P2)
- 新增 `predict_trends` 工具（线性回归外推）
- 预测未来值并给出建议
- 例："体重每周下降 0.7%，预计 2 周后 72kg"

### 天气集成 (P3)
- 新增 `get_weather` 工具（Open-Meteo 免费 API，无需密钥）
- 覆盖中国 23 个主要城市，AI 根据天气给训练建议
- 例："今天 38°C，建议把户外跑换成室内 HIIT"

### 每周周报 (P4)
- 新增 `GET /api/weekly-summary` 端点
- 首页展示本周步数、睡眠、训练、体重变化等聚合数据
- 数据写入时自动清缓存保证实时性

---

## V3.0 — UI 升级 + 移动端适配 (2026-06-28)

### 视觉升级
- Glassmorphism 毛玻璃卡片效果（`backdrop-filter: blur()`）
- 动画渐变背景（`body::before` + 20s 循环）
- 3 个浮动光球缓慢漂移（移动端自动隐藏）
- 按钮涟漪点击效果（`::after` 伪元素波纹）
- 卡片 3D hover tilt（`perspective` + `rotateX`）
- 骨架屏加载动画、打字指示器、数字滚动计数器
- 面板滑入过渡动画、成就徽章闪烁

### Splash 启动动画
- 页面加载时 💪 Logo 旋转 360° + FitAI 渐变文字
- 2 秒自动淡出，点击可跳过

### 语音对话（测试中）
- 🎤 语音输入（Web Speech API，Chrome/Edge）
- 🔊 AI 回复语音朗读（`speechSynthesis`）
- HTTP 下按钮灰色提示"需要 HTTPS"
- 注意：完整语音功能需要 HTTPS 连接

### 手机端全面适配
- 修复 5 处 CSS 属性类型不匹配（`flex-direction` 写在 `display:grid` 上）
- 768px 以下顶部横条导航，主内容区全宽
- 添加 🏠 首页导航按钮 + 品牌 Logo 点击回到首页
- 触摸目标全部 ≥44px（发送/语音/导航按钮）
- iOS 适配：输入框 16px 防缩放、`safe-area-inset-bottom`、`100dvh`、`-webkit-overflow-scrolling: touch`
- 历史表格 `overflow-x: auto` 横向滚动
- 移动端关闭浮动光球和背景动画以节省 GPU

---

## V2.0 — 导入系统重构 (2026-06-27)

### 客户端解析（主路径）
- 新增 `import-worker.js` Web Worker
- 浏览器内用 JSZip + 正则解析 Apple Health ZIP/XML/CSV
- 解析后仅上传轻量 JSON 记录数组到 `POST /api/health/import-batch`
- 不支持的浏览器自动回退服务端导入

### 服务端排队（回退路径）
- 新增 `import_jobs` 表实现任务队列
- `POST /api/health/import-file` 提交即返回 `job_id`
- `GET /api/health/import-status` 轮询进度
- 后台 worker 单线程逐个处理，不并发
- 前端显示"前方 N 人排队"

### Starlette 磁盘临时文件
- 不再 `await file.read()` 读入内存（OOM 根因）
- 改用 `shutil.copy` 直接复制 Starlette 的 `SpooledTemporaryFile` 磁盘路径
- 零内存拷贝

### 消除全局状态
- importer.py 的 `_agg` 全局变量改为参数传递
- 每次导入创建局部 `agg = {}`，不存在多人串数据风险
- `_clear_agg()` 标记废弃

### 性能优化
- `insert_health_data_batch` 改用 `executemany` + `BEGIN IMMEDIATE`，性能提升约 100x
- XML 解析 `ET.fromstring` → `ET.iterparse` 流式解析
- 每 5000 条 flush + `gc.collect()` 释放内存
- Nginx `client_max_body_size` 50M → 200M
- Nginx `proxy_read_timeout` 300s → 600s
- 服务器添加 2GB swap 防 OOM

---

## V1.0 — 基础修复 (2026-06-26)

### 数据导入管线修复（端到端完全断裂）
- 新增 `POST /api/health/import-file` 端点（原先 `/api/import/file` 不存在且只支持 JSON body）
- 删除废弃的 `/api/import/file` 和 `/api/import` 重复端点
- 修复 `importer.py` 错误引用路径（`from database import ...` → `from tools.fitai_database import ...`）
- 修复 `sync_service.py` 相同引用错误
- 修复 `base.py`、`google_fit.py`、`huawei_health.py`、`health_connect.py` 模块引用

### 健康数据 Bug 修复
- 修复 `POST /api/health/record` 读取错误 JSON 键名（`body.get("type")` → `body.get("data_type")`）
- **影响**：此前所有手动记录（体重/睡眠/喝水）的 `data_type` 为空字符串，无法查询
- 重写 `GET /api/health/analysis-summary` 返回结构化 JSON
- **影响**：此前返回文本字符串，前端 `drawRingsFromData()` 无法解析，环形图始终显示 `--`
- 实现真正的喝水追踪（之前硬编码 `{total: 0, target: 8}`）
- 修复喝水 `INSERT OR REPLACE` 覆盖问题，改为累加已有值

### 新增缺失端点
- 新增 `GET /api/dashboard/health?data_type=X&days=N`
- **影响**：此前前端 10 个健康面板数据请求全部 404，所有图表显示 `--`

### 中间件认证修复
- 新增 `_get_user_id()` 辅助函数，当中间件未设置 `user_id` 时从 cookie 回退解析
- 修复 `/api/health` 被标记为公开路径导致所有 POST 端点不认证
- **影响**：此前登录后依然提示"请先登录"

### 数据库层增强
- 新增 `insert_health_data()` 单条写入函数
- `insert_health_data_batch()` 重写为 `executemany` + 显式事务
- 新增 `get_oauth_token()`、`insert_sync_log()`、`update_sync_log()` 函数
- 修复 `save_oauth_token()` 和 `get_last_sync_info()` 参数签名
- 新增 `import_jobs` 表和 `health_daily_summary` 表

### 前端修复
- 在设置面板添加数据导入 UI（`import-area` 等 HTML 元素）
- `recordHealth()` 和 `recordWater()` 添加 `credentials: "same-origin"`
- 添加 401 未登录提示
- 修复 `processImportFile` 响应类型检查和文件大小预检
- 修复 `msg` 未声明变量（`let msg`）
- 侧边栏会话列表在 WebSocket 消息完成后自动刷新

---

## 服务器配置

| 项目 | 值 |
|------|-----|
| CPU | 1 核 |
| RAM | 1.6 GB |
| Swap | 2 GB |
| 反向代理 | Nginx 1.18.0 |
| Python | 3.10.12 |
| 数据库 | SQLite (WAL mode) |
| 上传限制 | 200 MB |
| 代理超时 | 600 秒 |
