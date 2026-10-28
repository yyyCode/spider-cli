# 小红书笔记爬虫设计

- 日期：2026-10-28
- 状态：已确认
- 适用范围：`E:\python\spider-cli`

## 1. 背景与目标

当前工具只支持抖音视频链接。本次新增小红书笔记链接支持：用户粘贴一条小红书笔记链接或分享口令，程序自动判断内容类型，下载视频或全部图片。

小红书笔记页是服务端渲染，页面内的 `window.__INITIAL_STATE__` 包含笔记标题、类型、图集和视频直链，匿名访问即可读取，不需要签名接口。

目标：

1. 支持小红书笔记链接，自动识别视频笔记和图集笔记。
2. 复用现有 Playwright、stealth 和下载方式，不引入新依赖。
3. 下载目录按笔记归档，视频和图集规则统一。
4. 解析逻辑为纯函数，可离线测试。

## 2. 范围

### 本次包含

- `xhslink.com` 短链和 `xiaohongshu.com` 笔记链接。
- 视频笔记：下载单个 mp4。
- 图集笔记：下载全部静态图片。
- 可选登录 Cookie，通过环境变量 `XHS_COOKIE` 注入。
- 单条链接的失败提示和部分成功统计。
- 单元测试与 README 更新。

### 本次不包含

- 用户主页、合集、搜索页的批量枚举。
- 评论、点赞等元数据抓取。
- 动图（live photo）中的视频部分。
- 验证码识别或风控绕过。
- 持久化浏览器登录态。

## 3. 总体架构

```
cli.py               菜单、链接平台识别、分发到对应爬虫
  ├─ douyin_spider.py   抖音，保持现有实现
  └─ xhs_spider.py      小红书，新增
utils.py             共享工具：链接提取、标题清理、平台识别
```

`xhs_spider.py` 不依赖抖音模块。共享函数从现有 `douyin_spider.py` 抽到 `utils.py`，`douyin_spider.py` 继续导入并对外保留原名，避免破坏现有调用和测试。

## 4. 数据流

1. CLI 从菜单输入中提取第一个 http/https 链接。
2. `detect_platform(url)` 判断平台，返回 `douyin`、`xhs` 或 `None`。
3. 构造对应爬虫并调用 `run()`。
4. 小红书爬虫：
   1. Playwright 启动 Chromium，设置桌面 UA、1920x1080 视口，注入 `stealth.min.js`。
   2. 如有 Cookie，解析 `name=value; name2=value2` 并注入 context。
   3. 访问用户提供的原始链接，保留 `xsec_token` 等查询参数，由浏览器跟随短链跳转。
   4. 等待 `window.__INITIAL_STATE__` 可用，取回 JSON。
   5. `parse_note_state` 从 state 中定位当前笔记，产出统一的 `NoteMedia` 数据。
   6. 按类型下载到 `<下载目录>/<标题>/`。

## 5. 解析规则

### 定位笔记

- 优先使用 `state.note.firstNoteId` 作为 key 读取 `noteDetailMap`。
- 取不到时遍历 `noteDetailMap`，选择第一个包含 `imageList` 或 `video` 的有效笔记。

### 标题

依次尝试 `note.title`、`note.desc` 第一行、笔记 ID、时间戳。结果经过 `sanitize_filename` 清理，长度上限沿用 50 字符。

### 类型与媒体

- `note.type == "video"` 或存在 `video.media.stream` 时按视频处理。
- 视频地址依次尝试 `stream.h264[0].masterUrl`、`h265[0].masterUrl`、`av1[0].masterUrl`。
- 其余情况按图集处理，遍历 `note.imageList`。
- 每张图片按以下顺序生成候选 URL：
  1. `https://ci.xiaohongshu.com/{traceId}?imageView2/2/format/png`
  2. `urlDefault`
  3. `infoList` 中的 `url`
  4. `urlPre`
- 下载时依次尝试候选，成功一个即停止。

### 输出

```
<下载目录>/
└── <标题>/
    ├── <标题>.mp4          # 视频笔记
    ├── 01.jpg              # 图集笔记
    ├── 02.jpg
    └── ...
```

图片扩展名优先取响应的 `Content-Type`，无法判断时按 URL 后缀，最后回退 `.jpg`。已存在且大小非空的文件跳过。

## 6. CLI 集成

- 菜单项"开始爬取视频"改为"开始爬取链接"。
- 输入链接后自动识别平台，不再要求用户先选择平台。
- 小红书爬虫的 Cookie 从环境变量 `XHS_COOKIE` 读取。
- 不支持的域名给出明确提示，不静默失败。

## 7. 错误处理

| 场景 | 行为 |
| --- | --- |
| 域名不支持 | 提示"仅支持抖音和小红书链接" |
| 未取到 note 数据 | 提示可能触发登录墙，建议设置 `XHS_COOKIE` |
| 视频地址为空 | 提示该笔记可能是动图或受限内容 |
| 单张图片下载失败 | 记录失败项，继续下载其余图片 |
| 全部下载失败 | 输出失败数量，`run()` 返回 `False` |
| 至少一个文件成功 | `run()` 返回 `True` |

## 8. 配置

| 名称 | 默认值 | 说明 |
| --- | --- | --- |
| `save_dir` | `videos` | 下载根目录，由 CLI 传入 |
| `headless` | `True` | 调试时可设为 `False` 观察页面 |
| `XHS_COOKIE` | 空 | 可选，登录墙笔记需要 |

## 9. 测试

全部离线，不启动浏览器：

- `detect_platform`：抖音、抖音短链、小红书 explore、小红书 discovery、xhslink、无关链接。
- `parse_note_state`：视频笔记、图集笔记、图片候选回退、空 state、缺少标题。
- `sanitize_filename`：非法字符、空标题、超长标题。
- 输出目录和图片序号生成。

真实链接的手动验证需要一条带 `xsec_token` 的小红书笔记链接。

## 10. 涉及文件

- 新增 `xhs_spider.py`
- 新增 `utils.py`
- 新增 `test_xhs_spider.py`
- 修改 `cli.py`：平台识别与分发
- 修改 `douyin_spider.py`：改为从 `utils` 导入共享函数
- 修改 `test_spider.py`：补充或调整共享函数测试
- 修改 `README.md`：小红书用法、Cookie、输出结构

## 11. 风险

- 小红书页面结构可能调整，`__INITIAL_STATE__` 字段名变化会导致解析失败。解析函数独立且有用例覆盖，便于快速修复。
- 匿名访问可能被登录墙拦截。通过 `XHS_COOKIE` 提供兜底，不自动破解。
- 原始图地址规则可能变化，候选回退链保证至少能拿到 `urlDefault`。
