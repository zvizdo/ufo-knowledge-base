#!/usr/bin/env python3
"""
bulk_import.py — Batch-import all transcripts into the UFO knowledge base.

- Processes transcripts sequentially from transcripts/
- Skips missing.md (meta file listing unavailable transcripts)
- Retries each import up to MAX_RETRIES times on failure, then skips
- Runs /kb-maintain every MAINTAIN_EVERY successful imports
- Runs /kb-maintain once more at the very end
- Resumes automatically from where it left off (checks import_log.json)
- Writes a full log to import_log.json

Usage:
    python bulk_import.py            # run / resume
    python bulk_import.py --reset    # wipe log and start fresh
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

KB_DIR = Path("/Users/anzekravanja/Projects/ufo-knowledge-base")
TRANSCRIPTS_DIR = KB_DIR / "transcripts"
LOG_FILE = KB_DIR / "import_log.json"

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
MAINTAIN_EVERY = 5
TIMEOUT_IMPORT = 2000   # 15 min — large transcripts spawn many wiki pages
TIMEOUT_MAINTAIN = 5000  # 10 min

SKIP_FILES = {"missing.md"}


# ── Log helpers ───────────────────────────────────────────────────────────────

def load_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return {
        "started_at": datetime.now().isoformat(),
        "last_updated": None,
        "processed": {},
        "maintain_runs": [],
    }


def save_log(log: dict) -> None:
    log["last_updated"] = datetime.now().isoformat()
    LOG_FILE.write_text(json.dumps(log, indent=2))
    print(f"    [log saved → {LOG_FILE.name}]")


# ── Claude CLI helpers ────────────────────────────────────────────────────────

def run_claude(prompt: str, timeout: int) -> tuple[bool, str]:
    """Invoke `claude -p <prompt>` and return (success, full_output)."""
    cmd = [
        "claude",
        "-p", prompt,
        "--model", MODEL,
        "--dangerously-skip-permissions",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(KB_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = result.stdout
        if result.stderr.strip():
            combined += "\n[STDERR]\n" + result.stderr
        return result.returncode == 0, combined
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: process did not finish within {timeout}s"
    except FileNotFoundError:
        sys.exit("ERROR: `claude` binary not found on PATH. Is Claude Code CLI installed?")
    except Exception as exc:
        return False, f"EXCEPTION: {exc}"


# ── Core actions ──────────────────────────────────────────────────────────────

def import_transcript(transcript: Path, log: dict) -> bool:
    """Try to import one transcript. Returns True on success."""
    name = transcript.name
    rel_path = f"transcripts/{name}"

    print(f"\n{'─' * 62}")
    print(f"  IMPORT  {name}")
    print(f"{'─' * 62}")

    last_output = ""
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Attempt {attempt}/{MAX_RETRIES} …")
        prompt = f"/kb-import {rel_path} - YouTube Transcript"
        success, output = run_claude(prompt, TIMEOUT_IMPORT)
        last_output = output

        tail = output[-300:].strip().replace("\n", " ↵ ")
        if success:
            print(f"  ✓  Success")
            log["processed"][name] = {
                "status": "success",
                "attempts": attempt,
                "completed_at": datetime.now().isoformat(),
                "output_tail": output[-3000:],
            }
            save_log(log)
            return True
        else:
            print(f"  ✗  Failed — {tail}")
            if attempt < MAX_RETRIES:
                print(f"  ↻  Retrying …")

    print(f"  ✗  All {MAX_RETRIES} attempts failed. Skipping.")
    log["processed"][name] = {
        "status": "failed",
        "attempts": MAX_RETRIES,
        "completed_at": datetime.now().isoformat(),
        "output_tail": last_output[-3000:],
    }
    save_log(log)
    return False


def run_maintain(log: dict, label: str) -> None:
    print(f"\n{'═' * 62}")
    print(f"  KB-MAINTAIN  ({label})")
    print(f"{'═' * 62}")
    success, output = run_claude("/kb-maintain Go through all the steps, report back what you did at each steps. You are allowed to make changes without my permission.", TIMEOUT_MAINTAIN)
    status = "success" if success else "failed"
    tail = output[-300:].strip().replace("\n", " ↵ ")
    print(f"  {'✓' if success else '✗'}  kb-maintain {status} — {tail}")
    log["maintain_runs"].append({
        "label": label,
        "status": status,
        "run_at": datetime.now().isoformat(),
        "output_tail": output[-3000:],
    })
    save_log(log)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-import transcripts into UFO KB")
    parser.add_argument("--reset", action="store_true", help="Wipe import_log.json and start fresh")
    parser.add_argument("--retry-failed", action="store_true", help="Re-attempt files that previously failed (default: skip them)")
    args = parser.parse_args()

    if args.reset and LOG_FILE.exists():
        LOG_FILE.unlink()
        print("Log wiped — starting fresh.\n")

    all_transcripts = sorted(
        f for f in TRANSCRIPTS_DIR.glob("*.md")
        if f.name not in SKIP_FILES
    )

    log = load_log()
    succeeded = {k for k, v in log["processed"].items() if v["status"] == "success"}
    failed    = {k for k, v in log["processed"].items() if v["status"] == "failed"}

    if args.retry_failed:
        skip_set = succeeded                  # retry failures, skip only successes
    else:
        skip_set = succeeded | failed         # skip everything already attempted

    pending = [t for t in all_transcripts if t.name not in skip_set]

    print("=" * 62)
    print("  UFO KB — Bulk Import")
    print("=" * 62)
    print(f"  Total transcripts : {len(all_transcripts)}")
    print(f"  Already imported  : {len(succeeded)}")
    print(f"  Previously failed : {len(failed)}  {'(will retry)' if args.retry_failed else '(skipped — use --retry-failed to re-run)'}")
    print(f"  To process        : {len(pending)}")
    print(f"  Model             : {MODEL}")
    print(f"  Retries per file  : {MAX_RETRIES}")
    print(f"  Maintain every    : {MAINTAIN_EVERY} successful imports")
    print(f"  Log file          : {LOG_FILE}")
    print("=" * 62)

    if not pending:
        print("\nNothing left to import.")
        run_maintain(log, label="final (already complete)")
        return

    success_since_last_maintain = 0

    for i, transcript in enumerate(pending, start=1):
        total_done = len(succeeded) + i - 1
        print(f"\n[{i}/{len(pending)}]  (total done: {total_done})")

        ok = import_transcript(transcript, log)
        if ok:
            success_since_last_maintain += 1

        if success_since_last_maintain >= MAINTAIN_EVERY:
            run_maintain(
                log,
                label=f"after {len(succeeded) + i} total imports"
            )
            success_since_last_maintain = 0

    # Final maintenance pass
    run_maintain(log, label="final")

    # ── Summary ──
    final = load_log()
    n_ok = sum(1 for v in final["processed"].values() if v["status"] == "success")
    n_fail = sum(1 for v in final["processed"].values() if v["status"] == "failed")
    failed_files = [k for k, v in final["processed"].items() if v["status"] == "failed"]

    print(f"\n{'=' * 62}")
    print(f"  DONE")
    print(f"  Successful imports : {n_ok}")
    print(f"  Failed imports     : {n_fail}")
    print(f"  kb-maintain runs   : {len(final['maintain_runs'])}")
    print(f"  Log                : {LOG_FILE}")
    if failed_files:
        print(f"\n  Failed files (check output_tail in log):")
        for f in failed_files:
            print(f"    • {f}")
    print("=" * 62)


if __name__ == "__main__":
    main()
