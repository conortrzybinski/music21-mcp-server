# Discord Webhook Integration Documentation

## Overview

This document provides comprehensive information about Discord webhook integration for the music21-mcp-server repository, including setup instructions, configuration details, and maintenance procedures.

## Quick Start

1. **Create Discord Webhook**: Follow [.github/webhook-config.md](../.github/webhook-config.md) for detailed setup
2. **Test Connection**: Run `./scripts/test-webhook.sh -u YOUR_WEBHOOK_URL`
3. **Configure Repository**: Add webhook URL to GitHub secrets and repository settings

## Webhook Events

### Supported GitHub Events

| Event | Description | Discord Notification |
|-------|-------------|---------------------|
| `workflow_run` | CI/CD pipeline completion | ✅/❌ Build status with details |
| `pull_request` | PR lifecycle events | 🔄 PR opened/merged/closed |
| `release` | New releases published | 🚀 Release announcements |
| `code_scanning_alert` | Security vulnerabilities | 🔒 Security alerts |
| `push` | Code commits (optional) | 📝 Commit notifications |

### Event Payload Examples

#### Workflow Run Event
```json
{
  "action": "completed",
  "workflow_run": {
    "name": "CI/CD Pipeline",
    "status": "completed",
    "conclusion": "success",
    "html_url": "https://github.com/repo/actions/runs/123"
  }
}
```

#### Pull Request Event
```json
{
  "action": "opened",
  "pull_request": {
    "title": "Add new harmony analysis tool",
    "user": {"login": "contributor"},
    "head": {"ref": "feature/harmony-tool"},
    "html_url": "https://github.com/repo/pull/42"
  }
}
```

## Discord Message Formatting

### Standard Message Structure
All webhook messages follow this structure:
- **Content**: Brief status/action description
- **Username**: `music21-mcp-server` (consistent branding)
- **Embeds**: Rich formatted information with:
  - Title and description
  - Color coding (green=success, red=failure, blue=info)
  - Structured fields (repository, branch, etc.)
  - Timestamp and footer

### Color Coding
- 🟢 **Green (65280)**: Success states (tests passed, PR merged)
- 🔴 **Red (16711680)**: Failure states (tests failed, build error)
- 🔵 **Blue (255)**: Information (PR opened, workflow started)
- 🟡 **Orange (16753920)**: Warnings (security alerts, deprecated features)
- 🟣 **Purple (9699539)**: Special events (releases, milestones)

## Repository Integration

### GitHub Actions Integration

#### Method 1: Direct Webhook Calls
Add to any workflow:
```yaml
- name: Notify Discord on Success
  if: success()
  env:
    DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
  run: |
    curl -H "Content-Type: application/json" \
         -d '{
           "content":"✅ **${{ github.workflow }}** completed successfully",
           "embeds":[{
             "title":"Workflow Success",
             "color":65280,
             "fields":[
               {"name":"Repository","value":"${{ github.repository }}","inline":true},
               {"name":"Branch","value":"${{ github.ref_name }}","inline":true},
               {"name":"Commit","value":"${{ github.sha }}","inline":true}
             ]
           }]
         }' \
         $DISCORD_WEBHOOK_URL
```

#### Method 2: Reusable Action
Create `.github/actions/discord-notify/action.yml`:
```yaml
name: 'Discord Notification'
description: 'Send notification to Discord webhook'
inputs:
  webhook-url:
    description: 'Discord webhook URL'
    required: true
  status:
    description: 'Workflow status'
    required: true
  title:
    description: 'Notification title'
    required: false
    default: 'Workflow Update'
runs:
  using: 'composite'
  steps:
    - name: Send Discord Notification
      shell: bash
      run: |
        # Implementation here
```

### Repository Webhook Configuration

The repository webhook should be configured with these settings:

```bash
# Using GitHub CLI
gh api repos/:owner/:repo/hooks \
  --method POST \
  --field name='web' \
  --field active=true \
  --field events='["workflow_run","pull_request","release","code_scanning_alert"]' \
  --field config='{"url":"'$DISCORD_WEBHOOK_URL'","content_type":"json"}'
```

## Security Considerations

### Webhook URL Protection
- Store webhook URLs as GitHub repository secrets
- Never commit webhook URLs to version control
- Use environment variables in all scripts and workflows
- Rotate webhook URLs quarterly

### Content Filtering
- Avoid including sensitive information in notifications
- Sanitize user input in commit messages
- Consider branch-based filtering for sensitive repositories

### Rate Limiting
Discord webhook rate limits:
- **30 requests/minute** per webhook
- **5 requests/second** burst limit
- Implement exponential backoff for failures

### Example Rate Limiting Implementation
```bash
# Bash function for rate-limited webhook calls
send_webhook_with_retry() {
    local url="$1"
    local payload="$2"
    local max_retries=3
    local retry_count=0
    local delay=1
    
    while [[ $retry_count -lt $max_retries ]]; do
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
                       -X POST \
                       -H "Content-Type: application/json" \
                       -d "$payload" \
                       "$url")
        
        http_code=$(echo "$response" | sed -n 's/.*HTTPSTATUS:\([0-9]*\)/\1/p')
        
        if [[ "$http_code" -eq 200 || "$http_code" -eq 204 ]]; then
            return 0
        elif [[ "$http_code" -eq 429 ]]; then
            echo "Rate limited, waiting ${delay}s before retry..."
            sleep $delay
            delay=$((delay * 2))
            retry_count=$((retry_count + 1))
        else
            echo "Failed with HTTP $http_code"
            return 1
        fi
    done
    
    return 1
}
```

## Customization

### Custom Message Templates

#### Success Template
```json
{
  "content": "✅ **CI/CD Success**",
  "username": "music21-mcp-server",
  "avatar_url": "https://github.com/music21-mcp.png",
  "embeds": [{
    "title": "{{workflow_name}} Completed",
    "description": "All checks passed successfully",
    "color": 65280,
    "fields": [
      {"name": "Branch", "value": "{{branch}}", "inline": true},
      {"name": "Duration", "value": "{{duration}}", "inline": true},
      {"name": "Tests", "value": "{{test_count}} passed", "inline": true}
    ],
    "footer": {"text": "GitHub Actions"},
    "timestamp": "{{timestamp}}"
  }]
}
```

#### Failure Template
```json
{
  "content": "❌ **CI/CD Failure**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "{{workflow_name}} Failed",
    "description": "{{failure_reason}}",
    "color": 16711680,
    "fields": [
      {"name": "Branch", "value": "{{branch}}", "inline": true},
      {"name": "Failed Job", "value": "{{failed_job}}", "inline": true},
      {"name": "Logs", "value": "[View Details]({{logs_url}})", "inline": false}
    ],
    "footer": {"text": "GitHub Actions"},
    "timestamp": "{{timestamp}}"
  }]
}
```

### Environment-Specific Configuration

#### Development Environment
```bash
# Less verbose, essential notifications only
EVENTS='["workflow_run","pull_request"]'
NOTIFICATION_LEVEL="minimal"
```

#### Production Environment
```bash
# Comprehensive monitoring
EVENTS='["workflow_run","pull_request","release","code_scanning_alert","push"]'
NOTIFICATION_LEVEL="detailed"
```

## Monitoring and Maintenance

### Health Checks

#### Daily Checks
- [ ] Verify webhook delivery success rate > 95%
- [ ] Check Discord channel for notification spam
- [ ] Monitor rate limiting incidents

#### Weekly Checks  
- [ ] Review notification relevance and team engagement
- [ ] Analyze webhook delivery logs for patterns
- [ ] Validate webhook URL security

#### Monthly Tasks
- [ ] Update notification templates based on feedback
- [ ] Review and optimize event filtering
- [ ] Performance analysis of webhook delivery times

### Troubleshooting Common Issues

#### Webhook Not Triggering
1. **Check GitHub webhook delivery logs**:
   ```bash
   gh api repos/:owner/:repo/hooks
   gh api repos/:owner/:repo/hooks/{hook_id}/deliveries
   ```

2. **Verify webhook events configuration**:
   ```bash
   gh api repos/:owner/:repo/hooks/{hook_id} | jq '.events'
   ```

3. **Test webhook URL manually**:
   ```bash
   curl -X POST \
        -H "Content-Type: application/json" \
        -d '{"content":"Test message"}' \
        YOUR_WEBHOOK_URL
   ```

#### Discord Not Receiving Messages
1. **Validate webhook URL format**
2. **Check Discord server permissions**
3. **Verify webhook wasn't deleted in Discord**
4. **Test with minimal payload first**

#### Rate Limiting Issues
1. **Reduce notification frequency**
2. **Implement message batching**
3. **Add exponential backoff retry logic**
4. **Consider using multiple webhooks for high-volume repos**

### Performance Optimization

#### Message Batching
For high-activity repositories, consider batching notifications:

```bash
# Collect multiple events and send as single notification
batch_notifications() {
    local events=("$@")
    local batch_payload='{"content":"📋 **Repository Activity Summary**","embeds":['
    
    for event in "${events[@]}"; do
        # Add event to batch payload
        batch_payload+="{\"title\":\"$event\",\"color\":255},"
    done
    
    batch_payload="${batch_payload%,}]}"
    send_webhook "$batch_payload"
}
```

#### Conditional Notifications
Only notify for significant events:

```yaml
# In GitHub Actions
- name: Check if notification needed
  id: check-notify
  run: |
    if [[ "${{ github.event_name }}" == "push" && "${{ github.ref }}" == "refs/heads/main" ]]; then
      echo "notify=true" >> $GITHUB_OUTPUT
    elif [[ "${{ github.event_name }}" == "pull_request" && "${{ github.event.action }}" == "opened" ]]; then
      echo "notify=true" >> $GITHUB_OUTPUT
    else
      echo "notify=false" >> $GITHUB_OUTPUT
    fi

- name: Send notification
  if: steps.check-notify.outputs.notify == 'true'
  # Webhook call here
```

## Best Practices

### Message Design
- ✅ Use consistent emoji and color coding
- ✅ Include actionable information (links, status)
- ✅ Keep messages concise but informative
- ❌ Don't spam with excessive notifications
- ❌ Avoid including sensitive data

### Technical Implementation
- ✅ Implement proper error handling
- ✅ Use exponential backoff for retries
- ✅ Log webhook delivery attempts
- ✅ Monitor delivery success rates
- ❌ Don't ignore rate limiting responses
- ❌ Avoid hardcoding webhook URLs

### Team Collaboration
- ✅ Establish notification channel guidelines
- ✅ Get team feedback on notification frequency
- ✅ Document webhook configuration changes
- ✅ Provide opt-out mechanisms when possible
- ❌ Don't overwhelm team with notifications
- ❌ Avoid changing configurations without notice

## Advanced Features

### Conditional Logic Based on Branch
```yaml
- name: Branch-specific notifications
  env:
    DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
  run: |
    if [[ "${{ github.ref }}" == "refs/heads/main" ]]; then
      WEBHOOK_URL="${{ secrets.DISCORD_WEBHOOK_MAIN }}"
    elif [[ "${{ github.ref }}" == "refs/heads/develop" ]]; then
      WEBHOOK_URL="${{ secrets.DISCORD_WEBHOOK_DEV }}"
    else
      WEBHOOK_URL="${{ secrets.DISCORD_WEBHOOK_FEATURE }}"
    fi
    
    # Send notification to appropriate channel
```

### Integration with External Services
```bash
# Combine with Slack, email, or other notification services
send_multi_platform_notification() {
    local message="$1"
    
    # Discord
    send_discord_webhook "$message"
    
    # Slack (if configured)
    if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
        send_slack_webhook "$message"
    fi
    
    # Email (if critical)
    if [[ "$severity" == "critical" ]]; then
        send_email_notification "$message"
    fi
}
```

### Metrics Collection
```bash
# Track webhook performance metrics
log_webhook_metrics() {
    local status="$1"
    local duration="$2"
    local event_type="$3"
    
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),webhook,$event_type,$status,$duration" >> webhook-metrics.csv
}
```

This comprehensive documentation should provide everything needed to successfully implement and maintain Discord webhook notifications for the music21-mcp-server repository.