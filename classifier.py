"""
Rule-based radiology study relevance classifier.

Determines whether a prior study is relevant to show alongside a current study,
based on body-region and organ-system overlap extracted from study descriptions.
"""

import re
from functools import lru_cache

# ---------------------------------------------------------------------------
# Laterality helpers
# ---------------------------------------------------------------------------
_LAT_LEFT  = re.compile(r'\b(left|lt)\b')
_LAT_RIGHT = re.compile(r'\b(right|rt)\b')
_LAT_BILAT = re.compile(r'\b(bilat|bilateral|bilaterally|both)\b')


def _laterality(text: str):
    t = text.lower()
    if _LAT_BILAT.search(t):
        return 'B'
    has_l = bool(_LAT_LEFT.search(t))
    has_r = bool(_LAT_RIGHT.search(t))
    if has_l and has_r:
        return 'B'
    if has_l:
        return 'L'
    if has_r:
        return 'R'
    return None


def _laterality_compatible(curr: str, prior: str) -> bool:
    lc = _laterality(curr)
    lp = _laterality(prior)
    if lc is None or lp is None:
        return True
    if 'B' in (lc, lp):
        return True
    return lc == lp


# ---------------------------------------------------------------------------
# Normalization — minimal: lower-case + collapse separator chars to space
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[_/\\-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---------------------------------------------------------------------------
# Region taxonomy
# ---------------------------------------------------------------------------
REGION_KEYWORDS: dict[str, list[str]] = {

    # --- Breast / mammary -------------------------------------------------
    "breast": [
        "mam ", "mammo", "mammogr", " mam",
        "breast", "r2 mammography",
        "standard screening combo",
        "digital screener",
        "ultrasound bilat screen",   # "ULTRASOUND BILAT SCREEN COMP"
        "ultrasound bilat diag",     # "ULTRASOUND BILAT DIAG COMP"
        "ultrasound lt diag",        # "ULTRASOUND LT DIAG TARGET"
        "ultrasound rt diag",
        "us breast",
        "us guide biopsy breast", "breast biopsy", "breast locali",
        "breast specimen", "breast stereo", "seed locali",
    ],

    # --- Transesophageal echo (adjacent to thorax) -------------------------
    "tee_cardiac": [
        "transesophageal",
        "tee ",
    ],

    # --- Standard echo / cardiac ultrasound (NOT adjacent to plain thorax) -
    "echo_cardiac": [
        "echo", "echocardiogr",
        " tte",
        "mr cardiac", "mri cardiac", "cardiac mri",  # cardiac MRI
    ],

    # --- Nuclear / functional cardiac -------------------------------------
    "nm_cardiac": [
        "myo perf", "nm myo", "myocard",
        "nm myo perf", "myo perf str",
        "nuclear cardiol",
    ],

    # --- Coronary --------------------------------------------------------
    "coronary": [
        "coronary", "ct coronary",
        "ct angio coronary", "coronary calc",
        "ct ffr", "ffr",
    ],

    # --- Chest / thorax --------------------------------------------------
    "thorax": [
        "chest", "thorax", "lung",
        "pulmon", "rib",
        "mediastin", "pleura",
        "esophag",
        "pa/lat", "frontal & latrl", "frontal _ latrl",
        "frontal and lateral",
        "1v frontal", "2v frontal",
        "thoracic aorta",
        "ct angio chest", "ct angio thorax",
        "sternum",           # sternal X-ray
        "nm pul perf",       # NM pulmonary perfusion scan
        "pul perfusion",
        "scoliosis",         # scoliosis survey covers spine+chest
        "biopsy lung",       # CT-guided lung biopsy
    ],

    # --- Brain / cranial -------------------------------------------------
    "brain": [
        "brain", "cranial", "intracrani", "cerebr",
        "angio brain", "mr angio brain", "mri angio brain", "mra brain",
        "internal auditory",
        "head^ cva", "brain^with",
        "eeg", "ne eeg",
        "brain perfusion",
        "angio head",        # "CT angio head" / "CT ANGIOGRAM, HEAD"
    ],

    # --- Head (CT/MRI head) -----------------------------------------------
    "head": [
        "ct head", "mri head", "mr head",
        "head/brain", "head wo", "head w ",
        "head without", "head with", "head^",
        "ct head/brain", "mri head/brain",
        "ct angio head",     # also in brain for direct match
    ],

    # --- Facial / sinuses ------------------------------------------------
    "facial": [
        "maxfacial", "maxillary", "facial bone",
        "paranasal", " sinus",
        "ct sinus", "mri sinus", "sinuses",
    ],

    # --- Thyroid / soft-tissue neck --------------------------------------
    "thyroid_neck": [
        "thyroid", "soft tissue neck",
        "parathyroid",
        "us thyroid",
    ],

    # --- Carotid vascular ------------------------------------------------
    "carotid_vascular": [
        "carotid ultrasound", "vas us carotid",
        "angio carotid", "mri angio carotid", "mr angio carotid",
        "mra carotid", "carotid arteri",
    ],

    # --- Cervical spine --------------------------------------------------
    "cervical_spine": [
        "cervical spine", "cervicl spine", "cervicl ",
        "c spine",    # after normalization "c-spine" → "c spine"
        "mri cerv spine", "ct cervical spine",
        "mri cerv",
    ],

    # --- Thoracic spine --------------------------------------------------
    "thoracic_spine": [
        "thoracic spine", "mri thoracic spine",
        "ct thoracic spine", "spine^thoracic",
        "t spine",    # "t-spine" → "t spine" after normalization
    ],

    # --- Lumbar / lumbosacral spine --------------------------------------
    "lumbar_spine": [
        "lumbar", "lumbosacral",
        "mri lumbar", "ct lumbar",
        "spine^lumbar",
        "l spine",    # "l-spine" → "l spine" after normalization
                      # WARNING: also a suffix of "cervicl spine"!
                      # Fixed in post-processing via original-description check.
    ],

    # --- Abdomen ---------------------------------------------------------
    "abdomen": [
        "abdomen", "abdominal", " abd ",
        "liver", "hepat", "gallbladder", "spleen",
        "pancreas", "kidney", "renal", "bowel",
        "colon", "appendix", "gastric", "stomach",
        "small bowel", "esophagram", "gi series", "upper gi",
        "us abdominal", "abdomen^liver",
        "abdominal arteriogram",
        "ct urogram", "ct drain peritoneal", "peritoneal",
    ],

    # --- Pelvis ----------------------------------------------------------
    "pelvis": [
        "pelvis", "pelvic", "prostate", "uterus", "ovary",
        "bladder", "rectum", "endovaginal", "gyn",
        "us pelvic", "transvaginal",
        "scrotum", "testicular", "testes",
    ],

    # --- Abdomen+Pelvis combined -----------------------------------------
    "abdomen_pelvis": [
        "abd/pelvis", "abd pelvis", "abdomen and pelvis",
        "abdomen/pelvis", "abd & pelvis",
        "ct renal colic",
    ],

    # --- Hip -------------------------------------------------------------
    "hip": [
        "hip ", " hip", "femur", "acetabul",
        "xr pelvis and hip", "xr femur",
    ],

    # --- Knee ------------------------------------------------------------
    "knee": ["knee"],

    # --- Shoulder --------------------------------------------------------
    "shoulder": ["shoulder"],

    # --- Upper extremity (below shoulder) --------------------------------
    "upper_extremity": [
        "elbow", "wrist", "forearm", "humerus",
        " hand", "finger", "upper arm", "thumb",
    ],

    # --- Lower extremity (below hip) -------------------------------------
    "lower_extremity": [
        "ankle", "foot ", " feet", "tibia", "fibula",
        " leg ", "toe", "metatars", "calcan",
    ],

    # --- Spine (generic) -------------------------------------------------
    "spine_general": [
        "spine", "spinal",
    ],

    # --- Peripheral vascular / venous ------------------------------------
    "vascular_peripheral": [
        "venous imaging", "venous doppler", "venous study",
        "vas venous", "claudication", "aortoiliac",
        "peripheral vascular", "arterial imaging",
        "vas transcranial", "transcranial doppler",
        "arterial",
    ],

    # --- Bone density ----------------------------------------------------
    "bone_density": [
        "dxa", "dexa", "bone density",
    ],

    # --- Whole-body nuclear / PET-CT -------------------------------------
    "whole_body_nm": [
        "skull to thigh", "skull thigh",
        "piflu", "whole body",
        "f18",
        "pet/ct", "pet ct",
        "skullbase to midthigh",
        "skull to mid",
    ],

    # --- Bone scan -------------------------------------------------------
    "bone_scan": [
        "bone scan", "nm bone",
    ],

    # --- Nuclear medicine (non-cardiac, non-bone) ------------------------
    "nm_misc": [
        "gastric emptying",
        "lung v/q", "v/q scan",
        "lymphoscintigr",
    ],

    # --- Neck (soft tissue) ----------------------------------------------
    "neck": [
        "soft tissue neck", "neck mass",
        "ct neck", "mri neck", "ct soft tissue neck",
    ],
}

# ---------------------------------------------------------------------------
# Adjacency map (symmetric)
# ---------------------------------------------------------------------------
ADJACENT: set[frozenset] = {
    # TEE ↔ thorax/chest
    frozenset({"tee_cardiac", "thorax"}),
    frozenset({"tee_cardiac", "echo_cardiac"}),
    frozenset({"tee_cardiac", "nm_cardiac"}),
    frozenset({"tee_cardiac", "coronary"}),

    # TTE/Echo ↔ cardiac (but NOT plain thorax)
    frozenset({"echo_cardiac", "nm_cardiac"}),
    frozenset({"echo_cardiac", "coronary"}),

    # Whole-body PET/CT ↔ major regions (NOT breast — 0 TPs, 41 FPs)
    frozenset({"whole_body_nm", "thorax"}),
    frozenset({"whole_body_nm", "brain"}),
    frozenset({"whole_body_nm", "head"}),
    frozenset({"whole_body_nm", "abdomen"}),
    frozenset({"whole_body_nm", "pelvis"}),
    frozenset({"whole_body_nm", "abdomen_pelvis"}),
    frozenset({"whole_body_nm", "nm_cardiac"}),
    frozenset({"whole_body_nm", "nm_misc"}),
    frozenset({"whole_body_nm", "bone_scan"}),
    frozenset({"whole_body_nm", "coronary"}),

    # Bone scan (whole-skeleton) ↔ thorax, abdomen
    frozenset({"bone_scan", "thorax"}),
    frozenset({"bone_scan", "abdomen"}),
    frozenset({"bone_scan", "pelvis"}),
    frozenset({"bone_scan", "abdomen_pelvis"}),
    frozenset({"bone_scan", "nm_misc"}),
    frozenset({"bone_scan", "bone_density"}),
    frozenset({"bone_scan", "whole_body_nm"}),

    # Abdomen ↔ pelvis
    frozenset({"abdomen", "abdomen_pelvis"}),
    frozenset({"pelvis", "abdomen_pelvis"}),

    # Hip
    frozenset({"hip", "lower_extremity"}),
    frozenset({"hip", "pelvis"}),

    # Spine hierarchy
    frozenset({"spine_general", "cervical_spine"}),
    frozenset({"spine_general", "thoracic_spine"}),
    frozenset({"spine_general", "lumbar_spine"}),

    # Neck / cervical level
    frozenset({"thyroid_neck", "cervical_spine"}),
    frozenset({"thyroid_neck", "neck"}),
    frozenset({"carotid_vascular", "neck"}),

    # Head ↔ brain
    frozenset({"head", "brain"}),
    frozenset({"head", "facial"}),

    # Bone density
    frozenset({"bone_density", "hip"}),
}

# Regions requiring laterality matching
LATERALITY_SENSITIVE = {
    "breast", "knee", "shoulder", "upper_extremity", "lower_extremity", "hip",
}


@lru_cache(maxsize=8192)
def get_regions(description: str) -> frozenset[str]:
    """Return canonical region labels for a study description."""
    norm = _normalize(description)
    found: set[str] = set()

    for region, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in norm:
                found.add(region)
                break

    # --- Post-processing ---

    # 1. "l spine" in lumbar_spine falsely matches "cervicl spine" suffix.
    #    Guard: only keep lumbar_spine if original description has a genuine
    #    lumbar indicator.
    if "lumbar_spine" in found:
        orig_lower = description.lower()
        has_lumbar = any(w in orig_lower for w in ["lumbar", "lumbosacral", "l-spine"])
        if not has_lumbar:
            found.discard("lumbar_spine")

    # 2. Remove spine_general when specific spine region found or bone_density
    if found & {"cervical_spine", "thoracic_spine", "lumbar_spine"} or "bone_density" in found:
        found.discard("spine_general")

    # 3. thoracic_spine must not bleed into thorax
    if "thoracic_spine" in found:
        found.discard("thorax")

    # 4. Carotid ultrasound → vascular, not brain
    if "carotid_vascular" in found and "carotid ultrasound" in norm:
        found.discard("brain")
        found.discard("head")

    # 5. Lung V/Q → nm_misc only (remove erroneous thorax match via "lung")
    orig_lower = description.lower()
    if "v/q" in orig_lower:
        found.discard("thorax")
        found.add("nm_misc")

    # 6. tee_cardiac supersedes echo_cardiac
    if "tee_cardiac" in found:
        found.discard("echo_cardiac")

    # 7. Lymphoscintography without breast context → nm_misc, not breast
    if "nm_misc" in found and "breast" in found and "lymphoscintigr" in norm:
        if not any(w in norm for w in ["mam", "mammogr", "breast biopsy"]):
            found.discard("breast")

    return frozenset(found)


def _regions_adjacent(r1: str, r2: str) -> bool:
    return frozenset({r1, r2}) in ADJACENT


def is_relevant(current_description: str, prior_description: str) -> bool:
    """Return True if the prior study is relevant to show with the current study."""
    curr_regions = get_regions(current_description)
    prior_regions = get_regions(prior_description)

    if not curr_regions or not prior_regions:
        return False

    # Direct region overlap
    shared = curr_regions & prior_regions
    if shared:
        lat_shared = shared & LATERALITY_SENSITIVE
        non_lat_shared = shared - LATERALITY_SENSITIVE
        if non_lat_shared:
            return True
        if lat_shared:
            return _laterality_compatible(current_description, prior_description)

    # Adjacency overlap
    for cr in curr_regions:
        for pr in prior_regions:
            if _regions_adjacent(cr, pr):
                return True

    return False
