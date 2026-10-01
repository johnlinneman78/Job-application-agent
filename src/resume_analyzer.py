"""
Resume Analyzer - Parse and extract structured information from resume PDF.
Phase 2: Resume Intelligence
"""

import os
import re
import yaml
import logging
from typing import List, Dict, Optional
from pathlib import Path

try:
    import pypdf as pdf_module
except ImportError:
    import PyPDF2 as pdf_module

from src.models import Resume

logger = logging.getLogger(__name__)


class ResumeAnalyzer:
    """Parse resume and extract structured data."""

    def __init__(self):
        # Comprehensive skills covering Sales, CRM, IT Support, Automation & Web
        self.tech_skills = [
            # Sales & CRM & Ops
            "crm", "salesforce", "hubspot", "pipeline management", "workflow automation",
            "quotes and proposals", "lead qualification", "vendor coordination",
            # IT & Infrastructure
            "enterprise it support", "data center operations", "hardware", "linux", "windows",
            "macos", "rack installation", "cable management", "ticketing", "networking",
            # Web & Programming & AI
            "web development", "seo", "ai-assisted project building", "technical writing",
            "python", "javascript", "html", "css", "typescript", "sql", "git",
            "api", "rest", "cloud", "aws", "azure", "gcp", "docker"
        ]

        # Soft & Consultative Skills
        self.soft_skills = [
            "consultative sales", "account management", "technical discovery",
            "customer communication", "cross-functional execution", "product demonstration",
            "leadership", "communication", "teamwork", "problem solving",
            "critical thinking", "collaboration", "adaptability", "time management"
        ]

    def _load_config(self) -> dict:
        """Helper to load personal info from config file if available."""
        base_dir = Path(__file__).parent.parent
        for fname in ["config.local.yaml", "config.yaml"]:
            for p in [Path(fname), base_dir / fname]:
                if p.exists():
                    try:
                        with open(p, "r", encoding="utf-8-sig") as f:
                            data = yaml.safe_load(f)
                            if data:
                                return data
                    except Exception:
                        pass
        return {}

    def parse_resume(self, file_path: str) -> Resume:
        """
        Parse PDF resume into structured data.
        """
        logger.info(f"Parsing resume: {file_path}")

        text = self._extract_text_from_pdf(file_path)

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
        """Extract raw text from PDF across all pages."""
        try:
            with open(file_path, "rb") as file:
                reader = pdf_module.PdfReader(file)
                pages_text = []
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
                return "\n".join(pages_text)
        except Exception as e:
            logger.error(f"Failed to read PDF: {e}")
            return ""

    def _extract_email(self, text: str) -> str:
        """Extract email address."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, text)
        if match:
            return match.group(0)

        cfg = self._load_config()
        return cfg.get("personal_info", {}).get("email", "")

    def _extract_phone(self, text: str) -> str:
        """Extract phone number with config fallback."""
        phone_pattern = r'(\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        match = re.search(phone_pattern, text)
        if match:
            return match.group(0)

        cfg = self._load_config()
        phone = cfg.get("personal_info", {}).get("phone")
        if phone:
            return str(phone)

        return ""

    def _extract_name(self, text: str) -> str:
        """Extract candidate name from header or config."""
        cfg = self._load_config()
        cfg_name = cfg.get("personal_info", {}).get("name")

        # Check for uppercase name at top of resume (e.g. 'JOHN DOE Portland')
        first_chunk = text[:300]
        name_match = re.search(r'([A-Z]{2,}\s+[A-Z]{2,}(?:\s+[A-Z]{2,})?)(?=[A-Z][a-z]|\b|\s*\|)', first_chunk)
        if name_match:
            candidate = name_match.group(1).strip()
            # Guard against common headers
            if candidate not in ["CORE SKILLS", "PROFESSIONAL EXPERIENCE", "CONSULTATIVE SALES", "TECHNICAL ACCOUNT"]:
                return candidate.title()

        # Check lines for standard 2-3 word capitalized name
        lines = text.splitlines()
        for line in lines[:5]:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'[,|]', line)
            cand = parts[0].strip()
            if cand and 2 <= len(cand.split()) <= 4 and not any(c.isdigit() for c in cand):
                return cand.title()

        return cfg_name if cfg_name else ""

    def _extract_technical_skills(self, text: str) -> List[str]:
        """Extract skills, honoring the explicit CORE SKILLS section."""
        found_skills = []

        # 1. Parse explicit CORE SKILLS section
        match = re.search(r'CORE SKILLS\s*[:\n]?(.*?)(?=PROFESSIONAL EXPERIENCE|\n[A-Z\s]{5,}\n|$)', text, re.DOTALL | re.IGNORECASE)
        if match:
            raw = match.group(1).replace('\n', ' ')
            items = [re.sub(r'\s+', ' ', s.strip()) for s in raw.split(',') if s.strip()]
            found_skills.extend(items)

        # 2. Add keyword matches from dictionary
        text_lower = text.lower()
        for skill in self.tech_skills:
            if len(skill) <= 4:
                if re.search(rf'\b{re.escape(skill)}\b', text_lower):
                    found_skills.append(skill.upper() if len(skill) <= 3 else skill.title())
            else:
                if skill in text_lower:
                    found_skills.append(skill.title())

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in found_skills:
            s_clean = s.strip()
            s_key = s_clean.lower()
            if s_key not in seen and len(s_clean) > 1:
                seen.add(s_key)
                unique.append(s_clean)

        return unique

    def _extract_soft_skills(self, text: str) -> List[str]:
        """Extract soft and consultative skills."""
        text_lower = text.lower()
        found = []

        for skill in self.soft_skills:
            if skill in text_lower:
                found.append(skill.title())

        if "discovery" in text_lower and "Technical Discovery" not in found:
            found.append("Technical Discovery")
        if "vendor coordination" in text_lower and "Vendor Coordination" not in found:
            found.append("Vendor Coordination")
        if "cross-functional" in text_lower and "Cross-Functional Execution" not in found:
            found.append("Cross-Functional Execution")

        return list(dict.fromkeys(found))

    def _extract_job_titles(self, text: str) -> List[str]:
        """Extract job titles from professional experience headers."""
        titles = []
        in_exp = False

        for line in text.splitlines():
            line_s = line.strip()
            if "PROFESSIONAL EXPERIENCE" in line_s:
                in_exp = True
                continue
            if in_exp and any(h in line_s for h in ["EDUCATION", "LICENSING IN PROGRESS"]):
                in_exp = False
                break
            if not in_exp or not line_s:
                continue

            if chr(8212) in line_s or ' — ' in line_s or ' – ' in line_s:
                sep = chr(8212) if chr(8212) in line_s else (' — ' if ' — ' in line_s else ' – ')
                parts = line_s.split(sep, 1)
                if len(parts) >= 2:
                    rest = parts[1].strip()
                    title = re.sub(r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*)?\d{4}.*$', '', rest, flags=re.IGNORECASE).strip()
                    title = title.rstrip('\u2013\u2014- ').strip()
                    if title and title not in titles:
                        titles.append(title)

        if not titles:
            title_keywords = [
                "sales representative", "account manager", "brand advocate",
                "technician", "builder", "specialist", "engineer", "lead"
            ]
            for line in text.splitlines():
                line_lower = line.lower()
                if any(k in line_lower for k in title_keywords) and len(line.strip()) < 60:
                    clean = line.strip()
                    if clean not in titles:
                        titles.append(clean)

        return titles[:7]

    def _extract_companies(self, text: str) -> List[str]:
        """Extract company names from professional experience headers."""
        companies = []
        in_exp = False

        for line in text.splitlines():
            line_s = line.strip()
            if "PROFESSIONAL EXPERIENCE" in line_s:
                in_exp = True
                continue
            if in_exp and any(h in line_s for h in ["EDUCATION", "LICENSING IN PROGRESS"]):
                in_exp = False
                break
            if not in_exp or not line_s:
                continue

            if chr(8212) in line_s or ' — ' in line_s or ' – ' in line_s:
                sep = chr(8212) if chr(8212) in line_s else (' — ' if ' — ' in line_s else ' – ')
                parts = line_s.split(sep, 1)
                if len(parts) >= 2:
                    comp = parts[0].strip().lstrip('•*-\u2022 ').strip()
                    if comp and comp not in companies:
                        companies.append(comp)

        return companies[:7]

    def _estimate_years_of_experience(self, text: str) -> float:
        """Estimate total years of experience across all roles."""
        pattern = r'(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(20\d{2})\s*[-\u2010-\u2015/]\s*(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(20\d{2}|present|current)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        total_months = 0
        current_year = 2026

        for m1, y1, m2, y2 in matches:
            start_year = int(y1)
            start_month = month_map.get(m1.lower() if m1 else '', 1)
            if y2.lower() in ['present', 'current']:
                end_year = current_year
                end_month = 9
            else:
                end_year = int(y2)
                end_month = month_map.get(m2.lower() if m2 else '', 12)

            if end_year > current_year:
                continue

            diff = (end_year - start_year) * 12 + (end_month - start_month)
            if 0 < diff < 600:
                total_months += diff

        years = round(total_months / 12, 1)
        if years < 1.0:
            cfg = self._load_config()
            cfg_years = cfg.get("personal_info", {}).get("years_of_experience")
            if cfg_years:
                return float(cfg_years)
            return 5.0
        return years

    def _extract_degrees(self, text: str) -> List[str]:
        """Extract degree names."""
        edu_match = re.search(r'EDUCATION.*?([A-Za-z\s]+?)\s*[——\-]\s*([A-Za-z\s]+?)\s*\|', text)
        if edu_match:
            deg = edu_match.group(2).strip()
            if deg:
                return [deg]

        keywords = ["bachelor", "master", "b.s.", "m.s.", "mba", "associate"]
        found = []
        for kw in keywords:
            if kw in text.lower():
                found.append(kw.upper())
        return list(set(found)) if found else ["Bachelor of Business Management"]

    def _extract_schools(self, text: str) -> List[str]:
        """Extract school / university name."""
        edu_match = re.search(r'EDUCATION\s*([A-Za-z\s]+?)\s*[——\-]', text)
        if edu_match:
            school = edu_match.group(1).strip()
            if school:
                return [school]

        for line in text.splitlines():
            if "university" in line.lower() or "college" in line.lower():
                clean = re.sub(r'EDUCATION', '', line, flags=re.IGNORECASE).strip()
                clean = clean.split(chr(8212))[0].split('|')[0].strip()
                if clean:
                    return [clean]

        return []

    def generate_role_fit_matrix(self, resume: Resume) -> Dict[str, float]:
        """
        Generate role fit scores for candidate's target job categories.
        """
        logger.info("Generating role fit matrix...")

        skills_set = set([s.lower() for s in resume.technical_skills] + [s.lower() for s in resume.soft_skills])

        target_roles = {
            "Account Manager": {"account management", "crm management", "quotes and proposals", "customer communication", "vendor coordination"},
            "Technical Account Manager": {"account management", "technical discovery", "enterprise it support", "crm management", "vendor coordination"},
            "Inside Sales Representative": {"consultative sales", "crm management", "quotes and proposals", "customer communication", "vendor coordination"},
            "Customer Success Manager": {"customer communication", "account management", "crm management", "vendor coordination"},
            "IT Support Specialist": {"enterprise it support", "data center operations", "workflow automation", "windows", "hardware"},
            "Sales Operations Specialist": {"crm management", "workflow automation", "quotes and proposals", "vendor coordination"},
            "Full Stack Developer": {"web development", "workflow automation", "python", "javascript", "html", "css"},
            "Software Engineer": {"python", "javascript", "git", "web development"}
        }

        role_fits = {}
        for role_name, required_skills in target_roles.items():
            matches = len(skills_set & required_skills)
            score = round(matches / len(required_skills), 2)
            if score >= 0.40:
                role_fits[role_name] = score

        logger.info(f"Generated {len(role_fits)} role fits")
        return role_fits
