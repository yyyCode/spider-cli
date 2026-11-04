# FastAPI Web 下载服务设计

- 日期：2026-11-04
- 状态：已确认
- 适用范围：`E:\python\spider-cli`

## 1. 背景与目标

当前项目提供命令行界面（`cli/`）和可复用的平台抓取逻辑（`core/`），只支持终端交互。本次新增一个 Web 前端：用户在浏览器里粘贴抖音或小红书的链接/分享口令，服务端解析并下载视频，最终把文件内容作为响应返回给浏览器。

本次只支持**视频**，小红书图集明确拒绝并提示暂不支持。

## 2. 范围

### 本次包含

- `web/` 包：FastAPI 应用、下载编排、静态前端资源。
- `POST /api/download`：输入链接或分享口令，同步返回视频文件流。
- `GET /`：暗色玻璃拟态的单页 UI。
- `GET /health`：探活接口。
- core 的最小改造：两个爬虫的 `run()` 成功时返回下载路径。
- 并发限制、临时目录与自动清理。
- 单元测试、`run-web.cmd`、README 更新。

### 本次不包含

- 小红书图集下载（返回 400 明确提示）。
- 异步任务队列、任务状态轮询、断点续传。
- 用户系统、限流、鉴权、持久化历史记录。
- 跨域开放（仅同源前端使用）。
- 大文件免内存下载（当前前端用 Blob，后续可改直链）。

## 3. 总体架构

```text
web/
├── __init__.py
├── __main__.py        # python -m web，解析 --host/--port/--reload 后启动 uvicorn
├── app.py             # FastAPI 应用、路由、静态资源挂载
├── service.py         # 下载编排：提取链接 → 识别平台 → 临时目录 → 调用 core
└── static/
    ├── index.html
    ├── styles.css
    └── app.js
```

依赖方向：`web → core`，`cli → core`，两侧互不依赖。web 层不复制任何平台解析逻辑。

## 4. core 改造

保持现有行为与 CLI 兼容，只补充返回值：

- `DouyinSpider.download_video()` 成功时返回文件路径，失败返回 `None`。
- `DouyinSpider.run()` 成功时返回下载文件路径，失败返回 `None`。
- 新增 `XhsSpider.resolve()`：执行 `fetch_html()` + `parse()`，返回 `NoteMedia`。
- `XhsSpider._download_video()` 成功时返回文件路径；`download_note()` 返回视频文件路径或图集目录路径。
- `XhsSpider.run()` 成功时返回上述路径，失败返回 `None`。

现有测试没有断言 `run()` 的返回值，CLI 也忽略返回值，因此改造向后兼容。

## 5. API 契约

### `POST /api/download`

请求：

```json
{ "url": "https://v.douyin.com/xxxx/ 复制此链接..." }
```

`url` 字段可以是纯链接，也可以是整段分享口令；服务端使用 `core.utils.extract_url_from_text` 提取第一个链接。

成功：`200`，响应体为视频二进制流，响应头：

```text
Content-Type: video/mp4
Content-Disposition: attachment; filename*=UTF-8''<URL 编码的中文标题>.mp4
```

失败：始终返回 JSON `{"detail": "..."}`。

| 状态码 | 场景 |
| --- | --- |
| 400 | 未识别到链接、平台不支持、小红书图集 |
| 502 | 平台页面解析失败、未捕获到视频流、上游下载失败 |
| 500 | 未预期异常 |

平台判定复用 `detect_platform`，只接受抖音和小红书域名，天然限制 SSRF 目标。

### `GET /health`

返回 `{"status": "ok"}`。

### `GET /`

返回 `web/static/index.html`，同时挂载：

- `/static` → `web/static`
- `/assets` → 项目根目录 `assets/`（复用 logo）

## 6. 下载流程与并发

1. 端点内用 `asyncio.Semaphore(2)` 限制同时进行的解析数（抖音无头浏览器较重）。
2. 同步爬虫通过 `starlette.concurrency.run_in_threadpool` 执行，避免阻塞事件循环。
3. 每次请求创建独立临时目录 `tempfile.mkdtemp(prefix="spider-web-")` 作为 `save_dir`。
4. 成功后用 `FileResponse` 返回，并通过 `BackgroundTask` 在响应结束后 `shutil.rmtree` 清理临时目录。
5. 任何失败路径立即清理临时目录。
6. 小红书登录墙继续通过环境变量 `XHS_COOKIE` 注入 Cookie。
7. 解析失败时，把爬虫日志尾部拼接进 `detail`，便于定位问题。

### 小红书图集判定

服务端先调用 `XhsSpider.resolve()` 拿到 `NoteMedia`：

- `kind == "video"`：继续下载并返回文件。
- `kind == "images"`：直接返回 400，不下载图片。

## 7. 前端 UI

暗色玻璃拟态风格：

- 全屏深蓝到紫色渐变背景，叠加缓慢漂浮的模糊光斑。
- 居中的半透明毛玻璃卡片，顶部展示 logo、标题、副标题。
- 多行输入框（可粘贴整段分享口令），输入时实时识别并显示平台徽章（抖音/小红书），无法识别时显示灰色提示。
- 渐变发光的主按钮"解析并下载"，输入为空时禁用；`Ctrl+Enter` 也可提交。
- 状态机：
  - 空闲：输入框 + 按钮。
  - 解析中：按钮进入 loading，显示旋转动画和轮换文案（解析链接 → 启动浏览器 → 下载视频）。
  - 成功：显示下载完成的文件名与体积。
  - 失败：红色玻璃提示框展示服务端返回的 `detail`。
- 下载实现：`fetch` 读取响应流，按 `Content-Length` 计算进度条；完成后生成 Blob 并触发浏览器保存，文件名从 `Content-Disposition` 解析。
- 响应式：窄屏下卡片占满宽度，按钮全宽。

## 8. 错误处理

- 前端始终先检查 `response.ok`；非 2xx 时尝试解析 JSON `detail`，解析失败则显示状态码。
- 后端 `WebDownloadError` 携带状态码与消息，端点统一转换为 `JSONResponse`。
- 未捕获异常记录日志后返回 500，不向客户端暴露堆栈。
- 临时目录清理使用 `ignore_errors=True`，避免清理失败影响响应。

## 9. 测试

新增 `tests/test_web.py`，使用 FastAPI `TestClient`，通过依赖注入/猴子补丁替换 spider 工厂，不触发真实网络：

- 正常下载：响应体为假视频字节，`Content-Disposition` 含文件名，临时目录已清理。
- 输入分享口令：正确提取链接。
- 无效输入 / 不支持平台：400。
- 小红书图集：400，且不调用下载。
- 爬虫返回 `None`：502。
- `/health` 返回 ok。
- `GET /` 返回 HTML 页面。

现有 `tests/test_douyin.py`、`tests/test_xhs.py` 保持通过。

## 10. 依赖与运行

`requirements.txt` 新增：

```text
fastapi
uvicorn[standard]
```

启动方式：

```bash
python -m web                 # 127.0.0.1:8000
python -m web --port 9000     # 自定义端口
```

新增 `run-web.cmd`（Windows 一键启动），README 增加"Web 服务"章节，说明启动方式、接口示例和视频范围限制。
