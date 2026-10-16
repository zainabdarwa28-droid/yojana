"""Speech layer v3: offline Whisper (this computer) and optional server-side gTTS.

Browser voice (recommended, works on phones and on the hosted app) lives in voice_component/index.html.
Whisper needs:  pip install faster-whisper   (first run downloads the model, needs internet once)

Every function reports WHY it failed instead of failing silently.
"""
import importlib.util
import io
import os
import sys
import tempfile
import time
from typing import NamedTuple, Optional

# Words the assistant should recognise. Giving Whisper a Hindi "prompt" with these makes it far more likely
# to write scheme names correctly instead of guessing similar-sounding words.
VOCAB_PROMPT = ("योजना, महतारी वंदन योजना, उज्ज्वला योजना, प्रधानमंत्री आवास योजना, आयुष्मान भारत कार्ड, राशन कार्ड, "
                "वृद्धावस्था पेंशन, सुकन्या समृद्धि योजना, आँगनबाड़ी, मातृ वंदना, परिवार, उम्र, हाँ, नहीं, बेटी, बेटा, पिता")
MODELS = ["tiny", "base", "small", "medium"]
_cache = {}
last_tts_error: Optional[str] = None


class STTResult(NamedTuple):
    text: Optional[str]
    lang: Optional[str]      # "hi" or "en" (what the speaker used), None if unknown
    error: Optional[str]     # human-readable reason when text is None
    seconds: float


def stt_available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def default_model() -> str:
    return os.getenv("WHISPER_MODEL", "small")


def _load(name: str):
    if name not in _cache:
        from faster_whisper import WhisperModel
        _cache[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _cache[name]


def transcribe(audio_bytes: bytes, lang_pref: Optional[str] = None, model: Optional[str] = None) -> STTResult:
    """lang_pref: "hi", "en" or None (auto). Choosing the language yourself is faster and more accurate."""
    t0 = time.time()
    if not stt_available():
        return STTResult(None, None, "faster-whisper is not installed. Run: pip install faster-whisper "
                                      "(or use the Browser microphone option).", 0.0)
    if not audio_bytes or len(audio_bytes) < 2000:
        return STTResult(None, None, "The recording was empty or too short. Press record, speak for 2-3 seconds, then stop.", 0.0)
    name = model or default_model()
    try:
        m = _load(name)
    except Exception as exc:
        return STTResult(None, None, f"Could not load the '{name}' speech model ({str(exc)[:160]}). "
                                      "The first run must download it, so check your internet connection.", time.time() - t0)
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            path = f.name

        def run(language, prompt):
            segs, info = m.transcribe(path, language=language, task="transcribe", beam_size=5, vad_filter=True,
                                      condition_on_previous_text=False, initial_prompt=prompt)
            return " ".join(s.text.strip() for s in segs).strip(), info

        if lang_pref in ("hi", "en"):
            text, _ = run(lang_pref, VOCAB_PROMPT if lang_pref == "hi" else None)
            lang = lang_pref
        else:                                   # auto: let Whisper listen first, then correct if needed
            text, info = run(None, None)
            detected = getattr(info, "language", None)
            prob = getattr(info, "language_probability", 0.0) or 0.0
            if detected == "en" and prob >= 0.6:
                lang = "en"
            elif detected == "hi" and prob >= 0.5:
                lang = "hi"
            else:                               # Chhattisgarhi is often mis-detected (Marathi/Nepali/Urdu...): force Hindi
                text, _ = run("hi", VOCAB_PROMPT)
                lang = "hi"
        if not text:
            return STTResult(None, lang, "I could not hear any words. Speak closer to the microphone, in a quiet place.", time.time() - t0)
        return STTResult(text, lang, None, time.time() - t0)
    except Exception as exc:
        return STTResult(None, None, f"Transcription failed: {str(exc)[:200]}", time.time() - t0)
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def speak(text: str, lang: str = "hi") -> Optional[bytes]:
    """Server-side text-to-speech with gTTS (needs internet). Returns MP3 bytes or None (see last_tts_error)."""
    global last_tts_error
    last_tts_error = None
    if importlib.util.find_spec("gtts") is None:
        last_tts_error = "gTTS is not installed. Run: pip install gTTS (or use Browser voice)."
        return None
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=text[:900], lang="hi" if lang == "hi" else "en").write_to_fp(buf)
        return buf.getvalue()
    except Exception as exc:
        last_tts_error = f"gTTS failed ({str(exc)[:120]}). It needs an internet connection."
        return None


def diagnose():
    """List of (check, ok, detail) used by the app's troubleshooting panel and doctor.py."""
    out = [("Python 3.9+", sys.version_info >= (3, 9), sys.version.split()[0])]
    try:
        import streamlit
        ver = streamlit.__version__
        ok = tuple(int(x) for x in ver.split(".")[:2] if x.isdigit()) >= (1, 39)
        out.append(("Streamlit 1.39+ (needed for st.audio_input)", ok, ver))
    except Exception:
        out.append(("Streamlit installed", False, "pip install streamlit"))
    out.append(("faster-whisper (offline voice input)", stt_available(), "pip install faster-whisper"))
    out.append(("gTTS (server-side spoken replies)", importlib.util.find_spec("gtts") is not None, "pip install gTTS"))
    return out
