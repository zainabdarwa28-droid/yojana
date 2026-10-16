# Yojana Saathi: voice-first helper for government schemes (prototype v2)

For women, girls, children and senior citizens of Chhattisgarh. Five ideas are built in:

| # | Idea | Where in the code |
|---|---|---|
| 1 | **Works on any phone**: phone-call (IVR) server + assisted mode | `ivr_server.py`, Saathi helper mode in `app.py` |
| 2 | **Understands Chhattisgarhi**: glossary of local words mapped to Hindi, accuracy compared with/without | `glossary_cg.json`, `evaluate.py questions_cg.csv` |
| 3 | **One conversation for the whole family** | `assistant.py` (family mode: say "family" / "परिवार") |
| 4 | **Not just "you may qualify"**: documents, where to go, SMS summary, reminder, document checklist | `assistant.py`, `store.py`, `notify.py`, result panel in `app.py` |
| 5 | **Local Saathi helper**: consent script, helper ID, printable slip, per-helper counts | Saathi helper mode in `app.py` |
| + | **Department insights**: anonymous counts of who was eligible, which rules block people | Insights mode in `app.py`, `store.py` |

Eligibility is decided by fixed rules in `schemes.json`, never by an AI model.

## Run
```bash
pip install streamlit pandas gTTS      # minimum
streamlit run app.py                   # web demo (Citizen / Saathi helper / Insights)
python cli.py                          # terminal demo
python evaluate.py questions_cg.csv    # Chhattisgarhi accuracy with vs without the glossary
python ivr_server.py                   # phone-call server on port 8080
python -c "import test_assistant as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('all tests passed')"
```
Voice: see the **Voice** section below. Run `python doctor.py` to check your computer.

## Voice (v3)
Two ways to talk to the app. Pick one in the sidebar under **Voice**:

| Option | Works on | Needs | Notes |
|---|---|---|---|
| **Browser microphone** (default) | Phones, laptops, and the hosted app | Chrome or Edge, microphone permission, internet | No installs. Hindi (hi-IN) and English (en-IN). Chhattisgarhi is understood as Hindi |
| **Offline Whisper** | Your own computer only | `pip install faster-whisper`, model downloaded once | Slower on weak laptops; choose `base` for speed, `small` or `medium` for accuracy |

Spoken replies: **Browser voice** (press Listen, or tick auto-read) needs a Hindi voice installed on the device;
**gTTS** needs internet. Pick the voice language yourself (Hindi or English) for the best accuracy.
Troubleshooting: sidebar > Voice > Voice troubleshooting, or `python doctor.py`.

## Language detection
Reply language follows what you say or type: Devanagari or romanised Hindi ("mujhe gas chahiye") gives Hindi,
clear English gives English, and very short answers ("30", "haan", "ration") keep the language of the conversation.
You can force a language in the sidebar.

## Try these
* Type `गैस चाहिए`, answer the questions, then look at "What to do next" (documents, where to go, SMS).
* Type `family`, then `myself 35, daughter 8, father-in-law 68`, and answer the questions.
* Chhattisgarhi: `लइका बर चाउर कहां मिलही`, `सियान मन बर महीना के पइसा कइसे मिलही`.
* Switch to **Saathi helper** mode, tick the consent box, run a check, download the slip.
* Switch to **Insights**, click "Load SYNTHETIC demo data" for a preview (clearly labelled demo rows).

## Phone calls (IVR)
`ivr_server.py` speaks Twilio-style TwiML. Run it, expose it with a tunnel or host, and set your provider's voice webhook
to `https://YOUR-URL/voice`. Callers can speak Hindi or press keys (menu digits, 1 = yes, 2 = no, 0 = repeat).
Verified here: the logic and HTTP responses (tests). NOT verified: a live call with a real provider, voice quality,
and Indian telephony rules (many Indian providers use other formats and need registration). Add request-signature
checks, HTTPS and rate limits before any real use.

## SMS and reminders
Citizens who tick consent and give a number are queued in `data/outbox.csv`. `python notify.py --list` shows the queue,
`python notify.py --send-due` prints (dry run) or sends via Twilio if credentials are set. Indian SMS needs DLT registration.

## Privacy
* The usage log (`data/events.csv`) stores NO names, phone numbers or Aadhaar numbers.
* Phone numbers are stored only with consent, only in the outbox.
* Children's data has special legal rules (DPDP Act 2023): confirm the current requirements before any pilot.
* On free cloud hosting the disk is temporary; use a database for a pilot.

## Before you demo or submit
1. **`schemes.json` is SAMPLE data.** Check every scheme (benefit, rules, documents, where to apply) against the official list
   (https://cmhelpline.cg.gov.in/Home/Schemes) and the department portals, then set `verified` to true and fill `last_verified`.
2. **`glossary_cg.json` is a starter list written without native-speaker review.** Check every word and add words from real recordings.
3. **`questions_cg.csv` is illustrative.** Replace it with real transcribed questions and report the real accuracy.
4. Test with 5-10 real users and keep the screenshots.
