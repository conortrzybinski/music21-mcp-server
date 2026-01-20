# Discord Webhook Configuration Guide

This guide provides comprehensive instructions for setting up Discord webhooks to receive automated notifications from the music21-mcp-server repository.

## Overview

Discord webhooks allow your repository to send real-time notifications to a Discord channel for various GitHub events such as:
- Workflow runs (CI/CD status)
- Pull requests (opened, merged, etc.)
- Releases
- Security alerts (code scanning)

## Prerequisites

- Discord server with administrator permissions
- GitHub repository with admin access
- GitHub CLI (`gh`) installed and authenticated

## Step 1: Create Discord Webhook

### 1.1 Discord Server Setup
1. Open Discord and navigate to your server
2. Right-click on the channel where you want notifications
3. Select **Edit Channel**
4. Go to **Integrations** tab
5. Click **Create Webhook**
6. Configure webhook:
   - **Name**: `music21-mcp-notifications` (or your preferred name)
   - **Channel**: Select the target channel
   - **Avatar**: Optional - upload a custom avatar
7. Copy the **Webhook URL** - you'll need this for GitHub configuration

### 1.2 Discord Webhook URL Format
The webhook URL will look like:
```
https://discord.com/api/webhooks/{webhook_id}/{webhook_token}
```

**⚠️ Security Note**: Keep this URL secret! Anyone with this URL can send messages to your Discord channel.

## Step 2: Configure GitHub Repository Webhooks

### 2.1 Add Webhook URL as GitHub Secret
First, store the Discord webhook URL as a repository secret:

```bash
# Replace YOUR_WEBHOOK_URL with your actual Discord webhook URL
gh secret set DISCORD_WEBHOOK_URL --body "YOUR_WEBHOOK_URL"
```

### 2.2 Set Up Repository Webhook (Method 1: GitHub CLI)
Configure the repository webhook to trigger on specific events:

```bash
# Create webhook for multiple events
gh api repos/:owner/:repo/hooks \
  --method POST \
  --field name='web' \
  --field active=true \
  --field events='["workflow_run","pull_request","release","code_scanning_alert","push"]' \
  --field config='{"url":"YOUR_DISCORD_WEBHOOK_URL","content_type":"json"}'
```

### 2.3 Set Up Repository Webhook (Method 2: GitHub Web Interface)
Alternative method using GitHub's web interface:

1. Go to your repository settings
2. Click **Webhooks** in the left sidebar
3. Click **Add webhook**
4. Configure:
   - **Payload URL**: Your Discord webhook URL
   - **Content type**: `application/json`
   - **Secret**: Leave empty for Discord webhooks
   - **Events**: Select individual events:
     - ✅ Workflow runs
     - ✅ Pull requests
     - ✅ Releases
     - ✅ Code scanning alerts
     - ✅ Pushes (optional)

## Step 3: Webhook Event Configuration

### 3.1 Monitored Events
The webhook is configured to monitor these GitHub events:

| Event Type | Description | When Triggered |
|------------|-------------|----------------|
| `workflow_run` | CI/CD pipeline status | Test runs, builds, deployments |
| `pull_request` | PR lifecycle events | Created, updated, merged, closed |
| `release` | Release management | Published, edited, deleted |
| `code_scanning_alert` | Security alerts | Vulnerability discovered |
| `push` | Code changes | Commits pushed to main branches |

### 3.2 Event Filtering
You can customize which events trigger notifications by modifying the events array in the webhook configuration.

## Step 4: Webhook Payload Customization

### 4.1 Discord Message Format
Discord webhooks receive JSON payloads. You can customize the message format by:

1. Using Discord's webhook parameters:
   - `content`: Main message text
   - `username`: Custom sender name
   - `avatar_url`: Custom avatar
   - `embeds`: Rich embed messages

2. Example custom payload structure:
```json
{
  "content": "📋 Repository Update",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Workflow Completed",
    "description": "CI/CD pipeline finished successfully",
    "color": 65280,
    "fields": [
      {
        "name": "Branch",
        "value": "main",
        "inline": true
      },
      {
        "name": "Status",
        "value": "✅ Success",
        "inline": true
      }
    ]
  }]
}
```

## Step 5: Testing Your Webhook

### 5.1 Manual Testing
Use the provided test script to verify webhook connectivity:

```bash
# Run the webhook test script
./scripts/test-webhook.sh
```

### 5.2 GitHub Event Testing
1. Create a test pull request
2. Push a commit to trigger CI
3. Verify notifications appear in your Discord channel

### 5.3 Webhook Delivery Verification
Check webhook delivery status in GitHub:
1. Repository Settings → Webhooks
2. Click on your webhook
3. Review "Recent Deliveries" tab
4. Check for successful 200 responses

## Step 6: Security Best Practices

### 6.1 Secret Management
- ✅ Store webhook URLs as GitHub repository secrets
- ✅ Use environment variables in workflows
- ❌ Never commit webhook URLs to code
- ❌ Don't share webhook URLs in public channels

### 6.2 Access Control
- Limit Discord channel permissions
- Use dedicated channels for notifications
- Regular webhook URL rotation (quarterly)

### 6.3 Rate Limiting
Discord webhooks have rate limits:
- 30 requests per minute per webhook
- 5 requests per second burst
- Consider batching notifications for high-activity repositories

## Step 7: Advanced Configuration

### 7.1 Conditional Notifications
You can create conditional logic in GitHub Actions to send notifications only for specific conditions:

```yaml
- name: Send Discord notification
  if: failure()
  env:
    DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
  run: |
    curl -H "Content-Type: application/json" \
         -d '{"content":"❌ Build failed on branch ${{ github.ref_name }}"}' \
         $DISCORD_WEBHOOK_URL
```

### 7.2 Custom Workflow Integration
Add Discord notifications to existing workflows:

```yaml
jobs:
  notify-discord:
    name: Notify Discord
    runs-on: ubuntu-latest
    if: always()
    needs: [test, build, security]
    steps:
      - name: Send notification
        uses: ./.github/actions/discord-notification
        with:
          webhook-url: ${{ secrets.DISCORD_WEBHOOK_URL }}
          status: ${{ job.status }}
```

## Troubleshooting

### Common Issues

1. **Webhook not triggering**
   - Verify webhook URL is correct
   - Check GitHub webhook delivery logs
   - Ensure events are properly configured

2. **Discord not receiving messages**
   - Verify Discord webhook URL format
   - Check Discord channel permissions
   - Test with `curl` command directly

3. **Rate limiting errors**
   - Reduce notification frequency
   - Batch multiple updates
   - Implement exponential backoff

### Debug Commands

```bash
# Test webhook connectivity
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"content":"Test message"}' \
  YOUR_DISCORD_WEBHOOK_URL

# Check GitHub webhook status
gh api repos/:owner/:repo/hooks

# View webhook deliveries
gh api repos/:owner/:repo/hooks/{hook_id}/deliveries
```

## Maintenance

### Regular Tasks
- [ ] Weekly: Review notification volume and relevance
- [ ] Monthly: Check webhook delivery success rates
- [ ] Quarterly: Rotate webhook URLs for security
- [ ] As needed: Update notification filters based on team feedback

### Monitoring
Set up monitoring for:
- Webhook delivery failures
- Discord channel message volume
- Team engagement with notifications

## Example Configuration Summary

For the music21-mcp-server repository, a typical configuration would be:

```bash
# 1. Create Discord webhook in your server channel
# 2. Store as GitHub secret
gh secret set DISCORD_WEBHOOK_URL --body "https://discord.com/api/webhooks/YOUR_WEBHOOK"

# 3. Configure repository webhook
gh api repos/brightliu/music21-mcp-server/hooks \
  --method POST \
  --field name='web' \
  --field active=true \
  --field events='["workflow_run","pull_request","release","code_scanning_alert"]' \
  --field config='{"url":"'$DISCORD_WEBHOOK_URL'","content_type":"json"}'
```

This setup will provide comprehensive notifications for all major repository activities while maintaining security and avoiding spam.