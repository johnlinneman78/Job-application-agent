"""
Resume Analyzer - Parse and extract information from resume.

Phase 2: Resume Intelligence
"""
import PyPDF2
import re
from typing import List, Dict
from pathlib import Path
from src.models import Resume
import logging

logger = logging.getLogger(__name__)


class ResumeAnalyzer:
    """Parse resume and extract structured data."""
    
    def __init__(self):
        # Common technical skills keywords
        self.tech_skills = [
            "python", "javascript", "java", "c++", "c#", "ruby", "go", "rust",
            "react", "angular", "vue", "node", "django", "flask", "spring",
            "sql", "postgresql", "mysql", "mongodb", "redis",
            "aws", "azure", "gcp", "docker", "kubernetes", "git",
            "html", "css", "typescript", "php", "swift", "kotlin"
        ]
        
        # Soft skills keywords
        self.soft_skills = [
            "leadership", "communication", "teamwork", "problem solving",
            "critical thinking", "collaboration", "adaptability", "creativity",
            "time management", "organization", "attention to detail"
        ]
    
    def parse_resume(self, file_path: str) -> Resume:
        """
        Parse PDF resume into structured data.
        
        Args:
            file_path: Path to PDF resume
            
        Returns:
            Resume object with parsed data
        """
        logger.info(f"Parsing resume: {file_path}")
        
        # Read PDF
        text = self._extract_text_from_pdf(file_path)
        
        # Extract fields
        name = self._extract_name(text)
        email = self._extract_email(text)
        phone = self._extract_phone(text)
        
        technical_skills = self._extract_technical_skills(text)
        soft_skills = self._extract_soft_skills(text)
        
        job_titles = self._extract_job_titles(text)
        companies = self._extract_companies(text)
        years_exp = self._estimate_years_of_experience(text)
        
        degrees = self._extract_degrees(text)
        schools = self._extract_schools(text)
        
        resume = Resume(
            name=name,
            email=email,
            phone=phone,
            technical_skills=technical_skills,
            soft_skills=soft_skills,
            job_titles=job_titles,
            companies=companies,
            years_of_experience=years_exp,
            degrees=degrees,
            schools=schools,
            raw_text=text
        )
        
        logger.info(f"Resume parsed: {name}, {len(technical_skills)} skills, {years_exp} years exp")
        return resume
    
    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extract raw text from PDF."""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            logger.error(f"Failed to read PDF: {e}")
            return ""
    
    def _extract_email(self, text: str) -> str:
        """Extract email address."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, text)
        return match.group(0) if match else "unknown@example.com"
    
    def _extract_phone(self, text: str) -> str:
        """Extract phone number."""
        phone_pattern = r'(\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        match = re.search(phone_pattern, text)
        return match.group(0) if match else "555-0000"
    
    def _extract_name(self, text: str) -> str:
        """Extract name (usually first line)."""
        lines = text.split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and len(line.split()) >= 2 and len(line.split()) <= 4:
                # Likely a name (2-4 words)
                if not any(char.isdigit() for char in line):
                    return line
        return "Unknown"
    
    def _extract_technical_skills(self, text: str) -> List[str]:
        """Extract technical skills."""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.tech_skills:
            if skill.lower() in text_lower:
                found_skills.append(skill.title())
        
        return list(set(found_skills))  # Remove duplicates
    
    def _extract_soft_skills(self, text: str) -> List[str]:
        """Extract soft skills."""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.soft_skills:
            if skill.lower() in text_lower:
                found_skills.append(skill.title())
        
        return list(set(found_skills))
    
    def _extract_job_titles(self, text: str) -> List[str]:
        """Extract previous job titles."""
        # Common job title patterns
        title_keywords = [
            "engineer", "developer", "designer", "manager", "analyst",
            "consultant", "specialist", "architect", "lead", "senior",
            "junior", "intern", "associate"
        ]
        
        lines = text.split('\n')
        titles = []
        
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in title_keywords):
                # Clean up the line
                line_clean = line.strip()
                if 10 < len(line_clean) < 60:  # Reasonable title length
                    titles.append(line_clean)
        
        return titles[:5]  # Return top 5
    
    def _extract_companies(self, text: str) -> List[str]:
        """Extract company names (simple heuristic)."""
        # This is a simplified version - could be improved
        # Look for lines that might be company names after job titles
        lines = text.split('\n')
        companies = []
        
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in ["engineer", "developer"]):
                # Next line might be company
                if i + 1 < len(lines):
                    potential_company = lines[i + 1].strip()
                    if 2 < len(potential_company.split()) < 6:
                        companies.append(potential_company)
        
        return companies[:5]
    
    def _estimate_years_of_experience(self, text: str) -> float:
        """Estimate years of experience based on date ranges."""
        # Look for year patterns (2020-2023, etc.)
        year_pattern = r'(20\d{2})\s*[-–]\s*(20\d{2}|present|current)'
        matches = re.findall(year_pattern, text, re.IGNORECASE)
        
        total_years = 0.0
        current_year = 2026
        
        for start_year, end_year in matches:
            start = int(start_year)
            if end_year.lower() in ['present', 'current']:
                end = current_year
            else:
                end = int(end_year)
            
            years = end - start
            if 0 < years < 50:  # Sanity check
                total_years += years
        
        return round(total_years, 1)
    
    def _extract_degrees(self, text: str) -> List[str]:
        """Extract degrees."""
        degree_keywords = [
            "bachelor", "master", "phd", "doctorate", "associate",
            "b.s.", "m.s.", "b.a.", "m.a.", "mba"
        ]
        
        text_lower = text.lower()
        degrees = []
        
        for keyword in degree_keywords:
            if keyword in text_lower:
                degrees.append(keyword.upper())
        
        return list(set(degrees))
    
    def _extract_schools(self, text: str) -> List[str]:
        """Extract school names (simplified)."""
        # Look for "University", "College", "Institute"
        school_keywords = ["university", "college", "institute"]
        
        lines = text.split('\n')
        schools = []
        
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in school_keywords):
                schools.append(line.strip())
        
        return schools[:3]  # Top 3
    
    def generate_role_fit_matrix(self, resume: Resume) -> Dict[str, float]:
        """
        Generate role fit scores for different job types.
        
        Returns:
            Dict of {role_title: confidence_score}
        """
        logger.info("Generating role fit matrix...")
        
        role_fits = {}
        
        # Example role matching logic
        skills_set = set([s.lower() for s in resume.technical_skills])
        
        # Software Engineer
        se_required = {"python", "javascript", "java", "sql", "git"}
        se_match = len(skills_set & se_required) / len(se_required)
        if se_match >= 0.5:
            role_fits["Software Engineer"] = round(se_match, 2)
        
        # Frontend Developer
        fe_required = {"javascript", "react", "html", "css"}
        fe_match = len(skills_set & fe_required) / len(fe_required)
        if fe_match >= 0.5:
            role_fits["Frontend Developer"] = round(fe_match, 2)
        
        # Backend Developer
        be_required = {"python", "java", "sql", "api"}
        be_match = len(skills_set & be_required) / len(be_required)
        if be_match >= 0.5:
            role_fits["Backend Developer"] = round(be_match, 2)
        
        # Full Stack Developer
        fs_required = {"javascript", "python", "react", "sql"}
        fs_match = len(skills_set & fs_required) / len(fs_required)
        if fs_match >= 0.5:
            role_fits["Full Stack Developer"] = round(fs_match, 2)
        
        logger.info(f"Generated {len(role_fits)} role fits")
        return role_fits
