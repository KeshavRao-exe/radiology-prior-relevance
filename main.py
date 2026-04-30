"""
Radiology Prior-Study Relevance API

POST /predict
  Body: { "cases": [...] }   (schema: relevant-priors-v1)
  Returns: { "predictions": [{"case_id", "study_id", "predicted_is_relevant"}] }
"""

import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from classifier_ml import is_relevant

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache  key: SHA-256 of (curr_desc, prior_desc) → bool
# ---------------------------------------------------------------------------
_cache: dict[str, bool] = {}


def _cache_key(curr: str, prior: str) -> str:
    return hashlib.sha256(f"{curr}|||{prior}".encode()).hexdigest()


def _predict_cached(curr_desc: str, prior_desc: str) -> bool:
    k = _cache_key(curr_desc, prior_desc)
    if k not in _cache:
        _cache[k] = is_relevant(curr_desc, prior_desc)
    return _cache[k]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class Study(BaseModel):
    study_id: str
    study_description: str
    study_date: Optional[str] = None


class Case(BaseModel):
    case_id: str
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    current_study: Study
    prior_studies: list[Study]


class PredictRequest(BaseModel):
    challenge_id: Optional[str] = None
    schema_version: Optional[int] = None
    generated_at: Optional[str] = None
    cases: list[Case]


class Prediction(BaseModel):
    case_id: str
    study_id: str
    predicted_is_relevant: bool


class PredictResponse(BaseModel):
    predictions: list[Prediction]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Radiology Prior Relevance API", version="1.0")


@app.get("/health")
def health():
    return {"status": "ok", "cache_size": len(_cache)}


@app.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest, request: Request):
    request_id = str(uuid.uuid4())[:8]
    n_cases = len(body.cases)
    n_priors = sum(len(c.prior_studies) for c in body.cases)
    logger.info(
        "req=%s  cases=%d  total_priors=%d",
        request_id, n_cases, n_priors,
    )
    t0 = time.perf_counter()

    predictions: list[Prediction] = []
    for case in body.cases:
        curr_desc = case.current_study.study_description
        n_case_priors = len(case.prior_studies)
        for prior in case.prior_studies:
            relevant = _predict_cached(curr_desc, prior.study_description)
            predictions.append(
                Prediction(
                    case_id=case.case_id,
                    study_id=prior.study_id,
                    predicted_is_relevant=relevant,
                )
            )
        logger.debug(
            "req=%s  case=%s  priors=%d  current='%s'",
            request_id, case.case_id, n_case_priors, curr_desc[:60],
        )

    elapsed = time.perf_counter() - t0
    n_relevant = sum(1 for p in predictions if p.predicted_is_relevant)
    logger.info(
        "req=%s  done  predictions=%d  relevant=%d  elapsed=%.3fs  cache_size=%d",
        request_id, len(predictions), n_relevant, elapsed, len(_cache),
    )
    return PredictResponse(predictions=predictions)


# ---------------------------------------------------------------------------
# Graceful error handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
