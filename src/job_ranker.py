"""
Job Ranker - Score and rank jobs based on resume fit.

Phase 4: Job Ranking
"""
from typing import List
from src.models import Resume, Job
import logging

logger = logging.getLogger(__name__)


class JobRanker:
    """
    Rank jobs based on multiple criteria:
    - Skill match (40%)
    - Title alignment (25%)
    - Seniority fit (15%)
    - Location match (10%)
    - Application friction (10%) - prefer resume-only
    """
    
    def __init__(self, resume: Resume):
        self.resume = resume
        self.resume_skills_set = set([s.lower() for s in resume.technical_skills])
        self.resume_titles_set = set([t.lower() for t in resume.job_titles])
    
    def score_job(self, job: Job) -> float:
        """
        Score a single job.
        
        Returns:
            Float score between 0.0 and 1.0
        """
        # Extract skills from job description
        job_skills = self._extract_skills_from_description(job.description)
        
        # Score components
        skill_score = self._score_skill_match(job_skills) * 0.40
        title_score = self._score_title_match(job.title) * 0.25
        seniority_score = self._score_seniority_fit(job.title) * 0.15
        location_score = self._score_location_match(job.location) * 0.10
        friction_score = self._score_application_friction(job) * 0.10
        
        total_score = skill_score + title_score + seniority_score + location_score + friction_score
        
        # Store individual scores
        job.skill_match = skill_score / 0.40  # Normalize back to 0-1
        job.title_match = title_score / 0.25
        job.location_match = location_score / 0.10
        job.match_score = round(total_score, 3)
        
        return job.match_score
    
    def rank_jobs(self, jobs: List[Job], limit: int = 50) -> List[Job]:
        """
        Rank jobs and return top N.
        
        Args:
            jobs: List of jobs to rank
            limit: Max number of jobs to return
            
        Returns:
            Sorted list of top jobs
        """
        logger.info(f"Ranking {len(jobs)} jobs...")
        
        # Score all jobs
        for job in jobs:
            self.score_job(job)
        
        # Sort by match_score descending
        ranked_jobs = sorted(jobs, key=lambda j: j.match_score, reverse=True)
        
        # Return top N
        top_jobs = ranked_jobs[:limit]
        
        logger.info(f"Ranked {len(jobs)} jobs, returning top {len(top_jobs)}")
        if top_jobs:
            logger.info(f"   Top job: {top_jobs[0].title} at {top_jobs[0].company} (score: {top_jobs[0].match_score})")
        else:
            logger.warning("   No jobs found to rank.")
        
        return top_jobs
    
    def _extract_skills_from_description(self, description: str) -> set:
        """Extract technical skills mentioned in job description."""
        desc_lower = description.lower()
        
        # Common tech skills
        all_skills = [
            "python", "javascript", "java", "c++", "c#", "ruby", "go", "rust",
            "react", "angular", "vue", "node", "django", "flask", "spring",
            "sql", "postgresql", "mysql", "mongodb", "redis",
            "aws", "azure", "gcp", "docker", "kubernetes", "git",
            "html", "css", "typescript", "php", "swift", "kotlin",
            "api", "rest", "graphql", "microservices"
        ]
        
        found_skills = set()
        for skill in all_skills:
            if skill in desc_lower:
                found_skills.add(skill)
        
        return found_skills
    
    def _score_skill_match(self, job_skills: set) -> float:
        """
        Score skill match between resume and job.
        
        Returns:
            0.0 to 1.0
        """
        if not job_skills:
            return 0.5  # Neutral if no skills listed
        
        # Calculate overlap
        overlap = self.resume_skills_set & job_skills
        match_ratio = len(overlap) / len(job_skills)
        
        return min(match_ratio, 1.0)
    
    def _score_title_match(self, job_title: str) -> float:
        """
        Score how well job title aligns with resume job titles.
        
        Returns:
            0.0 to 1.0
        """
        job_title_lower = job_title.lower()
        
        # Check for keyword matches
        title_keywords = [
            "engineer", "developer", "programmer", "software",
            "frontend", "backend", "full stack", "fullstack",
            "junior", "senior", "lead", "principal"
        ]
        
        resume_title_words = " ".join(self.resume.job_titles).lower()
        
        matches = 0
        for keyword in title_keywords:
            if keyword in job_title_lower and keyword in resume_title_words:
                matches += 1
        
        # Direct title match
        for resume_title in self.resume_titles_set:
            if resume_title in job_title_lower or job_title_lower in resume_title:
                return 1.0  # Perfect match
        
        # Keyword-based scoring
        return min(matches * 0.25, 1.0)
    
    def _score_seniority_fit(self, job_title: str) -> float:
        """
        Score whether seniority level fits resume.
        
        Returns:
            0.0 to 1.0
        """
        job_title_lower = job_title.lower()
        years_exp = self.resume.years_of_experience
        
        # Determine seniority indicators
        is_entry = any(word in job_title_lower for word in ["junior", "entry", "intern", "associate"])
        is_senior = any(word in job_title_lower for word in ["senior", "lead", "principal", "staff"])
        is_mid = not is_entry and not is_senior
        
        # Match against resume experience
        if years_exp < 2:
            # Entry level
            if is_entry or is_mid:
                return 1.0
            elif is_senior:
                return 0.3
        elif 2 <= years_exp < 5:
            # Mid level
            if is_mid:
                return 1.0
            elif is_entry or is_senior:
                return 0.6
        else:
            # Senior level
            if is_senior:
                return 1.0
            elif is_mid:
                return 0.8
            elif is_entry:
                return 0.4
        
        return 0.7  # Neutral if unclear
    
    def _score_location_match(self, job_location: str) -> float:
        """
        Score location match.
        
        Returns:
            0.0 to 1.0
        """
        job_location_lower = job_location.lower()
        
        # Perfect matches
        if "remote" in job_location_lower:
            return 1.0
        
        # Check against user's preferred locations (from config)
        # For now, simple heuristic
        preferred_locations = ["portland", "oregon", "remote"]
        
        for location in preferred_locations:
            if location in job_location_lower:
                return 0.9
        
        return 0.5  # Neutral for other locations
    
    def _score_application_friction(self, job: Job) -> float:
        """
        Score application friction.
        
        Resume-only jobs get highest score.
        
        Returns:
            0.0 to 1.0
        """
        # If job passed guard as SAFE (resume-only), give max score
        if job.has_easy_apply and job.guard_status.value == "safe":
            return 1.0
        
        # If has Easy Apply but guard status unknown
        if job.has_easy_apply:
            return 0.7
        
        # No Easy Apply
        return 0.3
