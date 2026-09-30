"""
Enhanced Application Executor with Robust Button Detection

Implements:
- Content settle gates to handle async loading
- Two-pass button detection with retry logic
- Click verification with state change validation
- Button inventory capture for debugging
"""
import logging
import time
import random
from typing import Optional, Callable, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Define allowed and denied button actions
ALLOWED_PRIMARY_ACTIONS = {
    "easy apply", "apply", "continue", "next step", "next",
    "review", "submit application", "submit", "done"
}

DENIED_ACTIONS = {
    "save", "follow", "share", "dismiss", "not now"
}


class EnhancedApplicationExecutor:
    """
    Enhanced executor with robust button detection and verification.
    
    Key improvements:
    1. Content settle gates before button scanning
    2. Multi-pass detection with retry logic
    3. Click verification with state change validation
    4. Enhanced failure diagnostics
    """
    
    def __init__(self, config, guard, page=None):
        self.config = config
        self.guard = guard
        self.page = page
        self.resume = None
        
        # Create data directory for artifacts
        Path("data").mkdir(exist_ok=True)
    
    # ==================== CORE IMPROVEMENTS ====================
    
    async def _wait_for_content_settle(self):
        """
        Wait for job detail panel to fully load before scanning for buttons.
        Prevents false negatives from async rendering.
        """
        # Wait for basic DOM ready
        await self.page.wait_for_timeout(500)
        await self.page.wait_for_load_state("domcontentloaded")
        
        # Wait for network to settle (optional but helpful)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # Timeout is fine, proceed anyway
        
        # Ensure at least one button exists (indicates UI is interactive)
        try:
            await self.page.get_by_role("button").first.wait_for(
                state="visible", 
                timeout=8000
            )
        except Exception:
            pass  # If no buttons exist, subsequent logic will handle it
        
        logger.debug("Content settled, ready for button detection")
    
    async def _find_primary_action_with_validation(self) -> Tuple[Optional[object], Optional[str]]:
        """
        Find primary action button with strict validation.
        
        Returns:
            (button_locator, action_name) or (None, None)
        """
        # Collect all visible buttons
        buttons = self.page.get_by_role("button")
        count = await buttons.count()
        candidates = []
        
        logger.debug(f"Scanning {min(count, 50)} buttons for primary action")
        
        for i in range(min(count, 50)):  # Limit scan to first 50 buttons
            try:
                btn = buttons.nth(i)
                
                # Skip if not visible
                if not await btn.is_visible():
                    continue
                
                # Get button text/label
                text = (await btn.inner_text() or "").strip().lower()
                aria_label = (await btn.get_attribute("aria-label") or "").strip().lower()
                name = f"{text} {aria_label}"
                
                # Skip denied actions
                if any(denied in name for denied in DENIED_ACTIONS):
                    logger.debug(f"Skipping denied action: {text}")
                    continue
                
                # Check if allowed action
                if any(allowed in name for allowed in ALLOWED_PRIMARY_ACTIONS):
                    candidates.append((name, btn))
                    logger.debug(f"Found candidate: {text}")
            
            except Exception as e:
                logger.debug(f"Error scanning button {i}: {e}")
                continue
        
        if not candidates:
            logger.warning("No primary action buttons found")
            return None, None
        
        # Prioritize by action specificity
        priority = ["submit", "review", "next", "continue", "apply"]
        for prio_word in priority:
            for name, btn in candidates:
                if prio_word in name:
                    logger.info(f"Selected primary action: {name} (priority: {prio_word})")
                    return btn, name
        
        # Return first candidate if no priority match
        logger.info(f"Selected first candidate: {candidates[0][0]}")
        return candidates[0][1], candidates[0][0]
    
    async def _find_ea_button_robust(self):
        """
        Two-pass Easy Apply button detection with retry logic.
        Reduces false negatives from timing issues.
        
        Returns:
            Button locator or None
        """
        logger.info("Starting Easy Apply button detection (2-pass)")
        
        for attempt in range(2):
            logger.debug(f"Detection attempt {attempt + 1}/2")
            
            # Settle before each attempt
            await self._wait_for_content_settle()
            
            # Try multiple selector strategies in priority order
            selectors = [
                # Tier 1: Stable ID (from recorded data)
                "button#jobs-apply-button",
                
                # Tier 2: Data attributes
                'button[data-control-name*="apply"]',
                
                # Tier 3: ARIA label
                'button[aria-label*="Easy Apply"]',
                'button[aria-label*="Apply"]',
                
                # Tier 4: Class-based (less stable)
                'button.jobs-apply-button',
            ]
            
            for selector in selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        # Verify it's not a "Save" or "Follow" button
                        text = (await btn.inner_text() or "").lower()
                        aria = (await btn.get_attribute("aria-label") or "").lower()
                        combined = f"{text} {aria}"
                        
                        if any(denied in combined for denied in DENIED_ACTIONS):
                            logger.debug(f"Rejected button (denied action): {text}")
                            continue
                        
                        logger.info(f"✓ Found Easy Apply button via: {selector}")
                        return btn
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # If first pass failed, wait and retry
            if attempt == 0:
                logger.warning("First pass failed, retrying after delay...")
                await self.page.wait_for_timeout(1200)
        
        # Both passes failed - capture diagnostics
        logger.error("Easy Apply button not found after 2 attempts")
        await self._capture_failure_artifacts("no_easy_apply_found")
        return None
    
    async def _safe_click_with_verification(
        self, 
        button_locator, 
        expected_change_fn: Callable,
        action_name: str,
        max_retries: int = 2
    ) -> bool:
        """
        Click button and verify the expected state change occurred.
        Prevents infinite loops and detects misclicks.
        
        Args:
            button_locator: Playwright locator for the button
            expected_change_fn: Async function that returns True if state changed correctly
            action_name: Human-readable action name for logging
            max_retries: Number of retry attempts
        
        Returns:
            True if click succeeded and state changed, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Pre-verify button is clickable
                if not await button_locator.is_visible():
                    logger.warning(f"{action_name}: Button not visible")
                    return False
                
                if await button_locator.is_disabled():
                    logger.warning(f"{action_name}: Button disabled")
                    return False
                
                # Capture state before click
                url_before = self.page.url
                
                # Perform click
                await button_locator.click()
                logger.info(f"✓ Clicked: {action_name}")
                
                # Wait for state change
                await self.page.wait_for_timeout(800)
                
                # Verify expected change occurred
                if await expected_change_fn():
                    logger.info(f"✓ {action_name}: State change verified")
                    return True
                
                # Retry if verification failed
                logger.warning(
                    f"{action_name}: State change not detected "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await self.page.wait_for_timeout(500)
                
            except Exception as e:
                logger.error(f"{action_name} failed: {e}")
                if attempt < max_retries - 1:
                    await self.page.wait_for_timeout(1000)
        
        logger.error(f"✗ {action_name}: Failed after {max_retries} attempts")
        return False
    
    async def _capture_failure_artifacts(self, reason: str):
        """
        Enhanced failure capture with button inventory.
        Creates screenshot + button inventory log for debugging.
        """
        timestamp = int(time.time())
        
        # Screenshot
        screenshot_path = f"data/failure_{reason}_{timestamp}.png"
        try:
            await self.page.screenshot(path=screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
        
        # Button inventory - log what buttons ARE present
        try:
            buttons = await self.page.get_by_role("button").all()
            button_inventory = []
            
            for i, btn in enumerate(buttons[:20]):  # First 20 buttons
                try:
                    if await btn.is_visible(timeout=500):
                        text = (await btn.inner_text() or "").strip()
                        aria = (await btn.get_attribute("aria-label") or "").strip()
                        button_inventory.append(
                            f"{i+1}. Text: '{text}' | ARIA: '{aria}'"
                        )
                except Exception:
                    continue
            
            # Save inventory to file
            inventory_path = f"data/button_inventory_{timestamp}.txt"
            with open(inventory_path, 'w', encoding='utf-8') as f:
                f.write(f"Failure Reason: {reason}\n")
                f.write(f"URL: {self.page.url}\n")
                f.write(f"Timestamp: {timestamp}\n\n")
                f.write("=" * 60 + "\n")
                f.write("VISIBLE BUTTONS:\n")
                f.write("=" * 60 + "\n")
                if button_inventory:
                    f.write("\n".join(button_inventory))
                else:
                    f.write("No visible buttons found\n")
            
            logger.info(f"Button inventory saved: {inventory_path}")
            
        except Exception as e:
            logger.warning(f"Failed to capture button inventory: {e}")
    
    # ==================== USAGE EXAMPLES ====================
    
    async def click_easy_apply_with_verification(self) -> bool:
        """
        Example: Click Easy Apply button with verification.
        
        Returns:
            True if modal opened successfully, False otherwise
        """
        btn = await self._find_ea_button_robust()
        if not btn:
            return False
        
        # Define what "success" looks like for this click
        async def verify_modal_opened():
            """Check if Easy Apply modal appeared"""
            modal_selectors = [
                'div[role="dialog"]',
                'div.jobs-easy-apply-modal',
                'div[data-test-modal]',
                'div[aria-label*="Easy Apply"]'
            ]
            for selector in modal_selectors:
                try:
                    if await self.page.locator(selector).is_visible(timeout=2000):
                        return True
                except Exception:
                    pass
            return False
        
        return await self._safe_click_with_verification(
            button_locator=btn,
            expected_change_fn=verify_modal_opened,
            action_name="Easy Apply"
        )
    
    async def get_delay_seconds(self) -> int:
        """
        Get delay between applications (respects debug mode).
        """
        if self.config.get("debug", {}).get("enabled", False):
            min_delay = self.config["debug"].get("min_delay", 1)
            max_delay = self.config["debug"].get("max_delay", 2)
            logger.info("DEBUG MODE: Using short delays")
        else:
            min_delay = self.config["application"].get("min_delay", 120)
            max_delay = self.config["application"].get("max_delay", 300)
        
        delay = random.randint(min_delay, max_delay)
        logger.info(f"Waiting {delay}s before next application...")
        return delay


# Example integration with existing code:
"""
# In your existing executor, replace button finding logic:

# OLD (fragile):
btn = self.page.locator("button.jobs-apply-button").first
if await btn.is_visible():
    await btn.click()

# NEW (robust):
enhanced = EnhancedApplicationExecutor(config, guard, page)
success = await enhanced.click_easy_apply_with_verification()
if success:
    # Continue with application
else:
    # Skip job
"""
