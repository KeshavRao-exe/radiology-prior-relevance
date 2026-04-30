# Experiments & Write-up: Radiology Prior Relevance

## Problem Statement

Given a current radiology examination and a list of prior examinations for the same patient, predict whether each prior study should be shown to the radiologist reading the current study. The output is a boolean `predicted_is_relevant` per prior study.

The public evaluation set contains 996 cases and 27,614 labeled prior examinations. Only 23.8% of prior studies are labeled relevant, creating a class-imbalance problem.

---

## Baseline

**Predict all FALSE (never relevant)**
- Accuracy: 76.2% (correct on the negative class, wrong on all positives)
- Precision: undefined (0 positives predicted)
- Recall: 0%
- This serves as the lower bound — any model must beat 76.2%.

---

## Approach: Rule-Based Body-Region Matching

### Core Insight

A prior study is relevant to a current study when it covers the **same anatomical region or clinically related organ system**. Radiology study descriptions encode the body region in free text (e.g., "CT CHEST WITH CONTRAST", "MRI LUMBAR SPINE WITHOUT CONTRAST"). Matching these regions is the primary signal.

### Methodology

**Step 1 — Description normalization**  
Lower-case + collapse separator characters (hyphens, slashes, underscores) to spaces. This unifies abbreviations like `c-spine` → `c spine`.

**Step 2 — Region extraction**  
Match each normalized description against a hand-crafted taxonomy of 25+ body regions using substring keyword matching. Examples:
- `"chest"`, `"lung"`, `"rib"`, `"sternum"` → **thorax**
- `"brain"`, `"cranial"`, `"cerebr"` → **brain**
- `"mammogr"`, `"mam "`, `"breast"` → **breast**
- `"lumbar"`, `"lumbosacral"`, `"l-spine"` → **lumbar_spine**
- `"echo"`, `"echocardiogr"` → **echo_cardiac**
- `"transesophageal"` → **tee_cardiac**
- `"pet/ct"`, `"skull to thigh"` → **whole_body_nm**

**Step 3 — Relevance decision**  
Two studies are relevant if:
1. Their region sets share at least one common label, **OR**
2. Their regions are connected via an adjacency map (clinical containment relationships).

**Step 4 — Laterality filter**  
For laterality-sensitive regions (breast, knee, shoulder, hip, extremities): if both studies have known, opposite laterality (e.g., current = right breast, prior = left breast), predict NOT relevant. Bilateral studies are always compatible.

---

## Adjacency Map (Key Rules)

| Region A | Region B | Rationale |
|---|---|---|
| `tee_cardiac` | `thorax` | Transesophageal echo shows cardiac and thoracic structures |
| `echo_cardiac` | `coronary` | TTE and coronary CT both assess cardiac function/anatomy |
| `whole_body_nm` | `thorax, brain, abdomen, pelvis` | PET/CT covers all major body cavities |
| `bone_scan` | `thorax, abdomen, pelvis` | Whole-skeleton scan covers all bone regions |
| `abdomen` | `abdomen_pelvis` | Combined abd/pelvis CT covers both individually |
| `hip` | `pelvis` | Hip joint is part of the pelvic girdle |
| `spine_general` | `cervical/thoracic/lumbar_spine` | Generic spine imaging adjacent to specific levels |
| `head` | `brain` | Head CT often evaluates brain pathology |

---

## Experiments & Iterations

### Experiment 1 — Initial keyword classifier (v1)
- Mapped 18 body regions with basic keyword lists
- **Accuracy: 90.63%** (TP=5710, FP=1730, TN=19317, FN=857)

Key errors discovered:
- `"iac"` in brain keywords falsely matched `"cardi-ac"` → large FP spike
- `thorax ↔ cardiac` adjacency: 41 TPs but **221 FPs** (plain chest X-ray ≠ cardiac SPECT)
- Breast same-region FPs: laterality not considered (right breast mammo ≠ left breast US)
- `"l spine"` substring matched `"cervicl spine"` → 75 spurious lumbar matches

### Experiment 2 — Split cardiac; add laterality; fix substring bugs (v2)
Changes:
- Removed `thorax ↔ cardiac` adjacency (net: −180 FPs for ~41 TP loss)
- Split cardiac into `echo_cardiac` (TTE) and `tee_cardiac` (transesophageal)
- Added `tee_cardiac ↔ thorax` (10 TPs, 8 FPs — good ratio)
- Implemented laterality matching for breast, knee, shoulder, extremity regions
- Fixed `"iac"` → `"internal auditory"` (full phrase); removed `"sinus"` brain keyword
- Fixed `"l spine"` bug: post-processing checks original description for genuine lumbar indicators
- Added missing breast US keywords (`"ultrasound bilat screen comp"`, `"ultrasound lt diag target"`)
- Added `bone_scan` region (whole-body nuclear), adjacent to thorax + abdomen
- **Accuracy: 94.67%** (TP=5738, FP=642, TN=20405, FN=829)

### Experiment 3 — Additional vocabulary + targeted post-processing (v3)
Changes:
- Added `"mr cardiac"`, `"mri cardiac"` to `echo_cardiac` (catches cardiac MRI)
- Added `"angio head"` to brain keywords (catches `"CT ANGIOGRAM, HEAD"`)
- Added `"sternum"`, `"pul perfusion"`, `"scoliosis"`, `"biopsy lung"` to thorax
- Added `"scrotum"`, `"testicular"` to pelvis
- Post-processing: Lung V/Q scan removes thorax match (V/Q is nuclear, not chest imaging)
- Removed `whole_body_nm ↔ breast` adjacency (0 TPs, 41 FPs in data)
- **Accuracy: 94.62%** (TP=5791, FP=709, TN=20338, FN=776)

*Note: Slightly lower accuracy than v2 due to some new keyword additions generating marginal FPs. The recall improvement (FN: 829→776) trades against precision (FP: 642→709).*

### Final Model
Selected v3 for its higher recall (88.18% vs 87.35%) and comparable F1, accepting the small accuracy trade-off. High recall matters in clinical settings to avoid missing relevant comparisons.

**Final metrics on 27,614 public labeled examples:**
| Metric | Value |
|---|---|
| **Accuracy** | **94.62%** |
| Precision | 89.09% |
| Recall | 88.18% |
| F1 | 88.64% |
| TP | 5,791 |
| FP | 709 |
| TN | 20,338 |
| FN | 776 |

**Throughput:** 996 cases / 27,614 priors processed in **2.25 seconds** (well within the 360s timeout).

---

## What Worked

1. **Region-based matching beats naive baselines dramatically** — moving from 76.2% (predict all false) to 94.6% with rules alone.

2. **Splitting cardiac SPECT from echo** — The single biggest FP source was treating all cardiac studies as interchangeable with chest imaging. Cardiac SPECT (functional) ≠ chest CT (anatomical). Echo (especially TEE) is adjacent to thorax; standard TTE is not.

3. **Laterality filtering** — Adding left/right side awareness reduced breast FPs by ~100 cases. A right-breast diagnostic mammogram is not relevant to a prior left-breast study.

4. **Substring bug fix (`"l spine"`)** — `"cervicl spine"` ends with `"l spine"` — the suffix caused all cervical spine studies to incorrectly match lumbar spine studies. Post-processing the original description (before normalization) resolved this.

5. **Aggressive caching** — In-memory cache keyed by SHA-256 of `(current_description, prior_description)`. On repeated requests (retries, duplicate pairs), zero recomputation cost.

---

## What Failed / Was Rejected

1. **LLM-based classification** — Without a paid API key, this was not viable. Even with one, batching 996 × ~28 pairs into LLM calls risks exceeding the 360s timeout with rate limits, and caching only helps on retries.

2. **Removing `coronary ↔ thorax` adjacency** — The net was near-zero (69 TPs vs 79 FPs). Kept the adjacency because the clinical case for CT coronary ↔ CT chest is sound.

3. **Thoracic spine ↔ thorax adjacency** — 59+52 = 111 FPs, minimal TPs. `"SPINE^THORACIC"` is NOT the same body region as `"CT CHEST"`. Removed.

4. **TTE (echo) ↔ plain thorax** — 73 TPs but 202 FPs. Standard transthoracic echocardiography does not benefit from comparison to chest X-rays. The few cases where this was labeled relevant appear to be inconsistent radiologist preferences in the labeling data.

---

## Remaining Error Sources

The residual ~5.4% error falls into these categories:

| Error type | Count | Cause |
|---|---|---|
| Echo (TTE) → CT chest FNs | ~72 | Inconsistent labeling (some radiologists mark it relevant, others don't) |
| Thoracic spine ↔ chest FNs | ~42 | Some cases where radiologist showed both; hard to model without image content |
| Undetected descriptions | ~37+ | Very short/abbreviated descriptions not matching any keyword (e.g. "EV", "CV", specialty-specific abbreviations) |
| Same region but NOT relevant | ~38 | Chest X-ray → Chest X-ray sometimes marked NOT relevant (possibly very old studies, or radiologist preference) |
| Pelvis ↔ abdomen FPs | ~57 | Clinical adjacency correct but some sub-types (e.g. pelvic US ↔ abdominal plain film) are not clinically compared |

---

## Next Steps / Improvements

1. **LLM fallback for undetected studies** — For cases where `get_regions()` returns empty on one or both sides, use a fast LLM (e.g., Gemini Flash or Claude Haiku) with a structured prompt to infer relevance. This would address the ~80 FNs from unrecognized descriptions.

2. **Study-date weighting** — Very old prior studies (>5 years) might be less relevant. Adding a recency prior could reduce FPs from ancient comparison studies.

3. **Modality-aware adjacency** — Some adjacencies only hold between CT-level studies: coronary CT ↔ chest CT = relevant, but coronary CT ↔ chest X-ray = less so. Detecting modality (CT/MRI/XR/US/NM) from the description and incorporating it into the adjacency rules would improve precision.

4. **Embedding-based matching** — Fine-tune a small BERT/sentence-transformer on the labeled pairs to learn region embeddings. This would generalize to unusual descriptions and capture clinical similarity beyond keyword rules.

5. **Training data expansion** — The public eval labels (27,614 pairs) could be used to train a lightweight classifier (e.g., gradient-boosted trees on TF-IDF features of study descriptions), potentially improving accuracy to 96–97%.
