"""
Application Executor - Submit applications to jobs with strict FSM logic.

Phase 7: Guarded Execution - STRICT FSM VERSION
"""
import asyncio
import logging
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import Page, BrowserContext, Locator
from src.models import Job, Application, ApplicationStatus, Platform
from src.application_guard import ApplicationGuard

logger = logging.getLogger(__name__)

class FSMState(Enum):
    JOB_PAGE = auto()
    EASY_APPLY_MODAL_OPEN = auto()
    STEP_IN_PROGRESS = auto()
    REVIEW = auto()
    SUBMIT_READY = auto()
    SUBMITTED = auto()
    SKIPPED = auto()

class TerminalReason(Enum):
    SUBMITTED = "SUBMITTED"
    COVER_LETTER_REQUIRED = "Cover letter required"
    SCREENING_QUESTIONS = "Screening questions present"
    EXTERNAL_REDIRECT = "External redirect"
    SECURITY_CHECKPOINT = "CAPTCHA / security checkpoint"
    UPLOAD_FAILED = "Upload failed / file picker blocked"
    NEXT_DISABLED = "Next button disabled"
    STUCK = "Unknown UI state after 3 recovery attempts"
    NO_EASY_APPLY = "No Easy Apply button found"

class ApplicationExecutor:
    """
    Execute job applications with strict FSM logic and resume-only policy.
    """
    
    def __init__(self, config: dict, guard: ApplicationGuard):
        self.config = config
        self.guard = guard
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.applications: List[Application] = []
        self._recovery_attempts = 0
        self._last_fingerprint = ""

    async def login_to_linkedin(self, page: Page) -> bool:
        """Perform manual login to LinkedIn."""
        logger.info("Opening LinkedIn login page...")
        await page.goto("https://www.linkedin.com/login", timeout=60000)
        logger.info("[PAUSE] Please log in to LinkedIn manually...")
        try:
            await page.wait_for_url("**/feed/**", timeout=300000)
            logger.info("LinkedIn login successful!")
            return True
        except Exception as e:
            logger.error(f"LinkedIn login failed: {e}")
            return False

    async def apply_to_linkedin_job(self, job: Job, resume_path: str) -> Application:
        """Apply to a single LinkedIn job using the Strict FSM approach."""
        app = Application(job=job, resume_path=resume_path, status=ApplicationStatus.PREPARED)
        state = FSMState.JOB_PAGE
        terminal_reason = None
        transitions = []
        buttons_clicked = []
        
        logger.info(f"--- Starting Application: {job.company} - {job.title} ---")
        
        try:
            await self.page.goto(job.url, timeout=30000)
            await self.page.wait_for_timeout(2000)
            
            self._recovery_attempts = 0
            self._last_fingerprint = ""
            
            for _ in range(20): # Safety limit for button advances
                transitions.append(state.name)
                
                if state == FSMState.JOB_PAGE:
                    ea_btn = await self._find_ea_button_robust()
                    if not ea_btn:
                        state = FSMState.SKIPPED
                        terminal_reason = TerminalReason.NO_EASY_APPLY
                        continue
                    
                    await ea_btn.click(force=True)
                    buttons_clicked.append("Easy Apply")
                    await self.page.wait_for_timeout(2000)
                    state = FSMState.EASY_APPLY_MODAL_OPEN

                elif state in [FSMState.EASY_APPLY_MODAL_OPEN, FSMState.STEP_IN_PROGRESS, FSMState.REVIEW]:
                    # 1. Check for success first
                    if await self._detect_success_proof():
                        state = FSMState.SUBMITTED
                        terminal_reason = TerminalReason.SUBMITTED
                        continue

                    # 2. Get Modal
                    modal = self.page.locator('[role="dialog"], .artdeco-modal, .jobs-easy-apply-modal').first
                    if not await modal.count():
                        # Maybe it closed on success?
                        if await self._detect_success_proof():
                            state = FSMState.SUBMITTED
                            terminal_reason = TerminalReason.SUBMITTED
                        else:
                            state = FSMState.SKIPPED
                            terminal_reason = TerminalReason.STUCK
                        continue

                    # 3. Detect Screening Questions (Immediate Skip)
                    if await self._is_screening_required(modal):
                        state = FSMState.SKIPPED
                        terminal_reason = TerminalReason.SCREENING_QUESTIONS
                        continue

                    # 4. Handle Resume (if visible)
                    await self._ensure_resume_selected(modal)

                    # 5. Identify and Click Best Button
                    btn, btn_type = await self._find_priority_button(modal)
                    if not btn:
                        # Attempt recovery if possible
                        if await self._attempt_recovery(modal, job):
                            continue
                        state = FSMState.SKIPPED
                        terminal_reason = TerminalReason.STUCK
                        continue

                    # 6. Click and Detect Progress
                    old_fingerprint = await self._get_modal_fingerprint(modal)
                    await self._click_robustly(btn)
                    buttons_clicked.append(btn_type)
                    await self.page.wait_for_timeout(2000)
                    
                    new_fingerprint = await self._get_modal_fingerprint(modal)
                    if new_fingerprint == old_fingerprint and not await self._detect_success_proof():
                        logger.warning(f"  No progress detected after clicking {btn_type}")
                        if await self._attempt_recovery(modal, job):
                            continue
                        state = FSMState.SKIPPED
                        terminal_reason = TerminalReason.STUCK
                        continue
                    
                    # Update State based on button clicked and result
                    if btn_type == "SUBMIT":
                        await self.page.wait_for_timeout(3000)
                        if await self._detect_success_proof():
                            state = FSMState.SUBMITTED
                            terminal_reason = TerminalReason.SUBMITTED
                        else:
                            state = FSMState.STEP_IN_PROGRESS # Retry or check for errors
                    elif btn_type == "REVIEW":
                        state = FSMState.REVIEW
                    else:
                        state = FSMState.STEP_IN_PROGRESS

                elif state == FSMState.SUBMITTED:
                    app.status = ApplicationStatus.SUBMITTED
                    app.submission_timestamp = datetime.now()
                    await self._close_modal_if_open()
                    break

                elif state == FSMState.SKIPPED:
                    app.status = ApplicationStatus.SKIPPED
                    app.error_message = terminal_reason.value
                    await self._close_modal_if_open()
                    break

            # Final Logging
            self._log_terminal_state(job, transitions, terminal_reason, buttons_clicked)
            return app

        except Exception as e:
            logger.error(f"✗ Unexpected Error: {e}")
            app.status = ApplicationStatus.FAILED
            return app

    async def _find_ea_button_robust(self):
        """
        VERIFIED SELECTORS - Extracted from 21 actual successful applications.
        Source: interaction_flow_1769567870414.json
        """
        logger.info("Starting Easy Apply detection (golden selectors)...")
        
        for attempt in range(2):
            logger.debug(f"Detection attempt {attempt + 1}/2")
            
            # Wait for content to settle
            await self._wait_for_content_settle()
            
            # Priority order based on ACTUAL recorded interactions
            selectors = [
                # 1. PRIMARY: Used in 100% of your successful applications
                '#jobs-apply-button-id',
                
                # 2. FALLBACK: Button text span (if structure changes)
                'button span.artdeco-button__text:has-text("Easy Apply")',
                'button span.artdeco-button__text:has-text("Apply")',
                
                # 3. LAST RESORT: XPath from logs
                'xpath=//*[@id="jobs-apply-button-id"]',
            ]
            
            for selector in selectors:
                try:
                    btn = self.page.locator(selector).first
                    
                    # Check visibility with timeout
                    if await btn.is_visible(timeout=2000):
                        logger.info(f"Found Easy Apply button via: {selector}")
                        
                        # Verify it's not a denied button
                        try:
                            text = (await btn.inner_text() or "").lower()
                            if any(denied in text for denied in ["save", "follow", "share"]):
                                logger.debug(f"Rejected denied button: {text}")
                                continue
                        except:
                            pass
                        
                        return btn
                        
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Retry logic
            if attempt == 0:
                logger.warning("First pass failed, waiting 1.2s before retry...")
                await self.page.wait_for_timeout(1200)
        
        # Both passes failed
        logger.error("✗ Easy Apply button NOT FOUND after 2 attempts")
        await self._capture_failure_artifacts("no_easy_apply_button")
        return None

    async def _wait_for_content_settle(self):
        """Wait for LinkedIn content to fully load."""
        # Basic DOM ready
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(500)
        
        # Network settle
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except:
            logger.debug("Network didn't settle in 5s, continuing anyway")
        
        # Wait for any button to exist
        try:
            await self.page.get_by_role("button").first.wait_for(
                state="visible",
                timeout=8000
            )
        except:
            pass

    async def _capture_failure_artifacts(self, reason: str):
        """Capture screenshot and button inventory on failure."""
        timestamp = int(time.time())
        
        # Ensure data dir exists
        Path("data").mkdir(exist_ok=True)
        
        # Screenshot
        screenshot_path = f"data/failure_{reason}_{timestamp}.png"
        try:
            await self.page.screenshot(path=screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
        
        # Button inventory
        try:
            buttons = await self.page.get_by_role("button").all()
            button_inventory = []
            
            for i, btn in enumerate(buttons[:20]):
                try:
                    if await btn.is_visible(timeout=500):
                        text = (await btn.inner_text() or "").strip()
                        aria = (await btn.get_attribute("aria-label") or "").strip()
                        button_inventory.append(
                            f"{i+1}. Text: '{text}' | ARIA: '{aria}'"
                        )
                except Exception:
                    continue
            
            inventory_path = f"data/button_inventory_{timestamp}.txt"
            with open(inventory_path, 'w', encoding='utf-8') as f:
                f.write(f"Failure Reason: {reason}\n")
                f.write(f"URL: {self.page.url}\n\n")
                f.write("VISIBLE BUTTONS:\n")
                if button_inventory:
                    f.write("\n".join(button_inventory))
                else:
                    f.write("No visible buttons found\n")
            
            logger.info(f"Button inventory saved: {inventory_path}")
        except Exception as e:
            logger.warning(f"Failed to capture button inventory: {e}")

    async def _find_priority_button(self, modal: Locator) -> Tuple[Optional[Locator], Optional[str]]:
        """
        STRICT Priority: Submit application > Next > Review > Continue
        """
        # 1. Submit application (Highest Priority)
        for s in ['button:has-text("Submit application")', 'button:has-text("Submit")']:
            loc = modal.locator(s).first
            if await loc.count() and await loc.is_visible(): return loc, "SUBMIT"
        
        # 2. Next / Continue
        for s in ['button:has-text("Next")', 'button:has-text("Continue")', 'button:has-text("next")']:
            loc = modal.locator(s).first
            if await loc.count() and await loc.is_visible(): return loc, "NEXT"

        # 3. Review
        loc = modal.locator('button:has-text("Review")').first
        if await loc.count() and await loc.is_visible(): return loc, "REVIEW"
            
        # Primary footer fallback (Strict Order)
        primary = modal.locator('.artdeco-modal__actionbar button.artdeco-button--primary').first
        if await primary.count() and await primary.is_visible():
            text = (await primary.inner_text()).lower()
            if "submit" in text: return primary, "SUBMIT"
            if "next" in text or "continue" in text: return primary, "NEXT"
            if "review" in text: return primary, "REVIEW"
            
        return None, None

    async def _is_screening_required(self, modal: Locator) -> bool:
        """
        STRICT Check: ANY specific question is a DISQUALIFIER.
        Allowed:
        - Contact Info confirmation
        - Resume selection
        - Terms/Privacy acknowledgements
        """
        # 1. Text/TextArea (Input fields)
        # Allow only known contact fields (phone/email usually pre-filled)
        if await modal.locator('textarea').count() > 0: return True
        
        inputs = await modal.locator('input[type="text"], input[type="email"], input[type="tel"]').all()
        for i in inputs:
            if await i.is_visible():
                label = (await i.get_attribute("aria-label") or "").lower()
                # If it's not a standard contact field we can't auto-fill, SKIP.
                # Usually these are pre-filled, but if empty and required, it's a question.
                # Strict Mode: Any visible text input that requires typing is risky.
                # However, LinkedIn usually pre-fills. We check if it is "Question" related.
                # Safest Strict Rule: If it looks like a custom question, Skip.
                if any(x in label for x in ["how many", "years", "experience", "salary", "sponsorship"]):
                    return True

        # 2. Selects (Dropdowns) - ALWAYS SKIP
        if await modal.locator('select').count() > 0: return True

        # 3. Radios - ALWAYS SKIP (Authorization/Sponsorship/Demographics)
        if await modal.locator('fieldset, [role="radiogroup"], input[type="radio"]').count() > 0:
            return True

        # 4. Checkboxes - Allow ONLY Terms/Privacy
        checkboxes = await modal.locator('input[type="checkbox"]').all()
        for c in checkboxes:
            if await c.is_visible():
                id_val = await c.get_attribute("id")
                label = ""
                if id_val:
                     label_elem = self.page.locator(f'label[for="{id_val}"]').first
                     if await label_elem.count():
                         label = (await label_elem.inner_text()).lower()
                
                # If label doesn't contain "terms", "privacy", "acknowledge", "agree" -> SKIP
                if not any(k in label for k in ["terms", "privacy", "policy", "acknowledge", "agree", "confirm"]):
                    return True

        return False

    async def _attempt_recovery(self, modal: Locator, job: Job) -> bool:
        self._recovery_attempts += 1
        # MAX 2 Retries (User Rule: "Max 2 retries per state")
        if self._recovery_attempts > 2: return False
        
        logger.warning(f"  Recovery Attempt {self._recovery_attempts} for {job.company}")
        
        if self._recovery_attempts == 1:
            # Scroll to bottom
            await modal.evaluate("el => el.scrollTop = el.scrollHeight")
            await self.page.wait_for_timeout(1000)
            return True
        
        if self._recovery_attempts == 2:
            # Try global selector fallback (implicitly handled by next loop's find)
            await self.page.wait_for_timeout(1000)
            return True
            
        return False

    async def _detect_success_proof(self) -> bool:
        content = (await self.page.content()).lower()
        # Confirmation screen text
        if any(p in content for p in ["application submitted", "your application has been submitted", "submitted"]):
            return True
        # Check for Submitted badge on page
        badge = self.page.locator('.artdeco-inline-feedback--success, :has-text("Applied")').first
        if await badge.count() and await badge.is_visible():
            return True
        return False

    async def _close_modal_if_open(self):
        close = self.page.locator('button:has-text("Done"), [aria-label*="Dismiss"], .artdeco-modal__dismiss').first
        if await close.count() and await close.is_visible():
            await close.click(force=True)

    def _log_terminal_state(self, job: Job, transitions: List[str], reason: Optional[TerminalReason], buttons: List[str]):
        status = reason.value if reason else "UNKNOWN"
        logger.info(f"Job: {job.title} + {job.company}")
        logger.info(f"States traversed: {' -> '.join(transitions)}")
        logger.info(f"Buttons clicked: {buttons}")
        logger.info(f"Final outcome: {status}")

    async def apply_to_jobs(self, jobs: List[Job], resume_path: str, context: BrowserContext) -> List[Application]:
        logger.info(f"Starting execution for {len(jobs)} jobs...")
        self.context = context
        if not self.page: self.page = await self.context.new_page()
        for job in jobs:
            if job.platform == Platform.LINKEDIN:
                app = await self.apply_to_linkedin_job(job, resume_path)
                self.applications.append(app)
            # Mandatory delay between applications
            await asyncio.sleep(self.config.get("application", {}).get("min_delay", 30))
        return self.applications
