"""
Data models for job application agent.
"""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class Resume(BaseModel):
    """Parsed resume data model."""
    
    name: str
    email: str
    phone: str
    
    # Skills
    technical_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    
    # Experience
    job_titles: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)
    years_of_experience: float = 0.0
    
    # Education
    degrees: List[str] = Field(default_factory=list)
    schools: List[str] = Field(default_factory=list)
    
    # Raw text
    raw_text: str = ""
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1-555-0123",
                "technical_skills": ["Python", "JavaScript", "React"],
                "soft_skills": ["Communication", "Leadership"],
                "job_titles": ["Software Engineer", "Developer"],
                "years_of_experience": 3.5
            }
        }


class GuardStatus(str, Enum):
    """Guard check result status."""
    SAFE = "safe"  # Resume-only, safe to apply
    SKIP_QUESTIONS = "skip_questions"  # Has custom questions
    SKIP_ASSESSMENT = "skip_assessment"  # Requires assessment
    SKIP_EXTERNAL_ATS = "skip_external_ats"  # Redirects to external ATS
    SKIP_NO_EASY_APPLY = "skip_no_easy_apply"  # No Easy Apply/Quick Apply
    UNKNOWN = "unknown"  # Could not determine


class Platform(str, Enum):
    """Job platform."""
    LINKEDIN = "linkedin"
    INDEED = "indeed"


class Job(BaseModel):
    """Job listing data model."""
    
    # Basic info
    job_id: str
    platform: Platform
    title: str
    company: str
    location: str
    
    # Details
    description: str = ""
    requirements: List[str] = Field(default_factory=list)
    salary_range: Optional[str] = None
    posted_date: Optional[datetime] = None
    url: str
    
    # Guard status
    guard_status: GuardStatus = GuardStatus.UNKNOWN
    guard_reason: str = ""
    has_easy_apply: bool = False
    
    # Ranking
    match_score: float = 0.0
    skill_match: float = 0.0
    title_match: float = 0.0
    location_match: float = 0.0
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "12345",
                "platform": "linkedin",
                "title": "Software Engineer",
                "company": "Acme Corp",
                "location": "Remote",
                "url": "https://linkedin.com/jobs/12345",
                "guard_status": "safe",
                "has_easy_apply": True,
                "match_score": 0.92
            }
        }


class ApplicationStatus(str, Enum):
    """Application submission status."""
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    FAILED = "failed"


class Application(BaseModel):
    """Application tracking model."""
    
    # Reference
    job: Job
    
    # Application materials
    resume_path: str
    tailored_resume_path: Optional[str] = None
    
    # Status
    status: ApplicationStatus = ApplicationStatus.PREPARED
    submission_timestamp: Optional[datetime] = None
    
    # Metadata
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    confirmation_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "job": {
                    "job_id": "12345",
                    "platform": "linkedin",
                    "title": "Software Engineer",
                    "company": "Acme Corp"
                },
                "resume_path": "data/resume.pdf",
                "status": "submitted",
                "confirmation_id": "APP-2026-12345"
            }
        }
