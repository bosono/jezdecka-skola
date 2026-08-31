from datetime import date
import supersaas


STATE = {
    "horses": [{"id": "h1", "name": "Dally", "pony": False},
               {"id": "h2", "name": "Sargas", "pony": True}],
    "riders": [{"id": "r1", "name": "Adéla Nováková"}],
    "slots": [
        {"id": "s1", "day": 0, "from": "16:00", "to": "17:00", "type": "skup", "coach": "Martina"},
        {"id": "s2", "day": 2, "from": "19:00", "to": "20:00", "type": "skok", "coach": "Veronika"},
    ],
    "assignments": [
        {"slot": "s1", "horse": "h1", "rider": "r1", "regular": True},
        {"slot": "s1", "horse": "h2", "rider": None, "regular": False},
    ],
}
MONDAY = date(2026, 8, 31)  # pondělí


def test_week_bookings_whole_week_concrete_dates():
    out = supersaas.week_bookings(STATE, MONDAY)
    assert len(out) == 2
    assert out[0]["start"] == "2026-08-31 16:00:00"
    assert out[0]["finish"] == "2026-08-31 17:00:00"
    # středa = pondělí + 2
    assert out[1]["start"] == "2026-09-02 19:00:00"


def test_week_bookings_full_name_has_label_and_mounts():
    out = supersaas.week_bookings(STATE, MONDAY, days=[0])
    assert "Skupinová" in out[0]["full_name"]
    assert "Martina" in out[0]["full_name"]
    assert "Dally" in out[0]["full_name"]


def test_week_bookings_single_day_filter():
    out = supersaas.week_bookings(STATE, MONDAY, days=[2])
    assert len(out) == 1
    assert out[0]["start"].startswith("2026-09-02")


def test_week_bookings_slot_minutes_splits_lesson():
    out = supersaas.week_bookings(STATE, MONDAY, days=[0], slot_minutes=30)
    assert len(out) == 2  # 16:00-17:00 → dva 30min bloky
    assert out[0]["start"] == "2026-08-31 16:00:00"
    assert out[0]["finish"] == "2026-08-31 16:30:00"
    assert out[1]["start"] == "2026-08-31 16:30:00"
    assert out[1]["finish"] == "2026-08-31 17:00:00"


def test_week_range_whole_week():
    frm, to = supersaas.week_range(MONDAY)
    assert frm == "2026-08-31 00:00:00"
    assert to == "2026-09-07 00:00:00"


import supersaas as ss


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.range_result = b"[]"

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url, data))
        if method == "GET":
            return 200, self.range_result, {}
        if method == "POST":
            return 201, b"{}", {"Location": "/api/bookings/999.json"}
        if method == "DELETE":
            return 200, b"", {}
        return 400, b"", {}


def test_client_create_returns_id_from_location():
    t = FakeTransport()
    client = ss.SuperSaasClient("KEY", "42", transport=t)
    bid = client.create_booking({"start": "2026-08-31 16:00:00", "finish": "2026-08-31 17:00:00", "full_name": "Skupinová"})
    assert bid == "999"
    method, url, data = t.calls[0]
    assert method == "POST"
    assert "api_key=KEY" in url


def test_client_replace_deletes_then_creates():
    t = FakeTransport()
    t.range_result = b'[{"id": 111}, {"id": 222}]'
    client = ss.SuperSaasClient("KEY", "42", transport=t)
    bookings = [{"start": "2026-08-31 16:00:00", "finish": "2026-08-31 17:00:00", "full_name": "A"}]
    result = client.replace(bookings, "2026-08-31 00:00:00", "2026-09-07 00:00:00")
    assert result["deleted"] == 2
    assert result["created"] == 1
    methods = [c[0] for c in t.calls]
    assert methods == ["GET", "DELETE", "DELETE", "POST"]


def test_is_configured(monkeypatch):
    monkeypatch.delenv("SUPERSAAS_API_KEY", raising=False)
    monkeypatch.delenv("SUPERSAAS_SCHEDULE_ID", raising=False)
    assert ss.is_configured() is False
    monkeypatch.setenv("SUPERSAAS_API_KEY", "k")
    monkeypatch.setenv("SUPERSAAS_SCHEDULE_ID", "42")
    assert ss.is_configured() is True
