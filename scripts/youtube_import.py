#!/usr/bin/env python3
"""
youtube_import.py — Unified YouTube transcript ingestion for the UFO KB.

Three subcommands:

  fetch <URL_OR_ID>             Stage one transcript:
                                  - resolve to canonical 11-char video ID
                                  - check off-topic-skipped registry
                                  - check idempotency (raw / staging / wiki)
                                  - pull metadata via `yt-dlp -J`
                                  - download captions (manual first, auto fallback)
                                  - convert WebVTT to clean prose
                                  - write transcripts/<id>.md with prefilled YAML frontmatter

  fetch --batch <FILE_OR_URL>   Stage many. <arg> is either:
                                  - a YouTube playlist URL (yt-dlp expands it), or
                                  - a path to a text file with one URL/ID per line
                                    (blank lines + lines starting with `#` are skipped)

  run-imports [--reset]         Run /kb-import on each file in transcripts/.
                                Uses Claude CLI session resume so the model context
                                (skill prompts, prior work) is reused across files
                                instead of reloading per call.
                                Flags:
                                  --reset            wipe import_log.json first
                                  --retry-failed     re-attempt previously failed files
                                  --new-session      force a fresh Claude session

  clean <FILE>                  Run the legacy clean_transcript.py logic on an existing
                                transcript .md (collapses VTT-residue blank lines).
                                Most users won't need this — `fetch` already produces
                                cleaned output.

Examples:
  python scripts/youtube_import.py fetch https://www.youtube.com/watch?v=abc123
  python scripts/youtube_import.py fetch -- -0g3lLGxNfc      # leading-dash IDs need --
  python scripts/youtube_import.py fetch --batch playlist.txt
  python scripts/youtube_import.py run-imports
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "ufo-kb"
TRANSCRIPTS_DIR = REPO_ROOT / "transcripts"
RAW_DIR = KB_DIR / "raw" / "youtube-transcripts"
WIKI_DIR = KB_DIR / "wiki" / "youtube-transcripts"
OFF_TOPIC_FILE = KB_DIR / "imports" / "off-topic-skipped.md"
LOG_FILE = REPO_ROOT / "import_log.json"

# Claude CLI batch settings (formerly bulk_import.py)
MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
MAINTAIN_EVERY = 5
TIMEOUT_IMPORT = 2000   # ~33 min — large transcripts spawn many wiki pages
TIMEOUT_MAINTAIN = 5000

SKIP_FILES = {"missing.md"}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?(?:[^ ]*&)?v=)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtu\.be/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/(?:embed|shorts|live)/)([A-Za-z0-9_-]{11})"),
]


# ── Video-ID resolution ───────────────────────────────────────────────────────

def resolve_video_id(arg: str) -> str:
    """Extract canonical 11-char video ID from a URL or bare ID."""
    arg = arg.strip()
    if VIDEO_ID_RE.match(arg):
        return arg
    for pat in URL_ID_PATTERNS:
        m = pat.search(arg)
        if m:
            return m.group(1)
    raise ValueError(f"Could not parse video ID from: {arg!r}")


def make_canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ── Off-topic gate + idempotency ──────────────────────────────────────────────

def find_off_topic_reason(video_id: str) -> str | None:
    """Return the registered skip reason for video_id, or None if not listed."""
    if not OFF_TOPIC_FILE.exists():
        return None
    text = OFF_TOPIC_FILE.read_text(encoding="utf-8")
    # Registry rows look like: | `5Ne8ZbYxjKs` | Title | Channel | Reason |
    for line in text.splitlines():
        if f"`{video_id}`" in line:
            return line.strip()
    return None


def already_present(video_id: str) -> Path | None:
    """Return the first path that already represents this video, or None."""
    for p in (
        TRANSCRIPTS_DIR / f"{video_id}.md",
        RAW_DIR / f"{video_id}.md",
        WIKI_DIR / f"{video_id}.md",
    ):
        if p.exists():
            return p
    return None


# ── yt-dlp wrappers ───────────────────────────────────────────────────────────

class YTDLPError(RuntimeError):
    pass


def _yt_dlp_json(url: str) -> dict:
    """Pull metadata as JSON. Raises YTDLPError on failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "-J", "--skip-download", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise YTDLPError(
            "yt-dlp not found on PATH. Install with: pip install yt-dlp"
        )
    except subprocess.TimeoutExpired:
        raise YTDLPError(f"yt-dlp metadata fetch timed out for {url}")
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip().splitlines()[-3:]
        raise YTDLPError(
            f"yt-dlp failed for {url}: {' / '.join(stderr_tail) or 'unknown error'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise YTDLPError(f"yt-dlp returned non-JSON output: {e}")


def _yt_dlp_subs(url: str, video_id: str, out_dir: Path) -> Path | None:
    """Download English subs to out_dir. Tries manual first, falls back to auto.
    Returns path to .vtt file, or None if no captions available."""
    base_args = [
        "yt-dlp",
        "--skip-download",
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--no-warnings",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]

    # Pass 1: manually-uploaded subs only
    subprocess.run(
        base_args + ["--write-sub", url],
        capture_output=True, text=True, timeout=180,
    )
    vtts = sorted(out_dir.glob(f"{video_id}*.vtt"))
    if vtts:
        return vtts[0]

    # Pass 2: auto-generated fallback
    subprocess.run(
        base_args + ["--write-auto-sub", url],
        capture_output=True, text=True, timeout=180,
    )
    vtts = sorted(out_dir.glob(f"{video_id}*.vtt"))
    if vtts:
        return vtts[0]

    return None


# ── VTT → plaintext ───────────────────────────────────────────────────────────

CUE_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}")
INLINE_TAG_RE = re.compile(r"<[^>]+>")
HTML_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def _strip_inline(s: str) -> str:
    s = INLINE_TAG_RE.sub("", s)
    for k, v in HTML_ENTITY.items():
        s = s.replace(k, v)
    return s.strip()


def vtt_to_text(vtt: str) -> str:
    """Convert WebVTT to plain continuous prose. Dedupes auto-caption
    rolling-window repetitions."""
    lines = vtt.replace("\r\n", "\n").split("\n")
    n = len(lines)

    # Skip the WEBVTT header block (until first blank line)
    i = 0
    if i < n and lines[i].lstrip().startswith("WEBVTT"):
        i += 1
        while i < n and lines[i].strip() != "":
            i += 1
        i += 1  # skip the blank

    cues: list[str] = []
    while i < n:
        # Drop leading blanks
        while i < n and lines[i].strip() == "":
            i += 1
        if i >= n:
            break

        # Optional cue identifier (any non-empty line that isn't a timestamp)
        if not CUE_RE.match(lines[i]):
            i += 1
            if i >= n:
                break

        if i >= n or not CUE_RE.match(lines[i]):
            # Couldn't sync; advance and try again
            i += 1
            continue
        i += 1  # consume the timestamp line

        # Payload until blank line
        payload: list[str] = []
        while i < n and lines[i].strip() != "":
            cleaned = _strip_inline(lines[i])
            if cleaned:
                payload.append(cleaned)
            i += 1

        if payload:
            cues.append(" ".join(payload))

    # Dedup rolling captions: drop exact repeats and prefix-extensions.
    deduped: list[str] = []
    for cue in cues:
        if not deduped:
            deduped.append(cue)
            continue
        prev = deduped[-1]
        if cue == prev:
            continue
        if cue.startswith(prev):
            deduped[-1] = cue
            continue
        if prev.endswith(cue):
            continue
        deduped.append(cue)

    text = " ".join(deduped)
    # Collapse runs of whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Frontmatter writer ────────────────────────────────────────────────────────

def _yaml_str(s: str) -> str:
    """Single-quoted YAML scalar (safest given embedded ", \\, etc.)."""
    return "'" + s.replace("'", "''") + "'"


def _format_published(yyyymmdd: str | None) -> str:
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return ""
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def write_staged_transcript(
    out_path: Path,
    *,
    video_id: str,
    title: str,
    channel: str,
    published: str,
    url: str,
    duration_minutes: int,
    body: str,
) -> None:
    fm_lines = [
        "---",
        f"video_id: {video_id}",
        f"title: {_yaml_str(title)}",
        f"channel: {_yaml_str(channel)}",
    ]
    if published:
        fm_lines.append(f"published: {published}")
    fm_lines += [
        f"url: {url}",
        f"duration_minutes: {duration_minutes}",
        "---",
        "",
        f"# {title}",
        "",
        f"**URL:** {url}",
        "",
        "---",
        "",
        body,
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(fm_lines), encoding="utf-8")


# ── fetch (single) ────────────────────────────────────────────────────────────

class FetchOutcome:
    STAGED = "staged"
    SKIPPED_OFF_TOPIC = "skipped:off-topic"
    SKIPPED_EXISTS = "skipped:exists"
    FAILED_NO_CAPTIONS = "failed:no-captions"
    FAILED_METADATA = "failed:metadata"
    FAILED_OTHER = "failed:other"


def fetch_one(arg: str, *, force: bool = False) -> tuple[str, str]:
    """Stage one transcript. Returns (video_id, outcome_string)."""
    try:
        video_id = resolve_video_id(arg)
    except ValueError as e:
        print(f"  ✗  {e}", file=sys.stderr)
        return ("?", FetchOutcome.FAILED_OTHER)

    print(f"\n──  fetch {video_id}  ──")

    if not force:
        reason = find_off_topic_reason(video_id)
        if reason:
            print(f"  ⊘  Off-topic registry hit:")
            print(f"     {reason}")
            print(f"     (remove the entry from {OFF_TOPIC_FILE.relative_to(REPO_ROOT)} to override)")
            return (video_id, FetchOutcome.SKIPPED_OFF_TOPIC)

        existing = already_present(video_id)
        if existing:
            print(f"  ⊘  Already present at {existing.relative_to(REPO_ROOT)}")
            print(f"     (pass --force to overwrite)")
            return (video_id, FetchOutcome.SKIPPED_EXISTS)

    url = make_canonical_url(video_id)

    print(f"  ◦  Pulling metadata via yt-dlp …")
    try:
        meta = _yt_dlp_json(url)
    except YTDLPError as e:
        print(f"  ✗  {e}", file=sys.stderr)
        return (video_id, FetchOutcome.FAILED_METADATA)

    title = (meta.get("title") or "").strip() or f"YouTube {video_id}"
    channel = (meta.get("channel") or meta.get("uploader") or "").strip() or "unknown"
    published = _format_published(meta.get("upload_date"))
    duration_seconds = int(meta.get("duration") or 0)
    duration_minutes = max(1, round(duration_seconds / 60)) if duration_seconds else 0

    print(f"  ◦  Title:    {title[:70]}{'…' if len(title) > 70 else ''}")
    print(f"  ◦  Channel:  {channel}")
    print(f"  ◦  Date:     {published or 'unknown'}")
    print(f"  ◦  Length:   {duration_minutes} min")

    print(f"  ◦  Fetching captions …")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            vtt_path = _yt_dlp_subs(url, video_id, tmp_path)
        except subprocess.TimeoutExpired:
            print(f"  ✗  Subtitle fetch timed out", file=sys.stderr)
            return (video_id, FetchOutcome.FAILED_OTHER)

        if vtt_path is None:
            print(f"  ✗  No English captions available (manual or auto)", file=sys.stderr)
            return (video_id, FetchOutcome.FAILED_NO_CAPTIONS)

        vtt_text = vtt_path.read_text(encoding="utf-8")

    body = vtt_to_text(vtt_text)
    if not body.strip():
        print(f"  ✗  Caption file parsed to empty body", file=sys.stderr)
        return (video_id, FetchOutcome.FAILED_NO_CAPTIONS)

    out_path = TRANSCRIPTS_DIR / f"{video_id}.md"
    write_staged_transcript(
        out_path,
        video_id=video_id,
        title=title,
        channel=channel,
        published=published,
        url=url,
        duration_minutes=duration_minutes,
        body=body,
    )

    body_words = len(body.split())
    rel = out_path.relative_to(REPO_ROOT)
    print(f"  ✓  Staged {rel}  ({body_words:,} words)")
    print(f"     Next: /kb-import {rel} - YouTube Transcript")
    return (video_id, FetchOutcome.STAGED)


# ── fetch --batch ─────────────────────────────────────────────────────────────

def _expand_playlist(url: str) -> list[str]:
    """Use yt-dlp to enumerate video IDs in a playlist URL."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-J", "--no-warnings", url],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        raise YTDLPError("yt-dlp not found on PATH")
    if result.returncode != 0:
        raise YTDLPError(f"playlist enumeration failed: {result.stderr.strip()[:200]}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise YTDLPError(f"non-JSON playlist output: {e}")
    entries = data.get("entries") or []
    ids = []
    for e in entries:
        if isinstance(e, dict) and e.get("id"):
            ids.append(e["id"])
    return ids


def _read_id_file(path: Path) -> list[str]:
    """Read a text file with one URL/ID per line; return list of resolved IDs.
    Skips blank lines and lines starting with `#`."""
    out = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(resolve_video_id(line))
        except ValueError:
            print(f"  ⚠  Could not parse: {line!r}; skipping", file=sys.stderr)
    return out


def fetch_batch(arg: str, *, force: bool = False) -> int:
    """Stage many. Returns process exit code (0 = all staged or skipped, 1 = any failures)."""
    is_url = arg.startswith("http://") or arg.startswith("https://")
    ids: list[str]
    if is_url:
        try:
            ids = _expand_playlist(arg)
        except YTDLPError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        if not ids:
            print("✗ Playlist returned 0 entries", file=sys.stderr)
            return 1
    else:
        path = Path(arg).expanduser().resolve()
        if not path.exists():
            print(f"✗ File not found: {path}", file=sys.stderr)
            return 1
        ids = _read_id_file(path)
        if not ids:
            print("✗ No URLs/IDs in file", file=sys.stderr)
            return 1

    print(f"Batch mode — {len(ids)} videos")

    results: list[tuple[str, str]] = []
    for vid in ids:
        results.append(fetch_one(vid, force=force))

    print(f"\n{'═' * 62}")
    print(f"  BATCH SUMMARY")
    print(f"{'═' * 62}")
    bucket: dict[str, list[str]] = {}
    for vid, outcome in results:
        bucket.setdefault(outcome, []).append(vid)
    for outcome, vids in sorted(bucket.items()):
        print(f"  {outcome:25s} {len(vids):4d}")
        for v in vids[:5]:
            print(f"     • {v}")
        if len(vids) > 5:
            print(f"     … and {len(vids) - 5} more")

    any_failed = any(o.startswith("failed:") for _, o in results)
    return 1 if any_failed else 0


# ── run-imports (replaces bulk_import.py) ─────────────────────────────────────

def _load_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {
        "started_at": datetime.now().isoformat(),
        "last_updated": None,
        "session_id": None,
        "processed": {},
        "maintain_runs": [],
    }


def _save_log(log: dict) -> None:
    log["last_updated"] = datetime.now().isoformat()
    LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"    [log saved → {LOG_FILE.name}]")


def _run_claude(prompt: str, timeout: int, *, session_id: str, first_call: bool) -> tuple[bool, str]:
    """Invoke `claude -p` reusing a single session across calls.

    The first call uses --session-id <uuid> to anchor the session; every
    subsequent call uses --resume <uuid> so the model context (skill prompts,
    prior import work) is reused instead of being reloaded per file.
    """
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--dangerously-skip-permissions"]
    if first_call:
        cmd += ["--session-id", session_id]
    else:
        cmd += ["--resume", session_id]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
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
        sys.exit("ERROR: `claude` binary not found on PATH. Install Claude Code CLI.")
    except Exception as exc:
        return False, f"EXCEPTION: {exc}"


def _import_one(transcript: Path, log: dict, session_id: str, first_call: bool) -> tuple[bool, bool]:
    """Try to import one transcript. Returns (success, used_first_call)."""
    name = transcript.name
    rel_path = f"transcripts/{name}"
    print(f"\n{'─' * 62}\n  IMPORT  {name}\n{'─' * 62}")

    last_output = ""
    used_first_call = first_call
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Attempt {attempt}/{MAX_RETRIES} …")
        prompt = f"/kb-import {rel_path} - YouTube Transcript"
        success, output = _run_claude(
            prompt, TIMEOUT_IMPORT,
            session_id=session_id,
            first_call=used_first_call,
        )
        last_output = output
        # After the very first claude call (success or fail), the session exists
        # on disk — every subsequent call must use --resume.
        used_first_call = False

        tail = output[-300:].strip().replace("\n", " ↵ ")
        if success:
            print(f"  ✓  Success")
            log["processed"][name] = {
                "status": "success",
                "attempts": attempt,
                "completed_at": datetime.now().isoformat(),
                "output_tail": output[-3000:],
            }
            _save_log(log)
            return True, used_first_call
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
    _save_log(log)
    return False, used_first_call


def _run_maintain(log: dict, label: str, session_id: str, first_call: bool) -> bool:
    print(f"\n{'═' * 62}\n  KB-MAINTAIN  ({label})\n{'═' * 62}")
    success, output = _run_claude(
        "/kb-maintain Go through all the steps, report back what you did at each step. "
        "You are allowed to make changes without my permission.",
        TIMEOUT_MAINTAIN,
        session_id=session_id,
        first_call=first_call,
    )
    status = "success" if success else "failed"
    tail = output[-300:].strip().replace("\n", " ↵ ")
    print(f"  {'✓' if success else '✗'}  kb-maintain {status} — {tail}")
    log["maintain_runs"].append({
        "label": label,
        "status": status,
        "run_at": datetime.now().isoformat(),
        "output_tail": output[-3000:],
    })
    _save_log(log)
    return success


def cmd_run_imports(args: argparse.Namespace) -> int:
    if args.reset and LOG_FILE.exists():
        LOG_FILE.unlink()
        print("Log wiped — starting fresh.\n")

    if not TRANSCRIPTS_DIR.exists():
        print(f"✗ Staging directory missing: {TRANSCRIPTS_DIR}", file=sys.stderr)
        return 1

    all_transcripts = sorted(
        f for f in TRANSCRIPTS_DIR.glob("*.md") if f.name not in SKIP_FILES
    )

    log = _load_log()
    succeeded = {k for k, v in log["processed"].items() if v["status"] == "success"}
    failed = {k for k, v in log["processed"].items() if v["status"] == "failed"}

    skip_set = succeeded if args.retry_failed else (succeeded | failed)
    pending = [t for t in all_transcripts if t.name not in skip_set]

    # Session continuity: reuse one Claude session across the whole batch so
    # the model retains skill prompts + prior import work in cache. `--reset`
    # or `--new-session` forces a fresh session.
    session_id = log.get("session_id")
    fresh_session = args.new_session or args.reset or not session_id
    if fresh_session:
        session_id = str(uuid.uuid4())
        log["session_id"] = session_id
        _save_log(log)
        print(f"  New Claude session: {session_id}")
    else:
        print(f"  Resuming Claude session: {session_id}")

    print("=" * 62)
    print("  UFO KB — Bulk Import")
    print("=" * 62)
    print(f"  Total transcripts : {len(all_transcripts)}")
    print(f"  Already imported  : {len(succeeded)}")
    print(f"  Previously failed : {len(failed)}  "
          f"{'(will retry)' if args.retry_failed else '(skipped — use --retry-failed to re-run)'}")
    print(f"  To process        : {len(pending)}")
    print(f"  Model             : {MODEL}")
    print(f"  Retries per file  : {MAX_RETRIES}")
    print(f"  Maintain every    : {MAINTAIN_EVERY} successful imports")
    print(f"  Log file          : {LOG_FILE}")
    print("=" * 62)

    if not pending:
        print("\nNothing left to import.")
        _run_maintain(log, "final (already complete)", session_id, first_call=fresh_session)
        return 0

    first_call = fresh_session
    success_since_last_maintain = 0
    for i, transcript in enumerate(pending, start=1):
        total_done = len(succeeded) + i - 1
        print(f"\n[{i}/{len(pending)}]  (total done: {total_done})")

        ok, _ = _import_one(transcript, log, session_id, first_call)
        first_call = False  # every later call must --resume the now-existing session

        if ok:
            success_since_last_maintain += 1

        if success_since_last_maintain >= MAINTAIN_EVERY:
            _run_maintain(
                log,
                f"after {len(succeeded) + i} total imports",
                session_id,
                first_call=False,
            )
            success_since_last_maintain = 0

    _run_maintain(log, "final", session_id, first_call=False)

    final = _load_log()
    n_ok = sum(1 for v in final["processed"].values() if v["status"] == "success")
    n_fail = sum(1 for v in final["processed"].values() if v["status"] == "failed")
    failed_files = [k for k, v in final["processed"].items() if v["status"] == "failed"]

    print(f"\n{'=' * 62}")
    print(f"  DONE")
    print(f"  Successful imports : {n_ok}")
    print(f"  Failed imports     : {n_fail}")
    print(f"  kb-maintain runs   : {len(final['maintain_runs'])}")
    print(f"  Claude session     : {final.get('session_id')}")
    print(f"  Log                : {LOG_FILE}")
    if failed_files:
        print(f"\n  Failed files (check output_tail in log):")
        for f in failed_files:
            print(f"    • {f}")
    print("=" * 62)
    return 0 if n_fail == 0 else 1


# ── clean (replaces clean_transcript.py) ──────────────────────────────────────

def clean_existing_md(path: Path) -> None:
    """Collapse VTT-residue blank lines in an already-staged transcript .md.
    Preserves the YAML front-matter and Markdown header section."""
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    parts = content.split("---\n\n", 1)
    if len(parts) == 2:
        header = parts[0] + "---\n\n"
        body = parts[1]
    else:
        header = ""
        body = content

    body = body.strip()
    paragraphs = re.split(r"\n{3,}", body)
    cleaned = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para = re.sub(r"\n\s*\n", " ", para)
        para = re.sub(r"\n", " ", para)
        para = re.sub(r" {2,}", " ", para)
        cleaned.append(para.strip())

    path.write_text(header + "\n\n".join(cleaned) + "\n", encoding="utf-8")
    print(f"Cleaned: {path}")


# ── CLI plumbing ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube_import",
        description="Stage, batch-stage, and bulk-import YouTube transcripts for the UFO KB.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Stage one transcript (or many with --batch)")
    p_fetch.add_argument(
        "target",
        nargs="?",
        help="YouTube URL or 11-char video ID (omit when using --batch)",
    )
    p_fetch.add_argument(
        "--batch",
        metavar="FILE_OR_URL",
        help="Stage many: pass a playlist URL OR a path to a text file with one URL/ID per line.",
    )
    p_fetch.add_argument(
        "--force", action="store_true",
        help="Overwrite existing staged/raw files; bypass off-topic registry.",
    )

    p_run = sub.add_parser("run-imports", help="Invoke /kb-import on each file in transcripts/")
    p_run.add_argument("--reset", action="store_true",
                       help="Wipe import_log.json and start fresh (also forces a new Claude session).")
    p_run.add_argument("--retry-failed", action="store_true",
                       help="Re-attempt files that previously failed (default: skip them).")
    p_run.add_argument("--new-session", action="store_true",
                       help="Start a fresh Claude session even if one exists in the log.")

    p_clean = sub.add_parser("clean", help="Collapse VTT-residue blank lines in an existing staged file")
    p_clean.add_argument("path", type=Path)

    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.cmd == "fetch":
        if args.batch and args.target:
            print("✗ Pass either <target> OR --batch, not both", file=sys.stderr)
            return 2
        if not args.batch and not args.target:
            print("✗ Pass a URL/ID or use --batch <file_or_url>", file=sys.stderr)
            return 2
        if args.batch:
            return fetch_batch(args.batch, force=args.force)
        _, outcome = fetch_one(args.target, force=args.force)
        return 0 if outcome.startswith("staged") or outcome.startswith("skipped:") else 1

    if args.cmd == "run-imports":
        return cmd_run_imports(args)

    if args.cmd == "clean":
        if not args.path.exists():
            print(f"✗ File not found: {args.path}", file=sys.stderr)
            return 1
        clean_existing_md(args.path)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
