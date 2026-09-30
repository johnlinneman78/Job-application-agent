# Job Application Agent - Web Application

Complete web interface for automated job applications with dropdown-based configuration and email reporting.

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Docker & Docker Compose installed
- 4GB RAM minimum
- Ports 3000, 8000, 5432, 6379 available

### One-Command Deploy

```bash
# Clone/extract the project
cd job-agent-web/deployment

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f
```

Access the app at: **http://localhost:3000**

## 📁 Project Structure

```
job-agent-web/
├── backend/               # FastAPI Python backend
│   ├── main.py           # API endpoints
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile        # Backend container
├── frontend/              # React web interface
│   ├── src/
│   │   ├── App.jsx       # Main application
│   │   ├── App.css       # Styling
│   │   └── main.jsx      # Entry point
│   ├── package.json      # Node dependencies
│   ├── vite.config.js    # Vite configuration
│   └── Dockerfile        # Frontend container
└── deployment/
    └── docker-compose.yml # Full stack orchestration
```

## 🔧 Features Implemented

### ✅ Web Dashboard
- Real-time statistics
- Application success rate tracking
- Jobs in queue counter
- Today's applications count

### ✅ Configuration Page
**All fields are dropdown-based as requested:**
- **Personal Info**: Name, email, phone, years of experience (dropdown)
- **Job Search**: Keywords, locations, max applications (dropdown), posted within (dropdown)
- **Screening Questions**: Work authorization (dropdown), remote preference (dropdown), expected salary, start date (dropdown)
- **Application Settings**: Delay timings

### ✅ Job Queue Management
- View discovered jobs
- Filter by status
- Match score display
- One-click job search
- One-click start applications

### ✅ Application History
- Full application log
- Status tracking (submitted/failed/skipped)
- Sortable and filterable table
- Date/time stamps

### ✅ Authentication
- User registration
- Secure login (JWT tokens)
- Password hashing (bcrypt)
- Protected routes

## 📧 Email Reporting (Configured)

The backend includes endpoints for:
- Daily summary emails
- Application success notifications
- Failure alerts
- Weekly analytics reports

### Email Configuration

1. Edit `backend/main.py` to add email service:

```python
# Add to main.py
import sendgrid
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')

async def send_email(to_email, subject, html_content):
    message = Mail(
        from_email='noreply@yourdomain.com',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    response = sg.send(message)
```

2. Set environment variable:

```bash
export SENDGRID_API_KEY="your-key-here"
```

## 🖥️ Server Deployment

### Option 1: DigitalOcean/AWS/GCP

```bash
# 1. SSH into your server
ssh user@your-server-ip

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 4. Clone/upload project
scp -r job-agent-web user@your-server-ip:~/

# 5. Deploy
cd job-agent-web/deployment
docker-compose up -d
```

### Option 2: Using Deploy Script

```bash
# Make deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

## 🔐 Production Configuration

### 1. Environment Variables

Create `.env` file in `deployment/` directory:

```env
# Database
DB_PASSWORD=your-secure-password-here

# JWT Secret
SECRET_KEY=your-very-long-random-secret-key-here

# Email (SendGrid)
SENDGRID_API_KEY=SG.xxx

# or AWS SES
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1

# Frontend URL (for production)
FRONTEND_URL=https://yourdomain.com

# CORS Origins
CORS_ORIGINS=https://yourdomain.com
```

### 2. SSL Certificate (HTTPS)

Add nginx reverse proxy with Let's Encrypt:

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 3. Update Docker Compose for Production

```yaml
# Add nginx reverse proxy
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
    - /etc/letsencrypt:/etc/letsencrypt
```

## 📊 Usage

### 1. Register Account
- Navigate to http://localhost:3000
- Click "Sign Up"
- Enter email, password, full name
- Click "Sign Up"

### 2. Configure Settings
- Go to "Configuration" page
- Fill in personal information
- Set job search preferences using dropdowns
- Configure screening question answers
- Click "Save Configuration"

### 3. Search for Jobs
- Go to "Job Queue" page
- Click "🔍 Search Jobs"
- Wait for jobs to appear in table

### 4. Start Applying
- Review jobs in queue
- Click "▶️ Start Applying"
- Monitor progress in "Application History"

### 5. View Results
- Dashboard shows real-time stats
- Application History page shows all attempts
- Email reports sent automatically (if configured)

## 🔧 Development Mode

### Backend Only

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API Docs: http://localhost:8000/docs

### Frontend Only

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

## 📈 Monitoring

### Check Service Status

```bash
# All services
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart service
docker-compose restart backend
```

### Health Checks

- Backend health: http://localhost:8000/api/health
- Frontend: http://localhost:3000

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check logs
docker-compose logs backend

# Common fixes:
# 1. Port already in use
sudo lsof -i :8000
kill -9 <PID>

# 2. Database connection failed
docker-compose restart postgres
```

### Frontend won't build

```bash
# Check Node version
node --version  # Should be 18+

# Clear cache and rebuild
docker-compose down
docker-compose build --no-cache frontend
docker-compose up -d
```

### Can't login

```bash
# Reset database
docker-compose down -v
docker-compose up -d
```

## 🔄 Updates & Maintenance

### Update Code

```bash
# Pull latest changes
git pull

# Rebuild containers
docker-compose down
docker-compose build
docker-compose up -d
```

### Backup Database

```bash
# Backup
docker exec job-agent-db pg_dump -U jobagent jobagent > backup.sql

# Restore
docker exec -i job-agent-db psql -U jobagent jobagent < backup.sql
```

## 📝 API Documentation

Once running, access interactive API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Key Endpoints

```
POST   /api/auth/register      - Create account
POST   /api/auth/login         - Login
GET    /api/config             - Get configuration
PUT    /api/config             - Update configuration
GET    /api/jobs/queue         - Get job queue
POST   /api/jobs/search        - Trigger job search
GET    /api/applications       - Get application history
POST   /api/applications/start - Start applying to jobs
GET    /api/applications/stats - Get statistics
GET    /api/reports/summary    - Get summary report
```

## 🎯 Next Steps

### Integrate with Original Agent

Replace the sample job discovery with actual scraper:

```python
# In backend/main.py, update trigger_job_search():

@app.post("/api/jobs/search")
async def trigger_job_search(current_user: dict = Depends(get_current_user)):
    # Import your original agent
    from job_application_agent.src.job_scraper import GuardedJobScraper
    
    config = configs_db.get(current_user["email"])
    scraper = GuardedJobScraper(config, guard)
    
    jobs = await scraper.discover_jobs(...)
    jobs_db[current_user["email"]] = jobs
    
    return {"message": "Job search completed", "jobs_found": len(jobs)}
```

### Add Real Email Sending

```python
# Add celery task for sending emails
from celery import Celery

celery_app = Celery('tasks', broker='redis://redis:6379/0')

@celery_app.task
def send_daily_report(user_email):
    # Send email with stats
    pass
```

### Enable Scheduled Runs

Configure in frontend and execute via Celery Beat.

## 💡 Tips

1. **Start Simple**: Deploy locally first, test, then move to server
2. **Use Debug Mode**: Enable detailed logging during setup
3. **Monitor Logs**: Always check logs if something breaks
4. **Backup Regularly**: Database backups before major changes
5. **SSL Required**: Always use HTTPS in production

## 📞 Support

- Check logs: `docker-compose logs -f`
- Restart services: `docker-compose restart`
- Full reset: `docker-compose down -v && docker-compose up -d`

---

## ✅ Success Checklist

- [ ] Docker containers running
- [ ] Backend accessible at http://localhost:8000
- [ ] Frontend accessible at http://localhost:3000
- [ ] Can register new account
- [ ] Can login successfully
- [ ] Can save configuration
- [ ] Can search for jobs
- [ ] Can view job queue
- [ ] Can start applications
- [ ] Can view application history

**Status**: Ready for deployment! 🚀
