"""Yojana Saathi: core dialogue logic (works offline, no API needed).

Features
  * Chhattisgarhi starter glossary mapped to standard Hindi before matching.
  * Single-scheme help: benefit, documents, where to go, eligibility check, SMS summary.
  * Whole-family check: one conversation covers every family member.
  * Eligibility is decided by fixed rules in schemes.json, never by an AI model.
"""
import json
import os
import pathlib
import re
import string
from dataclasses import dataclass, field
from typing import Optional

BASE = pathlib.Path(__file__).parent
KB_PATH = BASE / "schemes.json"
GLOSSARY_PATH = BASE / "glossary_cg.json"
HELPLINE = os.getenv("YOJANA_HELPLINE", "")   # optional number shown in SMS, e.g. a state helpline

_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = str.maketrans({c: " " for c in string.punctuation + "।॥?!,\u201c\u201d\u2018\u2019"})

# ---------------------------------------------------------------- vocabulary
YES = {"yes", "y", "yeah", "haan", "han", "ha", "haa", "ji", "hanji", "sure", "ok", "okay",
       "हाँ", "हां", "हा", "जी", "हव", "हौ", "बिल्कुल", "ठीक"}
NO = {"no", "n", "nahi", "nahin", "na", "nope", "नहीं", "नही", "ना", "नइ", "नई", "नाही"}
UNSURE = ["पता नहीं", "पता नही", "नहीं पता", "pata nahi", "pata nahin", "nahi pata", "don t know", "dont know", "not sure"]
DONE = {"done", "finish", "finished", "bas", "बस", "खत्म", "ख़त्म", "पूरा", "complete"}
DONE_PHRASES = ["no more", "that is all", "हो गया", "हो गई", "इतना ही"]
LIST_WORDS = ["कौन सी योजना", "कौन सा योजना", "सभी योजना", "कोन योजना", "which scheme", "all scheme", "list", "options", "help", "मदद"]
FAMILY_WORDS = ["family", "whole family", "परिवार", "pariwar", "parivar", "घर के सभी", "सबके लिए", "sabke liye"]
FEMALE_W = {"woman", "women", "female", "girl", "lady", "महिला", "औरत", "स्त्री", "लड़की", "बेटी", "बच्ची", "नारी", "बिटिया"}
MALE_W = {"man", "men", "male", "boy", "पुरुष", "आदमी", "लड़का", "बेटा", "मर्द"}

# (key, English label, Hindi label, default gender, words)
REL = [
    ("self", "You", "आप", None, ["myself", "me", "self", "i", "मैं", "मै", "main", "खुद", "अपना", "अपनी"]),
    ("daughter", "Daughter", "बेटी", "F", ["daughter", "beti", "बेटी", "बिटिया", "लड़की", "girl", "बच्ची"]),
    ("son", "Son", "बेटा", "M", ["son", "beta", "बेटा", "लड़का", "boy"]),
    ("mother", "Mother", "माँ", "F", ["mother", "mom", "maa", "माँ", "मां", "माता", "सास", "दादी", "नानी", "dadi", "nani"]),
    ("father", "Father", "पिता", "M", ["father", "dad", "papa", "पिता", "पापा", "ससुर", "दादा", "नाना", "dada", "nana"]),
    ("husband", "Husband", "पति", "M", ["husband", "pati", "पति"]),
    ("wife", "Wife", "पत्नी", "F", ["wife", "patni", "पत्नी"]),
    ("elder", "Senior", "बुजुर्ग", None, ["elder", "senior", "बुजुर्ग"]),
    ("child", "Child", "बच्चा", None, ["child", "kid", "बच्चा", "बच्चे"]),
]
WORD2REL = {w: r for r in REL for w in r[4]}
LABEL_OVERRIDE = {"ससुर": ("Father-in-law", "ससुर"), "सास": ("Mother-in-law", "सास"), "दादी": ("Grandmother", "दादी"),
                  "दादा": ("Grandfather", "दादा"), "नानी": ("Grandmother", "नानी"), "नाना": ("Grandfather", "नाना"),
                  "dadi": ("Grandmother", "दादी"), "dada": ("Grandfather", "दादा"), "nani": ("Grandmother", "नानी"), "nana": ("Grandfather", "नाना")}

_ONES = ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ", "दस", "ग्यारह", "बारह", "तेरह", "चौदह",
         "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस", "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस",
         "सत्ताईस", "अट्ठाईस", "उनतीस", "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस",
         "अड़तीस", "उनतालीस", "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चौवालीस", "पैंतालीस", "छियालीस", "सैंतालीस",
         "अड़तालीस", "उनचास", "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन",
         "उनसठ", "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर", "सत्तर",
         "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी", "अस्सी",
         "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी", "नब्बे",
         "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पंचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे", "सौ"]
NUM_WORDS = {w: (100 if w == "सौ" else i) for i, w in enumerate(_ONES)}
NUM_WORDS.update({"पांच": 5, "छः": 6, "छ": 6, "पन्द्रह": 15, "अठाईस": 28})
_YEAR_WORDS = {"साल", "वर्ष", "year", "years", "saal", "बरस"}

QUESTIONS = {
    "age": {"hi": "जिस व्यक्ति के लिए योजना चाहिए (आप या परिवार का सदस्य), उनकी उम्र कितनी है? बस संख्या बोलें।",
            "en": "How old is the person who needs this scheme (you or a family member)? Just say the number."},
    "gender": {"hi": "वह महिला/लड़की हैं या पुरुष/लड़का?", "en": "Is the person a woman/girl or a man/boy?"},
    "bpl": {"hi": "क्या आपके परिवार के पास BPL (गरीबी रेखा) राशन कार्ड है? हाँ या नहीं बोलें।",
            "en": "Does your family have a BPL (below poverty line) ration card? Say yes or no."},
    "pucca_house": {"hi": "क्या आपके परिवार के पास पक्का मकान है? हाँ या नहीं बोलें।",
                    "en": "Does your family own a pucca (permanent) house? Say yes or no."},
    "pregnant": {"hi": "क्या वह अभी गर्भवती हैं या बच्चे को दूध पिला रही हैं? हाँ या नहीं बोलें।",
                 "en": "Is she pregnant or breastfeeding now? Say yes or no."},
}
FIELD_TYPE = {"age": "int", "gender": "gender", "bpl": "bool", "pucca_house": "bool", "pregnant": "bool"}
HOUSEHOLD_FIELDS = ("bpl", "pucca_house")

MSG = {
    "hi": {
        "hello": "नमस्ते! मैं योजना साथी हूँ। किसी योजना का नाम बोलिए, या पूरे परिवार की जाँच के लिए 'परिवार' बोलिए।",
        "list": "मैं इन योजनाओं के बारे में बता सकती हूँ: {names}। आप किसके बारे में जानना चाहेंगे?",
        "not_understood": "माफ़ कीजिए, मैं यह योजना पहचान नहीं पाई। ",
        "benefit": "लाभ", "docs": "ज़रूरी दस्तावेज़", "how": "आवेदन कैसे करें",
        "offer": "क्या मैं देखूँ कि आप इस योजना के लिए पात्र हैं? हाँ या नहीं बोलें।",
        "retry": "मैं समझ नहीं पाई। ",
        "eligible": "अच्छी खबर! आप {name} के लिए पात्र लग रहे हैं।",
        "not_eligible": "अभी आप {name} के लिए पात्र नहीं लग रहे, क्योंकि: {reasons}।",
        "bring": "साथ ले जाएँ", "goto": "कहाँ जाएँ",
        "declined": "ठीक है। आप किसी और योजना के बारे में पूछ सकते हैं।",
        "family_hint": "पूरे परिवार की जाँच के लिए 'परिवार' बोलिए।",
        "disclaimer": "यह जानकारी मदद के लिए है। पक्की पुष्टि के लिए अपने पंचायत/ब्लॉक कार्यालय या CSC में पूछें।",
        "join": ", ",
        "fam_intro": "ठीक है, पूरे परिवार की जाँच करते हैं। बताइए कौन है और उम्र कितनी है, 'और' या कॉमा से अलग करके। जैसे: 'मैं 35, बेटी 8, ससुर 68'। पूरा होने पर 'बस' बोलिए।",
        "fam_need_one": "कृपया कम से कम एक सदस्य के बारे में बताइए। जैसे: 'मैं 35'।",
        "fam_retry": "मैं समझ नहीं पाई। सदस्य और उम्र बताइए, जैसे 'बेटी 8', या 'बस' बोलिए।",
        "more_n": "+{n} और", "fam_more": "अब तक {n} सदस्य जुड़े हैं। और कोई है? उसके बारे में बताइए, या 'बस' बोलिए।",
        "fam_add": "ठीक है, अगले सदस्य के बारे में बताइए।",
        "fam_gender_self": "क्या आप महिला हैं या पुरुष?", "fam_gender": "{label} महिला/लड़की हैं या पुरुष/लड़का?",
        "fam_age_self": "आपकी उम्र कितनी है?", "fam_age": "{label} की उम्र कितनी है?",
        "fam_preg_self": "क्या आप अभी गर्भवती हैं या बच्चे को दूध पिला रही हैं? हाँ या नहीं बोलें।",
        "fam_preg": "क्या {label} अभी गर्भवती हैं या बच्चे को दूध पिला रही हैं? हाँ या नहीं बोलें।",
        "fam_title": "पूरे परिवार की जाँच का नतीजा:", "fam_whole": "पूरे परिवार के लिए",
        "fam_none": "कोई योजना नहीं मिली; कार्यालय में पूछें", "age_word": "आयु",
        "sms_head": "योजना साथी", "sms_confirm": "अंतिम पुष्टि कार्यालय में।", "helpline": "हेल्पलाइन",
    },
    "en": {
        "hello": "Namaste! I am Yojana Saathi. Say the name of a scheme, or say 'family' to check the whole family.",
        "list": "I can tell you about: {names}. Which one would you like?",
        "not_understood": "Sorry, I could not recognise that scheme. ",
        "benefit": "Benefit", "docs": "Documents needed", "how": "How to apply",
        "offer": "Shall I check if you are eligible for this scheme? Say yes or no.",
        "retry": "I did not understand. ",
        "eligible": "Good news! You look eligible for {name}.",
        "not_eligible": "You do not look eligible for {name} right now, because: {reasons}.",
        "bring": "Bring", "goto": "Go to",
        "declined": "Okay. You can ask me about another scheme.",
        "family_hint": "To check the whole family, say 'family'.",
        "disclaimer": "This is for guidance only. Please confirm at your panchayat/block office or CSC.",
        "join": ", ",
        "fam_intro": "Okay, let us check the whole family. Tell me who each person is and their age, separated by 'and' or commas. For example: 'myself 35, daughter 8, father-in-law 68'. Say 'done' when finished.",
        "fam_need_one": "Please tell me about at least one person. For example: 'myself 35'.",
        "fam_retry": "I did not understand. Tell me who and their age, like 'daughter 8', or say 'done'.",
        "more_n": "+{n} more", "fam_more": "{n} person(s) added so far. Anyone else? Tell me about them, or say 'done'.",
        "fam_add": "Okay, tell me about the next person.",
        "fam_gender_self": "Are you a woman or a man?", "fam_gender": "Is {label} a woman/girl or a man/boy?",
        "fam_age_self": "How old are you?", "fam_age": "How old is {label}?",
        "fam_preg_self": "Are you pregnant or breastfeeding now? Say yes or no.",
        "fam_preg": "Is {label} pregnant or breastfeeding now? Say yes or no.",
        "fam_title": "Family check results:", "fam_whole": "For the whole family",
        "fam_none": "no scheme matched; please ask at your office", "age_word": "age",
        "sms_head": "Yojana Saathi", "sms_confirm": "Confirm at the office.", "helpline": "Helpline",
    },
}


# ---------------------------------------------------------------- text helpers
def load_glossary(path=GLOSSARY_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return dict(json.load(f).get("words", {}))
    except FileNotFoundError:
        return {}


GLOSSARY = load_glossary()


def normalize(text: str) -> str:
    return " ".join(text.lower().translate(_DIGITS).translate(_PUNCT).split())


def prepare(text: str, use_glossary: bool = True) -> str:
    t = normalize(text)
    if use_glossary and GLOSSARY:
        t = " ".join(GLOSSARY.get(tok, tok) for tok in t.split())
    return t


# Romanised Hindi ("Hinglish") words that are NOT ordinary English words
HINGLISH = {"kya", "hai", "hain", "chahiye", "chahie", "mujhe", "mere", "meri", "mera", "kaise", "kaisey", "kahan", "kab",
            "kitna", "kitne", "yojana", "paisa", "paise", "ghar", "beti", "beta", "nahi", "nahin", "haan", "aur", "liye",
            "batao", "bataiye", "milega", "milegi", "banega", "karna", "hoga", "apna", "aapka", "aap", "kuch", "parivar",
            "pariwar", "bachcha", "bacche", "bachche", "mahila", "mein", "hum", "humare", "hamare", "sarkari", "kaun"}
EN_WORDS = {"the", "is", "are", "how", "what", "where", "when", "why", "who", "i", "my", "for", "can", "want", "need", "get",
            "do", "does", "to", "of", "and", "a", "an", "about", "tell", "me", "please", "apply", "scheme", "eligible",
            "family", "which", "have", "has", "am", "we", "our", "you", "your", "with", "from", "myself"}


def detect_lang(text: str) -> str:
    """Script-based guess: any Devanagari letter means Hindi/Chhattisgarhi, otherwise English."""
    return "hi" if any("\u0900" <= ch <= "\u097f" for ch in text) else "en"


def decide_lang(text: str, last_lang: str = "hi", turns: int = 0, pending: bool = False) -> str:
    """Pick the reply language.
    Devanagari -> Hindi. Romanised Hindi ("mujhe gas chahiye") -> Hindi. Clear English -> English.
    Very short Latin answers ("30", "haan", "ration") keep the language of the conversation, so it does not flip."""
    if not text.strip():
        return last_lang
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi"
    if pending:
        return last_lang
    toks = normalize(text).split()
    if any(t in HINGLISH for t in toks):
        return "hi"
    if any(t in EN_WORDS for t in toks) or len(toks) >= 3:
        return "en"
    return last_lang if turns > 0 else "en"


def load_kb(path=KB_PATH):
    with open(path, encoding="utf-8") as f:
        return {s["id"]: s for s in json.load(f)["schemes"]}


def find_scheme(text: str, kb: dict, use_glossary: bool = True) -> Optional[str]:
    t = prepare(text, use_glossary)
    best, best_score = None, 0
    for sid, s in kb.items():
        score = sum(len(k) for k in s["keywords"] if normalize(k) in t)
        if score > best_score:
            best, best_score = sid, score
    return best


def parse_bool(text: str) -> Optional[bool]:
    n = prepare(text)
    if any(normalize(u) in n for u in UNSURE):
        return None
    toks = set(n.split())
    y, no = bool(toks & YES), bool(toks & NO)
    if y == no:
        return None
    return y


def parse_int(text: str, lo: int = 0, hi: int = 110) -> Optional[int]:
    toks = prepare(text).split()
    for tok in toks:
        if tok.isdigit() and lo <= int(tok) <= hi:
            return int(tok)
    for i, tok in enumerate(toks):
        if tok in NUM_WORDS:
            if tok == "एक" and not (i + 1 < len(toks) and toks[i + 1] in _YEAR_WORDS):
                continue   # "एक बेटी" (a daughter) is not the number 1
            if lo <= NUM_WORDS[tok] <= hi:
                return NUM_WORDS[tok]
    return None


def parse_gender(text: str) -> Optional[str]:
    toks = set(prepare(text).split())
    f, m = bool(toks & FEMALE_W), bool(toks & MALE_W)
    if f == m:
        return None
    return "F" if f else "M"


def is_done(text: str) -> bool:
    n = prepare(text)
    return bool(set(n.split()) & DONE) or any(normalize(p) in n for p in DONE_PHRASES)


def parse_members(text: str) -> list:
    """'myself 35, daughter 8 and father in law 68' -> list of member dicts."""
    out = []
    for seg in re.split(r"[,;\n]+|\s+(?:and|aur|और|तथा)\s+", text):
        if not seg.strip():
            continue
        toks = prepare(seg).split()
        hit = next((t for t in toks if t in WORD2REL), None)
        rel = WORD2REL[hit] if hit else None
        age = parse_int(seg)
        gender = parse_gender(seg)
        if rel is None and age is None and gender is None:
            continue
        if rel is None:
            rel = ("person", "Person", "व्यक्ति", None, [])
        lab_en, lab_hi = rel[1], rel[2]
        if hit in LABEL_OVERRIDE:
            lab_en, lab_hi = LABEL_OVERRIDE[hit]
        elif rel[0] in ("father", "mother") and "law" in toks:
            lab_en += "-in-law"
        out.append({"rel": rel[0], "label_en": lab_en, "label_hi": lab_hi,
                    "gender": gender or rel[3], "age": age, "pregnant": None})
    return out


def evaluate(scheme: dict, profile: dict):
    """Return (status, unmet_rules, missing_fields). Fixed rules only, no AI."""
    unmet, missing = [], []
    for r in scheme["rules"]:
        f = r["field"]
        if f not in profile or profile[f] is None:
            missing.append(f)
            continue
        v = profile[f]
        if r["op"] == "gte":
            ok = v >= r["value"]
        elif r["op"] == "lte":
            ok = v <= r["value"]
        else:
            ok = v == r["value"]
        if not ok:
            unmet.append(r)
    status = "not_eligible" if unmet else ("unknown" if missing else "eligible")
    return status, unmet, missing


def _dedupe(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_sms(lang: str, names: list, docs: list, where: list, limit: int = 320) -> str:
    """Short SMS text. Note: Hindi (Unicode) SMS fits only ~70 characters per message, so keep it brief."""
    m = MSG[lang]
    shown = names[:3]
    extra = f" {m['more_n'].format(n=len(names) - 3)}" if len(names) > 3 else ""
    parts = [m["sms_head"] + ": " + ", ".join(shown) + extra + ".",
             m["bring"] + ": " + ", ".join(docs[:4]) + ".",
             m["goto"] + ": " + ", ".join(where[:2]) + ".", m["sms_confirm"]]
    if HELPLINE:
        parts.append(f"{m['helpline']}: {HELPLINE}")
    sms = " ".join(parts)
    return sms if len(sms) <= limit else sms[: limit - 1].rstrip() + "\u2026"


# ---------------------------------------------------------------- session / reply
@dataclass
class Session:
    scheme_id: Optional[str] = None
    profile: dict = field(default_factory=dict)
    pending: Optional[str] = None
    lang: str = "hi"
    members: list = field(default_factory=list)
    household: dict = field(default_factory=dict)
    fam_more_done: bool = False
    turns: int = 0


@dataclass
class Reply:
    text: str
    lang: str
    scheme_id: Optional[str] = None
    sms: Optional[str] = None
    docs: list = field(default_factory=list)
    where: list = field(default_factory=list)
    outcome: Optional[dict] = None   # anonymous result for logging / dashboard


class Assistant:
    def __init__(self, kb=None):
        self.kb = kb or load_kb()

    # ---------- helpers
    def _names(self, lang):
        return MSG[lang]["join"].join(s["name_" + lang] for s in self.kb.values())

    def _summary(self, s, lang):
        m = MSG[lang]
        parts = [s["name_" + lang], f"{m['benefit']}: {s['benefit_' + lang]}",
                 f"{m['docs']}: {', '.join(s['documents_' + lang])}", f"{m['how']}: {s['how_' + lang]}"]
        if s.get("note_" + lang):
            parts.append(s["note_" + lang])
        return "\n".join(parts)

    def expects(self, sess: Session) -> Optional[str]:
        """What kind of answer is pending: bool / int / gender / members / None (used by the phone server)."""
        p = sess.pending
        if not p:
            return None
        if p == "_consent":
            return "bool"
        if p in FIELD_TYPE:
            return FIELD_TYPE[p]
        kind = p.split(":")[0]
        return {"fam_gender": "gender", "fam_age": "int", "fam_preg": "bool", "fam_house": "bool",
                "fam_more": "bool", "fam_collect": "members"}.get(kind)

    # ---------- single scheme
    def _next_question(self, sess, lang):
        _, _, missing = evaluate(self.kb[sess.scheme_id], sess.profile)
        if missing:
            sess.pending = missing[0]
            return QUESTIONS[missing[0]][lang]
        return None

    def _verdict(self, sess, lang) -> Reply:
        s, m = self.kb[sess.scheme_id], MSG[lang]
        status, unmet, _ = evaluate(s, sess.profile)
        sess.pending = None
        outcome = {"mode": "single", "schemes_checked": [s["id"]], "members": 1,
                   "eligible": [s["id"]] if status == "eligible" else [],
                   "unmet": [r["field"] for r in unmet]}
        if status == "eligible":
            docs, where = list(s["documents_" + lang]), [s["where_" + lang]]
            body = (m["eligible"].format(name=s["name_" + lang]) + "\n"
                    + f"{m['bring']}: {', '.join(docs)}\n{m['goto']}: {where[0]}")
            sms = build_sms(lang, [s["name_" + lang]], docs, where)
        else:
            reasons = m["join"].join(r["label_" + lang] for r in unmet)
            body, docs, where, sms = m["not_eligible"].format(name=s["name_" + lang], reasons=reasons), [], [], None
        body += "\n" + m["family_hint"] + "\n" + m["disclaimer"]
        return Reply(body, lang, s["id"], sms, docs, where, outcome)

    # ---------- family
    def _start_family(self, sess, lang) -> Reply:
        sess.members, sess.household, sess.fam_more_done, sess.pending = [], {}, False, "fam_collect"
        return Reply(MSG[lang]["fam_intro"], lang)

    def _add_members(self, sess, new):
        for mem in new:
            same = [x for x in sess.members if x["rel"] == mem["rel"]]
            if same:
                mem["label_en"] += f" {len(same) + 1}"
                mem["label_hi"] += f" {len(same) + 1}"
            sess.members.append(mem)

    def _family_needs(self, f):
        return any(r["field"] == f for s in self.kb.values() for r in s["rules"])

    def _fam_next(self, sess, lang) -> Reply:
        m = MSG[lang]
        for i, mem in enumerate(sess.members):
            lab = mem["label_" + lang]
            if mem["gender"] is None:
                sess.pending = f"fam_gender:{i}"
                return Reply(m["fam_gender_self"] if mem["rel"] == "self" else m["fam_gender"].format(label=lab), lang)
            if mem["age"] is None:
                sess.pending = f"fam_age:{i}"
                return Reply(m["fam_age_self"] if mem["rel"] == "self" else m["fam_age"].format(label=lab), lang)
        if not sess.fam_more_done:
            sess.pending = "fam_more"
            return Reply(m["fam_more"].format(n=len(sess.members)), lang)
        for i, mem in enumerate(sess.members):
            if mem["pregnant"] is None:
                if mem["gender"] == "F" and 15 <= mem["age"] <= 49:
                    sess.pending = f"fam_preg:{i}"
                    lab = mem["label_" + lang]
                    return Reply(m["fam_preg_self"] if mem["rel"] == "self" else m["fam_preg"].format(label=lab), lang)
                mem["pregnant"] = False
        for f in HOUSEHOLD_FIELDS:
            if f not in sess.household and self._family_needs(f):
                sess.pending = f"fam_house:{f}"
                return Reply(QUESTIONS[f][lang], lang)
        return self._family_report(sess, lang)

    def _family_report(self, sess, lang) -> Reply:
        m = MSG[lang]
        sess.pending = None
        lines, per_person, household_ids = [m["fam_title"]], {}, []
        unmet_fields, checked = [], list(self.kb)
        for sid, s in self.kb.items():
            for idx, mem in enumerate(sess.members):
                prof = {"age": mem["age"], "gender": mem["gender"], "pregnant": mem["pregnant"], **sess.household}
                status, unmet, _ = evaluate(s, prof)
                if status == "eligible":
                    if s.get("level") == "household":
                        if sid not in household_ids:
                            household_ids.append(sid)
                    else:
                        per_person.setdefault(idx, []).append(sid)
                elif status == "not_eligible":
                    unmet_fields += [r["field"] for r in unmet]
        elig_all = []
        for idx, mem in enumerate(sess.members):
            ids = per_person.get(idx, [])
            elig_all += ids
            names = m["join"].join(self.kb[i]["name_" + lang] for i in ids) or m["fam_none"]
            lines.append(f"- {mem['label_' + lang]} ({m['age_word']} {mem['age']}): {names}")
        if household_ids:
            lines.append(f"- {m['fam_whole']}: " + m["join"].join(self.kb[i]["name_" + lang] for i in household_ids))
        elig_all += household_ids
        elig_unique = _dedupe(elig_all)
        docs = _dedupe(d for i in elig_unique for d in self.kb[i]["documents_" + lang])
        where = _dedupe(self.kb[i]["where_" + lang] for i in elig_unique)
        sms = None
        if elig_unique:
            lines.append(f"{m['bring']}: {m['join'].join(docs)}")
            lines.append(f"{m['goto']}: {m['join'].join(where)}")
            sms = build_sms(lang, [self.kb[i]["name_" + lang] for i in elig_unique], docs, where)
        lines.append(m["disclaimer"])
        outcome = {"mode": "family", "schemes_checked": checked, "members": len(sess.members),
                   "eligible": elig_unique, "unmet": _dedupe(unmet_fields)}
        return Reply("\n".join(lines), lang, None, sms, docs, where, outcome)

    def _handle_family_pending(self, sess, text, lang) -> Optional[Reply]:
        m = MSG[lang]
        kind, _, arg = sess.pending.partition(":")
        if kind == "fam_collect":
            if is_done(text):
                if not sess.members:
                    return Reply(m["fam_need_one"], lang)
                sess.fam_more_done = True
                return self._fam_next(sess, lang)
            new = parse_members(text)
            if not new:
                return Reply(m["fam_retry"], lang)
            self._add_members(sess, new)
            return self._fam_next(sess, lang)
        if kind == "fam_more":
            b = parse_bool(text)
            if is_done(text) or b is False:
                sess.fam_more_done = True
                return self._fam_next(sess, lang)
            new = parse_members(text)
            if new:
                self._add_members(sess, new)
                return self._fam_next(sess, lang)
            return Reply(m["fam_add"] if b else m["fam_retry"], lang)
        i = int(arg) if arg.isdigit() else -1
        if kind == "fam_gender":
            g = parse_gender(text)
            if g:
                sess.members[i]["gender"] = g
                return self._fam_next(sess, lang)
        elif kind == "fam_age":
            a = parse_int(text)
            if a is not None:
                sess.members[i]["age"] = a
                return self._fam_next(sess, lang)
        elif kind == "fam_preg":
            b = parse_bool(text)
            if b is not None:
                sess.members[i]["pregnant"] = b
                return self._fam_next(sess, lang)
        elif kind == "fam_house":
            b = parse_bool(text)
            if b is not None:
                sess.household[arg] = b
                return self._fam_next(sess, lang)
        return None

    # ---------- main entry
    def handle(self, session: Session, text: str, lang: Optional[str] = None) -> Reply:
        if lang is None:
            lang = decide_lang(text, session.lang, session.turns, bool(session.pending))
        session.lang = lang
        if text.strip():
            session.turns += 1
        m = MSG[lang]
        norm = prepare(text)
        wants_family = any(normalize(w) in norm for w in FAMILY_WORDS)

        if session.pending:
            if session.pending.startswith("fam_"):
                r = self._handle_family_pending(session, text, lang)
                if r:
                    return r
                return Reply(m["retry"] + self._reask(session, lang), lang)
            if session.pending == "_consent":
                ans = parse_bool(text)
                if ans is True:
                    q = self._next_question(session, lang)
                    return Reply(q, lang, session.scheme_id) if q else self._verdict(session, lang)
                if ans is False:
                    session.pending = None
                    return Reply(m["declined"], lang, session.scheme_id)
            else:
                f = session.pending
                t = FIELD_TYPE[f]
                val = parse_int(text) if t == "int" else parse_gender(text) if t == "gender" else parse_bool(text)
                if val is not None:
                    session.profile[f] = val
                    session.pending = None
                    q = self._next_question(session, lang)
                    return Reply(q, lang, session.scheme_id) if q else self._verdict(session, lang)
            other = find_scheme(text, self.kb)
            if other is None and not wants_family:
                return Reply(m["retry"] + (QUESTIONS[session.pending][lang] if session.pending in QUESTIONS else m["offer"]),
                             lang, session.scheme_id)
            session.pending = None

        if wants_family:
            return self._start_family(session, lang)

        sid = find_scheme(text, self.kb)
        if sid:
            session.scheme_id, session.profile, session.pending = sid, {}, "_consent"
            return Reply(self._summary(self.kb[sid], lang) + "\n\n" + m["offer"], lang, sid)

        if any(normalize(w) in norm for w in LIST_WORDS) or not norm:
            return Reply(m["hello"] + " " + m["list"].format(names=self._names(lang)), lang)
        return Reply(m["not_understood"] + m["list"].format(names=self._names(lang)), lang)

    def _reask(self, sess, lang):
        m, p = MSG[lang], sess.pending
        if p in QUESTIONS:
            return QUESTIONS[p][lang]
        kind, _, arg = p.partition(":")
        if kind in ("fam_gender", "fam_age", "fam_preg"):
            mem = sess.members[int(arg)]
            key = kind + ("_self" if mem["rel"] == "self" else "")
            return m[key].format(label=mem["label_" + lang])
        if kind == "fam_house":
            return QUESTIONS[arg][lang]
        if kind == "fam_more":
            return m["fam_more"].format(n=len(sess.members))
        return m["fam_intro"]
