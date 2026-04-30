# Radiology Prior-Study Relevance

Given a current radiology exam and a list of prior exams for the same patient, predict whether each prior study is relevant to the current read.

## Approach

1. **Rule-based region matching** — extract body regions from study descriptions using keyword matching (25+ regions: thorax, brain, breast, spine levels, cardiac subtypes, etc.)
2. **Clinical adjacency** — studies in related regions (e.g. hip ↔ pelvis, abdomen ↔ abdomen-pelvis) are also marked relevant
3. **Laterality filtering** — left/right side awareness prevents false matches (e.g. right breast ≠ left breast)
4. **ML stacking** — a Gradient Boosting classifier (GBM) sits on top, trained on 10 features including the rule prediction, region overlap counts, and TF-IDF string similarities

**Accuracy: 94.62% (rule-based) → 95.29% (ML)**  
Evaluated on 27,614 labeled prior exams across 996 cases.

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "cases": [{
      "case_id": "1",
      "current_study": {"study_id": "A", "study_description": "CT CHEST WITH CONTRAST", "study_date": "2024-01-01"},
      "prior_studies": [{"study_id": "B", "study_description": "CT CHEST WITHOUT CONTRAST", "study_date": "2023-01-01"}]
    }]
  }'
```

## Live endpoint

```
POST https://radiology-prior-relevance-production.up.railway.app/predict
GET  https://radiology-prior-relevance-production.up.railway.app/health
```

## Files

| File | Purpose |
|---|---|
| `classifier.py` | Rule-based region extractor and relevance logic |
| `classifier_ml.py` | ML inference layer (loads `model.pkl`) |
| `model.pkl` | Trained GBM + TF-IDF vectorizers |
| `main.py` | FastAPI server |
| `experiments.md` | Full experiment log and write-up |
