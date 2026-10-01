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
12. **Radio answer verification**: Radio answers must be confirmed with `is_checked()` before they're logged. The radio question text comes from `QUESTION_TEXT_JS`, shared with the skip reason. Don't use separate selectors.
13. **Descriptive skip reasons**: Skip reasons end with `explain()`'s note. Use it to decide if the fix is in Settings (John) or in code (selectors).
14. **Verification before commit**:
   - Frontend: `cd frontend && npm run build` must succeed when frontend changes are made.
   - Tests: `python -m pytest tests/ -q --ignore=tests/test_unicode_safety.py` must pass (49 tests).
15. **No autonomous live runs**: Never initiate live application runs without explicit user confirmation.

---

## 4. Status
- **Last known GitHub commit**: 53fdd53 (always copy the hash from `git log --oneline -1` after pushing)
- **Current State**: 
  - Live-log fixes: 'currently' questions, verified radio selection, skip-reason notes, job locations from cards/top card. Includes the resume one-line-header fix. Verified with 49 passing tests.

---

## 5. Next Steps
- [ ] 1. John: fill in Settings before the next run:
  - Settings → Job search: remove "Remote" from Your cities, set Remote jobs to "my state", set Distance to 25 miles.
  - Settings → Screening answers: Bachelor's degree: No; High school diploma: Yes; Driver's license: Yes/No; Background check: Yes; Drug test: Yes; Require sponsorship: No; Authorized to work: Yes; Comfortable working on-site: Yes; Commute OK: Yes.
  - Upload the 2026 resume PDF in Settings.
- [ ] 2. Dry run (answer **n**). Check that `Location:` is filled in with a real location (e.g. "Portland, OR (On-site)") instead of "Unknown", and look for any `SKIP: Outside your area` lines.
- [ ] 3. Live run of 5 jobs. Every `Auto-answered:` line should be true. Check each one on LinkedIn (My Jobs > Applied).
- [ ] 4. Read the notes in brackets on each skip reason and send John any "could not select it" cases with the screenshot.
- [ ] 5. User configuration: Set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env` for email reply tracking.
- [ ] 6. Address mobile sideways scroll on Dashboard (`.dashboard-right`) and Queue pages.

---

## 6. Log
- **2026-09-30**: Applied Tracker page bug fixes to `frontend/src/App.jsx`. Verified frontend build (`npm run build`) and Python test suite (27 tests passed). Established and updated `AGENT_CONTEXT.md` with setup guidelines, complete hard rules, and clean UTF-8 encoding.
- **2026-09-30**: Fixed scraper location leak: when searching "Remote" (United States), locked work_types strictly to remote-only (f_WT=2) to prevent matching nationwide on-site/hybrid positions.
- **2026-09-30**: Integrated resume experience parsing (`src/experience.py`) with strict question matching, local-first search planning (`build_search_plan()`) with quotas and out-of-area skip checks, exact skip reason tracking with blocking question stats, and frontend settings controls. Verified 40 passing pytest tests and successful Vite build.
- **2026-10-01**: Applied live-log fixes: added question filler words ('currently', 'presently', etc.) and 'bd' alias to `src/experience.py`, robust radio option selection with `QUESTION_TEXT_JS` and `is_checked()` confirmation, descriptive `explain()` skip-reason notes, card and job-page location extraction to fix 'Location: Unknown', and one-line resume header support. 49 pytest tests passing.
