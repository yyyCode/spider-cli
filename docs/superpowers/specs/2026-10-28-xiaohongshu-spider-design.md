# 小红书笔记爬虫设计

- 日期：2026-10-28
- 状态：已确认，已按实测结果修订
- 适用范围：`E:\python\spider-cli`

## 1. 背景与目标

当前工具只支持抖音视频链接。本次新增小红书笔记链接支持：用户粘贴一条小红书笔记链接或分享口令，程序自动判断内容类型，下载视频或全部图片。

实测结论：

- 桌面 UA 访问笔记页会被重定向到登录页。
- 安卓移动端 UA 可以匿名访问公开笔记。
- 移动端返回的是服务端渲染 HTML，`window.__SETUP_SERVER_STATE__.LAUNCHER_SSR_STORE_PAGE_DATA.noteData` 中包含标题、描述、`imageList` 和视频 `masterUrl`。
- 图片原图可通过 `https://ci.xiaohongshu.com/{fileId}?imageView2/2/format/jpg` 获取。
- 视频 `masterUrl` 可直接用 requests 下载，无需浏览器。

因此小红书部分使用 requests + 移动端 UA，不启动 Playwright。抖音部分保持原实现。

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
  ├─ douyin_spider.py   抖音，保持现有 Playwright 实现
  └─ xhs_spider.py      小红书，新增，requests 实现
utils.py             共享工具：链接提取、标题清理、平台识别
```

`xhs_spider.py` 不依赖抖音模块，也不依赖 Playwright。共享函数从现有 `douyin_spider.py` 抽到 `utils.py`，`douyin_spider.py` 继续导入并对外保留原名，避免破坏现有调用和测试。

## 4. 数据流

1. CLI 从菜单输入中提取第一个 http/https 链接。
2. `detect_platform(url)` 判断平台，返回 `douyin`、`xhs` 或 `None`。
3. 构造对应爬虫并调用 `run()`。
4. 小红书爬虫：
   1. 使用 requests 以安卓移动端 UA 访问原始链接，保留 `xsec_token` 等查询参数，自动跟随 `xhslink.com` 短链跳转。
   2. 如果设置了 `XHS_COOKIE`，写入请求头 `Cookie`。
   3. 最终 URL 落到 `/login`、`/website-login` 或 `/captcha` 时，抛出登录限制错误。
   4. 从 HTML 中解析 `__SETUP_SERVER_STATE__`，取 `LAUNCHER_SSR_STORE_PAGE_DATA.noteData`。
   5. 取不到时回退解析 `__INITIAL_STATE__.note.noteDetailMap`。
   6. `parse_note` 产出统一的 `NoteMedia` 数据。
   7. 按类型下载到 `<下载目录>/<标题>/`。

## 5. 解析规则

### 定位笔记

- 优先读取 `LAUNCHER_SSR_STORE_PAGE_DATA.noteData`。
- 回退到 `note.noteDetailMap` 时，优先使用 URL 中的笔记 ID；取不到时遍历第一个包含 `imageList` 或 `video` 的有效笔记。
- 两种来源都取不到时，按登录限制处理并提示设置 `XHS_COOKIE`。

### 标题

依次尝试 `note.title`、`note.desc` 第一行、笔记 ID、时间戳。结果经过 `sanitize_filename` 清理，长度上限 50 字符。

### 类型与媒体

- `note.type == "video"` 或存在视频流时按视频处理。
- 视频候选按 h264、h265、av1、h266 的顺序收集，同一编码内按 `size` 从大到小排序，并追加 `backupUrls`。
- 其余情况按图集处理，遍历 `note.imageList`，每张图按以下顺序生成候选 URL：
  1. `https://ci.xiaohongshu.com/{fileId}?imageView2/2/format/jpg`
  2. `imageList[n].url`
  3. `infoList[n].url`
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
| 重定向到登录或验证码 | 提示设置 `XHS_COOKIE` 后重试 |
| 未解析到 noteData | 提示页面结构可能变化或需要登录 |
| 视频地址为空 | 提示该笔记可能是动图或受限内容 |
| 单张图片下载失败 | 记录失败项，继续下载其余图片 |
| 至少一个文件成功 | `run()` 返回 `True` |
| 全部下载失败 | 输出失败数量，`run()` 返回 `False` |

## 8. 配置

| 名称 | 默认值 | 说明 |
| --- | --- | --- |
| `save_dir` | `videos` | 下载根目录，由 CLI 传入 |
| `XHS_COOKIE` | 空 | 可选，完整 Cookie 字符串，登录墙笔记需要 |

小红书部分没有 `headless` 参数，因为它不使用浏览器。

## 9. 测试

全部离线，不启动浏览器、不访问网络：

- `detect_platform`：抖音、抖音短链、小红书 explore、小红书 discovery、xhslink、无关链接。
- `extract_url_from_text`：带 `xsec_token` 查询参数的链接必须完整保留。
- `parse_setup_state`：从最小 HTML 中解析 noteData。
- `parse_note`：视频笔记、图集笔记、图片候选顺序、标题回退、空数据。
- `sanitize_filename`：非法字符、空标题、超长标题。

真实链接的手动验证使用用户提供的视频笔记链接，并额外验证一张封面图片的下载。

## 10. 涉及文件

- 新增 `xhs_spider.py`
- 新增 `utils.py`
- 新增 `test_xhs_spider.py`
- 修改 `cli.py`：平台识别与分发
- 修改 `douyin_spider.py`：改为从 `utils` 导入共享函数
- 修改 `test_spider.py`：补充共享函数测试
- 修改 `README.md`：小红书用法、Cookie、输出结构

## 11. 风险

- 小红书移动端 SSR 字段可能调整。解析函数独立且有用例覆盖，便于快速修复。
- `masterUrl` 带签名和时效，必须在抓到后立即下载。
- 匿名访问可能被限制。通过 `XHS_COOKIE` 提供兜底，不自动破解。
- 图集笔记没有实测样本，当前按已确认的 `imageList` 结构实现，验证时至少覆盖封面图片下载。
