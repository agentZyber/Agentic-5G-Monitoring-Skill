"""Dataset pull strategies + telemetry replay into the event bus."""

import json

from corelab.core.bus import EventBus
from corelab.core.events import EventDomain
from corelab.datasets.pull import pull
from corelab.datasets.replay import replay_csv, replay_jsonl


# ---- pull -------------------------------------------------------------------


def test_pull_teleqna_downloads(tmp_path, monkeypatch):
    import corelab.packs.telco_bench.data as bench_data

    def fake_fetch(dest, url=bench_data.TELEQNA_URL, timeout=60):
        from pathlib import Path

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("{}")
        return dest

    monkeypatch.setattr(bench_data, "fetch_teleqna", fake_fetch)
    result = pull("teleqna", root=tmp_path)
    assert result["action"] == "downloaded"
    assert (tmp_path / "TeleQnA.txt").exists()
    assert "eval-only" in result["reminder"]


def test_pull_oversized_dataset_gives_guidance_not_download(tmp_path):
    result = pull("tele-data", root=tmp_path)
    assert result["action"] == "guide"
    assert "huggingface-cli download AliMaatouk/Tele-Data" in result["guide"]
    assert list(tmp_path.iterdir()) == []  # nothing was blind-downloaded


def test_pull_5g3e_surfaces_licence_warning(tmp_path):
    result = pull("5g3e", root=tmp_path)
    assert result["action"] == "guide"
    assert result["license"] == "verify"
    assert "LICENSE" in result["guide"]  # the registry note rides along


# ---- replay: CSV (5G3E-shaped) ---------------------------------------------------


def _write_csv(path, rows, header):
    path.write_text("\n".join([",".join(header)] + [",".join(map(str, r)) for r in rows]))


def test_replay_csv_publishes_kpi_events(tmp_path):
    csv_path = tmp_path / "upf_metrics.csv"
    _write_csv(
        csv_path,
        rows=[[0, "upf-1", 12.5, 3], [30, "upf-1", 99.9, 4], [60, "upf-2", 11.0, 2]],
        header=["ts", "nf", "cpu_pct", "sessions"],
    )
    bus = EventBus()
    report = replay_csv(
        bus, csv_path, domain="ran_kpi", entity_col="nf", ts_col="ts"
    )
    assert (report.published, report.skipped) == (3, 0)
    events = bus.store.recent(domain=EventDomain.RAN_KPI, limit=10)
    assert len(events) == 3
    newest = events[0]
    assert newest.entity_id == "upf-2"
    assert newest.payload == {"cpu_pct": 11.0, "sessions": 2.0}
    assert newest.event_type == "replay"
    assert newest.source == "upf_metrics.csv"


def test_replay_csv_value_cols_subset_and_max_events(tmp_path):
    csv_path = tmp_path / "m.csv"
    _write_csv(csv_path, rows=[[1, 10, 99], [2, 20, 98]], header=["ts", "dl_mbps", "noise"])
    bus = EventBus()
    report = replay_csv(bus, csv_path, value_cols=["dl_mbps"], ts_col="ts", max_events=1)
    assert report.published == 1
    event = bus.store.recent(limit=1)[0]
    assert event.payload == {"dl_mbps": 10.0}  # noise column excluded
    assert event.timestamp == "1"


def test_replay_csv_time_compression_sleeps_scaled(tmp_path):
    csv_path = tmp_path / "paced.csv"
    _write_csv(csv_path, rows=[[0, 1], [30, 2], [90, 3]], header=["ts", "v"])
    sleeps = []
    replay_csv(
        EventBus(), csv_path, ts_col="ts", speed=10.0, sleeper=sleeps.append
    )
    assert sleeps == [3.0, 6.0]  # (30-0)/10, (90-30)/10


def test_replay_csv_skips_empty_rows(tmp_path):
    csv_path = tmp_path / "gaps.csv"
    csv_path.write_text("ts,v\n1,\n2,5\n")
    report = replay_csv(EventBus(), csv_path, ts_col="ts")
    assert (report.published, report.skipped) == (1, 1)


# ---- replay: JSONL ------------------------------------------------------------------


def test_replay_jsonl_mixed_shapes(tmp_path):
    records = [
        {"domain": "qos", "source": "rec", "entity_id": "ue1", "payload": {"latency_ms": 120}},
        {"externalId": "ue2", "type": "alert", "locationInfo": {"cellId": "X"}},  # legacy
        {"unrelated": True},  # skipped
        "not json at all",
    ]
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) if not isinstance(r, str) else r for r in records)
    )
    bus = EventBus()
    report = replay_jsonl(bus, path)
    assert (report.published, report.skipped) == (2, 2)
    domains = {e.domain.value for e in bus.store.recent(limit=10)}
    assert domains == {"qos", "location"}
