"""Thin client for DeepSeek's raw Search and Fetch JSON APIs."""

import ipaddress
import time
from urllib.parse import urlsplit

import requests

from .errors import ResearchError, ResearchValidationError

SEARCH_PATH = "/v1/tools/search"
FETCH_PATH = "/v1/tools/fetch"
MAX_QUERY_CHARS = 128
MAX_URL_CHARS = 8192
MAX_RETRY_AFTER_SECONDS = 10.0

_ERROR_HINTS = {
    401: "DeepSeek API Key 无效或已失效，请检查 config.ini。",
    402: "DeepSeek 账户余额不足，请充值后重试。",
    403: "DeepSeek 拒绝了本次抓取请求（安全策略）。",
    404: "目标网页没有可用正文，或站点拒绝了访问。",
    408: "DeepSeek 读取请求超时，请稍后重试。",
    413: "请求体超过 DeepSeek 的大小限制。",
    429: "请求过于频繁（QPS 超限），请稍后重试。",
    500: "DeepSeek 服务内部错误，请稍后重试。",
    504: "DeepSeek 下游请求超时，请稍后重试。",
}


class DeepSeekClient:
    """Search the web or fetch one page as Markdown."""

    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()

    def search(
        self,
        query,
        count=None,
        need_content=None,
        ori_question=None,
        localization=None,
    ):
        query = (query or "").strip()
        if not query:
            raise ResearchValidationError("搜索词不能为空。")
        if len(query) > MAX_QUERY_CHARS:
            raise ResearchValidationError(
                f"搜索词不能超过 {MAX_QUERY_CHARS} 个字符。"
            )

        count = self.config.default_count if count is None else count
        try:
            count = int(count)
        except (TypeError, ValueError) as exc:
            raise ResearchValidationError("结果数量必须是整数。") from exc
        if not 1 <= count <= 50:
            raise ResearchValidationError("结果数量必须在 1 到 50 之间。")

        if need_content is None:
            need_content = self.config.default_need_content

        payload = {
            "query": query,
            "count": count,
            "need_content": bool(need_content),
        }

        if ori_question is not None:
            original = str(ori_question).strip()
            if original:
                if len(original) > MAX_QUERY_CHARS:
                    raise ResearchValidationError(
                        f"原始问题不能超过 {MAX_QUERY_CHARS} 个字符。"
                    )
                payload["ori_question"] = original

        if localization is not None:
            location = str(localization).strip()
            if location:
                try:
                    ipaddress.ip_address(location)
                except ValueError as exc:
                    raise ResearchValidationError(
                        "本地化 IP 必须是有效的 IPv4 或 IPv6 地址。"
                    ) from exc
                payload["localization"] = location

        data = self._post(SEARCH_PATH, payload)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ResearchError("DeepSeek 返回的搜索结果格式不正确。", 502)
        return data["results"]

    def fetch(self, url):
        url = self._validate_url(url)
        data = self._post(FETCH_PATH, {"url": url})
        if not isinstance(data, dict):
            raise ResearchError("DeepSeek 返回的抓取结果格式不正确。", 502)
        title = data.get("title")
        content = data.get("content")
        return {
            "title": title if isinstance(title, str) else "",
            "content": content if isinstance(content, str) else "",
        }

    def _validate_url(self, url):
        url = (url or "").strip()
        if not url:
            raise ResearchValidationError("网页地址不能为空。")
        if len(url) > MAX_URL_CHARS:
            raise ResearchValidationError(
                f"网页地址不能超过 {MAX_URL_CHARS} 个字符。"
            )
        if any(character.isspace() for character in url):
            raise ResearchValidationError("网页地址不能包含空白字符。")
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise ResearchValidationError("网页地址格式不正确。") from exc
        if parts.scheme not in ("http", "https"):
            raise ResearchValidationError("网页地址必须以 http:// 或 https:// 开头。")
        if not parts.hostname:
            raise ResearchValidationError("网页地址必须包含主机名。")
        if parts.username or parts.password:
            raise ResearchValidationError("网页地址不能携带用户名或密码。")
        return url

    def _post(self, path, payload):
        url = f"{self.config.base_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        timeout = (self.config.connect_timeout, self.config.read_timeout)
        attempts = self.config.max_retries + 1

        for attempt in range(attempts):
            try:
                response = self.session.post(
                    url, json=payload, headers=headers, timeout=timeout
                )
            except requests.Timeout as exc:
                if attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                raise ResearchError(
                    "DeepSeek 请求超时，请稍后重试。", 504
                ) from exc
            except requests.RequestException as exc:
                raise ResearchError(
                    "无法连接 DeepSeek API，请检查网络或 base_url 配置。", 502
                ) from exc

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ResearchError(
                        "DeepSeek 返回了无法解析的响应。", 502
                    ) from exc

            message = self._error_message(response)
            retryable = response.status_code in (408, 429) or (
                500 <= response.status_code < 600
            )
            if retryable and attempt + 1 < attempts:
                self._backoff(attempt, response)
                continue

            status = (
                response.status_code
                if 400 <= response.status_code < 500
                else 502
            )
            raise ResearchError(message, status)

        raise ResearchError("DeepSeek 请求失败，请稍后重试。", 502)

    def _backoff(self, attempt, response=None):
        delay = self.config.retry_backoff * (2 ** attempt)
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
        delay = min(max(delay, 0.0), MAX_RETRY_AFTER_SECONDS)
        if delay:
            time.sleep(delay)

    @staticmethod
    def _error_message(response):
        status = response.status_code
        if status == 400:
            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, dict):
                error = data.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str) and message.strip():
                        return message.strip()
            return "请求参数不合法，请检查输入。"
        hint = _ERROR_HINTS.get(status)
        if hint:
            return hint
        return f"DeepSeek API 请求失败（HTTP {status}）。"
