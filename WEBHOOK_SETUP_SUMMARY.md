# Discord Webhook Setup - Quick Reference

## Overview
Discord webhook integration for real-time CI/CD, PR, and security notifications from the music21-mcp-server repository.

## Quick Setup (3 Steps)

### 1. Create Discord Webhook
1. Open Discord → Your Server → Channel Settings
2. **Integrations** → **Create Webhook**
3. Name: `music21-mcp-notifications`
4. **Copy webhook URL** (format: `https://discord.com/api/webhooks/{id}/{token}`)

### 2. Automated Setup
```bash
# Run the automated setup script
./scripts/setup-webhook.sh -u "YOUR_DISCORD_WEBHOOK_URL"

# Or test first with dry run
./scripts/setup-webhook.sh -u "YOUR_WEBHOOK_URL" --dry-run
```

### 3. Test Connection
```bash
# Test webhook connectivity
./scripts/test-webhook.sh -u "YOUR_DISCORD_WEBHOOK_URL"

# Or use environment variable
export DISCORD_WEBHOOK_URL="YOUR_WEBHOOK_URL"
./scripts/test-webhook.sh
```

## What Gets Configured

### GitHub Repository
- ✅ **Webhook URL** stored as `DISCORD_WEBHOOK_URL` secret
- ✅ **Repository webhook** configured for events:
  - `workflow_run` - CI/CD pipeline status
  - `pull_request` - PR opened/merged/closed
  - `release` - New releases published
  - `code_scanning_alert` - Security vulnerabilities

### Discord Notifications
- 🟢 **Success**: Tests passed, builds completed
- 🔴 **Failure**: Tests failed, build errors
- 🔵 **Info**: PR activity, workflow started
- 🟡 **Warning**: Security alerts, partial failures
- 🟣 **Release**: Version releases, milestones

## Files Created/Updated

| File | Purpose |
|------|---------|
| `.github/webhook-config.md` | Complete setup instructions |
| `docs/webhook-integration.md` | Advanced configuration guide |
| `scripts/test-webhook.sh` | Test webhook connectivity |
| `scripts/setup-webhook.sh` | Automated setup script |
| `.github/workflows/webhook-example.yml` | Example workflow integration |

## Manual Setup (Alternative)

### GitHub CLI Commands
```bash
# Add webhook URL as secret
gh secret set DISCORD_WEBHOOK_URL --body "YOUR_WEBHOOK_URL"

# Configure repository webhook
gh api repos/:owner/:repo/hooks --method POST \
  --field name='web' \
  --field active=true \
  --field events='["workflow_run","pull_request","release","code_scanning_alert"]' \
  --field config='{"url":"YOUR_WEBHOOK_URL","content_type":"json"}'
```

### GitHub Web Interface
1. **Repository Settings** → **Webhooks** → **Add webhook**
2. **Payload URL**: Your Discord webhook URL
3. **Content type**: `application/json`
4. **Events**: Select individual events or choose "Let me select individual events"
5. **Active**: ✅ Checked

## Security Notes

⚠️ **Important Security Practices**:
- Never commit webhook URLs to version control
- Store URLs as GitHub repository secrets only
- Rotate webhook URLs quarterly
- Monitor webhook delivery logs for security

## Troubleshooting

### Common Issues
| Issue | Solution |
|-------|----------|
| Webhook not triggering | Check GitHub webhook delivery logs |
| Discord not receiving | Verify webhook URL format and permissions |
| Rate limiting | Reduce notification frequency |
| Permission errors | Ensure GitHub CLI is authenticated |

### Debug Commands
```bash
# Check webhook status
gh api repos/:owner/:repo/hooks

# Test webhook manually
curl -X POST -H "Content-Type: application/json" \
     -d '{"content":"Test"}' YOUR_WEBHOOK_URL

# View webhook deliveries
gh api repos/:owner/:repo/hooks/{hook_id}/deliveries
```

## Advanced Usage

### Custom Workflows
Add to any GitHub Actions workflow:
```yaml
- name: Notify Discord
  if: failure()
  env:
    DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
  run: |
    curl -H "Content-Type: application/json" \
         -d '{"content":"❌ Workflow failed"}' \
         $DISCORD_WEBHOOK_URL
```

### Environment-Specific Webhooks
```bash
# Different webhooks for different environments
gh secret set DISCORD_WEBHOOK_MAIN --body "MAIN_BRANCH_WEBHOOK_URL"
gh secret set DISCORD_WEBHOOK_DEV --body "DEVELOP_BRANCH_WEBHOOK_URL"
```

## Support Resources

- **Detailed Setup**: [.github/webhook-config.md](.github/webhook-config.md)
- **Advanced Config**: [docs/webhook-integration.md](docs/webhook-integration.md)
- **Test Scripts**: [scripts/test-webhook.sh](scripts/test-webhook.sh)
- **GitHub Webhooks**: https://docs.github.com/en/developers/webhooks-and-events/webhooks
- **Discord Webhooks**: https://discord.com/developers/docs/resources/webhook

---
**Setup Time**: ~5 minutes  
**Maintenance**: Quarterly URL rotation recommended