# AGENT CONTEXT — Job Application Agent
**Read this file first before doing anything in this repository.**

---

## 1. Project Overview
- **Project**: Auto Job Applier / Job Application Agent
- **Stack**: 
  - **Backend**: FastAPI (Python 3.8+), Playwright, BeautifulSoup4, IMAP email scanner (`src/tracker.py`)
  - **Frontend**: React (Vite, App Router / single-page dashboard in `frontend/`)
- **Core Functionality**:
  - Automated job search & application execution (LinkedIn Easy Apply, Indeed Quick Apply)
  - Guarded application pipeline (resume-only or verified screening answers)
  - Safe screening answers module (`src/screening_answers.py`): answers only user-configured questions
  - Tracker dashboard (`frontend/src/App.jsx`, `backend/tracker_routes.py`): stage management, recruiter follow-ups, reply sync via IMAP

---

## 2. Hard Rules (Non-Negotiable)
1. **Never commit `.env` or credentials to git**: `.env` holds sensitive credentials (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`). Ensure `.gitignore` always excludes `.env`.
2. **Safe screening answers only**: Never fabricate or guess answers. Only answer questions recognized and explicitly answered by the user in Settings. Unanswered questions must cause the job to be skipped.
3. **Never submit unconfirmed applications**: Always verify Easy Apply modal states and never brute-force or skip validations.
4. **Verification before commit**:
   - Frontend: `cd frontend && npm run build` must succeed.
   - Tests: `python -m pytest tests/test_settings.py tests/test_tracker.py -q` must pass (27 tests).
5. **No autonomous live runs**: Never initiate live application runs without explicit user confirmation.

---

## 3. Status
- **Last known GitHub commit**: 5367f77
- **Current State**: 
  - Settings tabs & screening answers backend/frontend implemented.
  - Tracker page frontend bug fixes applied and verified:
    - Recruiter name/URL resolution via `withRecruiter()`
    - Screening answers drawer handles both array & dict shapes
    - Stage dropdown displays only for submitted applications; skipped jobs display failure reason badge
    - Stat cards aligned to backend API response schema (`stats.overall`, `stats.submit_rate`, `stats.attempts`)
    - Corrected Gmail setup guidance to `GMAIL_ADDRESS`
    - Mobile responsiveness improvements for Tracker grid layouts

---

## 4. Next Steps
- [x] 1. Apply tracker page bug fixes to `frontend/src/App.jsx` and build frontend (`npm run build`)
- [x] 2. Run pytest suite (`python -m pytest tests/test_settings.py tests/test_tracker.py -q` — 27 passed)
- [ ] 3. User configuration: Set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env` for email reply tracking
- [ ] 4. User configuration: Review and fill in screening answers and salary preferences in Settings before next live run
- [ ] 5. Run dry-run verification (`dry_run=True`) to confirm search filters and screening answers logging
- [ ] 6. Address mobile sideways scroll on Dashboard (`.dashboard-right`) and Queue pages

---

## 5. Log
- **2026-09-30**: Applied Tracker page bug fixes to `frontend/src/App.jsx`. Verified frontend build (`npm run build`) and Python test suite (27 tests passed). Established `AGENT_CONTEXT.md`.
