from printguard.state import FAILED, OK, DayState, StateStore


def test_roundtrip(tmp_path):
    store = StateStore(tmp_path)
    store.save(DayState(day="2026-03-10", status=OK, job_id="9", attempts=2))
    loaded = store.load("2026-03-10")
    assert (loaded.status, loaded.job_id, loaded.attempts) == (OK, "9", 2)


def test_missing_day_is_none(tmp_path):
    assert StateStore(tmp_path).load("2026-03-10") is None


def test_save_leaves_no_temp_files(tmp_path):
    store = StateStore(tmp_path)
    store.save(DayState(day="2026-03-10", status=FAILED))
    assert [p.name for p in tmp_path.iterdir()] == ["2026-03-10.json"]
