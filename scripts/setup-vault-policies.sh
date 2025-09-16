#!/bin/bash
set -euo pipefail

# Setup Vault policies and secrets for video transcription batch processing
# This script configures the necessary Vault policies and verifies secret access

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Vault token is set
if [[ -z "${VAULT_TOKEN:-}" ]]; then
    log_error "VAULT_TOKEN environment variable is required"
    log_info "Set it with: export VAULT_TOKEN=your_vault_token"
    exit 1
fi

# Check if Vault is accessible
if ! vault status >/dev/null 2>&1; then
    log_error "Cannot connect to Vault. Check VAULT_ADDR and VAULT_TOKEN"
    exit 1
fi

log_info "Setting up Vault policies for video transcription batch processing..."

# Create transcription policy
log_info "Creating transcription-policy..."
vault policy write transcription-policy - <<EOF
# Allow reading AWS credentials for S3 access
path "secret/data/aws/transcription" {
  capabilities = ["read"]
}

# Allow reading HuggingFace token for model access
path "secret/data/hf/transcription" {
  capabilities = ["read"]
}
EOF

log_info "✅ Created transcription-policy"

# Verify the policy was created
if vault policy read transcription-policy >/dev/null 2>&1; then
    log_info "✅ Policy verification successful"
else
    log_error "❌ Policy verification failed"
    exit 1
fi

# Setup Nomad-Vault JWT authentication
log_info "Configuring Nomad-Vault JWT authentication..."

# Check if JWT auth method is already enabled for Nomad
JWT_NOMAD_PATH=""
if vault auth list | grep -q "jwt-nomad/"; then
    JWT_NOMAD_PATH="jwt-nomad"
    log_info "✅ JWT auth method found at jwt-nomad/"
elif vault auth list | grep -q "nomad.*jwt"; then
    JWT_NOMAD_PATH="nomad"
    log_info "✅ JWT auth method found at nomad/"
else
    log_info "Enabling JWT auth method for Nomad..."
    vault auth enable -path=jwt-nomad jwt
    JWT_NOMAD_PATH="jwt-nomad"
    log_info "✅ Enabled JWT auth method at jwt-nomad/"
fi

# Update the default nomad-workloads role to include transcription-policy
log_info "Updating default nomad-workloads role to include transcription-policy..."

# Get current policies from nomad-workloads role
CURRENT_POLICIES=$(vault read -field=token_policies auth/${JWT_NOMAD_PATH}/role/nomad-workloads)

# Add transcription-policy if not already present
if echo "$CURRENT_POLICIES" | grep -q "transcription-policy"; then
    log_info "✅ transcription-policy already in nomad-workloads role"
else
    log_info "Adding transcription-policy to nomad-workloads role..."

    # Update the role using JSON format (the only way that works reliably)
    vault write auth/${JWT_NOMAD_PATH}/role/nomad-workloads - <<EOF
{
  "bound_audiences": ["vault.io"],
  "bound_claims": {
    "nomad_job_id": ["*"],
    "nomad_namespace": ["*"]
  },
  "bound_claims_type": "glob",
  "user_claim": "nomad_job_id",
  "role_type": "jwt",
  "token_policies": ["nomad-build-service", "dns-config-read", "transcription-policy"],
  "token_ttl": "1h",
  "token_max_ttl": "24h"
}
EOF

    log_info "✅ Added transcription-policy to nomad-workloads role"
fi

# Also create a dedicated transcription role for explicit use
log_info "Creating dedicated JWT role for transcription jobs..."
vault write auth/${JWT_NOMAD_PATH}/role/transcription \
    bound_audiences="vault.io" \
    bound_subject="nomad-job" \
    user_claim="nomad_job_id" \
    role_type="jwt" \
    token_policies="transcription-policy" \
    token_ttl="1h" \
    token_max_ttl="24h"

log_info "✅ Created dedicated JWT role for transcription jobs at ${JWT_NOMAD_PATH}/"

# Check if required secrets exist
log_info "Verifying required secrets exist..."

# Check AWS credentials
if vault kv get secret/aws/transcription >/dev/null 2>&1; then
    log_info "✅ AWS credentials found at secret/aws/transcription"
else
    log_warn "⚠️  AWS credentials not found at secret/aws/transcription"
    log_info "Create them with:"
    log_info "  vault kv put secret/aws/transcription access_key=YOUR_KEY secret_key=YOUR_SECRET"
fi

# Check HuggingFace token
if vault kv get secret/hf/transcription >/dev/null 2>&1; then
    log_info "✅ HuggingFace token found at secret/hf/transcription"
else
    log_warn "⚠️  HuggingFace token not found at secret/hf/transcription"
    log_info "Create it with:"
    log_info "  vault kv put secret/hf/transcription token=YOUR_HF_TOKEN"
fi

log_info "🎉 Vault setup complete!"
log_info ""
log_info "Configured:"
log_info "- transcription-policy for secret access"
log_info "- JWT auth method for Nomad integration"
log_info "- JWT role mapping Nomad jobs to transcription-policy"
log_info ""
log_info "Next steps:"
log_info "1. Ensure AWS credentials and HF token are stored in Vault (if warnings above)"
log_info "2. Deploy transcription jobs using: generate-nomad-job --job-id <id> --job-name <name>"
log_info "3. Jobs will automatically authenticate via JWT and access secrets"