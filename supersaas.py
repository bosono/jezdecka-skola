import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta

TYPE_NAMES = {
    "skup": "Skupinová",
    "kaval": "Kavaletová",
    "komb": "Kombinovaná",
    "skok": "Skoková",
    "souk": "Soukromá",
}


def _parse_time(t):
    h, m = t.split(":")
    return time(int(h), int(m))


def _lesson_label(slot):
    name = TYPE_NAMES.get(slot.get("type"), slot.get("type", ""))
    coach = slot.get("coach")
    return name + (f" ({coach})" if coach else "")


def _lesson_mounts(slot, assignments, horses, riders):
    parts = []
    for a in assignments:
        if a.get("slot") != slot["id"]:
            continue
        h = horses.get(a.get("horse"))
        hn = h["name"] if h else "?"
        r = riders.get(a.get("rider"))
        parts.append(hn + (f"/{r['name'].split(' ')[0]}" if r else ""))
    return ", ".join(parts)


def _split(start_dt, finish_dt, slot_minutes):
    if not slot_minutes:
        return [(start_dt, finish_dt)]
    out = []
    cur = start_dt
    step = timedelta(minutes=slot_minutes)
    while cur < finish_dt:
        nxt = min(cur + step, finish_dt)
        out.append((cur, nxt))
        cur = nxt
    return out


def week_bookings(state, week_start, days=None, slot_minutes=None):
    horses = {h["id"]: h for h in state.get("horses", [])}
    riders = {r["id"]: r for r in state.get("riders", [])}
    assignments = state.get("assignments", [])
    day_set = set(range(7)) if days is None else set(days)
    out = []
    for s in state.get("slots", []):
        if s["day"] not in day_set:
            continue
        d = week_start + timedelta(days=s["day"])
        start_dt = datetime.combine(d, _parse_time(s["from"]))
        finish_dt = datetime.combine(d, _parse_time(s["to"]))
        mounts = _lesson_mounts(s, assignments, horses, riders)
        label = _lesson_label(s)
        full_name = label + (f": {mounts}" if mounts else "")
        for cs, cf in _split(start_dt, finish_dt, slot_minutes):
            out.append({
                "day": s["day"],
                "start": cs.strftime("%Y-%m-%d %H:%M:%S"),
                "finish": cf.strftime("%Y-%m-%d %H:%M:%S"),
                "full_name": full_name,
            })
    out.sort(key=lambda b: b["start"])
    return out


def week_range(week_start, days=None):
    ds = sorted(range(7) if days is None else days)
    first = week_start + timedelta(days=ds[0])
    last = week_start + timedelta(days=ds[-1] + 1)
    return first.strftime("%Y-%m-%d 00:00:00"), last.strftime("%Y-%m-%d 00:00:00")


class SuperSaasError(Exception):
    def __init__(self, status, body):
        super().__init__(f"SuperSaaS HTTP {status}: {body!r}")
        self.status = status
        self.body = body


def is_configured():
    return bool(os.environ.get("SUPERSAAS_API_KEY") and os.environ.get("SUPERSAAS_SCHEDULE_ID"))


def slot_minutes_from_env():
    v = os.environ.get("SUPERSAAS_SLOT_MINUTES", "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else None


class SuperSaasClient:
    def __init__(self, api_key, schedule_id, base_url="https://www.supersaas.com", transport=None):
        self.api_key = api_key
        self.schedule_id = str(schedule_id)
        self.base_url = base_url.rstrip("/")
        self._transport = transport or self._http

    def _http(self, method, url, headers, data):
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def _url(self, path, params=None):
        p = dict(params or {})
        p["api_key"] = self.api_key
        return f"{self.base_url}{path}?{urllib.parse.urlencode(p)}"

    def create_booking(self, booking):
        url = self._url("/api/bookings.json")
        payload = {
            "schedule_id": self.schedule_id,
            "booking": {k: booking[k] for k in ("start", "finish", "full_name")},
        }
        status, body, headers = self._transport(
            "POST", url, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8")
        )
        if status not in (200, 201):
            raise SuperSaasError(status, body)
        loc = headers.get("Location", "")
        tail = loc.rstrip("/").split("/")[-1]
        return tail.split(".")[0] if tail else None

    def list_range(self, from_dt, to_dt):
        url = self._url(f"/api/range/{self.schedule_id}.json", {"from": from_dt, "to": to_dt})
        status, body, _ = self._transport("GET", url, {}, None)
        if status != 200:
            raise SuperSaasError(status, body)
        return json.loads(body or b"[]")

    def delete_booking(self, booking_id):
        url = self._url(f"/api/bookings/{booking_id}.json", {"schedule_id": self.schedule_id})
        status, body, _ = self._transport("DELETE", url, {}, None)
        if status not in (200, 204):
            raise SuperSaasError(status, body)

    def replace(self, bookings, from_dt, to_dt):
        existing = self.list_range(from_dt, to_dt)
        deleted = 0
        for b in existing:
            bid = b.get("id")
            if bid is not None:
                self.delete_booking(bid)
                deleted += 1
        ids = [self.create_booking(b) for b in bookings]
        return {"deleted": deleted, "created": len(ids), "ids": ids}


def client_from_env(transport=None):
    return SuperSaasClient(
        os.environ["SUPERSAAS_API_KEY"], os.environ["SUPERSAAS_SCHEDULE_ID"], transport=transport
    )
