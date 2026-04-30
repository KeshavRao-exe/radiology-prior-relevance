# Deployment Instructions

## Option A — Railway (recommended, free, 2 minutes)

1. Go to **https://railway.app/new**
2. Click **"Deploy from GitHub repo"**
3. Select **`KeshavRao-exe/radiology-prior-relevance`**
4. Railway auto-detects the `Dockerfile` and builds
5. When the deploy turns green, click **"Settings → Networking → Generate Domain"**
6. Your endpoint URL will be: `https://<generated-name>.railway.app/predict`

## Option B — Render (free)

1. Go to **https://dashboard.render.com/new/web**
2. Connect GitHub → select `KeshavRao-exe/radiology-prior-relevance`
3. Set:
   - **Runtime**: Docker
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Deploy — URL will be `https://<name>.onrender.com/predict`

## Option C — Google Cloud Run (gcloud configured)

```bash
# Re-authenticate first
gcloud auth login

# Build and deploy (takes ~3 minutes)
gcloud run deploy radiology-prior-relevance \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --project assignment3stock-frontend
```

## Local testing

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Test
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"cases": [{"case_id": "1", "current_study": {"study_id": "A", "study_description": "CT CHEST WITH CONTRAST", "study_date": "2024-01-01"}, "prior_studies": [{"study_id": "B", "study_description": "CT CHEST WITHOUT CONTRAST", "study_date": "2023-01-01"}]}]}'
```

## Health check

`GET /health` returns `{"status": "ok", "cache_size": <n>}`
