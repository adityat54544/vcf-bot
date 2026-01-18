# Railway.app Deployment Guide for Aura VCF Bot

This guide will help you deploy the Aura VCF Bot to Railway.app for 24/7 operation.

## Deployment Steps

### 1. Prepare Your Railway.app Account
- Sign up at [https://railway.app](https://railway.app)
- Create a new project

### 2. Connect Your GitHub Repository
- Click "New Project" and select "Deploy from GitHub repo"
- Connect your GitHub account and select this repository
- Railway.app will automatically detect the Dockerfile

### 3. Configure Environment Variables
Go to the "Variables" tab and add the following:

**Required:**
- `BOT_TOKEN` = Your Telegram Bot Token (add as a secret)
  - Get this from @BotFather on Telegram

**Optional:**
- `WEBHOOK_URL` = Your Railway.app generated URL (e.g., `https://your-project.up.railway.app`)
- `PORT` = `8000` (default, Railway.app sets this automatically)
- `LOG_LEVEL` = `INFO` (default)
- `SECRET_TOKEN` = Your secret token for webhook validation (add as a secret)

### 4. Deployment Configuration
- Railway.app will automatically:
  - Use the Dockerfile for containerization
  - Use the Procfile for process management
  - Set up health checks using the `/health` endpoint
  - Monitor the service and restart if it crashes

### 5. Webhook Setup (Optional)
If you want to use webhooks instead of polling:
1. After deployment, get your Railway.app URL
2. Set `WEBHOOK_URL` to `https://your-project.up.railway.app`
3. Set `SECRET_TOKEN` for security
4. Restart the service

### 6. Monitoring and Maintenance
- Railway.app provides:
  - Automatic health checks every 30 seconds
  - Logs and monitoring dashboard
  - Automatic restarts if the service crashes
  - Resource usage monitoring

## Railway.app Specific Features

### Automatic Scaling
- The bot will automatically scale based on traffic
- Railway.app handles load balancing

### Persistent Operation
- The bot runs 24/7 without interruption
- Automatic restarts if any issues occur

### Health Monitoring
- Railway.app uses the `/health` endpoint to monitor bot status
- If the bot becomes unhealthy, Railway.app will restart it

## Troubleshooting

### Common Issues:
1. **Bot not starting**: Check that `BOT_TOKEN` is set correctly
2. **Webhook issues**: Ensure `WEBHOOK_URL` is correct and accessible
3. **Port conflicts**: Railway.app sets `PORT` automatically, don't override unless necessary

### Logs:
- Check Railway.app logs for detailed error information
- Use `railway logs` command if you have Railway CLI installed

## Cost Optimization
- Use Railway.app free tier for development
- Monitor resource usage in the dashboard
- Scale down when not in active development

## Updates
To update your bot:
1. Push changes to your GitHub repository
2. Railway.app will automatically redeploy
3. Monitor the deployment in the Railway.app dashboard

## Support
For Railway.app specific issues:
- Check [Railway.app documentation](https://docs.railway.app)
- Join Railway.app community for support

For bot-specific issues:
- Check the bot's health endpoint: `https://your-project.up.railway.app/health`
- Review the bot logs in Railway.app dashboard
