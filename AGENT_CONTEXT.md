# AGENT CONTEXT: Job Application Agent
**Read this file first before doing anything in this repository.**

---

## 1. Project Overview
- **Project**: Auto Job Applier / Job Application Agent
- **Stack**: 
  - **Backend**: FastAPI (Python 3.8+), Playwright, BeautifulSoup4, IMAP email scanner (`src/tracker.py`)
  - **Frontend**: React (Vite, single-page dashboard in `frontend/`)
- **Core Functionality**:
  - Automated job search & application execution (LinkedIn Easy Apply only)
  - Guarded application pipeline (resume-only or verified screening answers)
  - Safe screening answers module (`src/screening_answers.py`): answers only user-configured questions
  - Tracker dashboard (`frontend/src/App.jsx`, `backend/tracker_routes.py`): stage management, recruiter follow-ups, reply sync via IMAP

---

## 2. Local Setup
- **Path**: `C:\Users\uriel\.gemini\antigravity\scratch\job-application-agent`
- **Repo**: `https://github.com/johnlinneman78/Job-application-agent` (public)
- **Environment**: Runs locally only (visible browser + manual LinkedIn login). The Docker deploy in `deployment/` is broken and unused.
- **Run commands**:
  - Backend: `cd backend && python -m uvicorn main:app --port 8000`
  - Frontend: `cd frontend && npm run dev`
- **Ignored paths**: Never commit `.env`, `config.local.yaml`, `data/`, `backend/data/`, `uploads/`

---

## 3. Hard Rules (Non-Negotiable)
1. **Never commit `.env` or credentials to git**: `.env` holds sensitive credentials (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`). Ensure `.gitignore` always excludes `.env`.
2. **No personal data hard-coded**: No personal data (name, phone, email) hard-coded in code. Read from settings/environment.
3. **Safe screening answers only**: Never fabricate or guess answers. Only answer questions recognized and explicitly answered by the user in Settings. Unanswered questions must cause the job to be skipped.
4. **No "default Yes" logic**: Do not add "default Yes" answer logic. It was tried in commit 819b400 and removed because it submitted false answers.
5. **Submission verification**: A job counts as SUBMITTED only after Submit is clicked AND LinkedIn shows a visible confirmation. Never use page-source text as proof.
6. **Easy Apply button selectors**: `EASY_APPLY_SELECTORS` is shared by the guard and the executor. LinkedIn uses `#jobs-apply-button-id` for both Easy Apply and the external Apply button, so the button text must contain "Easy Apply".
7. **Modal selector usage**: Selectors built from `MODAL_SELECTOR` must use `in_modal(...)` (it is a comma list).
8. **Data structure schemas**:
   - Recruiter info is stored at `application.job.recruiter_name` / `recruiter_url`.
   - `answers_given` is a list of `{question, answer}`.
   - Tracker stages come from `src/tracker.py` `ALL_STAGES`: `applied`, `viewed`, `resume_downloaded`, `replied`, `interview`, `rejected`, `offer`, `withdrawn`, `no_response`.
9. **Account safety & application limits**: Keep volume to 10-15 applications a day with delays on (John's real account).
10. **Verification before commit**:
   - Frontend: `cd frontend && npm run build` must succeed.
   - Tests: `python -m pytest tests/test_settings.py tests/test_tracker.py -q` must pass (27 tests).
11. **No autonomous live runs**: Never initiate live application runs without explicit user confirmation.

---

## 4. Status
- **Last known GitHub commit**: 79a9a41 (always copy the hash from `git log --oneline -1` after pushing)
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

## 5. Next Steps
- [x] 1. Apply tracker page bug fixes to `frontend/src/App.jsx` and build frontend (`npm run build`)
- [x] 2. Run pytest suite (`python -m pytest tests/test_settings.py tests/test_tracker.py -q` - 27 passed)
- [ ] 3. User configuration: Set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env` for email reply tracking
- [ ] 4. User configuration: Review and fill in screening answers and salary preferences in Settings before next live run
- [ ] 5. Run dry-run verification (`dry_run=True`) to confirm search filters and screening answers logging
- [ ] 6. 3-job live run after the dry run; check answers_given and confirm on LinkedIn My Jobs > Applied (Indeed is not supported)
- [ ] 7. Address mobile sideways scroll on Dashboard (`.dashboard-right`) and Queue pages

---

## 6. Log
- **2026-09-30**: Applied Tracker page bug fixes to `frontend/src/App.jsx`. Verified frontend build (`npm run build`) and Python test suite (27 tests passed). Established and updated `AGENT_CONTEXT.md` with setup guidelines, complete hard rules, and clean UTF-8 encoding.
