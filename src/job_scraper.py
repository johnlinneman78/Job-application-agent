"""
Job Scraper with Guards - Discover jobs on LinkedIn and Indeed.

Phase 3: Job Discovery with Guard Integration
"""
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from src.models import Job, Platform, GuardStatus
from src.application_guard import ApplicationGuard
from src.locations import find_location, parse_card_text
from datetime import datetime, timedelta
import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Job card layouts, newest first. The first selector that finds cards is used.
CARD_SELECTORS = [
    'li[data-occludable-job-id]',                  # logged-in search list (2024+)
    'div.job-card-container',
    'li.jobs-search-results__list-item',
    'li.scaffold-layout__list-item',
    'div.job-search-card, div.base-search-card',   # logged-out pages
]


class JobScraper:
    """
    Scrape jobs from LinkedIn and Indeed with guard checks.
    """
    
    def __init__(self, config: dict, guard: ApplicationGuard):
        self.config = config
        self.guard = guard
        self.context: BrowserContext = None
        self.scraped_jobs: List[Job] = []
    
    async def discover_jobs(
        self,
        titles: List[str],
        locations: List[str],
        days_ago: int = 14,
        context: BrowserContext = None,
        page: Page = None
    ) -> List[Job]:
        """
        Discover jobs across all platforms.
        
        Args:
            titles: List of job titles to search
            locations: List of locations
            days_ago: Posted within N days
            context: Existing browser context (headful/logged-in)
            page: Existing browser page (reuse tab)
            
        Returns:
            List of Job objects with guard status
        """
        logger.info(f"Starting job discovery: {len(titles)} titles, {len(locations)} locations")
        
        all_jobs = []
        
        if context:
            # Use existing context (shares cookies/session)
            self.context = context
            
            # Scrape LinkedIn
            linkedin_jobs = await self._scrape_linkedin(titles, locations, days_ago, page=page)
            all_jobs.extend(linkedin_jobs)
            
            # Indeed not yet fully supported in headful scrape
        else:
            # Fallback to headless scrape (login not supported here)
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                self.context = await browser.new_context()
                
                # Scrape LinkedIn
                linkedin_jobs = await self._scrape_linkedin(titles, locations, days_ago)
                all_jobs.extend(linkedin_jobs)
                
                await browser.close()
        
        # Deduplicate
        all_jobs = self._deduplicate_jobs(all_jobs)
        
        logger.info(f"Discovered {len(all_jobs)} unique jobs")
        return all_jobs
    
    def build_search_plan(self, titles: List[str], locations: List[str]) -> List[dict]:
        """
        One entry per LinkedIn search, local searches first:
          local  = each city in Settings, on-site/hybrid only (+ distance)
          remote = remote-only search, either in the user's state(s) or anywhere in the US
        """
        from src.locations import is_remote_location, home_states, STATES

        search = self.config.get("search", {}) or {}
        selected = {w.lower() for w in (search.get("work_types") or [])}
        any_type = not selected
        local_types = sorted((selected & {"onsite", "hybrid"}) if not any_type else {"onsite", "hybrid"})
        remote_on = any_type or "remote" in selected or any(is_remote_location(l) for l in locations)
        remote_scope = (search.get("remote_scope") or "state").lower()   # "state" | "us" | "off"
        states = sorted(home_states(locations))

        plan = []
        for title in titles:
            for loc in locations:
                if is_remote_location(loc):
                    continue
                if local_types:
                    plan.append({"title": title, "location": loc, "work_types": local_types, "group": "local"})
        if remote_on and remote_scope != "off":
            remote_locs = [f"{STATES[s]}, United States" for s in states] if (remote_scope == "state" and states) else ["United States"]
            for title in titles:
                for rl in remote_locs:
                    plan.append({"title": title, "location": rl, "work_types": ["remote"], "group": "remote"})
        # de-duplicate, keep order
        seen, out = set(), []
        for p in plan:
            key = (p["title"].lower(), p["location"].lower(), tuple(p["work_types"]))
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    async def _scrape_linkedin(
        self,
        titles: List[str],
        locations: List[str],
        days_ago: int,
        page: Page = None
    ) -> List[Job]:
        """
        Run the search plan with fair quotas:
        - total cap = search.max_discovered (default 40)
        - local vs remote split = search.local_share percent (default 70% local)
        - each search contributes its share first, leftovers fill any empty slots after
        so one search can no longer use up the whole cap.
        """
        import math
        logger.info("Scraping LinkedIn...")
        should_close_page = False
        if not page:
            page = await self.context.new_page()
            should_close_page = True

        search = self.config.get("search", {}) or {}
        cap = int(search.get("max_discovered") or 40)
        local_share = max(0, min(100, int(search.get("local_share", 70))))
        plan = self.build_search_plan(titles, locations)
        groups = {g: [p for p in plan if p["group"] == g] for g in ("local", "remote")}
        if groups["local"] and groups["remote"]:
            quota = {"local": round(cap * local_share / 100), "remote": cap - round(cap * local_share / 100)}
        else:
            quota = {"local": cap if groups["local"] else 0, "remote": cap if groups["remote"] else 0}
        logger.info(f"Search plan: {len(groups['local'])} local + {len(groups['remote'])} remote searches, "
                    f"quota local={quota['local']} remote={quota['remote']}")

        seen_ids = set()
        picked = {"local": [], "remote": []}
        leftovers = {"local": [], "remote": []}
        for g in ("local", "remote"):
            if not groups[g] or quota[g] <= 0:
                continue
            per_search = max(3, math.ceil(quota[g] / len(groups[g])))
            for p in groups[g]:
                if len(picked[g]) >= quota[g]:
                    break
                url = self._build_linkedin_search_url(p["title"], p["location"], days_ago, work_types=p["work_types"])
                found = await self._scrape_one_search(page, url, p["title"], p["location"])
                fresh = [j for j in found if j.job_id not in seen_ids]
                for j in fresh:
                    j.search_group = g
                take = fresh[:min(per_search, quota[g] - len(picked[g]))]
                for j in take:
                    seen_ids.add(j.job_id)
                picked[g].extend(take)
                leftovers[g].extend(fresh[len(take):])
            # fill this group's empty slots from its own leftovers
            for j in leftovers[g]:
                if len(picked[g]) >= quota[g]:
                    break
                if j.job_id not in seen_ids:
                    seen_ids.add(j.job_id)
                    picked[g].append(j)
        # any slots still empty: borrow from the other group's leftovers
        jobs = picked["local"] + picked["remote"]
        for g in ("local", "remote"):
            for j in leftovers[g]:
                if len(jobs) >= cap:
                    break
                if j.job_id not in seen_ids:
                    seen_ids.add(j.job_id)
                    jobs.append(j)

        if should_close_page:
            await page.close()
        logger.info(f"Scraped {len(jobs)} LinkedIn jobs "
                    f"({sum(1 for j in jobs if getattr(j, 'search_group', '') == 'local')} local, "
                    f"{sum(1 for j in jobs if getattr(j, 'search_group', '') == 'remote')} remote)")
        return jobs

    async def _job_page_location(self, page: Page) -> Optional[str]:
        """Location from the job page's top card (old and new LinkedIn layouts, then plain text)."""
        for sel in ['.jobs-unified-top-card__bullet', '.job-details-jobs-unified-top-card__bullet',
                    '.job-details-jobs-unified-top-card__primary-description-container',
                    '.job-details-jobs-unified-top-card__tertiary-description-container',
                    '.jobs-unified-top-card__primary-description', '.topcard__flavor--bullet']:
            try:
                el = page.locator(sel).first
                if await el.count():
                    loc = find_location(await el.inner_text())
                    if loc:
                        return loc
            except Exception:
                pass
        try:
            top = page.locator('.job-details-jobs-unified-top-card__container--two-pane, .jobs-unified-top-card, .top-card-layout, main').first
            text = (await top.inner_text(timeout=3000))[:1500] if await top.count() else ""
            loc = find_location(text)
            if loc:
                # add the workplace tag ("On-site"/"Hybrid"/"Remote") if the top card shows one
                from src.locations import workplace_type
                wt = workplace_type(text[:600])
                if wt and not workplace_type(loc):
                    tag = {'onsite': 'On-site', 'hybrid': 'Hybrid', 'remote': 'Remote'}[wt]
                    loc = f"{loc} ({tag})"
                return loc
        except Exception:
            pass
        return None

    async def _scrape_one_search(self, page: Page, search_url: str, title: str, location: str) -> List[Job]:
        """Open one LinkedIn search and return up to 25 job candidates."""
        jobs: List[Job] = []
        try:
            await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(4000)
            # Scroll the results list a few times so lazy-loaded cards render
            for _ in range(6):
                try:
                    await page.evaluate("""() => {
                        const list = document.querySelector('.jobs-search-results-list, .jobs-search-results__list, .scaffold-layout__list > div, .scaffold-layout__list');
                        if (list) { list.scrollTop = list.scrollHeight; } else { window.scrollBy(0, 1500); }
                    }""")
                except Exception:
                    pass
                await page.wait_for_timeout(800)

            # Extract job listings. LinkedIn changes its class names often, so try the
            # known card layouts in order and use the first one that finds cards.
            job_cards, count = None, 0
            for sel in CARD_SELECTORS:
                job_cards = page.locator(sel)
                count = await job_cards.count()
                if count:
                    logger.debug(f"Job cards matched: {sel}")
                    break
            
            logger.info(f"Found {count} LinkedIn jobs for '{title}' in '{location}'")

            if count == 0:
                # LinkedIn renamed its CSS classes: fall back to job links,
                # which always look like /jobs/view/<id>/. Title/company are
                # filled in later by the guard step from the job page itself.
                links = await page.eval_on_selector_all(
                    'a[href*="/jobs/view/"]',
                    """els => els.map(e => {
                        const card = e.closest('li, [data-occludable-job-id], [data-job-id], .job-card-container, .base-card');
                        return {href: e.href, text: (e.innerText || '').trim(), card: card ? (card.innerText || '').trim() : ''};
                    })"""
                )
                seen_ids = set()
                for item in links:
                    href = item.get("href") or ""
                    jid = self._extract_linkedin_job_id(href)
                    if not jid or not jid.isdigit() or jid in seen_ids:
                        continue
                    seen_ids.add(jid)
                    parsed = parse_card_text(item.get("card") or "")
                    jobs.append(Job(
                        job_id=f"linkedin_{jid}",
                        platform=Platform.LINKEDIN,
                        title=(item.get("text") or parsed["title"] or "Unknown").split("\n")[0][:120] or "Unknown",
                        company=parsed["company"] or "Unknown",
                        location=parsed["location"] or "Unknown",
                        url=f"https://www.linkedin.com/jobs/view/{jid}/",
                        guard_status=GuardStatus.UNKNOWN,
                        has_easy_apply=False,  # verified later by the guard
                        posted_date=datetime.now(),
                    ))
                    if len(seen_ids) >= 25:
                        break
                logger.info(f"Fallback link scan found {len(seen_ids)} jobs")
                if not seen_ids:
                    Path("data").mkdir(exist_ok=True)
                    await page.screenshot(path=f"data/search_zero_results_{int(datetime.now().timestamp())}.png")
                return jobs

            # First 25 cards of this search
            for i in range(min(count, 25)):
                try:
                    card = job_cards.nth(i)
                    
                    # Extract basic info with broader selectors
                    job_title_el = card.locator('h3, a[data-tracking-control-name*="job"], .job-card-list__title, .job-card-list__title--link, a.job-card-container__link strong').first
                    job_title = (await job_title_el.inner_text()).strip() if await job_title_el.count() else "Unknown"

                    company_el = card.locator('h4, a[data-tracking-control-name*="company"], .job-card-container__company-name, .job-card-container__primary-description, .artdeco-entity-lockup__subtitle').first
                    company = (await company_el.inner_text()).strip() if await company_el.count() else "Unknown"

                    job_location_el = card.locator('span.job-search-card__location, .job-card-container__metadata-item, .job-card-container__metadata-wrapper li, .artdeco-entity-lockup__caption').first
                    job_location = (await job_location_el.inner_text()).strip() if await job_location_el.count() else "Unknown"

                    # Class names missing or changed: read the card's visible text instead
                    if "Unknown" in (job_title, company, job_location):
                        parsed = parse_card_text(await card.inner_text())
                        job_title = job_title if job_title != "Unknown" else (parsed["title"] or "Unknown")
                        company = company if company != "Unknown" else (parsed["company"] or "Unknown")
                        job_location = job_location if job_location != "Unknown" else (parsed["location"] or "Unknown")
                    job_title = job_title.split("\n")[0]

                    job_link_el = card.locator('a[href*="/jobs/view/"], a[data-tracking-control-name*="job"], .job-card-list__title, .job-card-container__link').first
                    job_link = await job_link_el.get_attribute('href') if await job_link_el.count() else None
                    
                    if job_link and job_link.startswith('/'):
                        job_link = f"https://www.linkedin.com{job_link}"
                    elif not job_link or not job_link.startswith('http'):
                        continue # Skip invalid links
                    
                    # Extract job ID from URL
                    job_id = self._extract_linkedin_job_id(job_link)
                    if job_id.isdigit():
                        job_link = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    
                    # Create Job object (guard check happens later)
                    job = Job(
                        job_id=f"linkedin_{job_id}",
                        platform=Platform.LINKEDIN,
                        title=job_title.strip(),
                        company=company.strip(),
                        location=job_location.strip(),
                        url=job_link,
                        guard_status=GuardStatus.UNKNOWN,
                        has_easy_apply=False,  # verified later by the guard (f_AL filter is not a guarantee)
                        posted_date=datetime.now()
                    )
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse LinkedIn job card: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Failed to scrape LinkedIn for '{title}' in '{location}': {e}")
        return jobs

    async def _scrape_indeed(
        self,
        titles: List[str],
        locations: List[str],
        days_ago: int,
        page: Page = None
    ) -> List[Job]:
        """Scrape Indeed jobs."""
        logger.info("Scraping Indeed...")
        jobs = []
        
        should_close_page = False
        if not page:
            page = await self.context.new_page()
            should_close_page = True
        
        for title in titles:
            for location in locations:
                try:
                    # Build Indeed search URL
                    search_url = self._build_indeed_search_url(title, location, days_ago)
                    await page.goto(search_url, timeout=30000)
                    await page.wait_for_timeout(3000)
                    
                    # Extract job listings
                    job_cards = page.locator('div.job_seen_beacon, div[data-testid="job-result"]')
                    count = await job_cards.count()
                    
                    logger.info(f"Found {count} Indeed jobs for '{title}' in '{location}'")
                    
                    # Limit to first 25 per search
                    for i in range(min(count, 25)):
                        try:
                            card = job_cards.nth(i)
                            
                            # Extract basic info
                            job_title = await card.locator('h2 a, a[data-testid="job-title"]').first.inner_text()
                            company = await card.locator('span[data-testid="company-name"]').first.inner_text()
                            job_location = await card.locator('div[data-testid="text-location"]').first.inner_text()
                            job_link = await card.locator('h2 a').first.get_attribute('href')
                            
                            # Make absolute URL
                            if not job_link.startswith('http'):
                                job_link = f"https://www.indeed.com{job_link}"
                            
                            # Extract job ID
                            job_id = self._extract_indeed_job_id(job_link)
                            
                            job = Job(
                                job_id=f"indeed_{job_id}",
                                platform=Platform.INDEED,
                                title=job_title.strip(),
                                company=company.strip(),
                                location=job_location.strip(),
                                url=job_link,
                                guard_status=GuardStatus.UNKNOWN,
                                posted_date=datetime.now()
                            )
                            
                            jobs.append(job)
                            
                        except Exception as e:
                            logger.warning(f"Failed to parse Indeed job card: {e}")
                            continue
                    
                except Exception as e:
                    logger.error(f"Failed to scrape Indeed for '{title}' in '{location}': {e}")
                    continue
        
        if should_close_page:
            await page.close()
        logger.info(f"Scraped {len(jobs)} Indeed jobs")
        return jobs
    
    # Settings -> LinkedIn search URL codes
    WORK_TYPE_CODES = {"onsite": "1", "remote": "2", "hybrid": "3"}
    EXPERIENCE_CODES = {"internship": "1", "entry": "2", "associate": "3", "mid_senior": "4", "director": "5", "executive": "6"}

    def _build_linkedin_search_url(self, title: str, location: str, days_ago: int, work_types: List[str] = None) -> str:
        """LinkedIn search URL built from the user's search settings (config["search"]).
        `work_types` overrides the Settings work types (the search plan passes local/remote types)."""
        from urllib.parse import urlencode
        from src.salary import linkedin_salary_filter

        search = self.config.get("search", {}) or {}
        work_types = [w.lower() for w in (work_types if work_types is not None else (search.get("work_types") or []))]
        loc = (location or "").strip()
        if loc.lower() in ("remote", "anywhere", "remote (us)"):
            loc = "United States"
            work_types = ["remote"]

        days = int(days_ago or search.get("posted_within_days") or 14)
        params = {
            "keywords": title,
            "location": loc,
            "f_TPR": f"r{max(1, days) * 86400}",
            "f_AL": "true",          # Easy Apply only
        }
        wt = [self.WORK_TYPE_CODES[w] for w in work_types if w in self.WORK_TYPE_CODES]
        if wt:
            params["f_WT"] = ",".join(sorted(set(wt)))
        ex = [self.EXPERIENCE_CODES[e] for e in (search.get("experience_levels") or []) if e in self.EXPERIENCE_CODES]
        if ex:
            params["f_E"] = ",".join(sorted(set(ex)))
        dist = search.get("distance_miles")
        if dist and "united states" not in loc.lower():
            params["distance"] = str(int(dist))
        sb2 = linkedin_salary_filter(self.config)
        if sb2:
            params["f_SB2"] = str(sb2)
        params["refresh"] = "true"
        return "https://www.linkedin.com/jobs/search/?" + urlencode(params)

    def excluded_reason(self, job: Job):
        """Title word or company on the user's exclude lists -> reason string, else None."""
        search = self.config.get("search", {}) or {}
        title = f" {(job.title or '').lower()} "
        for w in search.get("exclude_title_words") or []:
            w = str(w).strip().lower()
            if w and re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", title):
                return f"Title contains excluded word '{w}'"
        company = (job.company or "").lower()
        for c in search.get("exclude_companies") or []:
            c = str(c).strip().lower()
            if c and c in company:
                return f"Excluded company '{c}'"
        return None

    def _build_indeed_search_url(self, title: str, location: str, days_ago: int) -> str:
        """Build Indeed search URL."""
        title_encoded = title.replace(" ", "+")
        location_encoded = location.replace(" ", "+").replace(",", "%2C")
        
        url = (
            f"https://www.indeed.com/jobs?"
            f"q={title_encoded}&"
            f"l={location_encoded}&"
            f"fromage={days_ago}"
        )
        
        return url
    
    def _extract_linkedin_job_id(self, url: str) -> str:
        """Extract job ID from LinkedIn URL."""
        import re
        # Support /jobs/view/12345 or /jobs/search/?currentJobId=12345
        match = re.search(r'/view/(\d+)', url)
        if match:
            return match.group(1)
        
        match = re.search(r'currentJobId=(\d+)', url)
        if match:
            return match.group(1)
            
        return url.split('?')[0].split('/')[-1] if '/' in url else url[-10:]
    
    def _extract_indeed_job_id(self, url: str) -> str:
        """Extract job ID from Indeed URL."""
        import re
        match = re.search(r'jk=([a-f0-9]+)', url)
        return match.group(1) if match else url[-10:]
    
    def _deduplicate_jobs(self, jobs: List[Job]) -> List[Job]:
        """
        Remove duplicate jobs based on job_id (URL-derived).
        """
        seen = set()
        unique_jobs = []
        
        for job in jobs:
            if job.job_id not in seen:
                seen.add(job.job_id)
                unique_jobs.append(job)
        
        logger.info(f"Deduplication: {len(jobs)} → {len(unique_jobs)} unique jobs")
        return unique_jobs


class GuardedJobScraper(JobScraper):
    """
    Extended scraper that runs guard checks on each job.
    """
    
    async def discover_and_guard_check_jobs(
        self,
        titles: List[str],
        locations: List[str],
        days_ago: int = 14,
        context: BrowserContext = None,
        on_job_found = None
    ) -> List[Job]:
        """
        Discover jobs AND run guard checks.
        
        Returns only jobs that pass guard (resume-only).
        """
        logger.info("Starting guarded job discovery...")
        
        # Step 1: Discover jobs
        all_jobs = await self.discover_jobs(titles, locations, days_ago, context=context)
        
        # Step 2: Run guard checks
        safe_jobs = []
        
        # If context provided, use it (staying in session)
        if context:
            await self._run_guard_checks(all_jobs, context, safe_jobs, on_job_found=on_job_found)
        else:
            # Fallback for headless
            async with async_playwright() as p:
                headless_browser = await p.chromium.launch(headless=True)
                headless_context = await headless_browser.new_context()
                await self._run_guard_checks(all_jobs, headless_context, safe_jobs, on_job_found=on_job_found)
                await headless_browser.close()
        
        logger.info(f"Guard check complete: {len(safe_jobs)}/{len(all_jobs)} jobs safe to apply")
        return safe_jobs

    async def _run_guard_checks(self, all_jobs, context: BrowserContext, safe_jobs, page: Page = None, on_job_found = None):
        """Helper to run guard checks across all jobs."""
        
        should_close_page = False
        if not page:
            page = await context.new_page()
            should_close_page = True

        for job in all_jobs:
            try:
                await page.goto(job.url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Run guard check
                if job.platform == Platform.LINKEDIN:
                    # Update info if unknown (LinkedIn specific) - try multiple robust selectors
                    if job.title == "Unknown":
                        title_selectors = ['h1.t-24', 'h1[class*="job-title"]', '.jobs-unified-top-card__job-title', 'h1']
                        for sel in title_selectors:
                            el = page.locator(sel).first
                            if await el.count():
                                job.title = (await el.inner_text()).strip()
                                break
                        if job.title == "Unknown":
                            # Absolute fallback: Page title usually contains "Job Title | Company | LinkedIn"
                            p_title = await page.title()
                            if " | " in p_title:
                                job.title = p_title.split(" | ")[0]
                    
                    if job.company == "Unknown":
                        company_selectors = ['.jobs-unified-top-card__company-name', 'a[href*="/company/"]', '.job-details-jobs-unified-top-card__company-name']
                        for sel in company_selectors:
                            el = page.locator(sel).first
                            if await el.count():
                                job.company = (await el.inner_text()).strip()
                                break
                    
                    if job.location == "Unknown":
                        job.location = await self._job_page_location(page) or "Unknown"
                        if job.location == "Unknown":
                            logger.info(f"  Location not found on job page: {job.url}")
                    
                    reason = self.excluded_reason(job)
                    if not reason:
                        # On-site/hybrid job in a state the user didn't pick -> skip before applying
                        from src.locations import outside_area, home_states
                        allowed = home_states((self.config.get("search", {}) or {}).get("locations") or [])
                        try:
                            top_text = await page.locator("main").first.inner_text(timeout=3000)
                        except Exception:
                            top_text = ""
                        reason = outside_area(job.location, top_text, allowed)
                    if reason:
                        from src.application_guard import GuardResult
                        guard_result = GuardResult(GuardStatus.SKIP_EXCLUDED, reason)
                    else:
                        guard_result = await self.guard.check_linkedin_job(page)
                elif job.platform == Platform.INDEED:
                    # Update info if unknown (Indeed specific)
                    if job.title == "Unknown":
                        title_el = page.locator('h1[data-testid="jobsearch-JobInfoHeader-title"]').first
                        if await title_el.count():
                            job.title = (await title_el.inner_text()).strip()
                    
                    guard_result = await self.guard.check_indeed_job(page)
                else:
                    guard_result = None
                
                # Update job with guard status
                if guard_result:
                    job.guard_status = guard_result.status
                    job.guard_reason = guard_result.reason
                    if guard_result.is_safe:
                        job.has_easy_apply = True
                        try:
                            desc_el = page.locator('#job-details, .jobs-description__content').first
                            if await desc_el.count():
                                job.description = (await desc_el.inner_text()).strip()
                        except Exception as e:
                            logger.debug(f"Could not fetch job description: {e}")
                        # Posted pay vs. the user's minimum
                        try:
                            from src.salary import parse_salary_range, below_minimum
                            top = page.locator('.job-details-jobs-unified-top-card__container--two-pane, .jobs-unified-top-card, .job-details-fit-level-preferences, main').first
                            top_text = (await top.inner_text())[:4000] if await top.count() else ""
                            posted = parse_salary_range(top_text) or parse_salary_range(job.description or "")
                            if posted:
                                job.posted_salary = f"${posted[0]:,} - ${posted[1]:,} /yr"
                                job.salary_range = job.posted_salary
                            if below_minimum(posted, self.config):
                                job.guard_status = GuardStatus.SKIP_SALARY
                                job.guard_reason = f"Posted pay {job.posted_salary} is below your minimum"
                                logger.info(f"✗ SKIP: {job.guard_reason} - {job.title} at {job.company}")
                                await asyncio.sleep(2)
                                continue
                        except Exception as e:
                            logger.debug(f"Could not read salary: {e}")
                        # Extract Hiring Team / Recruiter info (LinkedHelper best practice for direct follow-up)
                        try:
                            hirer = page.locator('.hirer-card__hirer-information, .jobs-poster, [class*="hirer-card"], .message-the-recruiter').first
                            if await hirer.count():
                                name_el = hirer.locator('a[href*="/in/"], strong, .jobs-poster__name, h3').first
                                if await name_el.count():
                                    r_name = (await name_el.inner_text()).strip().split('\n')[0]
                                    if r_name and len(r_name) < 50:
                                        job.recruiter_name = r_name
                                    r_link = await name_el.get_attribute('href')
                                    if r_link:
                                        job.recruiter_url = r_link.split('?')[0]
                                        logger.info(f"  Found recruiter: {job.recruiter_name} ({job.recruiter_url})")
                        except Exception as e:
                            logger.debug(f"Could not extract recruiter info: {e}")

                        safe_jobs.append(job)
                        logger.info(f"SAFE: {job.title} at {job.company}")
                        if on_job_found:
                            try:
                                if asyncio.iscoroutinefunction(on_job_found):
                                    await on_job_found(job)
                                else:
                                    on_job_found(job)
                            except Exception as cb_err:
                                logger.warning(f"Error in on_job_found callback: {cb_err}")
                    else:
                        logger.info(f"✗ SKIP: {guard_result.status} - {guard_result.reason}")
                
                # Don't close page - we're reusing it for all guard checks
                await asyncio.sleep(2)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Guard check failed for {job.url}: {e}")
                continue
        
        if should_close_page:
            await page.close()
