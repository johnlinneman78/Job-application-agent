# Integration Guide: Applying Fixes to Your Existing Code

This guide shows exactly how to integrate the enhanced button detection logic into your existing `src/executor.py` and `src/application_guard.py` files.

## Step 1: Add Constants (Top of executor.py)

```python
# Add these at the top of src/executor.py, after imports:

ALLOWED_PRIMARY_ACTIONS = {
    "easy apply", "apply", "continue", "next step", "next",
    "review", "submit application", "submit", "done"
}

DENIED_ACTIONS = {
    "save", "follow", "share", "dismiss", "not now"
}
```

## Step 2: Replace Your Button Finding Method

Find your existing `_find_ea_button()` method and replace it with:

```python
async def _find_ea_button(self):
    """
    ENHANCED: Two-pass Easy Apply button detection with retry logic.
    """
    logger.info("Starting Easy Apply button detection (2-pass)")
    
    for attempt in range(2):
        # Settle before each attempt
        await self._wait_for_content_settle()
        
        # Try multiple selectors in priority order
        selectors = [
            "button#jobs-apply-button",
            'button[data-control-name*="apply"]',
            'button[aria-label*="Easy Apply"]',
            'button[aria-label*="Apply"]',
        ]
        
        for selector in selectors:
            try:
                btn = self.page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    # Verify it's not a denied button
                    text = (await btn.inner_text() or "").lower()
                    if any(denied in text for denied in DENIED_ACTIONS):
                        continue
                    
                    logger.info(f"Found Easy Apply via: {selector}")
                    return btn
            except Exception:
                continue
        
        if attempt == 0:
            await self.page.wait_for_timeout(1200)
    
    await self._capture_failure_artifacts("no_easy_apply_found")
    return None
```

## Step 3: Add Helper Methods to Your Executor Class

Add these methods to your ApplicationExecutor class:

```python
async def _wait_for_content_settle(self):
    """Wait for page content to fully load."""
    await self.page.wait_for_timeout(500)
    await self.page.wait_for_load_state("domcontentloaded")
    
    try:
        await self.page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    
    try:
        await self.page.get_by_role("button").first.wait_for(
            state="visible", 
            timeout=8000
        )
    except Exception:
        pass


async def _capture_failure_artifacts(self, reason: str):
    """Capture screenshot and button inventory on failure."""
    timestamp = int(time.time())
    
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
```

## Step 4: Update Your Click Logic

Find where you click the Easy Apply button and wrap it with verification:

```python
# OLD CODE:
# btn = await self._find_ea_button()
# await btn.click()

# NEW CODE:
btn = await self._find_ea_button()
if not btn:
    return SKIPPED_STATE

# Click with verification
await btn.click()
await self.page.wait_for_timeout(800)

# Verify modal opened
modal_selectors = [
    'div[role="dialog"]',
    'div.jobs-easy-apply-modal',
]
modal_opened = False
for sel in modal_selectors:
    try:
        if await self.page.locator(sel).is_visible(timeout=2000):
            modal_opened = True
            break
    except:
        pass

if not modal_opened:
    logger.warning("Modal did not open after click")
    return SKIPPED_STATE
```

## Step 5: Update application_guard.py

In your `src/application_guard.py`, update the Easy Apply check:

```python
async def check_has_easy_apply(self, page) -> bool:
    """
    ENHANCED: Use same selectors as executor to prevent mismatches.
    """
    # Wait for page to settle
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("domcontentloaded")
    
    # Use identical selector logic as executor
    selectors = [
        "button#jobs-apply-button",
        'button[data-control-name*="apply"]',
        'button[aria-label*="Easy Apply"]',
    ]
    
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=3000):
                # Verify it's not a denied action
                text = (await btn.inner_text() or "").lower()
                if "save" not in text and "follow" not in text:
                    return True
        except Exception:
            continue
    
    return False
```

## Step 6: Update config.yaml

Add debug section to your existing config:

```yaml
# Add this section
debug:
  enabled: false  # Set to true for testing
  min_delay: 1
  max_delay: 2
  save_artifacts: true
  verbose_logging: true
```

## Step 7: Update Delay Logic

Find where you calculate delays and add debug mode support:

```python
# In your apply_to_jobs() or similar method:
if self.config.get("debug", {}).get("enabled", False):
    delay = random.randint(
        self.config["debug"]["min_delay"],
        self.config["debug"]["max_delay"]
    )
    logger.info(f"DEBUG MODE: Waiting {delay}s...")
else:
    delay = random.randint(
        self.config["application"]["min_delay"],
        self.config["application"]["max_delay"]
    )
    logger.info(f"Waiting {delay}s before next application...")

await asyncio.sleep(delay)
```

## Testing Checklist

1. **Enable Debug Mode**
   ```yaml
   debug:
     enabled: true
   ```

2. **Run with Existing Jobs**
   ```bash
   python main.py data/resume.pdf --skip-discovery
   ```

3. **Check Outputs**
   - `data/button_inventory_*.txt` - See what buttons were visible
   - `data/failure_*.png` - Screenshots of failures
   - Console logs showing "Found Easy Apply via: X"

4. **Verify No More "Save" Misclicks**
   - Check logs for "Skipping denied action: save"
   - Confirm no navigation to save pages

5. **Measure Success Rate**
   - Count: "Easy Apply button detection" attempts
   - Count: "Found Easy Apply via:" successes
   - Target: >95% detection rate

## Common Issues & Solutions

### Issue: Still getting false negatives
**Solution**: Increase settle delay
```python
await self.page.wait_for_timeout(1000)  # Instead of 500
```

### Issue: Timeout errors
**Solution**: Increase visibility timeout
```python
if await btn.is_visible(timeout=5000):  # Instead of 2000
```

### Issue: Button inventory empty
**Solution**: Page hasn't loaded, increase wait before capture
```python
await self.page.wait_for_load_state("networkidle", timeout=10000)
```

## Rollback Plan

If you need to revert:
1. Keep a copy of your original `src/executor.py`
2. Changes are additive - just remove the new methods
3. Restore original `_find_ea_button()` method

## Next Steps After Integration

1. Run 5-10 test applications with debug mode
2. Review button inventory logs
3. Adjust selectors if needed based on actual button attributes
4. Disable debug mode for production
5. Monitor success metrics

---

**Questions or Issues?**

Check the button inventory files to see exactly what buttons are present when detection fails. This is your debugging goldmine.
