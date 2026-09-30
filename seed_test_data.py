import json
import os
from pathlib import Path
from datetime import datetime

base_dir = Path(r"c:\Users\uriel\.gemini\antigravity\scratch\job-application-agent")
backend_data_dir = base_dir / "backend" / "data"
jobs_file = backend_data_dir / "jobs.json"
configs_file = backend_data_dir / "configs.json"
source_jobs_file = base_dir / "data" / "jobs_discovered.json"
resume_path = str(base_dir / "data" / "resume.pdf")

user_email = "agent@test.com"

# 1. Update Config with Resume Path
if configs_file.exists():
    with open(configs_file, "r") as f:
        configs = json.load(f)
    if user_email in configs:
        configs[user_email]["personal_info"]["resume_path"] = resume_path
        with open(configs_file, "w") as f:
            json.dump(configs, f, indent=2)
        print(f"Updated config for {user_email} with resume path: {resume_path}")

# 2. Seed Jobs from discovered source
if source_jobs_file.exists():
    with open(source_jobs_file, "r") as f:
        discovered_jobs = json.load(f)
    
    # Take first 5 jobs and format for backend
    backend_jobs = []
    for j in discovered_jobs[:5]:
        backend_jobs.append({
            "id": j.get("job_id", f"job_{os.urandom(4).hex()}"),
            "title": j.get("title", "Software Engineer"),
            "company": j.get("company", "Tech Corp"),
            "location": j.get("location", "Remote"),
            "url": j.get("url", "https://linkedin.com"),
            "platform": "linkedin",
            "match_score": 0.9,
            "status": "queued",
            "discovered_at": datetime.now().isoformat()
        })
    
    with open(jobs_file, "r") as f:
        existing_jobs_db = json.load(f)
    
    existing_jobs_db[user_email] = backend_jobs
    
    with open(jobs_file, "w") as f:
        json.dump(existing_jobs_db, f, indent=2)
    print(f"Seeded {len(backend_jobs)} jobs for {user_email}")
else:
    print(f"Source jobs file not found at {source_jobs_file}")
