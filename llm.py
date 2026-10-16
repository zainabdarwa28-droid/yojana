"""OPTIONAL: rewrite an already-correct answer in simpler words. Off by default.

The AI never decides eligibility or invents facts: it only receives our verified answer text and must keep every
number, scheme name and step unchanged. If anything fails, the original text is returned.
Set ANTHROPIC_API_KEY and (optionally) YOJANA_MODEL, then: pip install anthropic
"""
import os


def simplify(text: str, lang: str = "hi") -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return text
    try:
        import anthropic
        client = anthropic.Anthropic()
        language = "simple spoken Hindi" if lang == "hi" else "very simple English"
        resp = client.messages.create(
            model=os.getenv("YOJANA_MODEL", "claude-sonnet-5-5"),
            max_tokens=600,
            system=(f"Rewrite the user's message in {language} for a woman with low literacy. Keep short sentences. "
                    "Do NOT add, remove or change any fact, number, scheme name, document or step. "
                    "Output only the rewritten text."),
            messages=[{"role": "user", "content": text}],
        )
        out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return out or text
    except Exception:
        return text
