# Project Specification: Job Application Agent Web Interface

## Project Overview
Build a production-ready web application interface for the automated job application agent. The system should allow users to configure, monitor, and manage their job search automation through an intuitive web dashboard, with deployment capabilities for cloud servers.

---

## Core Requirements

### 1. Web Application Architecture

**Technology Stack Recommendations:**
- **Backend Framework**: FastAPI (Python) or Flask - integrates seamlessly with existing Python agent
- **Frontend Framework**: React or Vue.js for responsive UI
- **Database**: PostgreSQL for user data, job tracking, and application history
- **Task Queue**: Celery with Redis for background job processing
- **Authentication**: JWT-based auth with email verification
- **Email Service**: SendGrid or AWS SES for notifications
- **File Storage**: S3 or local storage with encryption for resumes
- **Deployment**: Docker + Docker Compose for easy server deployment

### 2. User Interface Components

#### 2.1 Dashboard (Landing Page After Login)
**Features:**
- Overview statistics:
  - Total applications submitted today/this week
  - Success rate (applications submitted vs attempted)
  - Active job count in queue
  - Next scheduled run time
- Recent activity feed showing last 10 applications
- Quick action buttons: "Start New Job Search", "View Reports", "Configure Settings"
- System status indicator (running/idle/paused)

#### 2.2 Configuration Page
**All fields should be dropdown-based where applicable with smart defaults**

**Personal Information Section:**
- Full Name (text input, required)
- Email Address (email input, required, validated)
- Phone Number (formatted input with country code dropdown)
- Address Fields:
  - Street Address (text input)
  - City (autocomplete dropdown - major US cities)
  - State (dropdown - all US states)
  - ZIP Code (5-digit formatted input)
- Years of Experience (number dropdown: 0-20+)
- LinkedIn Profile URL (URL input, validated)
- Portfolio URL (URL input, optional)

**Job Search Preferences Section:**
- Job Titles/Keywords:
  - Multi-select dropdown with common roles:
    - Sales Development Representative
    - Business Development Representative
    - Customer Success Manager
    - Account Executive
    - Customer Service Representative
    - Inside Sales Representative
    - Account Manager
    - Sales Engineer
  - Allow custom text input for additional keywords
  
- Location Preferences:
  - Multi-select dropdown:
    - Remote (Worldwide)
    - Remote (US Only)
    - Hybrid
    - On-site
  - City/State selector (autocomplete, multiple)
  - Radius slider (if on-site/hybrid): 0-100 miles
  
- Seniority Levels (multi-select checkboxes):
  - Internship
  - Entry Level (0-2 years)
  - Mid Level (3-5 years)
  - Senior Level (5-10 years)
  - Lead/Principal (10+ years)
  - Executive/Director
  
- Job Platforms (multi-select checkboxes):
  - LinkedIn (with Easy Apply filter)
  - Indeed
  - Glassdoor
  - ZipRecruiter
  - Company career pages (future feature)
  
- Application Settings:
  - Max applications per day (number input with slider: 1-50)
  - Max applications per session (number input: 1-100)
  - Posted within (dropdown):
    - Last 24 hours
    - Last 3 days
    - Last week
    - Last 2 weeks
    - Last month
  - Language preference (dropdown):
    - English only
    - All languages

**Application Behavior Section:**
- Resume file upload:
  - Drag-and-drop zone
  - File type validation (PDF, DOCX)
  - Preview uploaded resume
  - Multiple resume support (dropdown to select which to use)
  
- Cover letter:
  - Upload pre-written cover letter
  - Or enable AI-generated custom cover letters per job
  
- Application pacing:
  - Delay between applications:
    - Dropdown presets: "Conservative (5-10 min)", "Moderate (2-5 min)", "Aggressive (30-60 sec)"
    - Custom range sliders (min/max in seconds)
  
- Auto-answer settings:
  - Enable/disable auto-fill for screening questions (toggle)
  - Common screening question answers:
    - Work authorization (dropdown: Yes/No/Require Sponsorship)
    - Security clearance (dropdown: None/Confidential/Secret/Top Secret)
    - Willing to relocate (dropdown: Yes/No/Maybe)
    - Expected salary (salary range sliders with currency selector)
    - Available start date (date picker or dropdown: Immediately/2 weeks/1 month/Negotiable)
    - Disability status (dropdown: Prefer not to say/No/Yes)
    - Veteran status (dropdown: Prefer not to say/No/Yes/Protected Veteran)
    - Gender (dropdown: Prefer not to say/Male/Female/Non-binary/Other)
    - Ethnicity (dropdown: Prefer not to say + standard EEOC categories)

**Safety Guards Section:**
- Strict mode toggle (checkbox with explanation tooltip)
- Maximum screening questions allowed (number input: 0-5)
- Skip conditions (checkboxes):
  - Skip jobs requiring assessments
  - Skip jobs with external ATS redirects
  - Skip jobs with video screening requirements
  - Skip jobs older than X days
- Blacklist/Whitelist:
  - Company blacklist (multi-text input with autocomplete)
  - Company whitelist (multi-text input with autocomplete)
  - Keyword exclusions (text input, comma-separated)

**Schedule & Automation Section:**
- Run mode (radio buttons):
  - Manual only (user triggers each run)
  - Scheduled runs
  - Continuous monitoring (with daily cap)
  
- Schedule configuration (if scheduled):
  - Time picker for daily runs (e.g., "Run at 9:00 AM daily")
  - Days of week selector (checkboxes: Mon-Sun)
  - Timezone dropdown (auto-detected, user can override)
  
- Pause/Resume controls:
  - Emergency stop button
  - Pause until date picker
  - Auto-pause after X applications toggle

#### 2.3 Resume Management Page
- List of uploaded resumes with:
  - File name
  - Upload date
  - File size
  - Set as default (radio button)
  - Preview button
  - Download button
  - Delete button (with confirmation)
- Upload new resume button
- Resume parser preview (shows extracted: name, email, phone, skills, experience)

#### 2.4 Job Queue Page
- Data table showing:
  - Job title
  - Company
  - Location
  - Match score (percentage)
  - Posted date
  - Status (Queued/In Progress/Applied/Skipped/Failed)
  - Easy Apply available (yes/no badge)
  - Actions: View details, Skip, Priority flag
  
- Filters:
  - Status filter (dropdown multi-select)
  - Company filter (searchable dropdown)
  - Date range picker
  - Match score range slider
  
- Sorting options (dropdown):
  - Match score (high to low)
  - Posted date (newest first)
  - Company name (A-Z)
  
- Bulk actions:
  - Select multiple jobs (checkboxes)
  - Bulk skip
  - Bulk apply (force apply)
  - Export to CSV

#### 2.5 Application History Page
- Data table with:
  - Application date/time
  - Job title
  - Company
  - Location
  - Status (Submitted/Failed/Skipped)
  - Failure reason (if applicable)
  - Application URL (link to LinkedIn)
  - Actions: View details, View screenshot, Retry
  
- Statistics cards:
  - Total applications submitted
  - Success rate
  - Average applications per day
  - Most applied-to companies
  - Top job titles applied for
  
- Charts:
  - Applications over time (line chart)
  - Success rate trend (line chart)
  - Applications by company (bar chart)
  - Applications by job title (pie chart)
  
- Export options:
  - Export date range to CSV/Excel
  - Generate PDF report

#### 2.6 Reports & Analytics Page
- Time period selector (dropdown):
  - Last 7 days
  - Last 30 days
  - Last 90 days
  - Custom date range
  
- Key Metrics Dashboard:
  - Total applications (number with trend indicator)
  - Success rate percentage (gauge chart)
  - Average response time (if tracking email responses)
  - Interview requests received
  
- Detailed Reports Section:
  - Application Success Report:
    - Breakdown by company
    - Breakdown by job title
    - Breakdown by location
  - Error Analysis Report:
    - Most common failure reasons
    - Button detection success rate
    - Guard system skip reasons
  - Time Analysis Report:
    - Peak application times
    - Average time per application
    - Session duration statistics
  
- Email Report Scheduling:
  - Frequency dropdown: Daily/Weekly/Monthly
  - Day of week (if weekly)
  - Time picker
  - Recipients (multi-email input)
  - Report format checkboxes: Summary/Detailed/Charts included

#### 2.7 Logs & Diagnostics Page
- Real-time log viewer:
  - Live tail of application logs (WebSocket connection)
  - Log level filter dropdown (DEBUG/INFO/WARNING/ERROR)
  - Search/filter text input
  - Download logs button (with date range selector)
  
- Failure diagnostics section:
  - List of recent failures with:
    - Timestamp
    - Job title/company
    - Failure reason
    - View screenshot button
    - View button inventory button
  - Auto-generated diagnostic report download
  
- System health indicators:
  - Browser connection status (green/yellow/red badge)
  - LinkedIn login status
  - Task queue status (number of pending jobs)
  - Database connection status
  - Email service status

#### 2.8 Settings Page
- Account Settings:
  - Change password
  - Email preferences
  - Timezone setting
  - Language preference
  
- Notification Settings:
  - Email notifications checkboxes:
    - Daily summary report
    - Application submitted confirmation
    - Application failed alert
    - Job queue empty notification
    - Weekly analytics report
  - Email delivery time picker
  - Test email button
  
- Security Settings:
  - Two-factor authentication toggle
  - Session timeout dropdown (15 min - 24 hours)
  - API key management (for advanced users)
  
- Danger Zone:
  - Clear all application history button (with confirmation)
  - Delete account button (with triple confirmation)
  - Export all data button (GDPR compliance)

---

## 3. Email Notification System

### 3.1 Email Templates Required

**Daily Summary Email:**
- Subject: "Job Application Summary - [Date]"
- Content:
  - Overview stats (applications submitted, success rate)
  - List of jobs applied to (company, title, link)
  - List of jobs skipped (with reasons)
  - Any errors encountered
  - Next scheduled run time
  
**Application Success Email:**
- Subject: "Application Submitted - [Job Title] at [Company]"
- Content:
  - Job details
  - Link to LinkedIn application
  - Match score
  - Submitted timestamp
  - Suggested follow-up actions

**Application Failed Email:**
- Subject: "Application Failed - [Job Title] at [Company]"
- Content:
  - Job details
  - Failure reason
  - Screenshot link (if available)
  - Suggested fix (if automated)
  - Retry button link

**Weekly Analytics Email:**
- Subject: "Weekly Job Search Report - [Date Range]"
- Content:
  - Week overview (total applications, success rate, top companies)
  - Charts embedded (applications over time, success rate)
  - Comparison to previous week
  - Recommendations for improving success rate
  - Link to full report in dashboard

**Job Queue Empty Alert:**
- Subject: "Job Queue Empty - Action Required"
- Content:
  - No jobs in queue notification
  - Suggestions: expand search criteria, check new postings, review skipped jobs
  - Quick configuration link

### 3.2 Email Configuration in UI
- SMTP settings page (for self-hosted email)
- Or integration with email services:
  - SendGrid API key input
  - AWS SES credentials
  - Mailgun API key
- Email template customization (advanced feature)
- Test email functionality before saving

---

## 4. Backend API Endpoints

### 4.1 Authentication Endpoints
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login (returns JWT)
- `POST /api/auth/logout` - Invalidate token
- `POST /api/auth/refresh` - Refresh JWT token
- `POST /api/auth/forgot-password` - Password reset email
- `POST /api/auth/reset-password` - Reset password with token

### 4.2 Configuration Endpoints
- `GET /api/config` - Get user configuration
- `PUT /api/config` - Update configuration
- `POST /api/config/validate` - Validate configuration before saving
- `GET /api/config/defaults` - Get default configuration template

### 4.3 Resume Endpoints
- `POST /api/resumes/upload` - Upload resume file
- `GET /api/resumes` - List user's resumes
- `GET /api/resumes/{id}` - Get resume details
- `DELETE /api/resumes/{id}` - Delete resume
- `PUT /api/resumes/{id}/set-default` - Set default resume
- `GET /api/resumes/{id}/preview` - Get parsed resume data

### 4.4 Job Endpoints
- `GET /api/jobs/queue` - Get job queue (paginated, filterable)
- `GET /api/jobs/{id}` - Get job details
- `POST /api/jobs/search` - Trigger job search (manual)
- `PUT /api/jobs/{id}/skip` - Skip a job
- `PUT /api/jobs/{id}/priority` - Flag job as priority
- `DELETE /api/jobs/{id}` - Remove job from queue

### 4.5 Application Endpoints
- `GET /api/applications` - Get application history (paginated, filterable)
- `GET /api/applications/{id}` - Get application details
- `POST /api/applications/start` - Start application process
- `POST /api/applications/stop` - Stop application process
- `POST /api/applications/{id}/retry` - Retry failed application
- `GET /api/applications/stats` - Get application statistics

### 4.6 Report Endpoints
- `GET /api/reports/summary` - Get summary statistics
- `GET /api/reports/detailed` - Get detailed analytics
- `GET /api/reports/export` - Export report (CSV/PDF)
- `POST /api/reports/schedule-email` - Schedule email report

### 4.7 Logs & Diagnostics Endpoints
- `GET /api/logs` - Get logs (paginated, filterable)
- `GET /api/logs/stream` - WebSocket for real-time logs
- `GET /api/diagnostics/failures` - Get recent failures
- `GET /api/diagnostics/screenshot/{id}` - Get failure screenshot
- `GET /api/diagnostics/button-inventory/{id}` - Get button inventory
- `GET /api/health` - System health check

### 4.8 Settings Endpoints
- `GET /api/settings` - Get user settings
- `PUT /api/settings` - Update user settings
- `POST /api/settings/email/test` - Send test email
- `POST /api/settings/notifications` - Update notification preferences

---

## 5. Database Schema

### 5.1 Tables Required

**users**
- id (UUID, primary key)
- email (string, unique, indexed)
- password_hash (string)
- full_name (string)
- created_at (timestamp)
- last_login (timestamp)
- is_active (boolean)
- timezone (string)

**configurations**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- config_json (JSONB) - stores all configuration
- created_at (timestamp)
- updated_at (timestamp)

**resumes**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- file_name (string)
- file_path (string, encrypted)
- file_size (integer)
- is_default (boolean)
- parsed_data (JSONB)
- uploaded_at (timestamp)

**jobs**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- job_id_external (string) - LinkedIn job ID
- platform (string)
- title (string, indexed)
- company (string, indexed)
- location (string)
- url (string)
- description (text)
- match_score (float)
- has_easy_apply (boolean)
- guard_status (enum: pending/safe/skip/failed)
- status (enum: queued/in_progress/applied/skipped/failed)
- discovered_at (timestamp, indexed)
- applied_at (timestamp, nullable)

**applications**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- job_id (UUID, foreign key)
- status (enum: submitted/failed/skipped)
- failure_reason (string, nullable)
- screenshot_path (string, nullable)
- button_inventory_path (string, nullable)
- applied_at (timestamp, indexed)
- metadata (JSONB)

**email_reports**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- report_type (enum: daily/weekly/monthly/custom)
- schedule (string) - cron expression
- recipients (array of strings)
- last_sent (timestamp)
- next_send (timestamp, indexed)
- is_active (boolean)

**logs**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- level (enum: debug/info/warning/error)
- message (text)
- context (JSONB)
- created_at (timestamp, indexed)

**sessions**
- id (UUID, primary key)
- user_id (UUID, foreign key)
- token (string, indexed)
- expires_at (timestamp, indexed)
- created_at (timestamp)

---

## 6. Deployment Requirements

### 6.1 Docker Setup
- Create `Dockerfile` for Python backend
- Create `Dockerfile` for frontend build
- Create `docker-compose.yml` with services:
  - Web backend (FastAPI/Flask)
  - Frontend (Nginx serving built React/Vue)
  - PostgreSQL database
  - Redis (for Celery task queue)
  - Celery worker (for background jobs)
  - Celery beat (for scheduled tasks)
  - Optional: PGAdmin (for database management)

### 6.2 Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `SECRET_KEY` - JWT signing key
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` - Email config
- `SENDGRID_API_KEY` or `AWS_SES_*` - Alternative email service
- `S3_BUCKET` or `FILE_STORAGE_PATH` - Resume storage
- `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` - For automated login (encrypted)
- `FRONTEND_URL` - For CORS configuration
- `LOG_LEVEL` - Application logging level

### 6.3 Server Requirements
- Minimum: 2 CPU cores, 4GB RAM, 20GB storage
- Recommended: 4 CPU cores, 8GB RAM, 50GB storage
- OS: Ubuntu 20.04 LTS or newer
- Docker & Docker Compose installed
- SSL certificate for HTTPS (Let's Encrypt)
- Firewall configured (ports 80, 443 open)

### 6.4 Deployment Script
Create `deploy.sh` script that:
1. Pulls latest code from Git repository
2. Builds Docker images
3. Runs database migrations
4. Restarts services with zero downtime
5. Verifies health checks pass
6. Rolls back if deployment fails

---

## 7. Security Considerations

### 7.1 Authentication & Authorization
- JWT tokens with short expiration (15 min access, 7 day refresh)
- Secure password hashing (bcrypt with salt)
- Rate limiting on login attempts (5 attempts per 15 min)
- Email verification required for new accounts
- Optional 2FA (TOTP-based)

### 7.2 Data Protection
- Resume files encrypted at rest
- LinkedIn credentials encrypted with user-specific key
- Database connections over SSL
- API requests over HTTPS only
- CORS configured for frontend domain only

### 7.3 Privacy & Compliance
- GDPR-compliant data export functionality
- Right to deletion (cascade delete user data)
- Clear privacy policy and terms of service
- Data retention policy (configurable)
- Audit log for sensitive operations

### 7.4 Application Security
- Input validation on all form fields
- SQL injection protection (parameterized queries)
- XSS protection (sanitize user inputs)
- CSRF tokens for state-changing operations
- Regular dependency updates

---

## 8. User Experience Enhancements

### 8.1 Responsive Design
- Mobile-first responsive layouts
- Touch-friendly interfaces for tablets
- Collapsible sidebar navigation
- Optimized loading times

### 8.2 Accessibility
- WCAG 2.1 Level AA compliance
- Keyboard navigation support
- Screen reader compatible
- High contrast mode option
- Font size adjustment

### 8.3 Onboarding Flow
- Welcome wizard for new users:
  1. Upload resume
  2. Configure basic preferences
  3. Set notification preferences
  4. Connect LinkedIn (with guided instructions)
  5. Run first job search (with tutorial tooltips)
- Interactive tutorial mode (can be replayed)
- Help tooltips throughout interface
- Link to documentation/video tutorials

### 8.4 Status Indicators
- Real-time progress bars during job search
- Live updates during application process
- Toast notifications for important events
- System status banner (all services operational)

---

## 9. Advanced Features (Future Enhancements)

### 9.1 AI-Powered Features
- Resume optimization suggestions
- Custom cover letter generation per job
- Interview question prediction based on job description
- Salary negotiation recommendations

### 9.2 Integration Capabilities
- Webhook support for external integrations
- Zapier integration
- Browser extension for manual job tracking
- Mobile app (iOS/Android)

### 9.3 Team Features
- Multi-user accounts (recruiter mode)
- Candidate management dashboard
- Application templates sharing
- Team analytics

### 9.4 Premium Features
- Advanced analytics and AI insights
- Priority support
- Higher application limits
- Custom domain for self-hosted
- White-label option

---

## 10. Development Phases

### Phase 1: MVP (4-6 weeks)
- Basic authentication and user management
- Configuration page with essential dropdowns
- Resume upload functionality
- Manual job search trigger
- Basic application history table
- Email notification for daily summary
- Docker deployment setup

### Phase 2: Core Features (4-6 weeks)
- Full configuration page with all dropdowns
- Job queue management
- Scheduled runs
- Detailed analytics dashboard
- Comprehensive email reports
- Real-time log viewer

### Phase 3: Polish & Enhancement (3-4 weeks)
- Advanced filtering and sorting
- Export capabilities
- Failure diagnostics interface
- Onboarding wizard
- Performance optimization
- Security hardening

### Phase 4: Advanced Features (4-6 weeks)
- AI-powered suggestions
- Team features
- Third-party integrations
- Mobile responsiveness
- Comprehensive testing

---

## 11. Testing Requirements

### 11.1 Unit Tests
- Backend API endpoint tests (>80% coverage)
- Frontend component tests
- Database model tests
- Email template rendering tests

### 11.2 Integration Tests
- Full application flow test (register → configure → apply)
- Email delivery tests
- Background job processing tests
- Database migration tests

### 11.3 End-to-End Tests
- Selenium/Playwright tests for critical user flows
- Load testing (100+ concurrent users)
- Security penetration testing
- Browser compatibility testing

### 11.4 Manual Testing Checklist
- User acceptance testing with real users
- Accessibility audit
- Mobile device testing
- Email client rendering tests (Gmail, Outlook, Apple Mail)

---

## 12. Documentation Requirements

### 12.1 User Documentation
- Getting started guide
- Configuration guide with screenshots
- FAQ section
- Video tutorials for key workflows
- Troubleshooting guide

### 12.2 Admin Documentation
- Installation guide
- Deployment guide
- Environment variables reference
- Database schema documentation
- API documentation (OpenAPI/Swagger)

### 12.3 Developer Documentation
- Architecture overview
- Code structure guide
- Contributing guidelines
- Development setup instructions
- Testing guide

---

## Success Criteria

The project is considered successful when:
1. ✅ Users can configure job search through intuitive dropdown-based UI
2. ✅ Application runs automatically on schedule without manual intervention
3. ✅ Email reports are delivered reliably with comprehensive statistics
4. ✅ System can be deployed to server in <30 minutes using provided scripts
5. ✅ 95%+ uptime for production deployment
6. ✅ Sub-2-second page load times for all UI pages
7. ✅ Zero security vulnerabilities in production code
8. ✅ Full mobile responsiveness across all pages
9. ✅ Complete test coverage (>80%) with passing CI/CD pipeline
10. ✅ Positive user feedback from beta testing (>4.0/5.0 rating)

---

## Deliverables

1. ✅ Complete web application (frontend + backend)
2. ✅ Docker deployment configuration
3. ✅ Database migration scripts
4. ✅ Email notification system with templates
5. ✅ API documentation (Swagger/OpenAPI)
6. ✅ User documentation and admin guide
7. ✅ Deployment guide and scripts
8. ✅ Test suite with >80% coverage
9. ✅ CI/CD pipeline configuration
10. ✅ Production-ready Docker Compose file
