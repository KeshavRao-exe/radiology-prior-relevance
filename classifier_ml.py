"""
ML-based relevance classifier.
Loads model.pkl (GradientBoostingClassifier + TF-IDF vectorizers) and
uses the rule-based classifier's features as input.
"""

import os
import pickle
from difflib import SequenceMatcher
from functools import lru_cache

import numpy as np

from classifier import get_regions, is_relevant as rule_is_relevant, ADJACENT

# ---------------------------------------------------------------------------
# Load model once at import time
# ---------------------------------------------------------------------------
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

with open(_MODEL_PATH, "rb") as _f:
    _bundle = pickle.load(_f)

_clf = _bundle["clf"]
_tfidf = _bundle["tfidf"]
_tfidf_char = _bundle["tfidf_char"]


# ---------------------------------------------------------------------------
# Feature extraction (mirrors training)
# ---------------------------------------------------------------------------
def _regions_adj_count(curr_regions, prior_regions) -> int:
    count = 0
    for cr in curr_regions:
        for pr in prior_regions:
            if frozenset({cr, pr}) in ADJACENT:
                count += 1
    return count


def _extract_features(curr_desc: str, prior_desc: str) -> np.ndarray:
    rule = float(rule_is_relevant(curr_desc, prior_desc))
    curr_r = get_regions(curr_desc)
    prior_r = get_regions(prior_desc)
    shared = curr_r & prior_r
    n_shared = len(shared)
    n_adj = _regions_adj_count(curr_r, prior_r)
    both_detected = float(bool(curr_r) and bool(prior_r))
    n_curr = len(curr_r)
    n_prior = len(prior_r)
    union = curr_r | prior_r
    jaccard = n_shared / len(union) if union else 0.0
    seq_ratio = SequenceMatcher(None, curr_desc.lower(), prior_desc.lower()).ratio()

    # TF-IDF cosine similarities
    vec_curr_w = _tfidf.transform([curr_desc])
    vec_prior_w = _tfidf.transform([prior_desc])
    cosim_word = float((vec_curr_w * vec_prior_w.T).toarray()[0, 0])

    vec_curr_c = _tfidf_char.transform([curr_desc])
    vec_prior_c = _tfidf_char.transform([prior_desc])
    cosim_char = float((vec_curr_c * vec_prior_c.T).toarray()[0, 0])

    return np.array([[rule, n_shared, n_adj, both_detected, n_curr, n_prior,
                      jaccard, seq_ratio, cosim_word, cosim_char]])


# ---------------------------------------------------------------------------
# Public interface (mirrors classifier.py)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8192)
def is_relevant(current_description: str, prior_description: str) -> bool:
    X = _extract_features(current_description, prior_description)
    return bool(_clf.predict(X)[0])
