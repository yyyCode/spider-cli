# 抖音视频爬虫完善设计

- 日期：2026-10-26
- 状态：已确认（方案 A：轻量分层）
- 适用范围：`E:\python\spider-cli`

## 1. 背景与目标

当前项目只能处理单条分享链接：Playwright 打开页面、监听响应嗅探 mp4、requests 直接下载。缺少登录态复用、请求限频、失败重试、断点续爬和风控识别，批量使用时容易遇到登录失效、403、文件下载不完整等问题。

本次目标：

1. 持久化并复用抖音登录态，首次扫码后长期免登录。
2. 支持一次导入多条链接，串行爬取并保存断点状态。
3. 对页面访问和文件下载分别限频，降低触发风控的概率。
4. 下载失败可重试、可续传；链接过期时能重新嗅探。
5. 显式识别登录失效、验证码等风控场景，给出可操作提示，不尝试自动破解。

## 2. 范围

### 本次包含

- 持久化浏览器 profile 与登录检测。
- 页面访问 / 媒体下载两级限频。
- 下载重试、断点续传、完整性校验。
- 批量多链接、去重、断点续爬、失败项重试。
- 反爬加固：启动参数、stealth 脚本、环境一致性、轻量行为模拟。
- 单元测试与 README 更新。

### 本次不包含

- 验证码自动识别或绕过。
- 代理 / 代理池。
- 多标签页并发解析。
- 用户主页、合集、搜索页的自动翻页枚举。
- 桌面 GUI。
- 视频元数据入库（数据库、CSV 等）。

## 3. 总体架构

保留 `DouyinSpider` 作为单条链接的编排入口，新增职责单一的模块：

```
cli.py                 CLI 菜单、批量输入、进度展示
  └─ batch.py          批量队列、去重、断点状态
       └─ douyin_spider.py   单条链接状态机、风控识别、直链嗅探
            ├─ session.py          持久化浏览器上下文、登录检测
            ├─ rate_limiter.py     页面 / 下载限频与全局冷却
            └─ downloader.py       HTTP 下载、重试、续传、校验
config.py              默认配置、config.json 读写、路径约定
stealth.min.js         浏览器指纹加固脚本
```

数据流向：

1. CLI 收集原始文本或文件路径，逐行调用 `extract_url_from_text`，得到 URL 列表。
2. `BatchRunner` 规范化 URL、按状态文件去重，生成待处理队列。
3. 对每个待处理项：
   - `page_limiter.wait()`；
   - 通过 `session` 打开持久化上下文和页面；
   - 导航、风控检测、嗅探直链、提取标题；
   - `download_limiter.wait()` 后由 `VideoDownloader` 下载；
   - 写回状态文件。
4. 全部结束后输出汇总，失败项保留在状态文件中供下次重试。

## 4. 模块设计

### 4.1 `config.py`

职责：定义默认配置、加载/合并 `config.json`、提供固定路径。

路径约定（避免 EXE 运行时依赖 cwd）：

- 配置根目录：`Path.home() / ".douyin-spider"`
- 配置：`~/.douyin-spider/config.json`
- 浏览器 profile：`~/.douyin-spider/profile`
- 状态：`~/.douyin-spider/state.json`
- 默认下载目录：首次生成配置时写入 `<当前工作目录>/videos` 的绝对路径。

默认配置：

```json
{
  "save_dir": "<cwd>/videos",
  "headless": false,
  "page_delay": [4.0, 9.0],
  "download_delay": [1.0, 2.0],
  "cooldown_seconds": 90,
  "max_retries": 3,
  "backoff_base": 1.0,
  "backoff_max": 8.0,
  "page_timeout_ms": 60000,
  "video_wait_timeout_ms": 15000,
  "login_timeout_seconds": 180,
  "min_video_size": 1048576,
  "chunk_size": 65536,
  "human_behavior": true
}
```

规则：

- 内置默认值 ← `config.json` 覆盖，浅合并即可。
- `config.json` 缺失或字段非法时使用默认值并记录警告，不中断运行。
- CLI 修改下载路径后写回 `config.json`。
- 不使用第三方配置库，仅标准库 `json` + `pathlib`。

### 4.2 `session.py`

职责：创建持久化浏览器上下文、判断登录态、提供登录入口。

```python
class BrowserSession:
    def __init__(self, config): ...
    def start(self) -> BrowserContext: ...
    def close(self) -> None: ...
    def is_logged_in(self) -> bool: ...
    def ensure_login(self, prompt_callback=None) -> bool: ...
```

实现要点：

- 使用 `chromium.launch_persistent_context(user_data_dir=..., headless=config.headless, args=..., locale="zh-CN", timezone_id="Asia/Shanghai", viewport={"width": 1920, "height": 1080})`。
- 启动参数：`--disable-blink-features=AutomationControlled`，并通过 `ignore_default_args=["--enable-automation"]` 去掉自动化提示。
- 不覆盖 `user_agent`，使用 Playwright 内核的真实 UA，避免 UA 与内核版本不一致。
- 登录判断：读取 `https://www.douyin.com` 域下 cookies，存在 `sessionid` 或 `sessionid_ss` 即视为已登录。
- `ensure_login()`：
  - 已登录：直接返回 `True`；
  - 未登录且有头：打开首页，每 2 秒轮询 cookie，最多等待 `login_timeout_seconds`；期间提示用户扫码，成功后返回 `True`；
  - 未登录且无头：返回 `False`，由调用方提示用户先执行「登录」菜单。
- profile 被其他进程占用时，Chromium 启动会失败；捕获异常并提示「请关闭其他正在使用该浏览器的程序后重试」。
- 每次批量任务复用同一个 context，任务结束后 `context.close()`。
- 注入 `stealth.min.js`：打包环境从 `sys._MEIPASS` 读取，开发环境从项目根目录读取。

### 4.3 `rate_limiter.py`

职责：控制请求节奏，支持全局冷却，可注入时钟以便测试。

```python
@dataclass(frozen=True)
class IntervalPolicy:
    min_seconds: float
    max_seconds: float

class RateLimiter:
    def __init__(self, policy, *, clock=time.monotonic, sleep=time.sleep, rng=None): ...
    def wait(self) -> float: ...          # 返回实际等待秒数
    def block_for(self, seconds: float) -> None: ...  # 设置全局冷却截止时间
```

规则：

- 每次 `wait()` 计算 `上次请求时间 + rng.uniform(min, max)`，与冷却截止时间取较大值。
- 页面访问与媒体下载各用一个实例：页面默认 4~9 秒，下载默认 1~2 秒。
- 命中 429 或风控（验证码、登录失效）时，调用两个实例的 `block_for(config.cooldown_seconds)`；403 属于直链过期，按「重新嗅探」处理，不触发长时间冷却。
- 时钟、sleep、随机数生成器均可注入，单元测试不产生真实等待。

### 4.4 `downloader.py`

职责：下载媒体文件，处理重试、续传和完整性校验。

```python
class LinkExpiredError(Exception): ...

@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0
    jitter: float = 0.3

@dataclass
class DownloadResult:
    ok: bool
    path: str
    bytes_written: int
    resumed: bool
    error: str | None = None

class VideoDownloader:
    def __init__(self, headers, limiter, retry_policy, config): ...
    def download(self, url: str, filepath: str) -> DownloadResult: ...
```

实现要点：

- 临时文件为 `filepath + ".part"`，完成后 `os.replace` 原子重命名。
- 续传：
  - `.part` 已存在且大小大于 0 时，发送 `Range: bytes=<size>-`；
  - 返回 206：追加写入；
  - 返回 200：清空 `.part` 从头写入；
  - 返回 416：删除 `.part` 后从头重试一次。
- 重试：
  - 可重试：`requests.Timeout`、`ConnectionError`、HTTP 5xx、429；
  - 429 额外触发 `limiter.block_for(cooldown_seconds)`；
  - 403 / 410 抛出 `LinkExpiredError`，由爬虫重新嗅探，不在下载器内重试；
  - 其他 4xx、磁盘写入错误直接返回 `DownloadResult(ok=False, error=...)`，不重试。
- 退避：`min(backoff_max, backoff_base * 2**(attempt-1))`，再乘 `[1-jitter, 1+jitter]` 随机系数。
- 完整性校验：
  - 若能确定总大小（200 的 `Content-Length` 或 206 的 `Content-Range` 总长），下载完成后比对文件大小；
  - 不一致时删除 `.part`，从头重试一次；仍不一致则失败。
- 下载分块 64KB，连接超时 10 秒，读取超时 60 秒。
- 复用现有 headers（Referer 等）。

### 4.5 `douyin_spider.py`

职责：单条链接的完整抓取流程，以及批量任务可复用的单条接口。

```python
@dataclass
class FetchResult:
    ok: bool
    url: str
    video_id: str | None
    title: str | None
    filepath: str | None
    size: int
    error: str | None
    risk: str | None          # login / captcha / no_video / None

class DouyinSpider:
    def __init__(self, url, session, config, page_limiter, download_limiter, log_callback=None): ...
    def fetch(self) -> FetchResult: ...
    def run(self) -> None: ...   # 兼容旧入口，内部调用 fetch 并打印结果
```

单条流程：

1. 记录 `page.on("response")`，只收集 200 且 `content-type` 含 `video/mp4` 或 URL 含 `.mp4`、大小超过 `min_video_size` 的候选。
2. `page_limiter.wait()` 后导航到目标 URL；导航超时重试 1 次。
3. 风控检测：
   - URL 跳转到登录页；
   - 页面文本命中关键词：`验证码`、`安全验证`、`请完成验证`、`登录后查看`；
   - 匹配验证码容器选择器：`#captcha_container`、`.captcha_verify_container`、`.verify-bar`。
4. 有头模式命中风控：记录日志，提示用户在浏览器中手动完成验证或登录，最多等待 120 秒后重新检测；仍失败则返回 `risk`。
5. 无头模式命中风控：直接返回失败，`error` 提示「请切换到有头模式并先执行登录/手动验证」。
6. 等待 `video` 元素，超时后执行轻量行为模拟（随机鼠标移动、1~3 次小幅滚动、停留 2~5 秒），再等待一次。
7. 提取标题：`page.title()` → `.desc` → `douyin_<时间戳>`，清洗非法字符并截断到 50 字符。
8. 选最大候选直链；没有候选项时回退读取 `video[src]` / `source[src]` 中的 http 链接。
9. 解析作品 ID：从最终 URL 或直链中匹配 `/video/(\d+)`、`/note/(\d+)`，匹配不到时返回 `None`。
10. `download_limiter.wait()` 后下载。
11. 下载器抛出 `LinkExpiredError` 时，重新导航并嗅探新直链，最多 2 次；仍失败则返回失败。
12. 每条处理结束后关闭 `page`；浏览器 context 由会话统一复用，批量任务结束后关闭。

反爬加固：

- 扩充 `stealth.min.js`：`navigator.webdriver`、`plugins`、`languages`、`platform`、`hardwareConcurrency`、`deviceMemory`、WebGL vendor/renderer、`window.chrome`、`permissions.query`、iframe `contentWindow.chrome`。
- 环境一致性：locale、timezone、视口固定为中文桌面环境；不伪造与内核不符的 UA。
- 行为模拟随机化：鼠标轨迹使用随机目标点和 `steps`，滚动距离随机，停留时间随机；仅在需要触发加载时使用，避免固定节奏。
- 本次不引入 `playwright-stealth` 等新依赖，继续使用本地脚本。

### 4.6 `batch.py`

职责：批量队列、去重、断点状态读写、汇总。

```python
@dataclass
class BatchItem:
    url: str
    status: str          # pending / success / skipped / failed / skipped_duplicate
    video_id: str | None = None
    title: str | None = None
    file: str | None = None
    size: int = 0
    attempts: int = 0
    error: str | None = None
    updated_at: str = ""

class StateStore:
    def load(self) -> None: ...
    def save(self) -> None: ...                 # 临时文件 + os.replace 原子写入
    def get(self, url: str) -> BatchItem | None: ...
    def upsert(self, item: BatchItem) -> None: ...
    def success_video_ids(self) -> set[str]: ...
    def failed_urls(self) -> list[str]: ...

class BatchRunner:
    def run(self, urls: list[str], *, force=False, retry_failed=False) -> BatchSummary: ...
```

状态文件格式：

```json
{
  "version": 1,
  "items": {
    "https://v.douyin.com/abc123/": {
      "url": "https://v.douyin.com/abc123/",
      "status": "success",
      "video_id": "7123456789012345678",
      "title": "视频标题",
      "file": "E:/python/spider-cli/videos/视频标题.mp4",
      "size": 10485760,
      "attempts": 1,
      "error": null,
      "updated_at": "2026-10-26T15:30:00+08:00"
    }
  }
}
```

去重规则：

- 输入阶段：按原始 URL 去重；`status == "success"` 且未指定 `force` 时标记 `skipped`。
- 运行阶段：解析出 `video_id` 后，若其他条目已成功下载同一 `video_id`，当前条目标记 `skipped_duplicate`。
- `retry_failed=True` 时只处理状态为 `failed` 的条目。

批量行为：

- 串行处理，每条之间由 `page_limiter` 控制节奏。
- 单条异常不终止整批，记录到状态文件后继续。
- 状态文件写入失败只记录日志，不中断当前任务。
- 结束时输出：总数、成功、跳过（含重复）、失败，以及失败链接列表。

### 4.7 `cli.py`

菜单项：

1. 登录 / 检查登录状态
2. 开始批量爬取
3. 重试失败项
4. 配置下载路径
5. 退出

交互细节：

- 「开始批量爬取」支持两种输入：
  - 逐行粘贴分享文本，空行结束；
  - 输入 `@<文件路径>`，从文本文件逐行读取。
- 每行用 `extract_url_from_text` 提取 URL，非法行跳过并提示行号。
- 进度输出示例：`[3/12] 成功：视频标题`、`[4/12] 跳过（已完成）`、`[5/12] 失败：需要登录`。
- 保留现有 TUI（`prompt_toolkit`）与普通数字菜单双套回退逻辑。
- 登录菜单在有头模式下打开抖音首页，等待扫码；完成后打印当前登录状态。
- 修改下载路径后写回 `config.json`。
- 批量任务共用同一个 `BrowserSession`，结束后关闭。

### 4.8 `stealth.min.js`

在现有脚本基础上补充：

- `navigator.languages = ["zh-CN", "zh", "en"]`
- `navigator.platform = "Win32"`
- `navigator.hardwareConcurrency = 8`
- `navigator.deviceMemory = 8`
- iframe `contentWindow.chrome` 补齐
- 保持 `webdriver`、`plugins`、WebGL、permissions 的现有处理

注意：只做常规指纹补齐，不伪造与运行环境明显冲突的值。

## 5. 错误处理与恢复

| 场景 | 处理 |
|---|---|
| 页面导航超时 | 退避后重试 1 次；仍失败则本条失败 |
| 登录失效 / 跳转登录页 | 有头模式提示手动登录并等待；无头模式本条失败并提示先登录 |
| 出现验证码 / 安全验证 | 有头模式等待人工处理；无头模式本条失败 |
| 等待视频超时 | 行为模拟后再等一次；仍无候选则本条失败 |
| 下载 403 / 410 | 重新导航嗅探新直链，最多 2 次 |
| 下载 429 | 全局冷却后按退避重试 |
| 下载 5xx / 超时 / 连接错误 | 退避重试，最多 `max_retries` 次 |
| 下载 4xx（非 403/410） | 不重试，本条失败 |
| 文件大小校验不一致 | 删除 `.part` 从头重试 1 次 |
| 状态文件损坏 | 备份为 `state.json.bak`，从空状态开始并记录警告 |
| 磁盘写入失败 | 本条失败，不重试 |

所有失败原因写入状态文件 `error` 字段，便于后续排查。

## 6. 测试策略

保持现有根目录测试风格，新增纯逻辑单测，不访问真实网络：

- `test_config.py`：默认配置、文件覆盖、非法字段回退、路径生成。
- `test_rate_limiter.py`：注入假时钟与假 sleep，验证最小间隔、抖动范围、冷却优先级。
- `test_downloader.py`：用 monkeypatch 模拟 `requests`，覆盖首次下载、206 续传、200 重下、403 抛 `LinkExpiredError`、5xx 重试、大小校验失败、`.part` 清理。
- `test_batch.py`：状态存取、原子写入、成功去重、`video_id` 去重、失败重试筛选、损坏状态文件恢复。
- `test_spider.py`：保留并更新现有测试；补充标题清洗、风控关键词判定、作品 ID 解析、候选直链选择。涉及 Playwright 的用例用 `@pytest.mark.integration` 标记，默认跳过。

验收命令：`pytest -q` 全部通过。

## 7. 实施阶段与验收标准

### P0 配置与登录态

- 新增 `config.py`、`session.py`，CLI 增加登录菜单。
- 验收：首次扫码后关闭程序，再次启动直接显示已登录，无需重新扫码。

### P1 限频、下载重试与风控识别

- 新增 `rate_limiter.py`、`downloader.py`，重构 `DouyinSpider` 单条流程。
- 验收：限频可配置且生效；模拟 403 时能重新嗅探；中断下载后重新运行可从 `.part` 续传。

### P2 批量与断点续爬

- 新增 `batch.py`，CLI 支持多行输入和 `@文件` 导入。
- 验收：3 条链接中 1 条失败，重跑时成功项跳过，失败项可通过菜单重试。

### P3 反爬加固

- 更新 `stealth.min.js` 与行为模拟。
- 验收：常规指纹检测项通过；请求时间间隔随机，无固定节奏。

### P4 测试与文档

- 补齐单测，更新 README。
- 验收：`pytest -q` 通过；README 覆盖登录、批量、配置、风控与合规说明。

## 8. 风险与合规

- 抖音页面结构和直链签名会变化，嗅探逻辑可能需要跟随调整。
- 持久化 profile 同一时间只能被一个进程使用，多开需提示用户。
- 无头模式更容易触发验证；首次登录和验证码处理必须使用有头模式。
- 程序不自动破解验证码、不绕过验证，只检测并提示人工处理。
- 默认低频串行，仅用于个人学习研究；README 保留合规声明，使用前应确认符合平台条款与当地法律。
- 当前 README 声明 Python 3.8+，但代码使用 `str | None`，本次统一要求 Python 3.10+。
