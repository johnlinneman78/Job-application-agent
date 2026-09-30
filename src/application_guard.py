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
        Check if LinkedIn job is safe to apply.
        
        Steps:
        1. Check for Easy Apply button
        2. Click to open modal
        3. Scan for questions/assessments
        4. Return SAFE or SKIP with reason
        """
        logger.info("Running LinkedIn guard check...")
        
        # Step 1: Check for Easy Apply button - support multiple selectors for logged-in view
        if not await self.check_has_easy_apply(page):
            return GuardResult(
                GuardStatus.SKIP_NO_EASY_APPLY,
                "No Easy Apply button found or not visible - likely requires full application"
            )
        
        easy_apply_button = page.locator('#jobs-apply-button-id').first
        if not await easy_apply_button.is_visible():
            # Fallback to text search if ID not found (unlikely given logs)
            easy_apply_button = page.locator('button span.artdeco-button__text:has-text("Easy Apply")').first
        
        # Step 2: Click Easy Apply (non-committing, just opens modal)
        try:
            # Ensure button is in view
            await easy_apply_button.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)
            
            logger.info("  Clicking Easy Apply to scan for questions...")
            await easy_apply_button.click(timeout=5000)
            
            # Wait for modal to appear
            await page.wait_for_selector('[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal', timeout=10000)
        except Exception as e:
            logger.error(f"Failed to open Easy Apply modal: {e}")
            return GuardResult(GuardStatus.UNKNOWN, f"Could not open Easy Apply modal: {str(e)}")
        
        # Step 3: Check modal contents for red flags
        modal = page.locator('[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal').first
        
        if not await modal.count():
            return GuardResult(GuardStatus.UNKNOWN, "Easy Apply modal not found")
        
        # Check for screening questions
        screening_indicators = [
            'textarea',  # Text input fields
            'select',    # Dropdown fields
            'input[type="radio"]',  # Radio buttons
        ]
        
        # Count how many simple questions there are
        question_count = 0
        for indicator in screening_indicators:
            question_count += await modal.locator(indicator).count()
        
        # In relaxed mode, allow up to max_simple_questions
        max_allowed = self.config.get("guards", {}).get("max_simple_questions", 2)
        if not self.strict_mode and question_count > 0 and question_count <= max_allowed:
            logger.info(f"Found {question_count} simple screening question(s) - allowed in relaxed mode")
            # Don't close modal yet - will need it for application
            return GuardResult(GuardStatus.SAFE, f"Easy Apply with {question_count} simple question(s)")
        elif question_count > max_allowed:
            # Too many questions - still skip
            close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
            if await close_button.count():
                await close_button.first.click()
            
            return GuardResult(
                GuardStatus.SKIP_QUESTIONS,
                f"Too many screening questions: {question_count} (max allowed: {max_allowed})"
            )
        
        # Check for assessment indicators
        assessment_keywords = ["assessment", "test", "hackerrank", "codility", "coding challenge"]
        modal_text = await modal.inner_text()
        modal_text_lower = modal_text.lower()
        
        for keyword in assessment_keywords:
            if keyword in modal_text_lower:
                close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
                if await close_button.count():
                    await close_button.first.click()
                
                return GuardResult(
                    GuardStatus.SKIP_ASSESSMENT,
                    f"Detected assessment requirement: '{keyword}'"
                )
        
        # Check for external ATS redirect
        for ats in self.external_ats:
            if ats.lower() in modal_text_lower:
                close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
                if await close_button.count():
                    await close_button.first.click()
                
                return GuardResult(
                    GuardStatus.SKIP_EXTERNAL_ATS,
                    f"Detected external ATS: {ats}"
                )
        
        # English check
        if self.config.get("search", {}).get("only_english_jobs", True):
            if not self._is_content_english(modal_text):
                close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
                if await close_button.count():
                    await close_button.first.click()
                return GuardResult(GuardStatus.SKIP_QUESTIONS, "Non-English job posting detected")
        
        # Check if only resume upload is required
        # Look for submit button without multi-step form
        submit_button = modal.locator('button:has-text("Submit application"), button:has-text("submit")')
        next_button = modal.locator('button:has-text("Next"), button:has-text("next")')
        
        # If there's a "Next" button, it likely has multiple steps (questions)
        if await next_button.count() > 0:
            # Check if the next button is for multi-step questions or just review
            review_indicators = await modal.locator('text="review"').count()
            if review_indicators == 0:
                close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
                if await close_button.count():
                    await close_button.first.click()
                
                return GuardResult(
                    GuardStatus.SKIP_QUESTIONS,
                    "Multi-step application detected (likely has questions)"
                )
        
        # If we got here, job appears to be resume-only
        # Close modal (don't submit yet - need permission)
        close_button = modal.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")')
        if await close_button.count():
            await close_button.first.click()
        
        logger.info("LinkedIn job passed guard check - resume-only")
        return GuardResult(GuardStatus.SAFE, "Resume-only Easy Apply detected")
    
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
        """
        VERIFIED CHECK - Using same selector as executor.
        Source: 21 successful human applications from interaction logs.
        """
        logger.info("Guard: Checking for Easy Apply button...")
        
        # Wait for page to settle
        await page.wait_for_timeout(1000)
        await page.wait_for_load_state("domcontentloaded")
        
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass
        
        # Use EXACT selector from recordings
        selectors = [
            '#jobs-apply-button-id',  # PRIMARY - from 21 successful clicks
            'button span.artdeco-button__text:has-text("Easy Apply")',
            'button span.artdeco-button__text:has-text("Apply")',
        ]
        
        for selector in selectors:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible(timeout=3000):
                    # Verify not a "Save" button
                    try:
                        text = (await elem.inner_text() or "").lower()
                        if "save" in text or "follow" in text:
                            continue
                    except:
                        pass
                    
                    logger.info(f"Guard passed: Found via {selector}")
                    return True
            except Exception as e:
                logger.debug(f"Guard selector {selector} failed: {e}")
                continue
        
        logger.warning("✗ Guard failed: No Easy Apply button found")
        return False
