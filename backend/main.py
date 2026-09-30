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
    from src.models import Resume, Job, Application as AgentApplication, Platform
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
            with open(file_path, 'r') as f:
                return json.load(f)
        except: return {}
    return {}

def save_db(data, file_path):
    with open(file_path, 'w') as f:
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
    except jwt.JWTError:
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
    
    # Update config with resume path
    config = configs_db.get(current_user["email"])
    if config:
        config["personal_info"]["resume_path"] = str(file_path)
        configs_db[current_user["email"]] = config
    
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
    user_email = current_user["email"]
    config = configs_db.get(user_email)
    
    if not config:
        raise HTTPException(status_code=400, detail="Search configuration not found. Please update settings first.")

    # Find resume path
    resume_path = config["personal_info"].get("resume_path")
    if not resume_path or not os.path.exists(resume_path):
        raise HTTPException(status_code=400, detail="Resume not found. Please upload a PDF in Settings.")

    async def run_scraper():
        try:
            logger.info(f"Starting background scraper for {user_email}")
            
            # 1. Instantiate Guard (required by scraper)
            guard = ApplicationGuard(config)
            
            # 2. Instantiate Scraper
            # Signature: JobScraper(config: dict, guard: ApplicationGuard)
            scraper = GuardedJobScraper(config, guard)
            
            # 3. Trigger Discovery
            # Signature: discover_and_guard_check_jobs(titles, locations, days_ago)
            discovered_jobs = await scraper.discover_and_guard_check_jobs(
                titles=config["search"]["keywords"],
                locations=config["search"]["locations"],
                days_ago=config["search"]["posted_within_days"]
            )
            
            processed_jobs = []
            for j in discovered_jobs:
                # Map back to storage format
                processed_jobs.append({
                    "id": str(os.urandom(4).hex()),
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "url": j.url,
                    "platform": j.platform.value if hasattr(j.platform, 'value') else str(j.platform),
                    "match_score": 0.85, # Scraper handles matching internally
                    "status": "queued",
                    "discovered_at": datetime.now().isoformat()
                })
            
            jobs_db[user_email] = processed_jobs
            save_db(jobs_db, JOBS_FILE)
            logger.info(f"Scraper finished for {user_email}. Found {len(processed_jobs)} jobs.")
        except Exception as e:
            logger.error(f"Scraper task failed for {user_email}: {str(e)}")
            import traceback
            traceback.print_exc()

    background_tasks.add_task(run_scraper)
    return {"message": "Job search initiated. Check back in ~60s."}

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

    async def run_executor():
        try:
            logger.info(f"Starting executor background task for {user_email}")
            if not resume_path or not os.path.exists(resume_path):
                logger.error(f"Executor failed: Resume not found at {resume_path}")
                return

            # Instantiate components
            guard = ApplicationGuard(config)
            executor = ApplicationExecutor(config, guard)
            
            from playwright.async_api import async_playwright
            user_data_dir = WORKSPACE_ROOT / "data" / "browser_context"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            async with async_playwright() as p:
                # Launch headful browser for the user to see/interact if needed
                logger.info(f"Launching headful browser with persistent context for {user_email}...")
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir.absolute()),
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                    viewport={"width": 1280, "height": 800}
                )
                page = context.pages[0] if context.pages else await context.new_page()
                
                # Check login status - robust DOM check
                await page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000) # Give it extra time for state to settle
                
                # Check for profile icon (logged in) or 'Sign in' buttons (logged out)
                is_logged_in = await page.locator(".global-nav__me-photo, #global-nav-typeahead").count() > 0
                is_login_page = "login" in page.url or "checkpoint" in page.url or await page.locator("button.sign-in-form__submit-button").count() > 0
                
                if not is_logged_in or is_login_page:
                    logger.info("  Login required. Waiting for user to log in manually...")
                    # The login_to_linkedin method in executor handles the wait
                    await executor.login_to_linkedin(page)
                
                # Inject session into executor
                executor.context = context
                executor.page = page

                for job_data in queued_jobs:
                    # Convert back to Agent models
                    from src.models import Job as CoreJob, Platform as CorePlatform
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
                    
                    # Execute Application
                    app_result = await executor.submit_application(agent_job, resume_path)
                    success = app_result.status == ApplicationStatus.SUBMITTED
                    
                    status = "submitted" if success else "failed"
                    job_data["status"] = status
                    
                    # Capture failure reason if available
                    failure_reason = app_result.error_message if not success else None
                    if not success and not failure_reason:
                        failure_reason = "Unknown automation failure"

                    app_record = {
                        "id": f"app_{os.urandom(4).hex()}",
                        "job": job_data,
                        "status": status,
                        "applied_at": datetime.now().isoformat(),
                        "failure_reason": failure_reason
                    }
                    
                    if user_email not in applications_db:
                        applications_db[user_email] = []
                    applications_db[user_email].append(app_record)
                    
                    save_db(applications_db, APPS_FILE)
                    save_db(jobs_db, JOBS_FILE)
                    
                    logger.info(f"Processed job: {agent_job.title} -> {status}")

            logger.info(f"Executor finished for {user_email}")
        except Exception as e:
            logger.error(f"Executor task failed: {str(e)}")
            import traceback
            traceback.print_exc()

    background_tasks.add_task(run_executor)
    return {"message": "Agent deployed. Watch terminal/History page for results."}

@app.get("/api/applications/stats")
async def get_application_stats(current_user: dict = Depends(get_current_user)):
    """Get application statistics."""
    applications = applications_db.get(current_user["email"], [])
    
    total = len(applications)
    submitted = len([a for a in applications if a["status"] == "submitted"])
    failed = len([a for a in applications if a["status"] == "failed"])
    
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
        "success_rate": 85.0  # Placeholder
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
