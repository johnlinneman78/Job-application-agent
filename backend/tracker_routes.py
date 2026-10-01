"""
Tracker API for the dashboard. Registered from backend/main.py with:

    from tracker_routes import register_tracker_routes
    register_tracker_routes(app, globals())

Endpoints (all require login):
    GET  /api/tracker                 applications + tracking info + stats + follow-ups + unmatched emails
    POST /api/tracker/sync            {"gmail": true, "linkedin": true, "days": 30} - runs in background
    GET  /api/tracker/sync/status     last sync times + result counts
    PUT  /api/tracker/{app_id}        {"stage": "...", "notes": "...", "follow_up_done": true}
    POST /api/tracker/{app_id}/note   regenerate the recruiter note -> {"note": "..."}
    POST /api/tracker/unmatched/assign {"message_id": "...", "app_id": "..."}
    POST /api/tracker/digest          send the daily summary email to yourself now
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src import tracker  # noqa: E402

logger = logging.getLogger(__name__)


class StageUpdate(BaseModel):
    stage: Optional[str] = None
    notes: Optional[str] = None
    follow_up_done: Optional[bool] = None


class SyncRequest(BaseModel):
    gmail: bool = True
    linkedin: bool = True
    days: int = 30


class AssignRequest(BaseModel):
    message_id: str
    app_id: str


def register_tracker_routes(app, ns: dict):
    """`ns` is backend/main.py's globals(): uses its auth, storage and browser helpers."""
    get_current_user = ns["get_current_user"]
    applications_db = ns["applications_db"]
    configs_db = ns["configs_db"]
    save_db = ns["save_db"]
    APPS_FILE = ns["APPS_FILE"]
    DB_DIR = ns["DB_DIR"]
    STATE_FILE = Path(DB_DIR) / "tracker_state.json"

    def load_state() -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
        return {}

    def save_state(st: dict):
        STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")

    def user_state(st: dict, email: str) -> dict:
        return st.setdefault(email, {})

    def find_app(email: str, app_id: str) -> dict:
        for r in applications_db.get(email, []):
            if r.get("id") == app_id:
                return r
        raise HTTPException(status_code=404, detail="Application not found")

    sync_running = {"value": False}

    # ------------------------------------------------------------ read

    @app.get("/api/tracker")
    async def get_tracker(current_user: dict = Depends(get_current_user)):
        email = current_user["email"]
        recs = applications_db.get(email, [])
        for r in recs:
            if r.get("status") == "submitted":
                tracker.ensure_tracking(r)
        tracker.refresh_no_response(recs)
        st = user_state(load_state(), email)
        due = tracker.follow_ups_due(recs)
        return {
            "applications": sorted(recs, key=lambda r: r.get("applied_at") or "", reverse=True),
            "stats": tracker.compute_stats(recs),
            "follow_ups_due": [r["id"] for r in due],
            "unmatched_emails": st.get("unmatched", [])[-50:],
            "last_gmail_sync": st.get("last_gmail_sync"),
            "last_linkedin_sync": st.get("last_linkedin_sync"),
            "gmail_configured": all(tracker.gmail_credentials()),
            "stages": tracker.ALL_STAGES,
        }

    @app.get("/api/tracker/sync/status")
    async def sync_status(current_user: dict = Depends(get_current_user)):
        st = user_state(load_state(), current_user["email"])
        return {"running": sync_running["value"], "last_gmail_sync": st.get("last_gmail_sync"),
                "last_linkedin_sync": st.get("last_linkedin_sync"), "last_result": st.get("last_result")}

    # ------------------------------------------------------------ manual edits

    @app.put("/api/tracker/{app_id}")
    async def update_tracking(app_id: str, body: StageUpdate, current_user: dict = Depends(get_current_user)):
        rec = find_app(current_user["email"], app_id)
        t = tracker.ensure_tracking(rec)
        if body.stage:
            try:
                tracker.set_stage_manual(rec, body.stage, body.notes)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        elif body.notes is not None:
            t["notes"] = body.notes[:2000]
        if body.follow_up_done is not None:
            t["follow_up_done"] = body.follow_up_done
        save_db(applications_db, APPS_FILE)
        return rec

    @app.post("/api/tracker/{app_id}/note")
    async def follow_up_note(app_id: str, current_user: dict = Depends(get_current_user)):
        rec = find_app(current_user["email"], app_id)
        job = rec.get("job") or {}
        cfg = configs_db.get(current_user["email"]) or {}
        name = (cfg.get("personal_info") or {}).get("name") or current_user.get("full_name", "")
        note = tracker.build_follow_up_note(job, name, job.get("matched_skills") or [],
                                            applied=rec.get("status") == "submitted")
        return {"note": note, "length": len(note)}

    @app.post("/api/tracker/unmatched/assign")
    async def assign_unmatched(body: AssignRequest, current_user: dict = Depends(get_current_user)):
        email = current_user["email"]
        all_state = load_state()
        st = user_state(all_state, email)
        item = next((u for u in st.get("unmatched", []) if u.get("message_id") == body.message_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Email not found")
        rec = find_app(email, body.app_id)
        tracker.apply_event(rec, item["stage"], "email", f"{item['subject'][:150]} — {item['from'][:60]}",
                            tracker._parse_dt(item.get("at")))
        st["unmatched"] = [u for u in st["unmatched"] if u.get("message_id") != body.message_id]
        save_state(all_state)
        save_db(applications_db, APPS_FILE)
        return rec

    # ------------------------------------------------------------ sync

    @app.post("/api/tracker/sync")
    async def run_sync(body: SyncRequest, background_tasks: BackgroundTasks,
                       current_user: dict = Depends(get_current_user)):
        email = current_user["email"]
        if sync_running["value"]:
            return {"message": "A tracker sync is already running."}
        addr, pwd = tracker.gmail_credentials()
        if body.gmail and not (addr and pwd):
            body.gmail = False
            gmail_note = " Gmail skipped: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env."
        else:
            gmail_note = ""
        browser_lock = ns.get("browser_lock")
        if body.linkedin and browser_lock is not None and browser_lock.locked():
            return {"message": "The browser is busy with a search/apply task. Try the sync after it finishes."}

        async def job():
            sync_running["value"] = True
            result = {}
            all_state = load_state()
            st = user_state(all_state, email)
            recs = applications_db.get(email, [])
            try:
                if body.gmail:
                    # imaplib is blocking - run it in a thread so the API stays responsive
                    result["gmail"] = await asyncio.to_thread(tracker.sync_gmail, recs, st, addr, pwd, body.days)
                if body.linkedin:
                    result["linkedin"] = await _linkedin_sync(recs)
                    st["last_linkedin_sync"] = datetime.now().isoformat(timespec="seconds")
                result["no_response_marked"] = tracker.refresh_no_response(recs)
            except Exception as e:
                logger.exception("Tracker sync failed")
                result["error"] = f"{type(e).__name__}: {e}"
            finally:
                st["last_result"] = result
                save_state(all_state)
                save_db(applications_db, APPS_FILE)
                sync_running["value"] = False
                logger.info(f"Tracker sync finished: {result}")

        async def _linkedin_sync(recs):
            from playwright.async_api import async_playwright
            executor = ns["ApplicationExecutor"]({}, ns["ApplicationGuard"]({}))
            async with browser_lock:
                async with async_playwright() as p:
                    context, page = await ns["open_logged_in_linkedin"](p, executor)
                    if not context:
                        return {"error": "LinkedIn login not completed"}
                    try:
                        return await tracker.sync_linkedin_applied(page, recs)
                    finally:
                        await context.close()

        background_tasks.add_task(job)
        return {"message": "Tracker sync started." + gmail_note}

    @app.post("/api/tracker/digest")
    async def send_digest_now(current_user: dict = Depends(get_current_user)):
        addr, pwd = tracker.gmail_credentials()
        if not (addr and pwd):
            raise HTTPException(status_code=400, detail="Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env first.")
        email = current_user["email"]
        recs = applications_db.get(email, [])
        st = user_state(load_state(), email)
        subject, body = tracker.build_digest(recs, st)
        await asyncio.to_thread(tracker.send_digest, subject, body, addr, pwd, None)
        return {"message": f"Digest sent to {addr}", "subject": subject}

    logger.info("Tracker routes registered")
