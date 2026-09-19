---
type: process
status: verified
consumes: [uploaded audio file, CallSummary shell, Claude]
produces: [CallSummary]
---

# transcribe

An uploaded call recording is transcribed by Whisper and distilled by Claude into a summary and action items on its CallSummary row.

## Input → Movement → Output

`POST /workspaces/{id}/calls` validates the audio, writes it to a temp file, and inserts an empty CallSummary shell, then enqueues `transcribe_call(call_id, audio_path)`. The worker loads the cached Whisper model, transcribes the file to text + duration, sends the transcript to Claude Sonnet for a 2-3 sentence summary plus a JSON action-item list, and persists all of it back onto the CallSummary row. The temp audio file is always unlinked in a `finally` block.

## Why this shape

Transcription is a Celery task, not inline, because Whisper is a heavy model (loaded once via `lru_cache`, `workers/transcribe.py:42`) and a full transcription can take minutes — far past an HTTP timeout — so the endpoint returns a `job_id` immediately and the client polls. The CallSummary shell is created *before* the task so the row exists to poll and attach results to. Temp-file cleanup lives in `finally` (`transcribe.py:127-131`) so a failed transcription never leaks the audio file.

## Steps

1. Endpoint validates + temp-writes audio, inserts CallSummary shell — `routers/calls.py:63-94`.
2. Enqueue `transcribe_call` with temp path, mark job dispatched — `calls.py:96-101`.
3. Whisper transcribe → (text, duration) — `workers/transcribe.py:48-55`, `:117`.
4. Claude Sonnet extract summary + action_items JSON — `transcribe.py:58-78`, `:118`.
5. Persist onto CallSummary row — `transcribe.py:92-110`.
6. Unlink temp file in finally — `transcribe.py:127-131`.

## Trigger

On-demand only — API-invoked at upload (`calls.py:98`, `transcribe_call.delay`). NO beat entry.

## If you change this

- **Hits:** `models/call_summary.py` (transcript/summary/action_items/duration_seconds/model_used); `routers/agents.py` `_mark_job_dispatched` + `GET /jobs/{id}` poller; requires the `whisper` package + `WHISPER_MODEL` env; ANTHROPIC_API_KEY.
- **Does not hit:** auth, ingest, scoring, discovery, outreach — the most isolated verb (only shared deps are the job-dispatch helper and the Claude client).

## Surfaces

| Surface | Role |
|---|---|
| `POST /workspaces/{id}/calls` | upload + trigger |
| Celery worker (Whisper + Claude) | transcribe + summarize |
| `GET /jobs/{job_id}` + calls list | poll status / read result |

## See

- Objects: [[CallSummary]], [[Contact]]
- Source: `apps/api/app/workers/transcribe.py`, `apps/api/app/routers/calls.py`
