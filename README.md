# Aura VCF Bot - Apply.Build Deployment

## Overview

This is a Telegram bot for VCF (Virtual Contact File) manipulation with Apply.Build deployment support. The bot provides the following functionality:

- Convert text/numbers to VCF format
- Count numbers in files
- Add contacts to existing VCF files
- Rename contacts in VCF files
- Rename VCF files

## Apply.Build / Nexpacks Deployment

### Requirements

- **Runtime**: Python 3.11
- **Install**: `pip install --no-cache-dir -r requirements.txt`
- **Start Command**: `./scripts/start.sh`
- **Port**: `$PORT` (platform-provided, default: 8000)
- **Health Check**: `GET /health` (returns `{"status": "ok"}`)
- **Probe Configuration**: 15s interval, 5s timeout, fail after 3 consecutive failures

### Configuration

#### Hardcoded Bot Token
The bot token is hardcoded in `bot/config.py` as: `7644164685:AAG1b0fmrR-iOS6j5q535YK34P42722s6cY`

#### Environment Variables (Optional)
You can still override the hardcoded token and set other options using environment variables:

- `BOT_TOKEN`: Override the hardcoded bot token
- `WEBHOOK_URL`: Full HTTPS URL for webhook registration
- `PORT`: Port to bind to (default: 8000)
- `LOG_LEVEL`: Logging level (default: INFO)
- `SECRET_TOKEN`: Secret token for webhook validation

### Webhook vs Polling

The bot supports both webhook and polling modes:
- **Webhook mode**: Used when `WEBHOOK_URL` is provided (recommended for production)
- **Polling mode**: Used as fallback when `WEBHOOK_URL` is not set

### Startup Process

1. **Environment Validation**: Checks for required `BOT_TOKEN`
2. **Webhook Registration**: If `WEBHOOK_URL` is set, registers webhook with Telegram
3. **ASGI Server Start**: Starts Gunicorn with Uvicorn workers

### Health Check

- **Endpoint**: `GET /health`
- **Response**: `{"status": "ok"}`
- **Status Codes**: 200 OK for healthy, 500 for errors

### Deployment Configuration

```yaml
name: aura-vcf-bot
runtime: python:3.11
build:
  commands:
    - pip install --no-cache-dir -r requirements.txt
start:
  command: ./scripts/start.sh
  port: $PORT
health:
  path: /health
  interval: 15s
  timeout: 5s
env:
  required:
    - BOT_TOKEN
  optional:
    - WEBHOOK_URL
    - PORT
    - LOG_LEVEL
    - SECRET_TOKEN
```

### Docker Configuration

The included `Dockerfile` provides:
- Python 3.11 slim base image
- Non-root user for security
- Health check endpoint
- Proper dependency installation
- Optimized layer caching

### Webhook Registration

To manually register the webhook:

```bash
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=$WEBHOOK_URL/webhook" \
     -d "secret_token=$SECRET_TOKEN"
```

### Troubleshooting

1. **Bot not starting**: Check `BOT_TOKEN` is set correctly
2. **Health check failing**: Verify the bot is running and port is exposed
3. **Webhook issues**: Check URL is publicly accessible and SSL is configured
4. **Polling mode**: If webhook fails, bot automatically falls back to polling

### Local Development

1. Copy `.env.example` to `.env` and set your `BOT_TOKEN`
2. Install dependencies: `pip install -r requirements.txt`
3. Start development server: `uvicorn bot.main:app --reload`

### Project Structure

```
aura_vcf_bot/
├── bot/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── health.py          # Health check endpoint
│   ├── webhook.py         # Webhook handling
│   ├── main.py            # ASGI application entry
│   ├── telegram_bot.py    # Core bot functionality
│   └── original_bot.py    # Original bot code (backup)
├── scripts/
│   └── start.sh           # Startup script
├── requirements.txt       # Dependencies
├── Dockerfile             # Container configuration
├── .env.example           # Environment template
└── README.md              # Documentation
```

## Bot Features

### Commands
- `/start` - Show main menu and bot information

### Menu Options
1. **TXT/Numbers → VCF**: Convert text files or numbers to VCF format
2. **Count Numbers**: Count unique numbers in uploaded files
3. **Add Contact**: Add a new contact to existing VCF files
4. **Rename Contacts**: Rename contacts in VCF files
5. **Rename VCF Files**: Rename VCF files in bulk

### File Handling
- Supports TXT, CSV, and VCF file formats
- Maximum file size: 20MB
- Automatic temporary file cleanup
- Batch processing with timeout handling

## Security
- Environment variable-based configuration
- Webhook secret token validation
- Non-root container execution
- Input validation and error handling
- Secure logging without sensitive data

## Monitoring
- Comprehensive logging with configurable levels
- Health check endpoint for platform monitoring
- Error handling with user notifications
- Performance metrics through logging

## 🐙 GitHub Repository

This project is now fully prepared for GitHub deployment!

### GitHub Features Included
- ✅ **Complete CI/CD Pipeline**: GitHub Actions workflow for testing and deployment
- ✅ **Comprehensive Documentation**: Updated README, CONTRIBUTING.md, and LICENSE
- ✅ **Code Quality**: Linting and testing workflows
- ✅ **Environment Management**: Proper .gitignore and .env.example files
- ✅ **Open Source Ready**: MIT License included

### GitHub Setup Instructions

1. **Create a new GitHub repository**:
   ```bash
   # Create new repository on GitHub.com
   # Then run these commands:
   git init
   git add .
   git commit -m "Initial commit - Aura VCF Bot ready for deployment"
   git branch -M main
   git remote add origin https://github.com/your-username/aura-vcf-bot.git
   git push -u origin main
   ```

2. **GitHub Actions will automatically run**:
   - Python 3.11 setup
   - Dependency installation
   - Linting with flake8
   - Health check testing

### Project Badges for GitHub

Add these to your GitHub README:

```markdown
![GitHub Actions](https://github.com/your-username/aura-vcf-bot/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128.0-green.svg)
```

### Contribution Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m "Add your feature"`
4. Push to branch: `git push origin feature/your-feature`
5. Open a Pull Request

## 🚀 Deployment Ready

The bot is now fully prepared for GitHub deployment with:
- ✅ All necessary GitHub files (.gitignore, LICENSE, CONTRIBUTING.md)
- ✅ CI/CD pipeline with GitHub Actions
- ✅ Comprehensive documentation
- ✅ Proper project structure
- ✅ Environment configuration
- ✅ Health check endpoints
- ✅ Error handling and logging

**Ready to deploy to GitHub!** 🎉
