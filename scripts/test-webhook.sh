#!/bin/bash

# Discord Webhook Test Script
# This script tests Discord webhook connectivity for the music21-mcp-server repository

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_NAME="Discord Webhook Test"
WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
DRY_RUN=false
VERBOSE=false

# Usage function
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Test Discord webhook connectivity for music21-mcp-server repository"
    echo ""
    echo "OPTIONS:"
    echo "  -u, --url URL        Discord webhook URL (can also use DISCORD_WEBHOOK_URL env var)"
    echo "  -d, --dry-run        Show what would be sent without actually sending"
    echo "  -v, --verbose        Enable verbose output"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "ENVIRONMENT VARIABLES:"
    echo "  DISCORD_WEBHOOK_URL  Discord webhook URL (alternative to -u flag)"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 -u https://discord.com/api/webhooks/123/abc"
    echo "  export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/123/abc' && $0"
    echo "  $0 --dry-run --verbose"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--url)
            WEBHOOK_URL="$2"
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

# Get repository information
get_repo_info() {
    local repo_name=""
    local branch_name=""
    local commit_hash=""
    
    if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
        repo_name=$(basename "$(git rev-parse --show-toplevel)" 2>/dev/null || echo "music21-mcp-server")
        branch_name=$(git branch --show-current 2>/dev/null || echo "unknown")
        commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    else
        repo_name="music21-mcp-server"
        branch_name="unknown"
        commit_hash="unknown"
    fi
    
    echo "$repo_name,$branch_name,$commit_hash"
}

# Create test message payload
create_test_payload() {
    local repo_info
    repo_info=$(get_repo_info)
    IFS=',' read -r repo_name branch_name commit_hash <<< "$repo_info"
    
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat << EOF
{
  "content": "🧪 **Webhook Test - music21-mcp-server**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Discord Webhook Test",
    "description": "Testing webhook connectivity for repository notifications",
    "color": 5814783,
    "fields": [
      {
        "name": "Repository",
        "value": "$repo_name",
        "inline": true
      },
      {
        "name": "Branch",
        "value": "$branch_name",
        "inline": true
      },
      {
        "name": "Commit",
        "value": "$commit_hash",
        "inline": true
      },
      {
        "name": "Test Type",
        "value": "Manual webhook test",
        "inline": false
      }
    ],
    "footer": {
      "text": "music21-mcp-server webhook test"
    },
    "timestamp": "$timestamp"
  }]
}
EOF
}

# Create sample notification payloads for different event types
create_sample_payloads() {
    local event_type="$1"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    case "$event_type" in
        "workflow_success")
            cat << 'EOF'
{
  "content": "✅ **CI/CD Pipeline - SUCCESS**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Workflow Completed Successfully",
    "description": "All tests passed and build completed",
    "color": 65280,
    "fields": [
      {
        "name": "Workflow",
        "value": "CI/CD Pipeline",
        "inline": true
      },
      {
        "name": "Branch",
        "value": "main",
        "inline": true
      },
      {
        "name": "Duration",
        "value": "3m 42s",
        "inline": true
      }
    ],
    "footer": {
      "text": "GitHub Actions"
    }
  }]
}
EOF
            ;;
        "workflow_failure")
            cat << 'EOF'
{
  "content": "❌ **CI/CD Pipeline - FAILED**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Workflow Failed",
    "description": "Tests failed or build error occurred",
    "color": 16711680,
    "fields": [
      {
        "name": "Workflow",
        "value": "CI/CD Pipeline",
        "inline": true
      },
      {
        "name": "Branch",
        "value": "feature/new-tool",
        "inline": true
      },
      {
        "name": "Failed Job",
        "value": "test (Python 3.11)",
        "inline": true
      }
    ],
    "footer": {
      "text": "GitHub Actions"
    }
  }]
}
EOF
            ;;
        "pull_request")
            cat << 'EOF'
{
  "content": "🔄 **Pull Request Activity**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Pull Request Opened",
    "description": "New pull request requires review",
    "color": 255,
    "fields": [
      {
        "name": "PR Title",
        "value": "Add new harmony analysis tool",
        "inline": false
      },
      {
        "name": "Author",
        "value": "contributor",
        "inline": true
      },
      {
        "name": "Branch",
        "value": "feature/harmony-tool",
        "inline": true
      },
      {
        "name": "Files Changed",
        "value": "5 files (+127 -23)",
        "inline": true
      }
    ],
    "footer": {
      "text": "GitHub Pull Request"
    }
  }]
}
EOF
            ;;
        "release")
            cat << 'EOF'
{
  "content": "🚀 **New Release Published**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Version 1.2.0 Released",
    "description": "New features and improvements available",
    "color": 9699539,
    "fields": [
      {
        "name": "Version",
        "value": "v1.2.0",
        "inline": true
      },
      {
        "name": "Type",
        "value": "Feature Release",
        "inline": true
      },
      {
        "name": "Highlights",
        "value": "• New chord analysis tool\n• Performance improvements\n• Bug fixes",
        "inline": false
      }
    ],
    "footer": {
      "text": "GitHub Release"
    }
  }]
}
EOF
            ;;
        "security_alert")
            cat << 'EOF'
{
  "content": "🔒 **Security Alert**",
  "username": "music21-mcp-server",
  "embeds": [{
    "title": "Code Scanning Alert",
    "description": "Potential security issue detected",
    "color": 16753920,
    "fields": [
      {
        "name": "Severity",
        "value": "Medium",
        "inline": true
      },
      {
        "name": "Tool",
        "value": "Bandit",
        "inline": true
      },
      {
        "name": "File",
        "value": "src/music21_mcp/tools/analysis.py",
        "inline": true
      }
    ],
    "footer": {
      "text": "GitHub Code Scanning"
    }
  }]
}
EOF
            ;;
        *)
            echo "Unknown event type: $event_type"
            return 1
            ;;
    esac
}

# Send webhook message
send_webhook() {
    local payload="$1"
    local description="$2"
    local url="$WEBHOOK_URL"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - Would send $description to Discord:"
        echo "$payload" | jq . 2>/dev/null || echo "$payload"
        return 0
    fi
    
    log_verbose "Sending $description to Discord webhook..."
    log_verbose "Payload: $payload"
    
    local response
    local http_code
    
    response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$url")
    
    http_code=$(echo "$response" | sed -n 's/.*HTTPSTATUS:\([0-9]*\)/\1/p')
    response_body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    log_verbose "HTTP Status: $http_code"
    log_verbose "Response: $response_body"
    
    case "$http_code" in
        200|204)
            log_success "Successfully sent $description"
            return 0
            ;;
        400)
            log_error "Bad request (400) - Check payload format"
            echo "Response: $response_body"
            return 1
            ;;
        401)
            log_error "Unauthorized (401) - Check webhook URL"
            return 1
            ;;
        404)
            log_error "Not found (404) - Webhook URL may be invalid or deleted"
            return 1
            ;;
        429)
            log_error "Rate limited (429) - Too many requests"
            return 1
            ;;
        *)
            log_error "Unexpected HTTP status: $http_code"
            echo "Response: $response_body"
            return 1
            ;;
    esac
}

# Run comprehensive webhook tests
run_tests() {
    local tests_passed=0
    local tests_total=0
    
    log_info "Starting comprehensive webhook tests..."
    echo ""
    
    # Test 1: Basic connectivity test
    tests_total=$((tests_total + 1))
    log_info "Test 1/6: Basic connectivity test"
    local test_payload
    test_payload=$(create_test_payload)
    if send_webhook "$test_payload" "basic connectivity test"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Test 2: Workflow success notification
    tests_total=$((tests_total + 1))
    log_info "Test 2/6: Workflow success notification"
    local success_payload
    success_payload=$(create_sample_payloads "workflow_success")
    if send_webhook "$success_payload" "workflow success notification"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Test 3: Workflow failure notification
    tests_total=$((tests_total + 1))
    log_info "Test 3/6: Workflow failure notification"
    local failure_payload
    failure_payload=$(create_sample_payloads "workflow_failure")
    if send_webhook "$failure_payload" "workflow failure notification"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Test 4: Pull request notification
    tests_total=$((tests_total + 1))
    log_info "Test 4/6: Pull request notification"
    local pr_payload
    pr_payload=$(create_sample_payloads "pull_request")
    if send_webhook "$pr_payload" "pull request notification"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Test 5: Release notification
    tests_total=$((tests_total + 1))
    log_info "Test 5/6: Release notification"
    local release_payload
    release_payload=$(create_sample_payloads "release")
    if send_webhook "$release_payload" "release notification"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Test 6: Security alert notification
    tests_total=$((tests_total + 1))
    log_info "Test 6/6: Security alert notification"
    local security_payload
    security_payload=$(create_sample_payloads "security_alert")
    if send_webhook "$security_payload" "security alert notification"; then
        tests_passed=$((tests_passed + 1))
    fi
    echo ""
    
    # Summary
    log_info "Test Results Summary:"
    echo "  Tests passed: $tests_passed/$tests_total"
    
    if [[ $tests_passed -eq $tests_total ]]; then
        log_success "All tests passed! Webhook is working correctly."
        return 0
    else
        log_warning "Some tests failed. Check the Discord channel and webhook configuration."
        return 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for required commands
    local missing_commands=()
    
    if ! command -v curl &> /dev/null; then
        missing_commands+=("curl")
    fi
    
    if ! command -v jq &> /dev/null; then
        log_warning "jq not found - JSON formatting will be limited"
    fi
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        echo "Please install the missing commands and try again."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Main function
main() {
    echo "======================================"
    echo "  $SCRIPT_NAME"
    echo "======================================"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Validate webhook URL
    if [[ -z "$WEBHOOK_URL" ]]; then
        log_error "Discord webhook URL not provided"
        echo ""
        echo "Please provide the webhook URL using one of these methods:"
        echo "1. Command line flag: $0 -u https://discord.com/api/webhooks/123/abc"
        echo "2. Environment variable: export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/123/abc'"
        echo ""
        show_usage
        exit 1
    fi
    
    if ! validate_webhook_url "$WEBHOOK_URL"; then
        log_error "Invalid Discord webhook URL format"
        echo "Expected format: https://discord.com/api/webhooks/{id}/{token}"
        exit 1
    fi
    
    log_info "Using webhook URL: ${WEBHOOK_URL:0:50}..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN MODE - No messages will be sent"
    fi
    
    echo ""
    
    # Run tests
    if run_tests; then
        echo ""
        log_success "Webhook testing completed successfully!"
        log_info "Check your Discord channel for the test messages."
        exit 0
    else
        echo ""
        log_error "Webhook testing completed with failures."
        exit 1
    fi
}

# Run main function
main "$@"