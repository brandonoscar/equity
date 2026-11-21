"""Lake <-> object storage sync, against an in-memory fake of the storage API. Offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from equity import lake_sync
from equity.lake_sync import Store, pull_state, push


class FakeBucket:
    """The three Supabase Storage calls the sync uses: list, upload, download."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.fail_next = 0

    def __call__(self, method: str, url: str, data: bytes | None, headers: dict[str, str]) -> bytes:
        self.calls.append((method, url, headers))
        if self.fail_next:
            self.fail_next -= 1
            raise OSError("connection reset")
        if "/object/list/" in url:
            req = json.loads(data or b"{}")
            prefix, off, lim = req["prefix"], req["offset"], req["limit"]
            names: dict[str, dict[str, object] | None] = {}
            for key, blob in self.objects.items():
                if key.startswith(prefix):
                    rest = key[len(prefix) :]
                    head, sep, _ = rest.partition("/")
                    names[head] = None if sep else {"size": len(blob)}
            rows = [{"name": n, "metadata": m} for n, m in sorted(names.items())]
            return json.dumps(rows[off : off + lim]).encode()
        key = url.split("/object/lake/", 1)[1]
        if method == "POST":
            assert data is not None
            self.objects[key] = data
            return b"{}"
        return self.objects[key]


def make_store(bucket: FakeBucket, key: str | None = None) -> Store:
    return Store(base_url="https://s.test/storage/v1", key=key, transport=bucket,
                 sleep=lambda s: None, log=lambda m: None)  # fmt: skip


def lake_with(tmp_path: Path) -> Path:
    lake = tmp_path / "lake"
    done = lake / "aa.parcels"
    (done / "parcel").mkdir(parents=True)
    (done / "_parts").mkdir()
    (done / "parcel" / "00000.parquet").write_bytes(b"P0")
    (done / "_parts" / "00000.json").write_text("{}")
    (done / "_plan.json").write_text("[{}]")
    (done / "_counts.json").write_text('{"parcel": 1}')
    going = lake / "bb.parcels"
    (going / "parcel").mkdir(parents=True)
    (going / "parcel" / "00000.parquet").write_bytes(b"Q0")
    (going / "_plan.json").write_text("[{}, {}]")
    return lake


def test_push_uploads_changed_files_and_skips_unchanged(tmp_path: Path) -> None:
    bucket = FakeBucket()
    lake = lake_with(tmp_path)
    (lake / "bb.parcels" / "parcel" / "x.tmp").write_text("partial")
    first = push(make_store(bucket, key="sk"), lake)
    assert first.uploaded == 8 and first.unchanged == 0
    assert "bb.parcels/parcel/x.tmp" not in bucket.objects
    sent = bucket.calls[0][2]
    assert sent["apikey"] == "sk"  # pragma: allowlist secret
    assert sent["Authorization"] == "Bearer sk"  # pragma: allowlist secret
    again = push(make_store(bucket), lake)
    assert (again.uploaded, again.unchanged) == (0, 8)
    assert "apikey" not in bucket.calls[-1][2]  # no key: left to a proxy
    (lake / "bb.parcels" / "parcel" / "00000.parquet").write_bytes(b"Q0-changed")
    assert push(make_store(bucket), lake).uploaded == 1


def test_push_reports_files_too_big(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lake_sync, "MAX_BYTES", 2)
    bucket = FakeBucket()
    lake = lake_with(tmp_path)
    (lake / "bb.parcels" / "parcel" / "00001.parquet").write_bytes(b"too big")
    r = push(make_store(bucket), lake)
    assert "bb.parcels/parcel/00001.parquet" in r.too_big
    assert "bb.parcels/parcel/00001.parquet" not in bucket.objects


def test_prune_finished_keeps_unfinished_and_unstored_sources(tmp_path: Path) -> None:
    bucket = FakeBucket()
    lake = lake_with(tmp_path)
    r = push(make_store(bucket), lake, prune_finished=True)
    assert r.pruned == ["aa.parcels"]
    assert not list((lake / "aa.parcels").glob("*/*.parquet"))
    assert (lake / "aa.parcels" / "_offloaded").exists()
    assert "aa.parcels/_offloaded" in bucket.objects
    assert (lake / "bb.parcels" / "parcel" / "00000.parquet").exists()  # not finished


def test_prune_needs_every_part_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lake_sync, "MAX_BYTES", 1)  # nothing fits: nothing may be pruned
    bucket = FakeBucket()
    lake = lake_with(tmp_path)
    assert push(make_store(bucket), lake, prune_finished=True).pruned == []
    assert (lake / "aa.parcels" / "parcel" / "00000.parquet").exists()


def test_pull_state_fetches_markers_not_parquet_and_never_overwrites(tmp_path: Path) -> None:
    bucket = FakeBucket()
    push(make_store(bucket), lake_with(tmp_path / "a"))
    fresh = tmp_path / "b" / "lake"
    (fresh / "bb.parcels").mkdir(parents=True)
    (fresh / "bb.parcels" / "_plan.json").write_text("local")
    n = pull_state(make_store(bucket), fresh)
    assert n == 3  # aa: plan, counts, one marker; bb: its only state file (plan) is local
    assert (fresh / "aa.parcels" / "_parts" / "00000.json").exists()
    assert (fresh / "bb.parcels" / "_plan.json").read_text() == "local"
    assert not list(fresh.rglob("*.parquet"))


def test_transient_errors_are_retried(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.fail_next = 2
    assert push(make_store(bucket), lake_with(tmp_path)).uploaded == 8
    bucket.fail_next = 99
    with pytest.raises(OSError, match="connection reset"):
        make_store(bucket).download("aa.parcels/_plan.json")


def test_list_pages_past_a_thousand(tmp_path: Path) -> None:
    bucket = FakeBucket()
    for i in range(1500):
        bucket.objects[f"src/parcel/{i:05d}.parquet"] = b"x"
    files, dirs = make_store(bucket).list_dir("src/parcel/")
    assert len(files) == 1500 and dirs == []


def test_main_push_and_pull(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    bucket = FakeBucket()
    monkeypatch.setattr(lake_sync, "urllib_transport", bucket)
    monkeypatch.setattr(lake_sync.Store, "__init__.__defaults__", None, raising=False)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sk")
    real_init = Store.__init__

    def init(self, *a, **kw) -> None:  # type: ignore[no-untyped-def]
        kw.setdefault("transport", bucket)
        real_init(self, *a, **kw)

    monkeypatch.setattr(Store, "__init__", init)
    lake = lake_with(tmp_path)
    assert lake_sync.main(["--lake", str(lake), "push"]) == 0
    assert "uploaded 8" in capsys.readouterr().out
    assert lake_sync.main(["--lake", str(tmp_path / "fresh"), "pull-state"]) == 0
    assert "pulled 4 state files" in capsys.readouterr().out


def test_only_limits_push_and_pull_to_the_named_sources(tmp_path: Path) -> None:
    """Parallel loaders each push and pull only their own sources, so one loader's stale copy
    of another source's state can never overwrite the other loader's progress."""
    bucket = FakeBucket()
    lake = lake_with(tmp_path / "a")
    r = push(make_store(bucket), lake, only=frozenset({"bb.parcels"}))
    assert r.uploaded == 3  # bb: parquet, plan, state bundle
    assert all(k.startswith("bb.parcels/") for k in bucket.objects)
    push(make_store(bucket), lake)
    fresh = tmp_path / "b" / "lake"
    assert pull_state(make_store(bucket), fresh, only=frozenset({"aa.parcels"})) == 3
    assert not (fresh / "bb.parcels").exists()


def test_pull_parts_downloads_missing_parquet_only(tmp_path: Path) -> None:
    from equity.lake_sync import pull_parts

    bucket = FakeBucket()
    push(make_store(bucket), lake_with(tmp_path / "a"))
    fresh = tmp_path / "b" / "lake"
    assert pull_parts(make_store(bucket), fresh, ["bb.parcels"]) == 1
    assert (fresh / "bb.parcels" / "parcel" / "00000.parquet").read_bytes() == b"Q0"
    assert pull_parts(make_store(bucket), fresh, ["bb.parcels"]) == 0  # already there
    assert pull_parts(make_store(bucket), fresh, ["aa.parcels"], tables=["address"]) == 0
