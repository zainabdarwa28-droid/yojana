"""Yojana Saathi web demo.   streamlit run app.py
Modes: Citizen (self-service) | Saathi helper (assisted, in person) | Insights (for departments)."""
import datetime as dt
import hashlib
import pathlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import llm
import speech
import store
from assistant import Assistant, Session

st.set_page_config(page_title="Yojana Saathi", page_icon="🙏")
BOT = st.session_state.setdefault("bot", Assistant())
_VOICE = components.declare_component("yojana_voice", path=str(pathlib.Path(__file__).parent / "voice_component"))
RULE_LABELS = {"bpl": "Not in BPL / poor-household category", "age": "Age rule not met", "gender": "Gender rule not met",
               "pucca_house": "Already owns a pucca house", "pregnant": "Not pregnant / breastfeeding"}

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Yojana Saathi")
    mode = st.radio("Mode", ["Citizen", "Saathi helper", "Insights (departments)"], index=0)
    lang_choice = st.radio("Reply language", ["Auto", "हिन्दी", "English"], index=0)
    st.subheader("Voice")
    voice_in = st.radio("Voice input", ["Browser microphone (recommended)", "Offline Whisper (this computer)", "Off (typing only)"], index=0,
                        help="Browser microphone works on phones and on the hosted app (Chrome or Edge, needs internet).")
    voice_lang = st.radio("Voice language", ["Auto (follow chat)", "हिन्दी / Chhattisgarhi", "English"], index=0,
                          help="Choosing the language yourself is the most accurate option.")
    spoken = st.radio("Spoken replies", ["Browser voice", "gTTS audio (needs internet)", "Off"], index=0)
    auto_speak = st.checkbox("Read each reply aloud automatically", value=False,
                             help="Browsers only allow this after you have pressed the microphone or Listen button once.") if spoken == "Browser voice" else False
    whisper_model = st.selectbox("Whisper model", speech.MODELS, index=speech.MODELS.index(speech.default_model())
                                 if speech.default_model() in speech.MODELS else 2) if voice_in.startswith("Offline") else None
    with st.expander("Voice troubleshooting"):
        for name, ok, detail in speech.diagnose():
            st.write(("✅ " if ok else "❌ ") + name + ("" if ok else f"  →  `{detail}`"))
        st.caption("Browser microphone: use Chrome or Edge, allow the microphone (lock icon), and keep internet on. "
                   "Offline Whisper: pip install faster-whisper, then run `python doctor.py --download small` once.")
    use_llm = st.checkbox("Simplify wording with AI (optional, needs API key)", value=False)
    district = st.text_input("District (optional)", value="")
    save_stats = st.checkbox("Save anonymous usage statistics", value=True,
                             help="No names, phone numbers or Aadhaar numbers are saved in these statistics.")
lang_pref = {"Auto": None, "हिन्दी": "hi", "English": "en"}[lang_choice]
VOICE_HINT = {"Auto (follow chat)": None, "हिन्दी / Chhattisgarhi": "hi", "English": "en"}[voice_lang]


def make_slip(reply) -> str:
    lines = ["YOJANA SAATHI - summary slip", dt.date.today().isoformat(), "", reply.text]
    if reply.sms:
        lines += ["", "SMS: " + reply.sms]
    return "\n".join(lines)


def process(key, channel, helper_id, text, lang_hint=None):
    sess = st.session_state[f"{key}_session"]
    reply = BOT.handle(sess, text, lang_pref or lang_hint)
    shown = llm.simplify(reply.text, reply.lang) if use_llm else reply.text
    audio, tts_err = None, None
    if spoken.startswith("gTTS") and text.strip():
        audio = speech.speak(shown, reply.lang)
        tts_err = speech.last_tts_error
    hist = st.session_state[f"{key}_history"]
    if text.strip():
        hist.append(("user", text, None))
    hist.append(("assistant", shown, audio))
    if tts_err:
        st.session_state[f"{key}_tts_error"] = tts_err
    if reply.outcome:
        st.session_state[f"{key}_last"] = reply
        if save_stats:
            store.log_event(reply.outcome, channel=channel, district=district, helper_id=helper_id, lang=reply.lang)


def reset(key):
    for suffix in ("session", "history", "last", "tts_error"):
        st.session_state.pop(f"{key}_{suffix}", None)


def result_panel(key, helper_mode):
    reply = st.session_state.get(f"{key}_last")
    if not reply or not (reply.docs or reply.sms):
        return
    st.divider()
    st.subheader("📋 What to do next")
    if reply.docs:
        have = st.multiselect("Tick the documents you already have", reply.docs, key=f"{key}_have")
        missing = [d for d in reply.docs if d not in have]
        if missing:
            st.warning("Still needed: " + ", ".join(missing))
        else:
            st.success("You have all the listed documents.")
    if reply.where:
        st.info("📍 Go to: " + "; ".join(reply.where))
    if reply.sms:
        st.text_area("SMS summary", value=reply.sms, height=100, key=f"{key}_sms_preview")
        phone = st.text_input("Mobile number for the SMS and reminder (optional)", key=f"{key}_phone")
        agree = st.checkbox("The citizen agrees to receive this SMS and one reminder", key=f"{key}_agree")
        days = st.selectbox("Remind after (days)", [0, 3, 7], index=1, key=f"{key}_days")
        if st.button("Queue SMS", key=f"{key}_queue"):
            ok = store.queue_sms(phone, reply.sms, agree, days)
            if ok:
                st.success("SMS queued (see outbox.csv; real sending needs an SMS provider).")
            else:
                st.error("Please enter a valid 10-digit number and tick the consent box.")
    if helper_mode:
        st.download_button("🖨️ Download summary slip", make_slip(reply), file_name="yojana_saathi_slip.txt", key=f"{key}_slip")


def chat_view(key, channel, helper_id=""):
    st.session_state.setdefault(f"{key}_session", Session())
    st.session_state.setdefault(f"{key}_history", [])
    if not st.session_state[f"{key}_history"]:
        process(key, channel, helper_id, "")
    c1, c2 = st.columns(2)
    if c1.button("👨‍👩‍👧 Whole family check", key=f"{key}_fam"):
        process(key, channel, helper_id, "परिवार" if lang_pref == "hi" else "family")
        st.rerun()
    if c2.button("Start over", key=f"{key}_reset"):
        reset(key)
        st.rerun()
    for role, text, audio in st.session_state[f"{key}_history"]:
        with st.chat_message(role):
            st.write(text)
            if audio:
                st.audio(audio, format="audio/mp3")
    sess = st.session_state[f"{key}_session"]
    voice_code = {"hi": "hi-IN", "en": "en-IN", None: ("en-IN" if sess.lang == "en" else "hi-IN")}[VOICE_HINT]
    last_text = next((t for r, t, _ in reversed(st.session_state[f"{key}_history"]) if r == "assistant"), "")
    use_browser_in, use_browser_out = voice_in.startswith("Browser"), spoken == "Browser voice"
    if use_browser_in or use_browser_out:
        got = _VOICE(lang=voice_code, speak_text=last_text.replace("\n- ", ". ").replace("\n", ". "),
                     speak_lang=("hi-IN" if sess.lang == "hi" else "en-IN"),
                     speak_id=str(len(st.session_state[f"{key}_history"])), auto_speak=auto_speak,
                     show_mic=use_browser_in, show_listen=use_browser_out, key=f"{key}_voice", default=None)
        if got and got.get("id") != st.session_state.get(f"{key}_voice_id"):
            st.session_state[f"{key}_voice_id"] = got["id"]
            process(key, channel, helper_id, got["text"], lang_hint=VOICE_HINT)
            st.rerun()
    if voice_in.startswith("Offline"):
        if not speech.stt_available():
            st.error("Offline Whisper is not installed. Run `pip install faster-whisper`, or switch Voice input to Browser microphone.")
        elif not hasattr(st, "audio_input"):
            st.error("Your Streamlit is too old for the recorder. Run `pip install --upgrade streamlit` (needs 1.39+).")
        else:
            clip = st.audio_input("🎤 Record / रिकॉर्ड करें", key=f"{key}_mic")
            if clip is not None:
                data = clip.getvalue()
                h = hashlib.md5(data).hexdigest()
                if st.session_state.get(f"{key}_audio") != h:
                    st.session_state[f"{key}_audio"] = h
                    with st.spinner("Listening to the recording..."):
                        res = speech.transcribe(data, VOICE_HINT, whisper_model)
                    if res.text:
                        st.caption(f"Heard ({res.lang}, {res.seconds:.1f}s): {res.text}")
                        process(key, channel, helper_id, res.text, lang_hint=res.lang)
                        st.rerun()
                    st.error(res.error)
    if st.session_state.get(f"{key}_tts_error"):
        st.warning(st.session_state[f"{key}_tts_error"])
    st.caption("Reply language: " + ("हिन्दी" if sess.lang == "hi" else "English") +
               ("  (set in the sidebar)" if lang_pref else "  (automatic: follows what you say or type)"))
    with st.form(f"{key}_form", clear_on_submit=True):
        typed = st.text_input("Type here / यहाँ लिखें", key=f"{key}_typed")
        sent = st.form_submit_button("Send")
    if sent and typed.strip():
        process(key, channel, helper_id, typed)
        st.rerun()
    result_panel(key, helper_mode=(channel == "saathi"))


# ------------------------------------------------------------------ modes
if mode == "Citizen":
    st.title("🙏 Yojana Saathi · योजना साथी")
    st.caption("Ask about government schemes for yourself or your family, in Hindi/Chhattisgarhi or English. "
               "Demo with sample scheme data. Final confirmation is always at the official office.")
    chat_view("citizen", "web")

elif mode == "Saathi helper":
    st.title("🤝 Saathi helper mode")
    st.caption("For a trained local helper (for example an SHG woman) sitting with a citizen at a panchayat, CSC or Anganwadi.")
    helper_id = st.text_input("Helper ID", value="SAATHI-01")
    with st.expander("Read this to the citizen first (privacy script)"):
        st.write("हिन्दी: मैं आपके साथ सरकारी योजनाओं की जाँच करूँगी। मैं आपका नाम या आधार नंबर नहीं लिखूँगी। "
                 "केवल बिना नाम की गिनती सुरक्षित रहेगी। क्या हम आगे बढ़ें?")
        st.write("English: I will help you check government schemes. I will not store your name or Aadhaar number. "
                 "Only anonymous counts are saved. May we continue?")
    if st.checkbox("I read the script and the citizen agreed to continue", key="saathi_consent"):
        chat_view("saathi", "saathi", helper_id)
        mine = [e for e in store.read_events() if e["helper_id"] == helper_id]
        st.sidebar.metric("Checks done by this helper", len(mine))
    else:
        st.info("Tick the box above after the citizen agrees.")

else:
    st.title("📊 Insights for departments")
    st.caption("Anonymous counts only: no names, phone numbers or Aadhaar numbers are stored in this log.")
    c1, c2 = st.columns(2)
    if c1.button("Load SYNTHETIC demo data"):
        store.load_demo_data(60)
        st.rerun()
    if c2.button("Clear demo data"):
        store.clear_demo_data()
        st.rerun()
    summary = store.summarize()
    if not summary["total"]:
        st.info("No data yet. Use the app, or load the synthetic demo data (clearly labelled DEMO) to preview this page.")
    else:
        if any(e["case_id"].startswith("DEMO-") for e in store.read_events()):
            st.warning("Some rows are SYNTHETIC demo data, not real citizens.")
        st.metric("Eligibility checks recorded", summary["total"])
        names = {sid: s["name_en"] for sid, s in BOT.kb.items()}

        def chart(title, counts, rename=None):
            if counts:
                st.subheader(title)
                df = pd.DataFrame({"count": counts.values()}, index=[(rename or {}).get(k, k) for k in counts])
                st.bar_chart(df)

        chart("Schemes people turned out eligible for", summary["eligible_by_scheme"], names)
        chart("Why people were NOT eligible (rules that failed)", summary["unmet_by_rule"], RULE_LABELS)
        chart("Channel", summary["by_channel"])
        chart("District", summary["by_district"])
        chart("Checks per Saathi helper", summary["by_helper"])
        st.caption("Use: spot schemes with low take-up, the rules or documents that stop people, and districts that need outreach.")
