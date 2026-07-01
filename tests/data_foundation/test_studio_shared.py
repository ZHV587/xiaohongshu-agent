from data_foundation import studio_shared as ss


def test_is_admin_open_id(monkeypatch):
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin, ou_two")
    assert ss.is_admin_open_id("ou_admin") is True
    assert ss.is_admin_open_id("ou_two") is True
    assert ss.is_admin_open_id("ou_nobody") is False
    assert ss.is_admin_open_id("") is False


def test_is_admin_open_id_unset(monkeypatch):
    monkeypatch.delenv("XHS_ADMIN_OPEN_IDS", raising=False)
    assert ss.is_admin_open_id("ou_admin") is False


def test_derive_stage_explicit_only():
    assert ss.derive_stage({"stage": "scheduled"}) == "scheduled"
    assert ss.derive_stage({"stage": "published"}) == "published"
    assert ss.derive_stage({"stage": "measured"}) == "measured"
    # 无显式 stage → None(不做启发式回退)
    assert ss.derive_stage({"metrics": {"likes": 1}, "note_url": "u"}) is None
    assert ss.derive_stage({}) is None
    assert ss.derive_stage({"stage": "bogus"}) is None


def test_day_of_month():
    assert ss.day_of_month("2026-06-12") == 12
    assert ss.day_of_month("2026-6-1") is None  # 长度<10
    assert ss.day_of_month("bad") is None
    assert ss.day_of_month(None) is None


def test_now_iso_is_utc_iso():
    v = ss.now_iso()
    assert "T" in v and ("+00:00" in v or v.endswith("Z"))
