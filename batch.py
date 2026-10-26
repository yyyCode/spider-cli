from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from config import STATE_PATH
from douyin_spider import DouyinSpider

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "skipped_duplicate"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class BatchItem:
    url: str
    status: str = STATUS_PENDING
    video_id: str | None = None
    title: str | None = None
    file: str | None = None
    size: int = 0
    attempts: int = 0
    error: str | None = None
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "BatchItem":
        return cls(
            url=str(data.get("url", "")),
            status=str(data.get("status", STATUS_PENDING)),
            video_id=data.get("video_id"),
            title=data.get("title"),
            file=data.get("file"),
            size=int(data.get("size", 0) or 0),
            attempts=int(data.get("attempts", 0) or 0),
            error=data.get("error"),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class BatchSummary:
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    failed_urls: list[str] = field(default_factory=list)


class StateStore:
    def __init__(
        self,
        path: Path = STATE_PATH,
        *,
        log: Callable[[str], None] = print,
    ):
        self.path = Path(path)
        self.log = log
        self.items: dict[str, BatchItem] = {}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("状态根节点必须是对象")
            raw_items = payload.get("items", {})
            if not isinstance(raw_items, dict):
                raise ValueError("items 必须是对象")
            self.items = {}
            for url, raw in raw_items.items():
                if not isinstance(raw, dict):
                    continue
                data = dict(raw)
                data.setdefault("url", url)
                self.items[url] = BatchItem.from_dict(data)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            backup = self.path.with_suffix(".json.bak")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.items = {}
            self.log(f"[State] 状态文件损坏，已备份到 {backup}: {exc}")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": {
                url: asdict(item)
                for url, item in self.items.items()
            },
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def get(self, url: str) -> BatchItem | None:
        return self.items.get(url)

    def upsert(self, item: BatchItem) -> None:
        self.items[item.url] = item

    def success_video_ids(self) -> set[str]:
        return {
            item.video_id
            for item in self.items.values()
            if item.status == STATUS_SUCCESS and item.video_id
        }

    def failed_urls(self) -> list[str]:
        return [
            item.url
            for item in self.items.values()
            if item.status == STATUS_FAILED
        ]


class BatchRunner:
    def __init__(
        self,
        session,
        config,
        store: StateStore,
        *,
        spider_factory: Callable[[str], object] | None = None,
        log: Callable[[str], None] = print,
    ):
        self.session = session
        self.config = config
        self.store = store
        self.log = log
        self._spider_factory = spider_factory or self._default_spider

    def _default_spider(self, url: str) -> DouyinSpider:
        return DouyinSpider(
            url,
            session=self.session,
            config=self.config,
            log_callback=self.log,
        )

    def run(
        self,
        urls: Iterable[str] | None = None,
        *,
        force: bool = False,
        retry_failed: bool = False,
    ) -> BatchSummary:
        if retry_failed and not urls:
            urls = self.store.failed_urls()
        unique = list(
            dict.fromkeys(
                url.strip()
                for url in (urls or [])
                if url and url.strip()
            )
        )
        summary = BatchSummary(total=len(unique))

        for index, url in enumerate(unique, start=1):
            existing = self.store.get(url)
            if not force and existing and existing.status == STATUS_SUCCESS:
                summary.skipped += 1
                self.log(
                    f"[{index}/{len(unique)}] 跳过（已完成）: "
                    f"{existing.title or url}"
                )
                continue

            item = existing or BatchItem(url=url)
            item.url = url
            item.attempts += 1
            item.updated_at = now_iso()
            self.log(f"[{index}/{len(unique)}] 开始: {url}")

            try:
                spider = self._spider_factory(url)
                result = spider.fetch(
                    skip_video_ids=self.store.success_video_ids()
                )
            except Exception as exc:
                item.status = STATUS_FAILED
                item.error = f"未预期错误: {exc}"
                summary.failed += 1
                summary.failed_urls.append(url)
                self.store.upsert(item)
                self._safe_save()
                self.log(f"[{index}/{len(unique)}] 失败: {item.error}")
                continue

            item.video_id = result.video_id or item.video_id
            item.title = result.title or item.title
            if result.skipped:
                item.status = STATUS_DUPLICATE
                item.error = None
                summary.skipped += 1
                self.log(
                    f"[{index}/{len(unique)}] 跳过（重复作品）: "
                    f"{item.title or url}"
                )
            elif result.ok:
                item.status = STATUS_SUCCESS
                item.file = result.filepath
                item.size = result.size
                item.error = None
                summary.success += 1
                self.log(f"[{index}/{len(unique)}] 成功: {item.title or url}")
            else:
                item.status = STATUS_FAILED
                item.error = result.error or "未知错误"
                summary.failed += 1
                summary.failed_urls.append(url)
                self.log(f"[{index}/{len(unique)}] 失败: {item.error}")

            self.store.upsert(item)
            self._safe_save()

        return summary

    def _safe_save(self) -> None:
        try:
            self.store.save()
        except OSError as exc:
            self.log(f"[State] 状态保存失败: {exc}")
