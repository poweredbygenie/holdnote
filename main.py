#!/usr/bin/env python3
"""
HoldNote - Intake to Brief

Dana takes every new-client intake call personally, then rebuilds it that
evening into notes she can write a 30-second on-hold script from. This turns
that first stretch - the call and the write-up - into a structured brief
produced from one voice memo, so a new client starts from a draft instead of
a blank page and a phone call.

Friction point: scale - one owner, ~60 clients, referrals turned away.

BUILD PROVENANCE (RFP Section 4)
    Prepared before kickoff: only a generic Python environment (venv plus the
    openai, anthropic, and python-dotenv packages) and the challenge's public
    RFP. No project-specific code predates this repository's first commit, and
    none of this code is copied from a prior project - it was written from
    scratch for this build. The commit history is the record.

ONE OUTCOME (RFP Section 2)
    This concept targets exactly one outcome for HoldNote: REDUCED OWNER-TIME.
    It does NOT target increased revenue. Not both - exactly one. There is no
    upsell, pricing, packaging, or lead-generation path anywhere in this tool;
    the only lever is cutting the owner-hours each new client costs.

AUDIO & DATA PROVENANCE (RFP Section 6.3 - prohibited content)
    - No real client data. The business ("Bright Harbor Family Dental"), person
      ("Priya") and town ("Meridian") are invented. No real client name, phone
      number, or recording from an actual HoldNote client appears anywhere; the
      sample deliberately omits any phone number.
    - No cloned voices. The only audio file, samples/intake_sample.mp3, is
      synthetic speech from the built-in macOS `say` system voice "Samantha",
      generated from samples/intake_sample.txt. No human voice was recorded,
      sampled, or cloned, and this tool neither performs nor depends on voice
      cloning.
    - No copyrighted commercial audio. No music, no hold-music beds, no jingle,
      and no sound libraries without rights (none are used at all), including
      licensed, royalty-free, or stock material. The lone .mp3 is
      machine-generated text-to-speech with no third-party rights attached.
      See samples/README.md.
    - No secrets committed. API keys are read from the environment (.env, which
      is gitignored); only .env.example, with empty values, is committed.
    See GUARDRAILS.md for the full statement.

Usage:
    python main.py                       # uses samples/intake_sample.mp3
    python main.py path/to/intake.mp3

Output:
    out/brief.json   - the structured brief (the deliverable artifact)
    stdout           - a human-readable summary for Dana
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"
# Synthetic macOS `say` TTS of a fictional intake. No real client, no cloned
# voice, no music / hold-music bed / licensed sound library (RFP Section 6.3).
DEFAULT_AUDIO = ROOT / "samples" / "intake_sample.mp3"

TRANSCRIBE_MODEL = "whisper-1"
BRIEF_MODEL = "claude-sonnet-5"   # structured extraction; claude-opus-5 for higher quality
MANUAL_MINUTES = 40               # Dana's rough intake-call + write-up time per client today
OUTCOME = "reduced owner-time"    # RFP Section 2: exactly one outcome, not revenue, not both

# The shape of out/brief.json. This IS the machine-readable artifact (MR-2).
BRIEF_SCHEMA = {
    "business": {
        "name": "string or null",
        "industry": "string or null",
        "location": "string or null",
        "contact_name": "string or null",
        "phone": "string or null",
        "website": "string or null",
        "hours": "string or null",
    },
    "brand_voice": {
        "tone_words": ["string"],
        "audience": "string or null",
        "origin_story": "string or null",
        "signature_details": ["string  # the running joke, the thing regulars know"],
        "differentiators": ["string"],
    },
    "verbatim_quotes": [
        {"quote": "exact words from the transcript",
         "use_for": "why this line belongs in the script"}
    ],
    "must_be_accurate": [
        {"item": "string  # price, offer, hours, name, number",
         "value_heard": "string",
         "confidence": "high | medium | low"}
    ],
    "disclosures_mentioned": {
        "hold_time_notice": "true | false | null  (null = never came up)",
        "callback_offer": "true | false | null",
        "same_day_or_emergency": "true | false | null",
        "other": ["string"],
    },
    "needs_confirmation": [
        {"field": "string",
         "heard_as": "string  # quote or paraphrase of what was unclear",
         "why": "string  # caller hedged / corrected themselves / inaudible / inferred"}
    ],
    "not_captured": ["string  # standard brief items this intake did not cover"],
}

SYSTEM_PROMPT = f"""You are an intake assistant for HoldNote, a one-person studio that
writes and records the on-hold messages small businesses play to callers on their phone line.

You receive a rough transcript of a business owner describing their business the way they
would on an intake call. Turn it into a structured brief that Dana (the owner and writer)
will review and write a 30-second on-hold script from.

Rules:
- Use ONLY what the transcript says. Never invent a fact, number, name, or detail.
  If something is not mentioned, use null or an empty list.
- One exception: `tone_words` may be inferred - give 3 to 5 adjectives for how the
  owner speaks (word choice, warmth, formality). Every other field stays grounded
  in what was actually said.
- The most valuable material is the brand voice: the origin story, the running joke,
  the thing regulars know, the phrase the owner uses for themselves. Capture the best
  2 to 4 of these as EXACT quotes from the transcript in `verbatim_quotes`, so Dana
  writes from the owner's own words rather than a paraphrase.
- Anything a script must get exactly right - prices, offers, hours, names, phone
  numbers - goes in `must_be_accurate`, with the value as you heard it and a
  confidence of high, medium, or low.
- If the caller hedges, corrects themselves, trails off, or you had to infer a value,
  add an entry to `needs_confirmation`. Do not silently pick a value. Deciding what
  the caller meant is Dana's call, not yours.
- For each field in `disclosures_mentioned`: true if the caller wants it in the
  message, false if they explicitly said to leave it out, null if it never came up.
- In `not_captured`, list standard brief items a writer would want that this intake
  did not cover.

Respond with ONLY a JSON object in this shape. No prose, no code fence:
{json.dumps(BRIEF_SCHEMA, indent=2)}
"""


def require_env(name: str) -> None:
    if not os.environ.get(name):
        sys.exit(f"Missing {name}. Copy .env.example to .env and fill it in.")


def transcribe(path: Path):
    """Spoken intake -> text. Returns (transcript, duration_seconds|None)."""
    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY from the environment
    with open(path, "rb") as f:
        r = client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=f,
            response_format="verbose_json",
        )
    return r.text.strip(), getattr(r, "duration", None)


def build_brief(transcript: str) -> dict:
    """Transcript -> structured brief dict."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    r = client.messages.create(
        model=BRIEF_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Intake transcript:\n\n{transcript}"}],
        output_config={"effort": "low"},  # structured extraction; deep reasoning not needed
    )
    raw = next(b.text for b in r.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].removeprefix("json").strip()
    return json.loads(raw)


def print_summary(brief: dict) -> None:
    b = brief.get("business", {})
    meta = brief["meta"]
    line = "-" * 60
    print(f"\n{line}")
    print(f"  BRIEF  ({b.get('name') or 'business name not stated'})")
    print(line)
    print(f"  Industry     : {b.get('industry') or '-'}")
    print(f"  Location     : {b.get('location') or '-'}")
    print(f"  Hours        : {b.get('hours') or '-'}")
    print(f"  Tone         : {', '.join(brief.get('brand_voice', {}).get('tone_words', [])) or '-'}")

    quotes = brief.get("verbatim_quotes", [])
    print(f"\n  In their own words ({len(quotes)}):")
    for q in quotes:
        print(f"    “{q.get('quote', '').strip()}”")
        print(f"       -> {q.get('use_for', '').strip()}")

    accurate = brief.get("must_be_accurate", [])
    if accurate:
        print(f"\n  Get these exactly right:")
        for item in accurate:
            print(f"    [{item.get('confidence', '?'):>6}] {item.get('item')}: {item.get('value_heard')}")

    confirm = brief.get("needs_confirmation", [])
    print(f"\n  Dana should confirm before publishing ({len(confirm)}):")
    for c in confirm:
        print(f"    - {c.get('field')}: {c.get('why')}")

    print(f"\n{line}")
    print(f"  {meta['status']}")
    print(f"  Outcome targeted: {meta['target_outcome']} (one outcome, not revenue - RFP Section 2)")
    print(f"  Agent time: {meta['agent_seconds']}s   "
          f"Manual estimate: ~{meta['manual_estimate_minutes']} min   "
          f"Saved: ~{meta['time_saved_minutes_estimate']} min this intake")
    print(f"  Written to: {OUT_DIR / 'brief.json'}")
    print(f"{line}\n")


def main() -> None:
    load_dotenv(ROOT / ".env")
    require_env("OPENAI_API_KEY")
    require_env("ANTHROPIC_API_KEY")

    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AUDIO
    if not audio.exists():
        sys.exit(f"Audio file not found: {audio}")

    started = time.monotonic()
    print(f"-> Transcribing {audio.name} ...")
    transcript, duration = transcribe(audio)
    print(f"-> Structuring the brief ...")
    brief = build_brief(transcript)
    elapsed = round(time.monotonic() - started, 1)

    brief["meta"] = {
        "status": ("DRAFT - for Dana's review. Not client-facing. Dana writes the "
                   "final script and records every voiceover."),
        "target_outcome": OUTCOME,          # RFP Section 2: exactly one - not revenue, not both
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_audio": audio.name,
        "audio_seconds": round(duration) if duration else None,
        "agent_seconds": elapsed,
        "manual_estimate_minutes": MANUAL_MINUTES,
        "time_saved_minutes_estimate": round(MANUAL_MINUTES - elapsed / 60, 1),
    }
    brief["transcript"] = transcript

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n")
    print_summary(brief)


if __name__ == "__main__":
    main()
