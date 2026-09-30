"""
CRITICAL FIXES for src/executor.py

Apply these changes to your existing executor.py file.
These fixes address the issues you're currently experiencing.
"""

# ============================================================================
# FIX #1: Enhanced Button Detection with TWO-PASS Logic
# ============================================================================

async def _find_ea_button_robust(self):
    """
    CRITICAL FIX: Two-pass detection with proper settle gates.
    
    Your current issue: Single-pass detection misses async-loaded buttons.
    This fix: Retry with delays to catch late-loading elements.
    """
    logger.info("Starting Easy Apply detection (2-pass with settle)")
    
    for attempt in range(2):
        logger.debug(f"Attempt {attempt + 1}/2")
        
        # CRITICAL: Wait for content to settle BEFORE scanning
        await self._wait_for_content_settle()
        
        # Your existing selectors (good!) but with proper retry
        selectors = [
            "button#jobs-apply-button",                    # Priority 1
            'button[data-control-name*="apply"]',          # Priority 2
            'button[aria-label*="Easy Apply"]',            # Priority 3
        ]
        
        for selector in selectors:
            try:
                btn = self.page.locator(selector).first
                
                # CRITICAL: Check visibility with reasonable timeout
                is_visible = await btn.is_visible(timeout=2000)
                if not is_visible:
                    continue
                
                # CRITICAL: Verify it's not a denied button
                text = (await btn.inner_text() or "").lower()
                aria = (await btn.get_attribute("aria-label") or "").lower()
                combined = f"{text} {aria}"
                
                # Your DENY list (good!)
                if any(word in combined for word in ["save", "follow", "share"]):
                    logger.debug(f"Rejected denied button: {text}")
                    continue
                
                logger.info(f"✓ Found Easy Apply button (selector: {selector})")
                return btn
                
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        # CRITICAL: Retry logic - wait before second pass
        if attempt == 0:
            logger.warning("First pass failed, waiting 1.2s before retry...")
            await self.page.wait_for_timeout(1200)
    
    # Both passes failed - capture diagnostics
    logger.error("✗ Easy Apply button NOT FOUND after 2 attempts")
    await self._capture_failure_artifacts("no_easy_apply_button")
    return None


# ============================================================================
# FIX #2: Content Settle Gate (MUST be called before button detection)
# ============================================================================

async def _wait_for_content_settle(self):
    """
    CRITICAL FIX: Wait for LinkedIn's async content to fully load.
    
    Your current issue: Scanning before job details panel hydrates.
    This fix: Deterministic wait for interactive content.
    """
    # Step 1: Basic DOM ready
    await self.page.wait_for_load_state("domcontentloaded")
    await self.page.wait_for_timeout(500)
    
    # Step 2: Network settle (catch XHR requests)
    try:
        await self.page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        logger.debug("Network didn't settle in 5s, continuing anyway")
    
    # Step 3: Wait for at least ONE button to exist
    # This ensures the UI is interactive
    try:
        await self.page.get_by_role("button").first.wait_for(
            state="visible",
            timeout=8000
        )
        logger.debug("Content settled - buttons visible")
    except Exception as e:
        logger.warning(f"No buttons found during settle: {e}")
    
    # Step 4: LinkedIn-specific: wait for job card to be visible
    try:
        # The job details card should be present
        await self.page.locator('.jobs-details, .job-details').first.wait_for(
            state="visible",
            timeout=3000
        )
    except Exception:
        pass  # Optional - not all pages have this


# ============================================================================
# FIX #3: Enhanced Failure Diagnostics
# ============================================================================

async def _capture_failure_artifacts(self, reason: str):
    """
    CRITICAL FIX: Capture what buttons ARE present when detection fails.
    
    This is your debugging goldmine - it tells you exactly which
    selectors to use for jobs where detection is failing.
    """
    import time
    timestamp = int(time.time())
    
    # Screenshot
    screenshot_path = f"data/failure_{reason}_{timestamp}.png"
    try:
        await self.page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"Screenshot: {screenshot_path}")
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
    
    # CRITICAL: Button inventory
    try:
        all_buttons = await self.page.get_by_role("button").all()
        visible_buttons = []
        
        for i, btn in enumerate(all_buttons[:30]):  # Check first 30 buttons
            try:
                if await btn.is_visible(timeout=500):
                    text = (await btn.inner_text() or "").strip()
                    aria_label = (await btn.get_attribute("aria-label") or "").strip()
                    data_control = (await btn.get_attribute("data-control-name") or "").strip()
                    btn_id = (await btn.get_attribute("id") or "").strip()
                    
                    visible_buttons.append({
                        "index": i + 1,
                        "text": text,
                        "aria_label": aria_label,
                        "data_control_name": data_control,
                        "id": btn_id
                    })
            except Exception:
                continue
        
        # Save inventory
        inventory_path = f"data/button_inventory_{timestamp}.txt"
        with open(inventory_path, 'w', encoding='utf-8') as f:
            f.write(f"BUTTON INVENTORY\n")
            f.write(f"{'='*70}\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"URL: {self.page.url}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Total visible buttons: {len(visible_buttons)}\n")
            f.write(f"{'='*70}\n\n")
            
            for btn in visible_buttons:
                f.write(f"Button #{btn['index']}\n")
                f.write(f"  Text: {btn['text']}\n")
                f.write(f"  ARIA Label: {btn['aria_label']}\n")
                f.write(f"  Data-Control: {btn['data_control_name']}\n")
                f.write(f"  ID: {btn['id']}\n")
                f.write(f"  {'-'*60}\n")
        
        logger.info(f"Button inventory: {inventory_path}")
        logger.info(f"Found {len(visible_buttons)} visible buttons on page")
        
    except Exception as e:
        logger.error(f"Button inventory failed: {e}")


# ============================================================================
# FIX #4: Main Application Flow Update
# ============================================================================

async def apply_to_linkedin_job(self, job, resume_path: str):
    """
    CRITICAL FIX: Proper flow with verification at each step.
    
    Your current issue: Skipping jobs before even attempting to find button.
    This fix: Always attempt, always verify, always log.
    """
    logger.info(f"{'='*70}")
    logger.info(f"Starting application: {job.company} - {job.title}")
    logger.info(f"{'='*70}")
    
    # Navigate to job
    try:
        await self.page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
        logger.info(f"Navigated to: {job.url}")
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return "FAILED_NAVIGATION"
    
    # CRITICAL: Don't trust job.has_easy_apply - always verify at runtime
    logger.info("Searching for Easy Apply button...")
    btn = await self._find_ea_button_robust()
    
    if not btn:
        logger.warning("No Easy Apply button found - skipping")
        return "SKIPPED_NO_BUTTON"
    
    # CRITICAL: Click with verification
    logger.info("Clicking Easy Apply button...")
    try:
        await btn.click()
        await self.page.wait_for_timeout(800)
        
        # Verify modal opened
        modal_opened = False
        modal_selectors = [
            'div[role="dialog"]',
            'div.jobs-easy-apply-modal',
            '.jobs-easy-apply-content',
        ]
        
        for selector in modal_selectors:
            try:
                if await self.page.locator(selector).is_visible(timeout=3000):
                    modal_opened = True
                    logger.info(f"✓ Modal opened (via {selector})")
                    break
            except:
                continue
        
        if not modal_opened:
            logger.error("✗ Modal did NOT open after click")
            await self._capture_failure_artifacts("modal_did_not_open")
            return "FAILED_MODAL_OPEN"
        
        # Continue with your existing modal navigation logic...
        # ... (submit forms, handle questions, etc.)
        
        return "SUBMITTED"
        
    except Exception as e:
        logger.error(f"Application failed: {e}")
        await self._capture_failure_artifacts("application_exception")
        return "FAILED_EXCEPTION"


# ============================================================================
# USAGE INSTRUCTIONS
# ============================================================================

"""
HOW TO APPLY THESE FIXES TO YOUR CODE:

1. Open your src/executor.py

2. Find and REPLACE your existing _find_ea_button() method with 
   _find_ea_button_robust() above

3. ADD the _wait_for_content_settle() method (should be new)

4. REPLACE or ENHANCE your _capture_failure_artifacts() method

5. UPDATE your apply_to_linkedin_job() to use the new flow

6. Test with: python main.py data/resume.pdf --skip-discovery

7. Check data/button_inventory_*.txt to see what buttons ARE present
   when detection fails

CRITICAL: The button inventory files will tell you EXACTLY what 
selectors to use for the jobs where detection is currently failing.
"""
