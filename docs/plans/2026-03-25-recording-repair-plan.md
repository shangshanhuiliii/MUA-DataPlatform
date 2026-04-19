# Recording Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop future recordings from missing `recordings` rows and introduce an admin-only exception workflow for historical missing/invalid recording metadata.

**Architecture:** New frontends send `auth_token` inside the `start_recording` WebSocket message. The backend requires that token for `new_task`, validates it, derives the current user, and creates the `recordings` row itself using an idempotent `directory_name`-keyed path. If the token is missing, the backend fails fast and asks the client to refresh/login again. Historical repair is handled through an admin-only exception management page instead of automatic backfill.

**Tech Stack:** FastAPI, SQLModel, JWT auth, browser JavaScript, MySQL, Docker

---

### Task 1: Record the agreed compatibility contract

**Files:**
- Modify: `docs/plans/2026-03-25-recording-repair-plan.md`

**Step 1: Capture supported rollout combinations**

Supported combinations:
- new frontend + new backend

Explicitly unsupported:
- old frontend + new backend
- new frontend + old backend

**Step 2: Capture the persistence ownership rule**

Rules:
- new frontend removes `createRecording`
- new backend owns recording creation
- `new_task` must carry `auth_token`
- missing token must fail fast instead of silently starting an untracked recording

### Task 2: Make backend recording creation idempotent

**Files:**
- Modify: `web/backend/crud/recording.py`
- Modify: `web/backend/routers/recordings.py`
- Test: `tests/web/backend/services/test_task_record_service.py`

**Step 1: Add `ensure_recording`**

Behavior:
- lookup by `directory_name`
- return existing row if present
- otherwise create row
- handle unique-key races by reloading existing row after integrity errors

**Step 2: Make `POST /api/recordings` use the idempotent path**

Behavior:
- return existing row instead of failing on duplicate `directory_name`
- preserve safe idempotent semantics for direct API callers

### Task 3: Move new frontend persistence to backend `start_recording`

**Files:**
- Modify: `web/backend/services/task_record_service.py`
- Modify: `web/static/js/components/task-recorder.js`
- Test: `tests/web/backend/services/test_task_record_service.py`

**Step 1: Send `auth_token` in `start_recording`**

Use the existing JWT stored in `localStorage` under `auth_token`.

**Step 2: Validate token server-side**

Behavior:
- required for every `new_task` start request
- derive current active user from JWT
- never trust a raw `recorded_by` value from the client

**Step 3: Create recording from backend**

Behavior:
- only for `new_task`
- create on backend after recording becomes ready
- set `recorded_by` from the authenticated user

**Step 4: Remove frontend `createRecording`**

Behavior:
- new frontend no longer calls `POST /api/recordings`

### Task 4: Add admin-only recording exception management

**Files:**
- Create: backend exception APIs
- Create: frontend admin page/components
- Reuse: existing admin auth and user APIs

**Step 1: Surface exception types**

At minimum:
- directory exists on disk but not in `recordings`
- `recordings` row exists but task/user relationship is invalid

**Step 2: Admin repair workflow**

Admin can:
- inspect the directory
- see inferred task metadata
- assign the actual recorder
- create or repair the DB row

**Step 3: Do not rely on automatic backfill**

Historical data repair is intentional and user-confirmed, especially for `recorded_by`.

### Task 5: Verify rollout

**Files:**
- Reuse: `deploy/find-missing-recordings.sh`

**Step 1: Verify missing-token fail-fast**

Expected:
- `new_task` without `auth_token` is rejected immediately
- failed requests do not create recording directories or DB rows

**Step 2: Verify new frontend flow**

Expected:
- `start_recording` includes `auth_token`
- backend creates the recording row
- no frontend `createRecording` request is sent

**Step 3: Re-run missing-recording audit**

Expected:
- newly created recordings stop appearing in the missing list
