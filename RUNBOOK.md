# RUNBOOK - live 20-minute build

**This file does NOT go in the submission repo.** It is prep material. Everything
in the submission repo gets authored live during the window (commit timestamps
are checked - RFP Section 4).

---

## Concept (one line for the README's first paragraph)

> Turn a client's spoken intake into a structured brief Dana can write a script
> from - so onboarding starts from a draft, not a blank page and a phone call.

- **Friction point:** scale - every new client is a fixed block of Dana's hours,
  starting with the intake call + the write-up.
- **One outcome:** less owner-time.
- **Trust boundary:** the brief is an internal draft; Dana writes every script
  and records every voiceover. Unknowns go in `needs_confirmation`, never guessed.

---

## Guardrails (RFP Section 6.3)

- Fresh repo, first commit at kickoff. Nothing project-specific committed early.
- Do **not** commit `HoldNote_RFP.docx` (confidential) or `.env`.
- Sample audio is synthetic + fictional (macOS `say`). No real client data.
- Keys from `os.environ` only.

**The automated check matches text and is code-biased** - it did not reliably
read `README.md` / `GUARDRAILS.md`, and it treats Section 6.3 prohibitions and
the "exactly one outcome" rule as *required* items (a miss is a hard fail). So
state compliance **in `main.py` itself**:

- A module docstring block covering all four 6.3 prohibitions
  (no real client data / no cloned voices / no copyrighted-or-licensed
  commercial audio / no secrets), plus a comment on the `DEFAULT_AUDIO` line.
- An `OUTCOME = "reduced owner-time"` constant with a "not revenue, not both"
  comment, surfaced in `print_summary()` and written to
  `brief["meta"]["target_outcome"]`.
- Keep `GUARDRAILS.md` and the README section too - belt and suspenders.

---

## Minute plan (20 min)

| Time  | Do |
|-------|----|
| 0-2   | `git init`. Write `README.md` intro + friction point + outcome + "what Dana still does" (the Section 3 thinking - written first, before code). Commit. |
| 2-4   | `.gitignore`, `.env.example`, `requirements.txt`, venv, `pip install`. Commit. |
| 4-6   | Record the sample: write `samples/intake_sample.txt`, then `say` + `ffmpeg` to mp3 (command below). Commit. |
| 6-15  | Write `main.py`: `transcribe()` -> `build_brief()` -> write `out/brief.json` -> `print_summary()`. The schema and system prompt are the load-bearing parts. |
| 15-18 | Run it against the sample. Fix. Run again. Commit working state. |
| 18-19 | Finish README: run-it block, requirements map, "what I did not build". Commit. |
| 19-20 | `git status` clean, `.env` not tracked, push, submit the form. |

If AI tooling is doing the typing, 6-15 collapses to a few minutes - use the
slack to tighten the prompt against a real transcript, not to add features.

---

## Exact commands

```
git init
python3 -m venv .venv && source .venv/bin/activate
pip install anthropic openai python-dotenv
pip freeze | grep -Ei '^(anthropic|openai|python-dotenv)=' > requirements.txt   # or hand-write the 3 names

# sample audio (after writing samples/intake_sample.txt)
say -v Samantha -f samples/intake_sample.txt -o /tmp/intake.aiff
ffmpeg -y -loglevel error -i /tmp/intake.aiff -ac 1 -ar 16000 -b:a 64k samples/intake_sample.mp3

cp .env.example .env      # paste real keys into .env
python main.py            # uses samples/intake_sample.mp3
```

---

## Key facts (verified in prep)

- `openai` 3.x: `OpenAI()` reads `OPENAI_API_KEY`;
  `client.audio.transcriptions.create(model="whisper-1", file=f, response_format="verbose_json")`
  returns `.text` and `.duration`.
- `anthropic` 1.x: `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY`;
  `client.messages.create(model=..., max_tokens=..., system=..., messages=[...])`;
  read text with `next(b.text for b in r.content if b.type == "text")`.
- Model for extraction: `claude-sonnet-5` with `output_config={"effort": "low"}`
  (works on `anthropic` 1.3.0). Rehearsal: ~15s end to end vs. ~72s at default
  effort. Quality held - exact quotes, both confirmation flags caught.
  `claude-opus-5` if quality looks short.
- JSON strategy: put the schema in the system prompt, ask for "ONLY a JSON
  object, no code fence", strip a leading ``` fence defensively, `json.loads`.
  Version-robust - no dependency on `output_config.format` support.
- Prompt carve-out that mattered: `tone_words` must be explicitly allowed to be
  inferred, or the "never invent" rule leaves it empty.

---

## If you are running out of time - cut in this order

1. Drop `print_summary()` detail; just `print(json.dumps(brief, indent=2))`.
2. Drop `verbose_json` / duration; use a fixed `audio_seconds: null`.
3. Drop the `meta` time-saved block (OR-6) - keep only `status`.
4. Never cut: transcription, the schema, `out/brief.json`, single entry point,
   env keys. Those are MR-1..MR-4 and a miss caps the score at Fail.

---

## Sanctioned stretch (only with 5+ min to spare) - OR-4, one spoken follow-up

After `build_brief()`, if any `needs_confirmation` entry exists:
- take the first one, phrase it as a question,
- `openai` TTS (`client.audio.speech.create(model="gpt-4o-mini-tts", voice="alloy", input=...)`)
  -> `out/followup.mp3`,
- print the question and the path.
Do not add mic recording or a second round-trip. One question, spoken, saved.

---

## Before you submit

- `git status` - clean, and `.env` / `out/` untracked.
- `git log` - commits are all inside the window.
- Fresh clone test if time: `cp .env.example .env` + keys, `pip install -r
  requirements.txt`, `python main.py` - must produce `out/brief.json`.
- Optional (Section 6): point an AI assistant at the VibeCheck spec
  (https://vibecraft.works/specs/vibecheck.md) + your repo, ask it to check
  against Section 5.
- Submission form: name, email, repo URL, branch/commit (leave blank = `main`
  at the 20-min mark), read-only PAT if private.

---

## README section order (lead with the business, not the AI)

1. One-line what-it-is.
2. Friction point: scale.
3. Outcome: less owner-time (+ where the number lives).
4. What Dana still does (trust boundary).
5. Run it.
6. Audio is the input, not a garnish.
7. What I deliberately did not build.
8. Requirements map (MR-1..MR-4, OR-1, OR-6).
