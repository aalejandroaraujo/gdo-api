# Deployment

## Virtual Environment Setup

**IMPORTANT:** This project requires Python 3.11 (Azure Functions runtime version).

### Activate .venv311

Always activate the virtual environment before running any commands:

| Terminal | Command |
|----------|---------|
| **Git Bash (Windows)** | `source .venv311/Scripts/activate` |
| **PowerShell (Windows)** | `.\.venv311\Scripts\Activate.ps1` |
| **Linux/macOS** | `source .venv311/bin/activate` |

You'll see `(.venv311)` in your prompt when activated.

### First-Time Setup

If `.venv311` doesn't exist:

```bash
# Windows
py -3.11 -m venv .venv311

# Linux/macOS
python3.11 -m venv .venv311

# Then activate (see above) and install dependencies
pip install -r requirements.txt
```

---

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
# 1. Activate virtual environment (REQUIRED)
source .venv311/Scripts/activate   # Git Bash
# OR
.\.venv311\Scripts\Activate.ps1    # PowerShell

# 2. Install dependencies (first time only)
pip install -r requirements.txt

# 3. Create local.settings.json (first time only)
cp local.settings.json.example local.settings.json
# Edit with your actual keys

# 4. Run locally
func start --port 9090
```

### local.settings.json Template

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "OPENAI_API_KEY": "your-key-here",
    "JWT_SIGNING_KEY": "your-32-char-secret-key-here",
    "POSTGRES_CONNECTION_STRING": "postgresql://user:pass@host:5432/db"
  },
  "Host": {
    "LocalHttpPort": 9090
  }
}
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
# Ensure venv is activated first!
source .venv311/Scripts/activate  # Git Bash

# Create Function App (first time only)
az functionapp create \
  --name your-function-app \
  --resource-group your-rg \
  --storage-account yourstorageaccount \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4

# Deploy
func azure functionapp publish func-gdo-health-prod
```

**Current Production App:** `func-gdo-health-prod`

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
    },
    "http": {
      "routePrefix": "api"
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
