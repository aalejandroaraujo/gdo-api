# Deployment

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for GPT and moderation |
| `AzureWebJobsStorage` | Azure Storage connection string |
| `FUNCTIONS_WORKER_RUNTIME` | Must be `python` |

### Optional (for session persistence)

| Variable | Description | Default |
|----------|-------------|---------|
| `NOCODB_API_URL` | NocoDB base API URL | - |
| `NOCODB_API_KEY` | NocoDB authentication token | - |
| `NOCODB_TABLE_NAME` | Target table name | `sessions` |
| `NOCODB_AUTH_METHOD` | `xc-token` or `bearer` | `xc-token` |

## Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Create local.settings.json
cat > local.settings.json << SETTINGS
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "OPENAI_API_KEY": "your-key-here"
  }
}
SETTINGS

# Run locally
func start
```

## Docker Deployment

```bash
# Build image
docker build -t mental-health-functions .

# Run locally
docker run -p 8080:80 \
  -e OPENAI_API_KEY=your-key \
  -e AzureWebJobsStorage=your-connection-string \
  mental-health-functions
```

## Azure Deployment

### Via GitHub Actions (recommended)

Push to `main` branch triggers automatic deployment via `.github/workflows/azure-function-deploy.yml`.

Required GitHub Secrets:
- `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`

### Via Azure CLI

```bash
# Create Function App
az functionapp create \
  --name your-function-app \
  --resource-group your-rg \
  --storage-account yourstorageaccount \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4

# Deploy
func azure functionapp publish your-function-app
```

### Via Container

```bash
# Push to ACR
az acr login --name yourregistry
docker tag mental-health-functions yourregistry.azurecr.io/mental-health:v1
docker push yourregistry.azurecr.io/mental-health:v1

# Update Function App
az functionapp config container set \
  --name your-function-app \
  --resource-group your-rg \
  --image yourregistry.azurecr.io/mental-health:v1
```

## Configuration Files

### host.json

```json
{
  "version": "2.0",
  "functionTimeout": "00:05:00",
  "extensions": {
    "durableTask": {
      "hubName": "TestTaskHub"
    }
  }
}
```

### requirements.txt

```
azure-functions
azure-functions-durable
openai
httpx
```

## Monitoring

- **Application Insights** - Enable for logging and metrics
- **Live Metrics** - Real-time monitoring (better than Log Stream)
- **Function App Logs** - Azure Portal > Function App > Monitor
