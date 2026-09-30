"""
Application Guard System - Enforces hard constraints.

CRITICAL: This module ensures we ONLY apply to resume-only jobs.
          Never bypass or brute-force application steps.
"""
from typing import Tuple, Optional
import re
from playwright.async_api import Page, Locator
from src.models import GuardStatus, Platform
import logging

logger = logging.getLogger(__name__)

# Shared with src/executor.py so guard and executor always agree.
# LinkedIn uses id="jobs-apply-button-id" for BOTH Easy Apply and the external
# "Apply" button, so callers must also check the text says "Easy Apply".
EASY_APPLY_SELECTORS = [
    '#jobs-apply-button-id',
    'button.jobs-apply-button',
    'button[aria-label*="Easy Apply" i]',
    'button:has-text("Easy Apply")',
]
DENIED_BUTTON_WORDS = ["save", "follow", "share", "dismiss", "not now"]


class GuardResult:
    """Result from guard check."""
    
    def __init__(self, status: GuardStatus, reason: str = ""):
        self.status = status
        self.reason = reason
        self.is_safe = status == GuardStatus.SAFE
    
    def __repr__(self):
        return f"GuardResult(status={self.status}, reason='{self.reason}')"


class ApplicationGuard:
    """
    Enforces hard constraints:
    - ONLY apply to resume-only jobs
    - SKIP jobs with questions, assessments, external ATS
    - NEVER brute-force or bypass
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.strict_mode = config.get("guards", {}).get("strict_mode", True)
        self.external_ats = config.get("guards", {}).get("external_ats", [])
        self.assessment_platforms = config.get("guards", {}).get("assessment_platforms", [])
    
    async def check_linkedin_job(self, page: Page) -> GuardResult:
        """
        Cheap pre-check: does this job have a real (in-LinkedIn) Easy Apply button?

        The form itself is NOT opened here. Opening every form twice (once in the
        guard, once in the executor) doubled LinkedIn activity, and the old modal
        scan disagreed with the executor about what counts as a question.
        The executor inspects each form step and skips on the first real question.
        """
        logger.info("Running LinkedIn guard check...")
        if "checkpoint" in page.url or "/login" in page.url:
            return GuardResult(GuardStatus.UNKNOWN, "LinkedIn security checkpoint / not logged in")

        if not await self.check_has_easy_apply(page):
            return GuardResult(
                GuardStatus.SKIP_NO_EASY_APPLY,
                "No Easy Apply button (external apply or already applied)"
            )

        if self.config.get("search", {}).get("only_english_jobs", True):
            try:
                body = await page.locator("main").first.inner_text(timeout=3000)
            except Exception:
                body = ""
            if body and not self._is_content_english(body):
                return GuardResult(GuardStatus.SKIP_QUESTIONS, "Non-English job posting detected")

        return GuardResult(GuardStatus.SAFE, "Easy Apply present - form is checked step by step during apply")

    async def check_indeed_job(self, page: Page) -> GuardResult:
        """
        Check if Indeed job is safe to apply.
        
        Similar logic to LinkedIn but adapted for Indeed's UI.
        """
        logger.info("Running Indeed guard check...")
        
        # Check for "Easily apply" badge
        easily_apply = page.locator('button:has-text("Easily apply"), div:has-text("Easily apply")')
        
        if not await easily_apply.count():
            return GuardResult(
                GuardStatus.SKIP_NO_EASY_APPLY,
                "No 'Easily apply' option - requires full application"
            )
        
        # Click apply button
        apply_button = page.locator('button:has-text("Apply now"), button:has-text("apply")')
        
        if not await apply_button.count():
            return GuardResult(GuardStatus.SKIP_NO_EASY_APPLY, "Apply button not found")
        
        try:
            await apply_button.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            logger.error(f"Failed to click Indeed apply button: {e}")
            return GuardResult(GuardStatus.UNKNOWN, f"Could not start application: {str(e)}")
        
        # Check for screening questions on Indeed
        screening_indicators = [
            'text="screening question"',
            'text="additional question"',
            'textarea',
            'select',
            'input[type="radio"]',
            'text="Are you authorized to work"',
            'text="require sponsorship"',
        ]
        
        page_text = await page.inner_text('body')
        page_text_lower = page_text.lower()
        
        # English check
        if self.config.get("search", {}).get("only_english_jobs", True):
            if not self._is_content_english(page_text):
                await page.go_back()
                return GuardResult(GuardStatus.SKIP_QUESTIONS, "Non-English job posting detected")
        
        # Check for questions
        for indicator in screening_indicators:
            if await page.locator(indicator).count() > 0:
                # Go back
                await page.go_back()
                return GuardResult(
                    GuardStatus.SKIP_QUESTIONS,
                    f"Detected screening question: {indicator}"
                )
        
        # Check for external ATS
        for ats in self.external_ats:
            if ats.lower() in page_text_lower or ats.lower() in page.url.lower():
                await page.go_back()
                return GuardResult(
                    GuardStatus.SKIP_EXTERNAL_ATS,
                    f"Redirected to external ATS: {ats}"
                )
        
        # Check for assessments
        for assessment in self.assessment_platforms:
            if assessment.lower() in page_text_lower:
                await page.go_back()
                return GuardResult(
                    GuardStatus.SKIP_ASSESSMENT,
                    f"Assessment required: {assessment}"
                )
        
        # If made it here, appears safe
        # Go back without submitting (need permission first)
        await page.go_back()
        
        logger.info("Indeed job passed guard check - resume-only")
        return GuardResult(GuardStatus.SAFE, "Resume-only quick apply detected")
    
    def should_skip_job(self, guard_result: GuardResult) -> bool:
        """
        Determine if job should be skipped based on guard result.
        
        In strict mode (default), skip anything that's not SAFE.
        """
        if self.strict_mode:
            return guard_result.status != GuardStatus.SAFE
        
        # In non-strict mode, only skip obvious red flags
        return guard_result.status in [
            GuardStatus.SKIP_QUESTIONS,
            GuardStatus.SKIP_ASSESSMENT,
            GuardStatus.SKIP_EXTERNAL_ATS
        ]

    def _is_content_english(self, text: str) -> bool:
        """Simple heuristic to check if text is primarily English."""
        if not text:
            return True
            
        # Common English stop words
        english_indicators = [" the ", " and ", " state ", " city ", " is ", " in ", " with ", " for ", " applying "]
        text_lower = text.lower()
        
        # Count occurrences of English indicators
        match_count = sum(1 for indicator in english_indicators if indicator in text_lower)
        
        # If we find at least a few common English words, assume it's English
        # (This is better than a full library for speed and simplicity)
        return match_count >= 2

    async def check_has_easy_apply(self, page) -> bool:
        """Uses the SAME selectors and rules as the executor."""
        logger.info("Guard: Checking for Easy Apply button...")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        for _ in range(2):
            for selector in EASY_APPLY_SELECTORS:
                try:
                    elem = page.locator(selector).first
                    if not await elem.count() or not await elem.is_visible():
                        continue
                    label = ((await elem.inner_text()) + " " + (await elem.get_attribute("aria-label") or "")).lower()
                    if any(w in label for w in DENIED_BUTTON_WORDS):
                        continue
                    if "easy apply" not in label:
                        continue  # plain "Apply" = external company site
                    logger.info(f"Guard passed: Found via {selector}")
                    return True
                except Exception as e:
                    logger.debug(f"Guard selector {selector} failed: {e}")
            await page.wait_for_timeout(1500)

        logger.warning("Guard failed: No Easy Apply button found")
        return False
