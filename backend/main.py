"""
Job Application Agent - FastAPI Backend
Main application entry point
"""
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
from pathlib import Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timedelta
import jwt
import bcrypt
import logging
import json
import sys
import os
from pathlib import Path
from collections import deque

# Add workspace root to sys.path to allow importing from src/
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.append(str(WORKSPACE_ROOT))

# Fix for Windows console UnicodeEncodeError
if sys.platform == "win32":
    import io
    # Ensure stdout/stderr use utf-8 and don't crash on problematic chars
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Imports from core agent
try:
    from src.models import Resume, Job, Application as AgentApplication, Platform, ApplicationStatus
    from src.job_scraper import GuardedJobScraper
    from src.executor import ApplicationExecutor
    from src.application_guard import ApplicationGuard
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    # Fallback to local placeholders if src not found (will fail at runtime, but helpful for diagnosis)
    class Platform: LINKEDIN = "linkedin"; INDEED = "indeed"

# Initialize FastAPI
app = FastAPI(
    title="Job Application Agent API",
    description="Automated job application system with golden selectors",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
ALGORITHM = "HS256"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log Buffer for UI
log_buffer = deque(maxlen=100)

class UIHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": msg
            })
        except Exception:
            self.handleError(record)

ui_handler = UIHandler()
ui_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(ui_handler)
# Ensure src logs also go to the buffer
logging.getLogger("src").addHandler(ui_handler)

# ==================== MODELS ====================

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class JobSearchConfig(BaseModel):
    keywords: List[str]
    locations: List[str]
    seniority: List[str]
    platforms: List[str] = ["linkedin"]
    max_applications: int = 10
    posted_within_days: int = 14

class PersonalInfo(BaseModel):
    name: str
    email: EmailStr
    phone: str
    address: str
    city: str
    state: str
    zip_code: str
    years_of_experience: int
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    resume_path: Optional[str] = None

class ApplicationSettings(BaseModel):
    min_delay: int = 120
    max_delay: int = 300
    auto_answer_screening: bool = True

class ScreeningAnswers(BaseModel):
    work_authorization: str = "Yes"
    require_sponsorship: str = "No"
    remote_preference: str = "Yes"
    willing_to_relocate: str = "No"
    expected_salary: str = "120000"
    start_date: str = "Immediately"

class Configuration(BaseModel):
    personal_info: PersonalInfo
    search: JobSearchConfig
    application: ApplicationSettings
    screening_answers: ScreeningAnswers

class JobSchema(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    platform: str = "linkedin"
    match_score: float = 0.0
    status: str = "queued"
    discovered_at: datetime = datetime.now()

class ApplicationSchema(BaseModel):
    id: str
    job: JobSchema
    status: str
    applied_at: datetime
    failure_reason: Optional[str] = None

class EmailReportConfig(BaseModel):
    frequency: str  # daily, weekly, monthly
    recipients: List[EmailStr]
    time: str  # HH:MM format
    enabled: bool = True

# ==================== IN-MEMORY STORAGE (MVP) ====================
# TODO: Replace with PostgreSQL in production

# File-based storage paths
DB_DIR = WORKSPACE_ROOT / "backend" / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = DB_DIR / "users.json"
CONFIGS_FILE = DB_DIR / "configs.json"
JOBS_FILE = DB_DIR / "jobs.json"
APPS_FILE = DB_DIR / "applications.json"

def load_db(file_path):
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except: return {}
    return {}

def save_db(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# Load databases
users_db = load_db(USERS_FILE)
configs_db = load_db(CONFIGS_FILE)
jobs_db = load_db(JOBS_FILE)
applications_db = load_db(APPS_FILE)
email_reports_db = {} 

# Constants
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ==================== BROWSER HELPERS ====================
import asyncio
# Only one browser task at a time: search and apply share the same saved
# LinkedIn profile folder, and Chromium locks that folder while it is open.
browser_lock = asyncio.Lock()
active_browser_task = None
active_task_type = None
active_browser_context = None
stop_requested = False
BROWSER_PROFILE_DIR = WORKSPACE_ROOT / "data" / "browser_context"


async def open_logged_in_linkedin(p, executor):
    """Launch the saved Chromium profile and make sure LinkedIn is logged in.
    Returns (context, page), or (None, None) if login was not completed."""
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE_DIR.absolute()),
        headless=False,  # LinkedIn login needs a visible window
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
    )
    page = context.pages[0] if context.pages else await context.new_page()
    if not await executor.login_to_linkedin(page):
        logger.error("LinkedIn login not completed - stopping.")
        await context.close()
        return None, None
    return context, page

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Decode JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:  # PyJWT has no JWTError (that was python-jose)
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user."""
    token = credentials.credentials
    payload = decode_token(token)
    email = payload.get("sub")
    if email not in users_db:
        raise HTTPException(status_code=401, detail="User not found")
    return users_db[email]

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(user: UserRegister):
    """Register new user."""
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_data = {
        "email": user.email,
        "full_name": user.full_name,
        "password_hash": hash_password(user.password),
        "created_at": datetime.now().isoformat(),
        "is_active": True
    }
    users_db[user.email] = user_data
    save_db(users_db, USERS_FILE)
    
    # Create access token
    token = create_access_token({"sub": user.email})
    
    # Return token and user info (without password)
    user_info = {k: v for k, v in user_data.items() if k != "password_hash"}
    
    logger.info(f"User registered: {user.email}")
    print(f"DEBUG: Processed registration for {user.email}")
    return TokenResponse(access_token=token, user=user_info)

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """Login user."""
    user = users_db.get(credentials.email)
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create token
    token = create_access_token({"sub": credentials.email})
    
    # Return token and user info
    user_info = {k: v for k, v in user.items() if k != "password_hash"}
    
    logger.info(f"User logged in: {credentials.email}")
    print(f"DEBUG: Processed login for {credentials.email}")
    return TokenResponse(access_token=token, user=user_info)

@app.post("/api/auth/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout user (client should delete token)."""
    logger.info(f"User logged out: {current_user['email']}")
    return {"message": "Logged out successfully"}

# ==================== CONFIGURATION ENDPOINTS ====================

@app.get("/api/config")
async def get_config(current_user: dict = Depends(get_current_user)):
    """Get user configuration."""
    config = configs_db.get(current_user["email"])
    if not config:
        # Return default configuration
        return {
            "personal_info": {
                "name": current_user["full_name"],
                "email": current_user["email"],
                "phone": "",
                "address": "",
                "city": "",
                "state": "",
                "zip_code": "",
                "years_of_experience": 0,
                "linkedin_url": "",
                "portfolio_url": ""
            },
            "search": {
                "keywords": ["customer service", "sales"],
                "locations": ["Remote"],
                "seniority": ["Entry Level"],
                "platforms": ["linkedin"],
                "max_applications": 10,
                "posted_within_days": 14
            },
            "application": {
                "min_delay": 10,
                "max_delay": 30,
                "auto_answer_screening": True
            },
            "screening_answers": {
                "work_authorization": "Yes",
                "require_sponsorship": "No",
                "remote_preference": "Yes",
                "willing_to_relocate": "No",
                "expected_salary": "120000",
                "start_date": "Immediately"
            }
        }
    return config

@app.put("/api/config")
async def update_config(config: Configuration, current_user: dict = Depends(get_current_user)):
    """Update user configuration."""
    configs_db[current_user["email"]] = config.dict()
    save_db(configs_db, CONFIGS_FILE)
    logger.info(f"Configuration updated: {current_user['email']}")
    return {"message": "Configuration updated successfully", "config": config}

@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload resume for the user."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    user_dir = UPLOAD_DIR / current_user["email"]
    user_dir.mkdir(exist_ok=True)
    
    file_path = user_dir / "resume.pdf"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update config with resume path (create default config if none saved yet)
    config = configs_db.get(current_user["email"]) or await get_config(current_user)
    config["personal_info"]["resume_path"] = str(file_path.absolute())
    configs_db[current_user["email"]] = config
    save_db(configs_db, CONFIGS_FILE)
    
    logger.info(f"Resume uploaded for {current_user['email']}: {file_path}")
    return {"message": "Resume uploaded successfully", "path": str(file_path)}

# ==================== JOB ENDPOINTS ====================

@app.get("/api/jobs/queue")
async def get_job_queue(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get job queue with optional filtering."""
    jobs = jobs_db.get(current_user["email"], [])
    
    if status:
        jobs = [j for j in jobs if j.get("status") == status]
    
    return {"jobs": jobs, "total": len(jobs)}

@app.post("/api/jobs/search")
async def trigger_job_search(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Trigger real job search via the agent."""
    global active_browser_task, active_task_type, stop_requested
    user_email = current_user["email"]
    config = configs_db.get(user_email)
    
    if not config:
        raise HTTPException(status_code=400, detail="Search configuration not found. Please update settings first.")

    # Find resume path (optional since LinkedIn retains uploaded resume)
    resume_path = config["personal_info"].get("resume_path")
    if not resume_path or not Path(resume_path).is_file():
        for cand in [Path("data/resume.pdf"), Path("uploads") / user_email / "resume.pdf", Path("backend/uploads") / user_email / "resume.pdf"]:
            if cand.is_file():
                resume_path = str(cand.absolute())
                config["personal_info"]["resume_path"] = resume_path
                break

    if browser_lock.locked() or (active_browser_task and not active_browser_task.done()):
        task_label = active_task_type or "task"
        return {"message": f"A {task_label} is already running. Click 'Stop Task' to cancel it if needed."}

    stop_requested = False

    async def run_scraper():
        global active_browser_task, active_task_type, active_browser_context, stop_requested
        async with browser_lock:
            active_browser_task = asyncio.current_task()
            active_task_type = "search"
            try:
                logger.info(f"Starting background scraper for {user_email}")
                from playwright.async_api import async_playwright
                guard = ApplicationGuard(config)
                executor = ApplicationExecutor(config, guard)
                scraper = GuardedJobScraper(config, guard)

                # Initialize ranker if resume exists
                ranker = None
                if resume_path and Path(resume_path).is_file():
                    try:
                        from src.resume_analyzer import ResumeAnalyzer
                        from src.job_ranker import JobRanker
                        analyzer = ResumeAnalyzer()
                        parsed_resume = analyzer.parse_resume(resume_path)
                        ranker = JobRanker(parsed_resume)
                        logger.info(f"Initialized JobRanker for scoring with resume: {resume_path}")
                    except Exception as e:
                        logger.warning(f"Failed to initialize JobRanker: {e}")

                # Incremental safe job callback so jobs appear immediately in the queue
                async def on_safe_job(job):
                    if ranker:
                        try:
                            ranker.score_job(job)
                        except Exception as e:
                            logger.warning(f"Could not score job {job.title}: {e}")

                    # Generate personalized follow-up note template if recruiter is found (LinkedHelper tip)
                    follow_up_note = ""
                    if getattr(job, 'recruiter_name', None):
                        first_name = job.recruiter_name.split()[0]
                        candidate_name = config.get("personal_info", {}).get("name", "Applicant")
                        top_skill = job.matched_skills[0] if getattr(job, 'matched_skills', None) else "account management"
                        follow_up_note = (
                            f"Hi {first_name}, I recently submitted my application for the {job.title} role at {job.company} via Easy Apply. "
                            f"With my background in {top_skill} and client success, I would love the chance to connect and introduce myself. Best, {candidate_name}"
                        )

                    processed = {
                        "id": job.job_id,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "url": job.url,
                        "platform": job.platform.value if hasattr(job.platform, 'value') else str(job.platform),
                        "match_score": job.match_score,
                        "recruiter_name": getattr(job, 'recruiter_name', None),
                        "recruiter_url": getattr(job, 'recruiter_url', None),
                        "matched_skills": getattr(job, 'matched_skills', []),
                        "follow_up_note": follow_up_note,
                        "status": "queued",
                        "discovered_at": datetime.now().isoformat()
                    }
                    current_list = jobs_db.get(user_email, [])
                    if not any(x["id"] == job.job_id for x in current_list):
                        current_list.append(processed)
                        jobs_db[user_email] = current_list
                        save_db(jobs_db, JOBS_FILE)

                async with async_playwright() as p:
                    context, page = await open_logged_in_linkedin(p, executor)
                    if not context:
                        return
                    active_browser_context = context
                    discovered_jobs = await scraper.discover_and_guard_check_jobs(
                        titles=config["search"]["keywords"],
                        locations=config["search"]["locations"],
                        days_ago=config["search"]["posted_within_days"],
                        context=context,
                        on_job_found=on_safe_job
                    )
                    await context.close()

                logger.info(f"Scraper finished for {user_email}. Total safe jobs in queue: {len(jobs_db.get(user_email, []))}")
            except asyncio.CancelledError:
                logger.info(f"Scraper task stopped for {user_email}.")
            except Exception as e:
                logger.error(f"Scraper task failed for {user_email}: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                active_browser_task = None
                active_task_type = None
                active_browser_context = None

    background_tasks.add_task(run_scraper)
    return {"message": "Job search started. Matching jobs will appear in your queue live!"}

@app.put("/api/jobs/{job_id}/skip")
async def skip_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Skip a job."""
    jobs = jobs_db.get(current_user["email"], [])
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = "skipped"
            logger.info(f"Job skipped: {job_id} by {current_user['email']}")
            return {"message": "Job skipped", "job": job}
    
    raise HTTPException(status_code=404, detail="Job not found")

@app.get("/api/agent/status")
async def get_agent_status(current_user: dict = Depends(get_current_user)):
    """Check running state of browser tasks."""
    is_running = (active_browser_task is not None and not active_browser_task.done()) or browser_lock.locked()
    return {
        "is_running": is_running,
        "task_type": active_task_type if is_running else None
    }

@app.post("/api/agent/stop")
async def stop_agent(current_user: dict = Depends(get_current_user)):
    """Stop any active search or application task."""
    global active_browser_task, active_task_type, active_browser_context, stop_requested
    stop_requested = True
    stopped = False

    if active_browser_task and not active_browser_task.done():
        active_browser_task.cancel()
        task_name = active_task_type or "task"
        logger.info(f"Stop signal sent for active {task_name} by {current_user['email']}")
        stopped = True

    if active_browser_context:
        try:
            await active_browser_context.close()
        except Exception:
            pass
        active_browser_context = None

    active_browser_task = None
    active_task_type = None

    return {"message": "Agent task stopped successfully." if stopped else "No active agent task was running."}

@app.post("/api/jobs/reset")
async def reset_jobs(current_user: dict = Depends(get_current_user)):
    """Reset and clear discovered jobs queue for current user."""
    user_email = current_user["email"]
    jobs_db[user_email] = []
    save_db(jobs_db, JOBS_FILE)
    logger.info(f"Jobs queue reset for {user_email}")
    return {"message": "Queue and search results reset successfully."}

# ==================== APPLICATION ENDPOINTS ====================

@app.get("/api/applications")
async def get_applications(current_user: dict = Depends(get_current_user)):
    """Get application history."""
    applications = applications_db.get(current_user["email"], [])
    return {"applications": applications, "total": len(applications)}

@app.post("/api/applications/start")
async def start_applications(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Start the real guarded application process."""
    user_email = current_user["email"]
    jobs = jobs_db.get(user_email, [])
    queued_jobs = [j for j in jobs if j["status"] == "queued"]
    
    if not queued_jobs:
        return {"message": "No jobs in queue to apply for."}

    config = configs_db.get(user_email)
    if not config:
        raise HTTPException(status_code=400, detail="Configuration missing.")

    resume_path = config["personal_info"].get("resume_path")
    if not resume_path or not Path(resume_path).is_file():
        for cand in [Path("data/resume.pdf"), Path("uploads") / user_email / "resume.pdf", Path("backend/uploads") / user_email / "resume.pdf"]:
            if cand.is_file():
                resume_path = str(cand.absolute())
                config["personal_info"]["resume_path"] = resume_path
                break
        if not resume_path or not Path(resume_path).is_file():
            resume_path = ""

    if browser_lock.locked() or (active_browser_task and not active_browser_task.done()):
        task_label = active_task_type or "task"
        return {"message": f"A {task_label} is already running. Click 'Stop Task' to cancel it if needed."}

    async def run_executor():
        global active_browser_task, active_task_type, active_browser_context
        async with browser_lock:
            active_browser_task = asyncio.current_task()
            active_task_type = "apply"
            try:
                logger.info(f"Starting executor background task for {user_email} (resume_path='{resume_path}')")

                guard = ApplicationGuard(config)
                executor = ApplicationExecutor(config, guard)
                executor.resume_path = resume_path
                max_apps = int(config.get("search", {}).get("max_applications", 10))

                from playwright.async_api import async_playwright
                from src.models import Job as CoreJob, Platform as CorePlatform

                async with async_playwright() as p:
                    context, page = await open_logged_in_linkedin(p, executor)
                    if not context:
                        return
                    active_browser_context = context
                    executor.context = context
                    executor.page = page

                    batch = queued_jobs[:max_apps]
                    for n, job_data in enumerate(batch):
                        agent_job = CoreJob(
                            job_id=job_data["id"],
                            title=job_data["title"],
                            company=job_data["company"],
                            location=job_data["location"],
                            url=job_data["url"],
                            platform=CorePlatform.LINKEDIN if "linkedin" in job_data["platform"].lower() else CorePlatform.INDEED
                        )

                        job_data["status"] = "in_progress"
                        save_db(jobs_db, JOBS_FILE)

                        app_result = await executor.apply_to_linkedin_job(agent_job, resume_path)
                        status = app_result.status.value  # submitted / skipped / failed
                        job_data["status"] = status

                        app_record = {
                            "id": f"app_{os.urandom(4).hex()}",
                            "job": job_data,
                            "status": status,
                            "applied_at": datetime.now().isoformat(),
                            "failure_reason": None if status == "submitted" else (app_result.error_message or "Unknown")
                        }
                        applications_db.setdefault(user_email, []).append(app_record)
                        save_db(applications_db, APPS_FILE)
                        save_db(jobs_db, JOBS_FILE)
                        logger.info(f"Processed job: {agent_job.title} -> {status} ({app_record['failure_reason'] or 'ok'})")

                        if n < len(batch) - 1:
                            delay = executor._delay_seconds()
                            logger.info(f"Waiting {delay}s before next application...")
                            await asyncio.sleep(delay)

                    await context.close()
                logger.info(f"Executor finished for {user_email}")
            except asyncio.CancelledError:
                logger.info(f"Executor stopped by user for {user_email}")
                for j in queued_jobs:
                    if j.get("status") == "in_progress":
                        j["status"] = "queued"
                save_db(jobs_db, JOBS_FILE)
            except Exception as e:
                logger.error(f"Executor task failed: {str(e)}")
                import traceback
                traceback.print_exc()
                for j in queued_jobs:
                    if j.get("status") == "in_progress":
                        j["status"] = "failed"
                save_db(jobs_db, JOBS_FILE)
            finally:
                active_browser_task = None
                active_task_type = None
                active_browser_context = None

    background_tasks.add_task(run_executor)
    return {"message": "Application submissions started in background."}

@app.get("/api/applications/stats")
async def get_application_stats(current_user: dict = Depends(get_current_user)):
    """Get application statistics."""
    applications = applications_db.get(current_user["email"], [])
    
    total = len(applications)
    submitted = len([a for a in applications if a["status"] == "submitted"])
    failed = len([a for a in applications if a["status"] in ("failed", "skipped")])
    
    return {
        "total_applications": total,
        "submitted": submitted,
        "failed": failed,
        "success_rate": (submitted / total * 100) if total > 0 else 0
    }

# ==================== REPORT ENDPOINTS ====================

@app.get("/api/reports/summary")
async def get_report_summary(current_user: dict = Depends(get_current_user)):
    """Get summary statistics."""
    applications = applications_db.get(current_user["email"], [])
    jobs = jobs_db.get(current_user["email"], [])
    
    return {
        "total_applications": len(applications),
        "jobs_in_queue": len([j for j in jobs if j["status"] == "queued"]),
        "applications_today": len([a for a in applications 
                                   if datetime.fromisoformat(a["applied_at"]).date() == datetime.now().date()]),
        "success_rate": (len([a for a in applications if a["status"] == "submitted"]) / len(applications) * 100) if applications else 0
    }

@app.post("/api/reports/schedule-email")
async def schedule_email_report(
    config: EmailReportConfig,
    current_user: dict = Depends(get_current_user)
):
    """Schedule email report."""
    email_reports_db[current_user["email"]] = config.dict()
    logger.info(f"Email report scheduled: {current_user['email']}, frequency: {config.frequency}")
    return {"message": "Email report scheduled", "config": config}

# ==================== HEALTH CHECK ====================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Job Application Agent API",
        "docs": "/docs",
        "health": "/api/health"
    }

@app.get("/api/debug")
async def debug_info():
    """Get debug information."""
    return {
        "users_count": len(users_db),
        "configs_count": len(configs_db),
        "jobs_count": len(jobs_db),
        "uptime": datetime.now().isoformat()
    }

@app.get("/api/logs")
async def get_logs(current_user: dict = Depends(get_current_user)):
    """Get the latest logs for the UI."""
    return {"logs": list(log_buffer)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
