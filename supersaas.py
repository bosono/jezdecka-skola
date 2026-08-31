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
