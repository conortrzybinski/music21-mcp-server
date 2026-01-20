#!/bin/bash

# Discord Webhook Setup Script
# Automates the setup process for Discord webhooks in the music21-mcp-server repository

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_NAME="Discord Webhook Setup"
WEBHOOK_URL=""
REPO_OWNER=""
REPO_NAME=""
DRY_RUN=false
VERBOSE=false

# Usage function
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Setup Discord webhook for music21-mcp-server repository"
    echo ""
    echo "OPTIONS:"
    echo "  -u, --url URL        Discord webhook URL (required)"
    echo "  -r, --repo REPO      Repository in format owner/name (auto-detected if in git repo)"
    echo "  -d, --dry-run        Show what would be done without making changes"
    echo "  -v, --verbose        Enable verbose output"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 -u https://discord.com/api/webhooks/123/abc"
    echo "  $0 -u https://discord.com/api/webhooks/123/abc -r brightliu/music21-mcp-server"
    echo "  $0 --url https://discord.com/api/webhooks/123/abc --dry-run"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--url)
            WEBHOOK_URL="$2"
            shift 2
            ;;
        -r|--repo)
            if [[ "$2" =~ ^[^/]+/[^/]+$ ]]; then
                REPO_OWNER=$(echo "$2" | cut -d'/' -f1)
                REPO_NAME=$(echo "$2" | cut -d'/' -f2)
            else
                echo -e "${RED}Error: Repository format should be owner/name${NC}"
                exit 1
            fi
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}[VERBOSE]${NC} $1"
    fi
}

# Validate webhook URL format
validate_webhook_url() {
    local url="$1"
    if [[ ! "$url" =~ ^https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+$ ]]; then
        return 1
    fi
    return 0
}

# Auto-detect repository information
detect_repository() {
    if [[ -n "$REPO_OWNER" && -n "$REPO_NAME" ]]; then
        return 0
    fi
    
    if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
        local remote_url
        remote_url=$(git remote get-url origin 2>/dev/null || echo "")
        
        if [[ "$remote_url" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
            REPO_OWNER="${BASH_REMATCH[1]}"
            REPO_NAME="${BASH_REMATCH[2]}"
            log_info "Auto-detected repository: $REPO_OWNER/$REPO_NAME"
        else
            log_warning "Could not auto-detect repository from git remote"
            return 1
        fi
    else
        log_warning "Not in a git repository - please specify repository with -r flag"
        return 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_commands=()
    
    if ! command -v gh &> /dev/null; then
        missing_commands+=("gh (GitHub CLI)")
    fi
    
    if ! command -v curl &> /dev/null; then
        missing_commands+=("curl")
    fi
    
    if ! command -v jq &> /dev/null; then
        log_warning "jq not found - JSON formatting will be limited"
    fi
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        echo ""
        echo "Installation instructions:"
        echo "- GitHub CLI: https://cli.github.com/"
        echo "- curl: Usually pre-installed on most systems"
        echo "- jq: https://stedolan.github.io/jq/download/"
        exit 1
    fi
    
    # Check GitHub CLI authentication
    if ! gh auth status > /dev/null 2>&1; then
        log_error "GitHub CLI not authenticated"
        echo ""
        echo "Please run: gh auth login"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Test webhook connectivity
test_webhook() {
    local url="$1"
    
    log_info "Testing webhook connectivity..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - Would test webhook connectivity"
        return 0
    fi
    
    local test_payload='{
        "content":"🧪 **Setup Test**",
        "username":"music21-mcp-server",
        "embeds":[{
            "title":"Webhook Setup Test",
            "description":"Testing webhook connectivity during setup",
            "color":5814783,
            "fields":[
                {"name":"Repository","value":"'$REPO_OWNER/$REPO_NAME'","inline":true},
                {"name":"Setup Script","value":"Automated setup","inline":true}
            ],
            "footer":{"text":"music21-mcp-server setup"},
            "timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }]
    }'
    
    local response
    local http_code
    
    response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$test_payload" \
        "$url")
    
    http_code=$(echo "$response" | sed -n 's/.*HTTPSTATUS:\([0-9]*\)/\1/p')
    
    case "$http_code" in
        200|204)
            log_success "Webhook connectivity test passed"
            return 0
            ;;
        400)
            log_error "Webhook test failed - Bad request (check payload format)"
            return 1
            ;;
        401)
            log_error "Webhook test failed - Unauthorized (check webhook URL)"
            return 1
            ;;
        404)
            log_error "Webhook test failed - Not found (webhook may be deleted)"
            return 1
            ;;
        429)
            log_error "Webhook test failed - Rate limited"
            return 1
            ;;
        *)
            log_error "Webhook test failed - HTTP $http_code"
            return 1
            ;;
    esac
}

# Add webhook URL as GitHub secret
add_github_secret() {
    local url="$1"
    
    log_info "Adding webhook URL as GitHub repository secret..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - Would add DISCORD_WEBHOOK_URL secret to $REPO_OWNER/$REPO_NAME"
        return 0
    fi
    
    log_verbose "Setting DISCORD_WEBHOOK_URL secret for $REPO_OWNER/$REPO_NAME"
    
    if echo "$url" | gh secret set DISCORD_WEBHOOK_URL --repo "$REPO_OWNER/$REPO_NAME"; then
        log_success "Successfully added DISCORD_WEBHOOK_URL secret"
    else
        log_error "Failed to add GitHub secret"
        return 1
    fi
}

# Configure repository webhook
configure_repository_webhook() {
    local url="$1"
    
    log_info "Configuring repository webhook..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - Would configure repository webhook for events: [workflow_run,pull_request,release,code_scanning_alert]"
        return 0
    fi
    
    local events='["workflow_run","pull_request","release","code_scanning_alert"]'
    
    log_verbose "Creating webhook with events: $events"
    
    local webhook_response
    webhook_response=$(gh api "repos/$REPO_OWNER/$REPO_NAME/hooks" \
        --method POST \
        --field name='web' \
        --field active=true \
        --raw-field events="$events" \
        --field config='{"url":"'$url'","content_type":"json"}' 2>&1)
    
    if [[ $? -eq 0 ]]; then
        log_success "Successfully configured repository webhook"
        
        # Extract webhook ID for reference
        local webhook_id
        if command -v jq &> /dev/null; then
            webhook_id=$(echo "$webhook_response" | jq -r '.id // "unknown"')
            log_verbose "Webhook ID: $webhook_id"
        fi
    else
        if echo "$webhook_response" | grep -q "Hook already exists"; then
            log_warning "Repository webhook already exists - you may need to update it manually"
            log_info "To update existing webhook, go to: https://github.com/$REPO_OWNER/$REPO_NAME/settings/hooks"
        else
            log_error "Failed to configure repository webhook"
            echo "$webhook_response"
            return 1
        fi
    fi
}

# Generate setup summary
generate_summary() {
    echo ""
    echo "=========================================="
    echo "  Setup Summary"
    echo "=========================================="
    echo ""
    log_info "Configuration completed for:"
    echo "  Repository: $REPO_OWNER/$REPO_NAME"
    echo "  Webhook URL: ${WEBHOOK_URL:0:50}..."
    echo ""
    log_info "What was configured:"
    echo "  ✅ Discord webhook connectivity tested"
    echo "  ✅ DISCORD_WEBHOOK_URL secret added to repository"
    echo "  ✅ Repository webhook configured for events:"
    echo "     • workflow_run (CI/CD status)"
    echo "     • pull_request (PR lifecycle)"
    echo "     • release (new releases)"
    echo "     • code_scanning_alert (security alerts)"
    echo ""
    log_info "Next steps:"
    echo "  1. Test the webhook with: ./scripts/test-webhook.sh"
    echo "  2. Trigger a workflow to see notifications in action"
    echo "  3. Review .github/webhook-config.md for advanced configuration"
    echo "  4. Check webhook delivery status at:"
    echo "     https://github.com/$REPO_OWNER/$REPO_NAME/settings/hooks"
    echo ""
    log_success "Discord webhook setup complete!"
}

# Main function
main() {
    echo "======================================"
    echo "  $SCRIPT_NAME"
    echo "======================================"
    echo ""
    
    # Validate arguments
    if [[ -z "$WEBHOOK_URL" ]]; then
        log_error "Discord webhook URL is required"
        echo ""
        show_usage
        exit 1
    fi
    
    if ! validate_webhook_url "$WEBHOOK_URL"; then
        log_error "Invalid Discord webhook URL format"
        echo "Expected format: https://discord.com/api/webhooks/{id}/{token}"
        exit 1
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Auto-detect or validate repository
    if ! detect_repository; then
        log_error "Could not determine repository information"
        echo "Please specify repository with -r owner/name"
        exit 1
    fi
    
    log_info "Setting up webhook for repository: $REPO_OWNER/$REPO_NAME"
    log_info "Using webhook URL: ${WEBHOOK_URL:0:50}..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN MODE - No changes will be made"
    fi
    
    echo ""
    
    # Step 1: Test webhook connectivity
    if ! test_webhook "$WEBHOOK_URL"; then
        log_error "Webhook connectivity test failed - aborting setup"
        exit 1
    fi
    
    # Step 2: Add GitHub secret
    if ! add_github_secret "$WEBHOOK_URL"; then
        log_error "Failed to add GitHub secret - aborting setup"
        exit 1
    fi
    
    # Step 3: Configure repository webhook
    if ! configure_repository_webhook "$WEBHOOK_URL"; then
        log_error "Failed to configure repository webhook"
        log_warning "You may need to configure the webhook manually"
        log_info "Manual configuration instructions available in .github/webhook-config.md"
        exit 1
    fi
    
    # Generate summary
    if [[ "$DRY_RUN" != "true" ]]; then
        generate_summary
    else
        echo ""
        log_info "DRY RUN completed - no actual changes made"
        log_info "Run without --dry-run to apply changes"
    fi
}

# Run main function
main "$@"