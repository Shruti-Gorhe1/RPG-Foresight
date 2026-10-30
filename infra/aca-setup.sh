#!/usr/bin/env bash
# =============================================================================
# aca-setup.sh — one-time provisioning of all Azure Container Apps for __APP_NAME__
#
# Creates (in the shared ACA environment):
#   __APP_NAME__-be       FastAPI backend  (internal ingress, port __BACKEND_PORT__)
#   __APP_NAME__-worker   Temporal worker  (no ingress; same image, command override)
#   __APP_NAME__-fe       React/nginx UI   (external ingress, port 80)
#
# Ingress design (learned the hard way):
#   * Backend is INTERNAL + --allow-insecure so the FE nginx can proxy over
#     http://__APP_NAME__-be.internal.<env>/... without a 301 http->https redirect.
#   * FE BACKEND_URL therefore uses http:// and the .internal. FQDN.
#
# Prereqs: az login; a Postgres (with a database), Redis, and Azure OpenAI you
# can point at; the ACA environment already exists. Edit the VARIABLES block,
# then: bash infra/aca-setup.sh
# =============================================================================
set -euo pipefail

# ── VARIABLES — edit these ────────────────────────────────────────────────────
SUBSCRIPTION="${SUBSCRIPTION:-<your-subscription-id>}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Zenlabs-Agent-Foundry}"
ENVIRONMENT="${ENVIRONMENT:-zaf-aca-pvt-env}"
ACR="${ACR:-zafacr-gqfyc3h8eya2djey.azurecr.io}"

BE_APP="__APP_NAME__-be"
WORKER_APP="__APP_NAME__-worker"
FE_APP="__APP_NAME__-fe"
BE_IMAGE="$ACR/__APP_NAME__-be:latest"
FE_IMAGE="$ACR/__APP_NAME__-fe:latest"

BACKEND_PORT="__BACKEND_PORT__"
NAMESPACE="__NAMESPACE__"
TASK_QUEUE="__TASK_QUEUE__"

# Backing services — use Key Vault references in production.
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://user:pass@your-pg.postgres.database.azure.com:5432/__DB_NAME__?ssl=require}"
REDIS_URL="${REDIS_URL:-rediss://:<access-key>@zaf-redis-cache.eastus2.redis.azure.net:10000}"
TEMPORAL_HOST="${TEMPORAL_HOST:-temporal-be.internal.$(echo "$ENVIRONMENT")...:443}"
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-https://<your-openai>.openai.azure.com/}"
AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-<key>}"
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-4.1-mini}"
KV_URL="${KV_URL:-https://zaf-kv-01.vault.azure.net/}"
# ── END VARIABLES ─────────────────────────────────────────────────────────────

echo "=== Subscription ==="
az account set --subscription "$SUBSCRIPTION"

ACR_NAME="${ACR%%.*}"
ACR_USER="$(az acr credential show --name "$ACR_NAME" --query username -o tsv)"
ACR_PASS="$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' -o tsv)"

COMMON_ENV=(
  "APP_ENV=production"
  "LOG_LEVEL=INFO"
  "DATABASE_URL=$DATABASE_URL"
  "REDIS_URL=$REDIS_URL"
  "TEMPORAL_HOST=$TEMPORAL_HOST"
  "TEMPORAL_NAMESPACE=$NAMESPACE"
  "TEMPORAL_TASK_QUEUE_AGENTS=$TASK_QUEUE"
  "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT"
  "AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY"
  "AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT"
  "AZURE_KEYVAULT_URL=$KV_URL"
)

echo "=== Backend API ($BE_APP) — internal + allow-insecure ==="
az containerapp create \
  --name "$BE_APP" --resource-group "$RESOURCE_GROUP" --environment "$ENVIRONMENT" \
  --image "$BE_IMAGE" \
  --target-port "$BACKEND_PORT" --ingress internal --allow-insecure \
  --min-replicas 0 --max-replicas 3 --cpu 1.0 --memory 2Gi \
  --registry-server "$ACR" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
  --env-vars "${COMMON_ENV[@]}" --only-show-errors

BE_FQDN="$(az containerapp show --name "$BE_APP" --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)"
echo "Backend (internal): http://$BE_FQDN"

echo "=== Temporal Worker ($WORKER_APP) — no ingress ==="
az containerapp create \
  --name "$WORKER_APP" --resource-group "$RESOURCE_GROUP" --environment "$ENVIRONMENT" \
  --image "$BE_IMAGE" --ingress none \
  --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1Gi \
  --registry-server "$ACR" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
  --command python -- -m workers.worker \
  --env-vars "${COMMON_ENV[@]}" --only-show-errors

echo "=== Frontend ($FE_APP) — external; proxies /api to backend over http ==="
az containerapp create \
  --name "$FE_APP" --resource-group "$RESOURCE_GROUP" --environment "$ENVIRONMENT" \
  --image "$FE_IMAGE" \
  --target-port 80 --ingress external \
  --min-replicas 0 --max-replicas 3 --cpu 0.5 --memory 1Gi \
  --registry-server "$ACR" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
  --env-vars "BACKEND_URL=http://$BE_FQDN" --only-show-errors

FE_FQDN="$(az containerapp show --name "$FE_APP" --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)"

echo ""
echo "============================================================"
echo "  Frontend:  https://$FE_FQDN"
echo "  Backend:   http://$BE_FQDN  (internal)"
echo "  Worker:    $WORKER_APP  (no ingress)"
echo "============================================================"
echo "Next: run DB migrations, then set CORS_ALLOWED_ORIGINS on the backend:"
echo "  az containerapp update -n $BE_APP -g $RESOURCE_GROUP \\"
echo "    --set-env-vars CORS_ALLOWED_ORIGINS=https://$FE_FQDN"
