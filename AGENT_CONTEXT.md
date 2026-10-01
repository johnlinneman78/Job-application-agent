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
  - Safe screening answers module (`src/screening_answers.py`): answers only user-configured questions or strict resume matches
  - Experience extraction module (`src/experience.py`): extracts job history, areas, and tools with strict matching
  - Local-first search planner (`src/job_scraper.py`): searches local cities first (on-site/hybrid) then remote with quotas
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
3. **Safe screening answers only**: Never fabricate or guess answers. Only answer questions recognized and explicitly answered by the user in Settings or strictly derived from the resume. Unanswered questions must cause the job to be skipped.
4. **Experience answers hierarchy & strict matching**: Experience answers come from (1) Settings overrides, then (2) the resume via `src/experience.py`. Matching is strict: the question must be about exactly that area/tool, with no extra qualifiers. Never loosen this to answer more questions; skipping is better than overstating.
5. **Local-first search planning**: Search runs through `build_search_plan()`: local (on-site/hybrid, distance) first, then remote (`f_WT=2`, scope state/us/off), with quotas. Don't go back to the nested title×location loop with one global cap.
6. **No "default Yes" logic**: Do not add "default Yes" answer logic. It was tried in commit 819b400 and removed because it submitted false answers.
7. **Submission verification**: A job counts as SUBMITTED only after Submit is clicked AND LinkedIn shows a visible confirmation. Never use page-source text as proof.
8. **Easy Apply button selectors**: `EASY_APPLY_SELECTORS` is shared by the guard and the executor. LinkedIn uses `#jobs-apply-button-id` for both Easy Apply and the external Apply button, so the button text must contain "Easy Apply".
9. **Modal selector usage**: Selectors built from `MODAL_SELECTOR` must use `in_modal(...)` (it is a comma list).
10. **Data structure schemas**:
   - Recruiter info is stored at `application.job.recruiter_name` / `recruiter_url`.
   - `answers_given` is a list of `{question, answer}`.
   - Tracker stages come from `src/tracker.py` `ALL_STAGES`: `applied`, `viewed`, `resume_downloaded`, `replied`, `interview`, `rejected`, `offer`, `withdrawn`, `no_response`.
11. **Account safety & application limits**: Keep volume to 10-15 applications a day with delays on (John's real account).
12. **Verification before commit**:
   - Frontend: `cd frontend && npm run build` must succeed.
   - Tests: `python -m pytest tests/ -q --ignore=tests/test_unicode_safety.py` must pass (40 tests).
13. **No autonomous live runs**: Never initiate live application runs without explicit user confirmation.

---

## 4. Status
- **Last known GitHub commit**: 7fb6646 (always copy the hash from `git log --oneline -1` after pushing)
- **Current State**: 
  - Experience extraction from resume (`src/experience.py`), local-first search with quotas (`build_search_plan()`), exact skip failure reasons, and frontend settings controls for remote scope & resume experience fully integrated and verified (40 tests passing, clean frontend build).

---

## 5. Next Steps
- [ ] 1. John: in Settings → Job search, remove "Remote" from Your cities (remote is now its own setting), pick the Remote jobs scope and mix, and set distance to 25 miles.
- [ ] 2. John: check the "From your resume" box under Screening answers looks right.
- [ ] 3. Dry run (`dry_run=True`), then a 5-job live run. Then review "Questions that blocked applications" on the Tracker page.
- [ ] 4. User configuration: Set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env` for email reply tracking.
- [ ] 5. Address mobile sideways scroll on Dashboard (`.dashboard-right`) and Queue pages.

---

## 6. Log
- **2026-09-30**: Applied Tracker page bug fixes to `frontend/src/App.jsx`. Verified frontend build (`npm run build`) and Python test suite (27 tests passed). Established and updated `AGENT_CONTEXT.md` with setup guidelines, complete hard rules, and clean UTF-8 encoding.
- **2026-09-30**: Fixed scraper location leak: when searching "Remote" (United States), locked work_types strictly to remote-only (f_WT=2) to prevent matching nationwide on-site/hybrid positions.
- **2026-09-30**: Integrated resume experience parsing (`src/experience.py`) with strict question matching, local-first search planning (`build_search_plan()`) with quotas and out-of-area skip checks, exact skip reason tracking with blocking question stats, and frontend settings controls. Verified 40 passing pytest tests and successful Vite build.
