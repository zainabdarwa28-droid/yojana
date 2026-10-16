"""Send queued SMS messages.   python notify.py --list     python notify.py --send-due

Without credentials this only PRINTS what it would send (safe for the demo).
For real sending with Twilio set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM and `pip install twilio`.
Indian providers (Exotel, MSG91, etc.) need DLT registration of the SMS template first; check their documentation.
"""
import csv
import datetime as dt
import os
import sys

import store


def _send(phone: str, text: str) -> bool:
    sid, tok, frm = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (sid and tok and frm):
        print(f"[DRY RUN] to +91{phone}: {text}")
        return True
    try:
        from twilio.rest import Client
        Client(sid, tok).messages.create(to="+91" + phone, from_=frm, body=text)
        return True
    except Exception as exc:
        print("send failed:", exc)
        return False


def send_due(today=None) -> int:
    today = (today or dt.date.today()).isoformat()
    rows, sent = store.read_outbox(), 0
    for r in rows:
        if r["status"] == "queued" and r["due_date"] <= today and _send(r["phone"], r["text"]):
            r["status"] = "sent"
            sent += 1
    with open(store.OUTBOX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=store.OUTBOX_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return sent


if __name__ == "__main__":
    if "--send-due" in sys.argv:
        print(send_due(), "message(s) processed")
    else:
        for r in store.read_outbox():
            print(r["due_date"], r["status"], "xxxxxx" + r["phone"][-4:], r["text"][:60])
