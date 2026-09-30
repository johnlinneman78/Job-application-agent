#!/bin/bash

# Job Application Agent - Deployment Script
# Automated deployment to server

set -e

echo "🚀 Job Application Agent - Deployment Script"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    echo "Please install Docker Compose first"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed${NC}"
echo -e "${GREEN}✓ Docker Compose is installed${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ No .env file found. Creating from template...${NC}"
    cat > .env << EOF
# Database
DB_PASSWORD=changeme123

# JWT Secret (generate a random string in production)
SECRET_KEY=$(openssl rand -base64 32)

# Email Service (optional)
# SENDGRID_API_KEY=your-key-here

# CORS Origins
CORS_ORIGINS=http://localhost:3000
EOF
    echo -e "${GREEN}✓ Created .env file${NC}"
    echo -e "${YELLOW}⚠ Please edit .env and update DB_PASSWORD and SECRET_KEY${NC}"
fi

echo ""
echo "📦 Building Docker containers..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}✓ Services are running${NC}"
else
    echo -e "${RED}❌ Services failed to start${NC}"
    echo "Check logs with: docker-compose logs"
    exit 1
fi

echo ""
echo "=============================================="
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo "=============================================="
echo ""
echo "📍 Access Points:"
echo "   Frontend: http://localhost:3000"
echo "   Backend API: http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "📊 Useful Commands:"
echo "   View logs: docker-compose logs -f"
echo "   Stop services: docker-compose down"
echo "   Restart: docker-compose restart"
echo "   View status: docker-compose ps"
echo ""
echo "🎯 Next Steps:"
echo "   1. Open http://localhost:3000"
echo "   2. Register a new account"
echo "   3. Configure your job search settings"
echo "   4. Start applying!"
echo ""
