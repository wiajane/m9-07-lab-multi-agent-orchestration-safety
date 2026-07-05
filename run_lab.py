import asyncio
import json
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from pipeline import build_pipeline, notes_to_prompt, screen_notes

APP_NAME = "orchestrate_then_defend"
USER_ID = "student"


def load_notes(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


async def run_once(notes: list[dict], guarded: bool, label: str) -> dict:
    """Runs the pipeline once and returns {agent_name: final_text}."""
    pipeline = build_pipeline(guarded=guarded)
    runner = InMemoryRunner(agent=pipeline, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    message = types.Content(
        role="user", parts=[types.Part(text=notes_to_prompt(notes))]
    )

    outputs: dict[str, str] = {}
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts)
            outputs[event.author] = text

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    for agent_name, text in outputs.items():
        print(f"\n--- {agent_name} output ---\n{text.strip()}")
    return outputs


async def run_mode(mode: str):
    clean_notes = [n for n in load_notes("notes.json") if n["id"] != "note-3"]
    full_notes = load_notes("notes.json")

    if mode in ("clean", "all"):
        await run_once(clean_notes, guarded=False, label="1) CLEAN NOTES (sanity check, no guardrail needed)")

    if mode in ("poisoned", "all"):
        await run_once(full_notes, guarded=False, label="2) BEFORE: full notes.json, UNGUARDED -> attack should land")

    if mode in ("defended", "all"):
        await run_once(full_notes, guarded=True, label="3) AFTER: full notes.json, GUARDED (Approach A: instruction-level)")

    if mode in ("defended2", "all"):
        screened, flagged = screen_notes(full_notes)
        print(f"\n[screen] flagged note ids: {flagged}")
        await run_once(screened, guarded=True, label="4) AFTER: full notes.json, screened (B) + guarded (A) -- defense in depth")

    if mode in ("stretch", "all"):
        try:
            stretch_notes = load_notes("notes_injection2.json")
        except FileNotFoundError:
            print("\n[stretch] notes_injection2.json not found, skipping")
            return
        screened, flagged = screen_notes(stretch_notes)
        print(f"\n[screen] flagged note ids in 2nd injection: {flagged}")
        await run_once(stretch_notes, guarded=False, label="5) STRETCH BEFORE: 2nd injection, UNGUARDED")
        await run_once(screened, guarded=True, label="6) STRETCH AFTER: 2nd injection, screened + guarded")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    valid = {"clean", "poisoned", "defended", "defended2", "stretch", "all"}
    if mode not in valid:
        print(f"Unknown mode '{mode}'. Choose from: {sorted(valid)}")
        sys.exit(1)
    asyncio.run(run_mode(mode))
