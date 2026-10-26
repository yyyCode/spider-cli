from batch import (
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_SUCCESS,
    BatchItem,
    BatchRunner,
    StateStore,
)
from config import AppConfig
from douyin_spider import FetchResult


class FakeSpider:
    def __init__(self, result):
        self.result = result
        self.seen_skip_ids = None

    def fetch(self, skip_video_ids=None):
        self.seen_skip_ids = skip_video_ids
        return self.result


def make_runner(tmp_path, results):
    config = AppConfig(save_dir=tmp_path)
    store = StateStore(tmp_path / "state.json", log=lambda message: None)
    spiders = []

    def factory(url):
        spider = FakeSpider(results[url])
        spiders.append(spider)
        return spider

    runner = BatchRunner(
        None,
        config,
        store,
        spider_factory=factory,
        log=lambda message: None,
    )
    return runner, store, spiders


def success(url, video_id="1", title="video"):
    return FetchResult(
        ok=True,
        url=url,
        video_id=video_id,
        title=title,
        filepath=f"/tmp/{title}.mp4",
        size=10,
    )


def test_state_store_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path, log=lambda message: None)
    store.upsert(
        BatchItem(
            url="https://a",
            status=STATUS_SUCCESS,
            video_id="1",
            title="t",
        )
    )
    store.save()

    loaded = StateStore(path, log=lambda message: None)
    loaded.load()

    item = loaded.get("https://a")
    assert item is not None
    assert item.status == STATUS_SUCCESS
    assert item.video_id == "1"
    assert not (tmp_path / "state.json.tmp").exists()


def test_success_video_ids_and_failed_urls(tmp_path):
    store = StateStore(tmp_path / "state.json", log=lambda message: None)
    store.upsert(BatchItem(url="https://a", status=STATUS_SUCCESS, video_id="1"))
    store.upsert(BatchItem(url="https://b", status=STATUS_FAILED, error="boom"))

    assert store.success_video_ids() == {"1"}
    assert store.failed_urls() == ["https://b"]


def test_corrupt_state_file_is_backed_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    store = StateStore(path, log=lambda message: None)

    store.load()

    assert store.items == {}
    assert (tmp_path / "state.json.bak").exists()


def test_runner_downloads_and_saves_success(tmp_path):
    url = "https://v.douyin.com/a/"
    runner, store, spiders = make_runner(tmp_path, {url: success(url)})

    summary = runner.run([url])

    assert summary.success == 1
    assert store.get(url).status == STATUS_SUCCESS
    assert store.get(url).file.endswith("video.mp4")
    assert (tmp_path / "state.json").exists()
    assert len(spiders) == 1


def test_runner_skips_existing_success(tmp_path):
    url = "https://v.douyin.com/a/"
    runner, store, spiders = make_runner(tmp_path, {})
    store.upsert(BatchItem(url=url, status=STATUS_SUCCESS, title="done"))

    summary = runner.run([url])

    assert summary.skipped == 1
    assert spiders == []


def test_runner_retry_failed_only(tmp_path):
    ok_url = "https://v.douyin.com/ok/"
    bad_url = "https://v.douyin.com/bad/"
    runner, store, spiders = make_runner(
        tmp_path,
        {bad_url: success(bad_url, video_id="2")},
    )
    store.upsert(BatchItem(url=ok_url, status=STATUS_SUCCESS, video_id="1"))
    store.upsert(BatchItem(url=bad_url, status=STATUS_FAILED, error="boom"))

    summary = runner.run(None, retry_failed=True)

    assert summary.total == 1
    assert summary.success == 1
    assert store.get(bad_url).status == STATUS_SUCCESS
    assert len(spiders) == 1


def test_runner_marks_duplicate_video_id_as_skipped(tmp_path):
    old_url = "https://v.douyin.com/old/"
    new_url = "https://v.douyin.com/new/"
    duplicate = FetchResult(
        ok=True,
        url=new_url,
        video_id="42",
        title="same video",
        skipped=True,
    )
    runner, store, spiders = make_runner(tmp_path, {new_url: duplicate})
    store.upsert(BatchItem(url=old_url, status=STATUS_SUCCESS, video_id="42"))

    summary = runner.run([new_url])

    assert summary.skipped == 1
    assert store.get(new_url).status == STATUS_DUPLICATE
    assert spiders[0].seen_skip_ids == {"42"}


def test_runner_continues_after_spider_exception(tmp_path):
    bad_url = "https://v.douyin.com/bad/"
    ok_url = "https://v.douyin.com/ok/"
    config = AppConfig(save_dir=tmp_path)
    store = StateStore(tmp_path / "state.json", log=lambda message: None)

    def factory(url):
        if url == bad_url:
            raise RuntimeError("boom")
        return FakeSpider(success(url))

    runner = BatchRunner(
        None,
        config,
        store,
        spider_factory=factory,
        log=lambda message: None,
    )

    summary = runner.run([bad_url, ok_url])

    assert summary.failed == 1
    assert summary.success == 1
    assert store.get(bad_url).status == STATUS_FAILED
    assert store.get(ok_url).status == STATUS_SUCCESS
