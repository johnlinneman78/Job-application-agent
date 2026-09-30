# Auto Job Applier - Guarded Resume-Only Application Agent

## Overview

A **guarded, resumable job-application agent** that autonomously discovers and prepares job applications, applying **ONLY to resume-only jobs** on LinkedIn Easy Apply and Indeed Quick Apply.

### Hard Constraints (Non-Negotiable)

✅ **Apply ONLY when:**
- Job has LinkedIn Easy Apply OR Indeed Quick Apply
- Submission requires **resume upload or profile attach ONLY**
- **Zero free-text or multi-choice questions**
- No screening questions
- No assessments (HackerRank, Codility, etc.)
- No external ATS redirects (Workday, Greenhouse, Lever, etc.)

❌ **Skip immediately if:**
- Application includes ANY screening questions
- Application redirects to external ATS
- Application requires written responses
- Application requires answering multi-choice questions

🚫 **Never:**
- Brute-force or bypass application steps
- Attempt to answer questions programmatically
- Submit incomplete applications

---

## Features

### Autonomous Operations (No Permission Needed)
- ✓ Resume parsing and skill extraction
- ✓ Job discovery on LinkedIn and Indeed
- ✓ Guard checks to detect resume-only jobs
- ✓ Job ranking by skill match, title fit, location
- ✓ Dry-run report generation

### Guarded Operations (Permission Required)
- 🔐 Logging into LinkedIn or Indeed
- 🔐 Submitting applications
- 🔐 Sending email confirmations

---

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

---

## Configuration

Edit `config.yaml` to customize:

```yaml
# Job Search Preferences
search:
  keywords:
    - "software engineer"
    - "junior developer"
  
  locations:
    - "Remote"
    - "Portland, OR"
  
  max_applications: 50
  posted_within_days: 14

# Guard System (resume-only enforcement)
guards:
  strict_mode: true  # Never apply to jobs with questions
  
  external_ats:
    - "workday"
    - "greenhouse"
    - "lever"
  
  assessment_platforms:
    - "hackerrank"
    - "codility"
```

---

## Usage

### Dry-Run Mode (Recommended First)

```bash
# Discover and rank jobs WITHOUT submitting
python main.py data/resume.pdf --dry-run
```

**Output:**
- Resume analysis
- Role fit matrix
- Top 50 matched jobs (resume-only)
- Dry-run report table

### Real Application Mode

```bash
# Full workflow WITH permission gates
python main.py data/resume.pdf
```

**Workflow:**
1. Parse resume → ✓ Auto
2. Discover jobs → ✓ Auto
3. Guard check each job → ✓ Auto
4. Rank top 50 jobs → ✓ Auto
5. Show dry-run report → ✓ Auto
6. **STOP → Request permission**
7. Submit applications → 🔐 Requires approval
8. Email summary → 🔐 Requires approval

---

## Project Structure

```
job-application-agent/
├── src/
│   ├── models/
│   │   └── __init__.py         # Resume, Job, Application models
│   ├── resume_analyzer.py      # Parse resume, extract skills
│   ├── job_scraper.py          # LinkedIn + Indeed discovery
│   ├── job_ranker.py           # Score and rank jobs
│   ├── application_guard.py    # Hard constraint enforcement
│   └── executor.py             # [TODO] Guarded submission
├── data/
│   ├── resume.pdf              # Your resume (input)
│   ├── jobs_discovered.json    # Scraped jobs with guard results
│   └── jobs_ranked.json        # Top 50 ranked jobs
├── config.yaml                  # User preferences
├── main.py                      # Main orchestrator
├── requirements.txt
└── README.md
```

---

## How It Works

### Phase 1: Resume Intelligence

```python
analyzer = ResumeAnalyzer()
resume = analyzer.parse_resume("data/resume.pdf")

# Extracts:
# - Name, email, phone
# - Technical skills (Python, React, SQL, etc.)
# - Soft skills
# - Job titles, companies, years of experience
# - Education (degrees, schools)
```

### Phase 2: Job Discovery with Guards

```python
scraper = GuardedJobScraper(config, guard)
jobs = await scraper.discover_and_guard_check_jobs(
    titles=["software engineer"],
    locations=["Remote"],
    days_ago=14
)

# For each job:
# 1. Check for Easy Apply / Quick Apply
# 2. Open application modal
# 3. Scan for questions, assessments, external ATS
# 4. Return SAFE or SKIP with reason code
```

**Guard Detection Logic:**

```python
# LinkedIn Example
async def check_linkedin_job(page):
    # Click "Easy Apply" button
    await easy_apply_button.click()
    
    # Check for red flags
    if modal.locator('textarea').count() > 0:
        return SKIP_QUESTIONS  # Text input detected
    
    if "screening" in modal.text():
        return SKIP_QUESTIONS
    
    if "hackerrank" in modal.text():
        return SKIP_ASSESSMENT
    
    if "Next" button without "Review":
        return SKIP_QUESTIONS  # Multi-step form
    
    # If clean, return SAFE
    return SAFE
```

### Phase 3: Job Ranking

```python
ranker = JobRanker(resume)
ranked_jobs = ranker.rank_jobs(jobs, limit=50)

# Scoring:
# - Skill match (40%)
# - Title alignment (25%)
# - Seniority fit (15%)
# - Location match (10%)
# - Application friction - resume-only preferred (10%)
```

### Phase 4: Dry-Run Report

Displays a table of top job matches:

```
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ #  ┃ Company             ┃ Title                          ┃ Platform   ┃ Location       ┃ Match   ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ 1  │ Acme Corp           │ Software Engineer              │ linkedin   │ Remote         │ 92%     │
│ 2  │ XYZ Inc             │ Junior Developer               │ indeed     │ Portland, OR   │ 88%     │
...
```

### Phase 5: Permission Gate

Before any external actions, agent **STOPS** and asks:

```
⚠️  PERMISSION REQUIRED

Ready to apply to 50 jobs.
This will:
  1. Log into LinkedIn and/or Indeed
  2. Submit resume-only applications
  3. Track all submissions

Do you want to proceed? (y/n):
```

---

## Safety Guarantees

✅ **Never bypass application questions** - Guard blocks immediately  
✅ **Never brute-force** - Guard fails safely if unexpected UI appears  
✅ **Permission-gated sensitive actions** - Login and submit require explicit approval  
✅ **Full audit trail** - All actions logged with timestamps  
✅ **Headful browser** - User can see and stop agent at any time  
✅ **Rate limiting** - Human-like delays (2-5 min) between applications  

---

## Current Status

**Implemented:**
- ✅ Phase 1: Resume parsing and analysis
- ✅ Phase 2: Job discovery with guard checks
- ✅ Phase 3: Job ranking system
- ✅ Phase 4: Dry-run report generation
- ✅ Phase 5: Permission gate system
- ✅ Phase 6: Executor (guarded submission logic)
- ✅ Data models (Resume, Job, Application)
- ✅ Application guard (LinkedIn + Indeed)

**TODO:**
- ⏳ Phase 7: Email reporter
- ⏳ Phase 8: Resumability (save/load state)
- ⏳ Testing suite

---

## Testing

```bash
# Test resume parsing
python -c "from src.resume_analyzer import ResumeAnalyzer; \
           analyzer = ResumeAnalyzer(); \
           resume = analyzer.parse_resume('data/resume.pdf'); \
           print(resume)"

# Test dry-run (no submissions)
python main.py data/resume.pdf --dry-run
```

---

## Troubleshooting

### "No Easy Apply jobs found"
- Check that `f_AL=true` is in LinkedIn search URL (Easy Apply filter)
- Verify job postings actually have Easy Apply option
- Try broader search keywords

### "Guard check takes too long"
- Guard checks are headful (visible browser) and rate-limited
- Expected: ~2-3 seconds per job
- For 75 jobs: ~3-5 minutes total

### "Resume parsing failed"
- Ensure resume is PDF format (not image-based PDF)
- Check that PyPDF2 can extract text: `pdftotext resume.pdf -`

---

## License

MIT License - Use responsibly and in compliance with platform terms of service.

---

## Disclaimer

**IMPORTANT:** This tool automates browser interactions with LinkedIn and Indeed. Users are responsible for compliance with platform terms of service. The authors are not liable for any account restrictions or violations resulting from use of this software.

**Platform Policies:**
- Review LinkedIn's and Indeed's terms of service before use
- Use at your own risk
- Consider rate limiting and human-like behavior to avoid detection

---

## Contributing

Contributions welcome! Key areas:
- **Executor implementation** (Phase 6)
- **Email reporter** (Phase 7)
- **Improved resume parsing** (extract more fields)
- **Better guard detection** (handle edge cases)
- **Testing suite** (unit + integration tests)

---

**Built with:**
- Python 3.11+
- Playwright (browser automation)
- Pydantic (data validation)
- Rich (terminal UI)
