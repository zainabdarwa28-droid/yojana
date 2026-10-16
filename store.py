"""Anonymous usage log (for the department insights page) and an SMS outbox.

Privacy: the event log stores NO names, phone numbers or Aadhaar numbers. Only: time, channel, district, helper id,
language, which schemes were eligible and which eligibility rules failed.
Phone numbers go to the outbox ONLY when the citizen consents, and only so an SMS/reminder can be sent.
Note: on free cloud hosting the disk is temporary; use a real database for a pilot.
"""
import csv
import datetime as dt
import os
import pathlib
import random
import uuid
from collections import Counter

DATA = pathlib.Path(os.getenv("YOJANA_DATA", pathlib.Path(__file__).parent / "data"))
EVENTS = DATA / "events.csv"
OUTBOX = DATA / "outbox.csv"
EVENT_FIELDS = ["case_id", "timestamp", "channel", "district", "helper_id", "lang", "mode",
                "members", "schemes_checked", "eligible", "unmet_fields"]
OUTBOX_FIELDS = ["created", "due_date", "phone", "text", "status"]


def _append(path, fields, row):
    DATA.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


def _read(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def log_event(outcome: dict, channel="web", district="", helper_id="", lang="hi", prefix="") -> str:
    """Record one anonymous result. `outcome` comes from Reply.outcome. Returns the case id."""
    if not outcome:
        return ""
    case_id = prefix + uuid.uuid4().hex[:8]
    _append(EVENTS, EVENT_FIELDS, {
        "case_id": case_id, "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "channel": channel, "district": district.strip(), "helper_id": helper_id.strip(), "lang": lang,
        "mode": outcome.get("mode", ""), "members": outcome.get("members", 1),
        "schemes_checked": "|".join(outcome.get("schemes_checked", [])),
        "eligible": "|".join(outcome.get("eligible", [])), "unmet_fields": "|".join(outcome.get("unmet", []))})
    return case_id


def read_events():
    return _read(EVENTS)


def summarize(events=None) -> dict:
    ev = read_events() if events is None else events
    eligible, unmet, channel, district, helper = Counter(), Counter(), Counter(), Counter(), Counter()
    for e in ev:
        eligible.update([x for x in e["eligible"].split("|") if x])
        unmet.update([x for x in e["unmet_fields"].split("|") if x])
        channel[e["channel"] or "web"] += 1
        if e["district"]:
            district[e["district"]] += 1
        if e["helper_id"]:
            helper[e["helper_id"]] += 1
    return {"total": len(ev), "eligible_by_scheme": dict(eligible.most_common()),
            "unmet_by_rule": dict(unmet.most_common()), "by_channel": dict(channel),
            "by_district": dict(district.most_common()), "by_helper": dict(helper.most_common())}


def load_demo_data(n: int = 60, seed: int = 7) -> int:
    """SYNTHETIC rows so the dashboard can be shown. Case ids start with DEMO- so they are easy to remove."""
    rnd = random.Random(seed)
    ids = ["mahtari", "ujjwala", "pmayg", "ayushman", "ayushman_vv", "ration", "nsap", "sukanya", "pmmvy", "anganwadi", "pmposhan"]
    districts = ["Raipur", "Bilaspur", "Bastar", "Surguja", "Kanker", "Korba"]
    for _ in range(n):
        elig = rnd.sample(ids, rnd.randint(0, 4))
        unmet = rnd.sample(["bpl", "age", "pucca_house", "pregnant", "gender"], rnd.randint(0, 2))
        log_event({"mode": rnd.choice(["single", "family"]), "members": rnd.randint(1, 4),
                   "schemes_checked": ids, "eligible": elig, "unmet": unmet},
                  channel=rnd.choice(["web", "ivr", "saathi", "saathi"]), district=rnd.choice(districts),
                  helper_id=rnd.choice(["", "SAATHI-01", "SAATHI-02"]), lang=rnd.choice(["hi", "hi", "en"]), prefix="DEMO-")
    return n


def clear_demo_data() -> int:
    rows = read_events()
    keep = [r for r in rows if not r["case_id"].startswith("DEMO-")]
    if EVENTS.exists():
        with open(EVENTS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            w.writeheader()
            w.writerows(keep)
    return len(rows) - len(keep)


def queue_sms(phone: str, text: str, consent: bool, remind_in_days: int = 0) -> bool:
    """Queue an SMS (and optional reminder). Does nothing without consent or a valid 10-digit number."""
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    if not consent or len(digits) != 10:
        return False
    today = dt.date.today()
    _append(OUTBOX, OUTBOX_FIELDS, {"created": today.isoformat(),
                                    "due_date": (today + dt.timedelta(days=remind_in_days)).isoformat(),
                                    "phone": digits, "text": text, "status": "queued"})
    return True


def read_outbox():
    return _read(OUTBOX)
