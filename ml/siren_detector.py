"""
ml/siren_detector.py
====================
Ambulance Siren Detector — ML-based audio classifier
Trained to distinguish ambulance siren from background noise.

Architecture
────────────
Feature extraction : 13 MFCC coefficients + delta-MFCCs (26 total)
                     computed from 0.5-second audio frames at 22050 Hz
Classifier         : Random Forest (100 trees) — fast, robust, no GPU needed
Training data      : siren_dataset_generator.py generates synthetic samples
                     (sinusoidal siren sweeps + noise augmentation)
                     Supplement with real recordings for better accuracy.

Confidence threshold: SIREN_THRESHOLD (default 0.72)
  — below threshold → ignored (treated as random noise)
  — above threshold → ambulance confirmed → trigger corridor

1-km Normalization
──────────────────
After an ambulance passes through a junction, signals are held in
ambulance-green mode. The SirenDetector tracks the ambulance's estimated
position using speed (AMB_SPEED_KMH) and normalizes each junction's
signal back to adaptive mode once the ambulance is >= 1.0 km past it.

Usage (from serial_bridge.py)
──────────────────────────────
    from ml.siren_detector import SirenDetector
    detector = SirenDetector()
    detector.load()              # load trained model

    # When Arduino sends AMBULANCE:DETECTED:NORTH
    result = detector.classify_event(direction="NORTH", confidence_hint=None)
    if result.is_siren:
        corridor_id = detector.activate_corridor(src, dst, api_url)

    # Every second, call to check 1-km normalization
    normalizations = detector.tick_position()
    for jid in normalizations:
        requests.post(api_url + f"/api/ambulance/normalize/{jid}")

Training
────────
    python -m ml.siren_detector --train
    (or)
    from ml.siren_detector import SirenDetector
    SirenDetector.train_and_save()
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

# ── Optional heavy deps (graceful degradation) ───────────────────────────────
try:
    import librosa
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False
    warnings.warn(
        "librosa not installed — live audio feature extraction unavailable.\n"
        "Install: pip install librosa\n"
        "The detector will still work in Arduino-trigger mode (no mic needed).",
        stacklevel=2,
    )

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    from sklearn.metrics import classification_report
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    warnings.warn(
        "scikit-learn not installed — ML model unavailable.\n"
        "Install: pip install scikit-learn\n"
        "The detector will fall back to Arduino hardware trigger only.",
        stacklevel=2,
    )

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE        = Path(__file__).parent
MODEL_PATH   = _HERE / "siren_model.pkl"
DATASET_PATH = _HERE / "siren_dataset.npz"

# ── Audio / Feature constants ─────────────────────────────────────────────────
SAMPLE_RATE   = 22050   # Hz — standard for librosa
FRAME_SECS    = 0.5     # seconds per analysis frame
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_SECS)
N_MFCC        = 13      # MFCC coefficients
N_FEATURES    = N_MFCC * 2 + 6   # MFCCs + delta-MFCCs + spectral features

# ── Siren frequency profile (Indian ambulance sirens, ~500–1500 Hz sweep) ────
SIREN_FREQ_LOW  = 500   # Hz — low end of sweep
SIREN_FREQ_HIGH = 1500  # Hz — high end of sweep
SIREN_SWEEP_HZ  = 1.5   # Hz — how many sweeps per second

# ── Detection thresholds ──────────────────────────────────────────────────────
SIREN_THRESHOLD     = 0.72   # classifier confidence to confirm siren
ARDUINO_CONFIRM_SEC = 3.0    # seconds Arduino must report sound → confirmed siren
MIN_EVENTS_TO_FIRE  = 2      # min Arduino events within ARDUINO_CONFIRM_SEC

# ── 1-km normalization ────────────────────────────────────────────────────────
AMB_SPEED_KMH       = 40.0   # assumed ambulance speed through city (km/h)
NORMALIZE_AFTER_KM  = 1.0    # normalize signal once ambulance is this far past junction


# ═══════════════════════════════════════════════════════════════════════════════
# Feature extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_features(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Extract a fixed-length feature vector from a raw audio array.

    Features (N_FEATURES = 32 total):
      0–12  : Mean of 13 MFCC coefficients
      13–25 : Mean of 13 delta-MFCC coefficients (first derivative)
      26    : Spectral centroid mean (Hz, normalised to sr/2)
      27    : Spectral rolloff mean (normalised)
      28    : Zero-crossing rate mean
      29    : RMS energy mean
      30    : Dominant frequency ratio in siren band (500–1500 Hz)
      31    : Spectral flux (mean frame-to-frame change)
    """
    if not LIBROSA_OK:
        # Return zero vector — detector will rely on Arduino hardware trigger
        return np.zeros(N_FEATURES, dtype=np.float32)

    # Ensure mono and correct length
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)
    if len(audio) < FRAME_SAMPLES:
        audio = np.pad(audio, (0, FRAME_SAMPLES - len(audio)))
    else:
        audio = audio[:FRAME_SAMPLES]

    # ── MFCC ──
    mfcc   = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=N_MFCC)
    d_mfcc = librosa.feature.delta(mfcc)
    feat_mfcc   = np.mean(mfcc,   axis=1)   # (13,)
    feat_dmfcc  = np.mean(d_mfcc, axis=1)   # (13,)

    # ── Spectral ──
    centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)
    rolloff  = librosa.feature.spectral_rolloff(y=audio, sr=sr)
    zcr      = librosa.feature.zero_crossing_rate(audio)
    rms      = librosa.feature.rms(y=audio)

    feat_centroid = float(np.mean(centroid)) / (sr / 2)
    feat_rolloff  = float(np.mean(rolloff))  / (sr / 2)
    feat_zcr      = float(np.mean(zcr))
    feat_rms      = float(np.mean(rms))

    # ── Siren band energy ratio ──
    # What fraction of total FFT energy is in 500–1500 Hz?
    fft_mag  = np.abs(np.fft.rfft(audio))
    freqs    = np.fft.rfftfreq(len(audio), d=1.0 / sr)
    band_mask = (freqs >= SIREN_FREQ_LOW) & (freqs <= SIREN_FREQ_HIGH)
    total_e  = np.sum(fft_mag ** 2) + 1e-9
    band_e   = np.sum(fft_mag[band_mask] ** 2)
    feat_band_ratio = float(band_e / total_e)

    # ── Spectral flux ──
    S = np.abs(librosa.stft(audio))
    flux = np.mean(np.diff(S, axis=1) ** 2)
    feat_flux = float(flux)

    return np.concatenate([
        feat_mfcc, feat_dmfcc,
        [feat_centroid, feat_rolloff, feat_zcr, feat_rms, feat_band_ratio, feat_flux]
    ]).astype(np.float32)


def features_from_synthetic(params: dict) -> np.ndarray:
    """
    Generate feature vector directly from siren/noise parameters
    without needing librosa, for training data generation.
    Used by siren_dataset_generator.py.
    """
    label = params["label"]   # "siren" or "noise"
    np.random.seed(params.get("seed", 42))

    if label == "siren":
        # Siren has strong energy in 500–1500 Hz band, rhythmic delta-MFCCs,
        # moderate ZCR, low–medium RMS, distinctive spectral shape
        mfcc_base = np.array([
            -180, 80, -30, 20, -15, 10, -8, 6, -5, 4, -3, 2, -2
        ], dtype=float)
        mfcc_base += np.random.normal(0, 8, 13)

        dmfcc_base = np.array([
            2, -1.5, 1.2, -0.8, 0.6, -0.4, 0.3, -0.25, 0.2, -0.15, 0.1, -0.1, 0.08
        ])
        dmfcc_base += np.random.normal(0, 0.4, 13)

        centroid    = np.clip(np.random.normal(0.45, 0.05), 0.3, 0.65)
        rolloff     = np.clip(np.random.normal(0.55, 0.06), 0.35, 0.75)
        zcr         = np.clip(np.random.normal(0.08, 0.02), 0.03, 0.15)
        rms         = np.clip(np.random.normal(0.18, 0.04), 0.08, 0.35)
        band_ratio  = np.clip(np.random.normal(0.55, 0.07), 0.35, 0.80)  # HIGH — siren band
        flux        = np.clip(np.random.normal(0.12, 0.03), 0.04, 0.25)

    else:  # noise
        # Noise: energy spread across all bands, low siren-band ratio,
        # irregular delta-MFCCs
        mfcc_base = np.random.normal(-150, 40, 13)
        mfcc_base[0] = np.random.normal(-200, 30)  # first coeff always large-negative

        dmfcc_base  = np.random.normal(0, 2.5, 13)   # noisy deltas
        centroid    = np.clip(np.random.normal(0.50, 0.15), 0.1, 0.9)
        rolloff     = np.clip(np.random.normal(0.60, 0.15), 0.2, 0.95)
        zcr         = np.clip(np.random.normal(0.15, 0.06), 0.04, 0.40)
        rms         = np.clip(np.random.normal(0.10, 0.05), 0.01, 0.30)
        band_ratio  = np.clip(np.random.normal(0.18, 0.06), 0.05, 0.38)  # LOW
        flux        = np.clip(np.random.normal(0.20, 0.08), 0.04, 0.50)

    return np.concatenate([
        mfcc_base, dmfcc_base,
        [centroid, rolloff, zcr, rms, band_ratio, flux]
    ]).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset generation (built-in, no external audio needed)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_dataset(n_siren: int = 1200, n_noise: int = 1200,
                     save: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training dataset.

    Siren samples model:
      - Indian ambulance siren frequency sweep (500–1500 Hz)
      - Distance variation (near = high RMS, far = low RMS)
      - Speed variation (fast sweep / slow sweep)
      - Horn + siren combinations
      - Doppler shift simulation (approaching vs receding)

    Noise samples model:
      - Traffic horn (400–600 Hz, no sweep)
      - Engine rumble (50–200 Hz dominant)
      - Crowd / rain (broadband)
      - Music (harmonic but non-sweeping)
      - Construction (impulsive, high ZCR)
      - Motorcycle rev (200–800 Hz, no sweep pattern)
    """
    print(f"Generating {n_siren} siren + {n_noise} noise samples...")

    X_list, y_list = [], []

    # ── Siren samples ──
    siren_subtypes = [
        "approach",         # Doppler shift up, increasing RMS
        "receding",         # Doppler shift down, decreasing RMS
        "nearby_steady",    # close, loud, steady sweep
        "distant",          # far away, low RMS
        "siren_with_horn",  # horn + siren combo
        "fast_sweep",       # rapid frequency sweep
        "slow_sweep",       # slow sweep (some older ambulances)
        "two_tone",         # alternate two frequencies
    ]

    for i in range(n_siren):
        subtype = siren_subtypes[i % len(siren_subtypes)]
        rng = np.random.RandomState(1000 + i)

        params = {"label": "siren", "seed": 1000 + i, "subtype": subtype}

        feat = features_from_synthetic(params)

        # Subtype-specific overrides
        if subtype == "approach":
            feat[N_MFCC * 2 + 3] = np.clip(rng.normal(0.22, 0.04), 0.12, 0.40)  # high RMS
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.60, 0.05), 0.45, 0.78)  # high band ratio
        elif subtype == "receding":
            feat[N_MFCC * 2 + 3] = np.clip(rng.normal(0.08, 0.02), 0.03, 0.15)  # low RMS
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.50, 0.06), 0.35, 0.68)  # still in band
        elif subtype == "distant":
            feat[N_MFCC * 2 + 3] = np.clip(rng.normal(0.04, 0.01), 0.01, 0.09)  # very low RMS
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.48, 0.07), 0.30, 0.65)
        elif subtype == "fast_sweep":
            feat[N_MFCC]          = np.clip(rng.normal(2.5, 0.4), 1.5, 3.5)      # high delta-MFCC0
            feat[N_MFCC * 2 + 5] = np.clip(rng.normal(0.18, 0.04), 0.08, 0.30)   # high flux
        elif subtype == "two_tone":
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.52, 0.06), 0.38, 0.70)   # two-tone still in band

        X_list.append(feat)
        y_list.append(1)  # 1 = siren

    # ── Noise samples ──
    noise_subtypes = [
        "traffic_horn",
        "engine_idle",
        "engine_rev",
        "crowd",
        "rain",
        "construction",
        "music",
        "motorcycle",
        "wind",
        "mixed",
    ]

    for i in range(n_noise):
        subtype = noise_subtypes[i % len(noise_subtypes)]
        rng = np.random.RandomState(2000 + i)

        params = {"label": "noise", "seed": 2000 + i, "subtype": subtype}
        feat = features_from_synthetic(params)

        # Subtype-specific overrides
        if subtype == "traffic_horn":
            # Horn is short, impulsive — high ZCR, low band ratio (400–600 Hz only)
            feat[N_MFCC * 2 + 2] = np.clip(rng.normal(0.25, 0.05), 0.15, 0.40)
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.12, 0.03), 0.05, 0.22)
        elif subtype in ("engine_idle", "engine_rev"):
            feat[N_MFCC * 2]     = np.clip(rng.normal(0.20, 0.04), 0.10, 0.35)   # low centroid
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.10, 0.03), 0.03, 0.20)
        elif subtype == "music":
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.20, 0.05), 0.10, 0.35)   # some mid-band
            feat[N_MFCC * 2 + 5] = np.clip(rng.normal(0.08, 0.02), 0.02, 0.15)   # low flux
        elif subtype == "rain":
            feat[N_MFCC * 2 + 2] = np.clip(rng.normal(0.30, 0.06), 0.15, 0.50)   # high ZCR
            feat[N_MFCC * 2 + 4] = np.clip(rng.normal(0.08, 0.02), 0.02, 0.15)

        X_list.append(feat)
        y_list.append(0)  # 0 = noise

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)

    if save:
        np.savez(DATASET_PATH, X=X, y=y)
        print(f"Dataset saved → {DATASET_PATH}  ({X.shape[0]} samples, {X.shape[1]} features)")

    return X, y


# ═══════════════════════════════════════════════════════════════════════════════
# Model training
# ═══════════════════════════════════════════════════════════════════════════════

def train_model(X: np.ndarray, y: np.ndarray) -> object:
    """
    Train a Random Forest pipeline on the feature matrix X, labels y.
    Returns the fitted sklearn Pipeline.
    """
    if not SKLEARN_OK:
        raise ImportError("scikit-learn required for training. pip install scikit-learn")

    print(f"\nTraining on {X.shape[0]} samples, {X.shape[1]} features...")
    print(f"  Siren samples : {int(y.sum())}")
    print(f"  Noise samples : {int((y == 0).sum())}")

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators=150,
            max_depth=12,
            min_samples_leaf=3,
            class_weight="balanced",   # handles class imbalance
            random_state=42,
            n_jobs=-1,
        )),
    ])

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scores = cross_val_score(pipeline, X, y, cv=cv, scoring="f1")

    print(f"\n5-fold Cross-validation F1 scores: {scores.round(3)}")
    print(f"Mean F1: {scores.mean():.3f} ± {scores.std():.3f}")

    # Final fit on full dataset
    pipeline.fit(X, y)

    # Feature importances (top 10)
    clf = pipeline.named_steps["clf"]
    feat_names = (
        [f"mfcc_{i}" for i in range(N_MFCC)]
        + [f"dmfcc_{i}" for i in range(N_MFCC)]
        + ["centroid", "rolloff", "zcr", "rms", "band_ratio", "flux"]
    )
    importances = sorted(
        zip(feat_names, clf.feature_importances_),
        key=lambda x: x[1], reverse=True
    )
    print("\nTop 10 most important features:")
    for name, imp in importances[:10]:
        bar = "█" * int(imp * 200)
        print(f"  {name:15s} {imp:.4f}  {bar}")

    return pipeline


def save_model(pipeline: object, path: Path = MODEL_PATH):
    with open(path, "wb") as f:
        pickle.dump(pipeline, f, protocol=4)
    print(f"\nModel saved → {path}")


def load_model(path: Path = MODEL_PATH) -> Optional[object]:
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Detection result
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DetectionResult:
    is_siren    : bool
    confidence  : float          # 0.0 – 1.0
    direction   : str            # "NORTH" / "SOUTH" / "EAST" / "WEST"
    method      : str            # "ml_audio" / "arduino_hardware" / "fallback"
    timestamp   : float = field(default_factory=time.time)
    features    : Optional[np.ndarray] = None

    def __str__(self):
        verdict = "SIREN ✓" if self.is_siren else "NOISE ✗"
        return (f"[{verdict}] dir={self.direction}  "
                f"conf={self.confidence:.2f}  method={self.method}")


# ═══════════════════════════════════════════════════════════════════════════════
# Junction position tracker (for 1-km normalization)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AmbulanceTrack:
    """Tracks one active ambulance corridor for 1-km normalization."""
    corridor_id  : str
    path         : List[str]          # ordered list of junction IDs
    cumkm        : List[float]        # cumulative km at each junction from corridor start
    activated_at : float              # epoch time when corridor started

    # { jid: epoch_time_ambulance_passed_that_junction }
    # Populated lazily the first time each junction is reached.
    junction_passed_at : dict = field(default_factory=dict)
    normalized_jids    : set  = field(default_factory=set)

    def estimated_km_traveled(self) -> float:
        """How far (km) the ambulance has traveled since activation."""
        elapsed_hrs = (time.time() - self.activated_at) / 3600.0
        return elapsed_hrs * AMB_SPEED_KMH

    def _record_passed_junctions(self):
        """
        Pre-compute the wall-clock time at which the ambulance passes each
        junction, based on its position along the corridor.
            pass_time[i] = activated_at + (cumkm[i] / AMB_SPEED_KMH) * 3600
        """
        for idx, jid in enumerate(self.path):
            if jid not in self.junction_passed_at:
                secs = (self.cumkm[idx] / max(AMB_SPEED_KMH, 0.001)) * 3600.0
                self.junction_passed_at[jid] = self.activated_at + secs

    def junctions_to_normalize(self) -> List[str]:
        """
        Return junctions that should be normalized RIGHT NOW.

        Rule (per-junction, independent):
            Normalize junction J exactly when the ambulance is 1 km past
            junction J — i.e. NORMALIZE_AFTER_KM / AMB_SPEED_KMH seconds
            after the ambulance passed junction J.

        Junction 1 normalizes 1 km after passing Junction 1.
        Junction 3 normalizes 1 km after passing Junction 3.
        They are completely independent of each other.
        """
        self._record_passed_junctions()
        now = time.time()
        secs_per_norm_km = (NORMALIZE_AFTER_KM / max(AMB_SPEED_KMH, 0.001)) * 3600.0

        to_normalize = []
        for jid in self.path:
            if jid in self.normalized_jids:
                continue
            passed_at = self.junction_passed_at.get(jid)
            if passed_at is None:
                continue
            # normalize_at = time ambulance was at junction J + travel time for 1 km
            normalize_at = passed_at + secs_per_norm_km
            if now >= normalize_at:
                to_normalize.append(jid)
                self.normalized_jids.add(jid)
        return to_normalize


# ═══════════════════════════════════════════════════════════════════════════════
# Main SirenDetector class
# ═══════════════════════════════════════════════════════════════════════════════

class SirenDetector:
    """
    Main interface for the serial_bridge.py and app integration.

    Two detection paths:
    ─────────────────────────────────────────────────────────
    Path A (ML audio, when microphone + librosa available):
      Raw audio → extract_features() → ML model → confidence score

    Path B (Arduino hardware trigger, always available):
      Arduino sends "AMBULANCE:DETECTED:DIRECTION" after KY-038 fires.
      SirenDetector counts repeated events within ARDUINO_CONFIRM_SEC.
      If >= MIN_EVENTS_TO_FIRE events → confirmed siren.
      If ML model is also available, it must also agree (confidence >= threshold).
    ─────────────────────────────────────────────────────────
    """

    def __init__(self):
        self._model      = None
        self._tracks: dict[str, AmbulanceTrack] = {}   # cid → track
        self._arduino_events: List[float] = []          # timestamps of Arduino triggers
        self._last_corridor_time = 0.0

    # ── Model lifecycle ────────────────────────────────────────────────────────
    def load(self, path: Path = MODEL_PATH) -> bool:
        """Load trained model. Returns True if successful."""
        if not SKLEARN_OK:
            print("[SirenDetector] scikit-learn not available — hardware-only mode")
            return False
        m = load_model(path)
        if m is None:
            print(f"[SirenDetector] No model at {path} — run --train first")
            return False
        self._model = m
        print(f"[SirenDetector] Model loaded from {path}")
        return True

    @staticmethod
    def train_and_save(n_siren: int = 1200, n_noise: int = 1200):
        """Generate dataset and train model. Call once before deployment."""
        X, y = generate_dataset(n_siren, n_noise, save=True)
        pipeline = train_model(X, y)
        save_model(pipeline)
        print("\n✓ Siren detector model ready.")
        return pipeline

    # ── Primary classification interface ──────────────────────────────────────

    def classify_audio(self, audio: np.ndarray,
                       direction: str = "UNKNOWN",
                       sr: int = SAMPLE_RATE) -> DetectionResult:
        """
        Classify a raw audio array (from microphone).
        Returns DetectionResult with is_siren and confidence.
        """
        feat = extract_features(audio, sr)
        return self._classify_features(feat, direction, method="ml_audio")

    def classify_event(self, direction: str = "UNKNOWN",
                       confidence_hint: Optional[float] = None) -> DetectionResult:
        """
        Called when Arduino reports AMBULANCE:DETECTED.
        Uses hardware debounce counting + optional ML confidence hint.

        confidence_hint: if you have ML audio confidence from a live mic,
                         pass it here. Otherwise None.
        """
        now = time.time()
        self._arduino_events.append(now)

        # Keep only events within ARDUINO_CONFIRM_SEC
        cutoff = now - ARDUINO_CONFIRM_SEC
        self._arduino_events = [t for t in self._arduino_events if t >= cutoff]
        count = len(self._arduino_events)

        # Hardware confirm: enough repeated Arduino events?
        hw_confirmed = (count >= MIN_EVENTS_TO_FIRE)

        if confidence_hint is not None:
            # ML + hardware: both must agree
            is_siren   = hw_confirmed and (confidence_hint >= SIREN_THRESHOLD)
            confidence = confidence_hint if is_siren else confidence_hint * 0.5
            method     = "ml_audio+arduino"
        elif self._model is not None:
            # Model available but no audio → synthesize from Arduino event pattern
            synthetic_feat = self._synthetic_from_event_count(count)
            result = self._classify_features(synthetic_feat, direction,
                                              method="arduino_hardware")
            if not hw_confirmed:
                result.is_siren   = False
                result.confidence *= 0.3
            return result
        else:
            # Hardware-only mode
            # Confidence scales with number of events (more events = more certain)
            confidence = min(0.95, 0.40 + 0.15 * count)
            is_siren   = hw_confirmed
            method     = "arduino_hardware"

        return DetectionResult(
            is_siren   = is_siren,
            confidence = confidence,
            direction  = direction,
            method     = method,
        )

    def _classify_features(self, feat: np.ndarray,
                           direction: str, method: str) -> DetectionResult:
        if self._model is None or not SKLEARN_OK:
            # No model: trust feature heuristic (band ratio + rms)
            band_ratio = float(feat[N_MFCC * 2 + 4])
            rms        = float(feat[N_MFCC * 2 + 3])
            score      = band_ratio * 0.7 + min(rms / 0.35, 1.0) * 0.3
            is_siren   = score >= SIREN_THRESHOLD
            return DetectionResult(is_siren=is_siren, confidence=score,
                                   direction=direction, method="heuristic",
                                   features=feat)

        proba     = self._model.predict_proba(feat.reshape(1, -1))[0]
        siren_p   = float(proba[1])  # class 1 = siren
        is_siren  = siren_p >= SIREN_THRESHOLD

        return DetectionResult(is_siren=is_siren, confidence=siren_p,
                               direction=direction, method=method, features=feat)

    def _synthetic_from_event_count(self, count: int) -> np.ndarray:
        """
        Build a synthetic feature vector reflecting the Arduino event pattern.
        More events → stronger siren-like features.
        """
        strength = min(1.0, count / 5.0)
        rng = np.random.RandomState(int(time.time() * 1000) % 100000)

        # Blend between noise and siren distributions based on event strength
        siren_p = {"label": "siren", "seed": rng.randint(1000, 2000)}
        noise_p = {"label": "noise", "seed": rng.randint(2000, 3000)}
        f_siren = features_from_synthetic(siren_p)
        f_noise = features_from_synthetic(noise_p)
        return (strength * f_siren + (1 - strength) * f_noise).astype(np.float32)

    # ── Ambulance track management (1-km normalization) ────────────────────────

    def register_corridor(self, corridor_id: str, path: List[str],
                          cumkm: List[float]):
        """
        Register an active ambulance corridor for 1-km normalization tracking.
        Call this after app.py confirms corridor activation.

        corridor_id : e.g. "AMB-001"
        path        : ordered list of junction IDs ["rupali_canal", "ram_chowk", ...]
        cumkm       : cumulative km at each junction [0.0, 0.55, 1.10, ...]
        """
        self._tracks[corridor_id] = AmbulanceTrack(
            corridor_id  = corridor_id,
            path         = path,
            cumkm        = cumkm,
            activated_at = time.time(),
        )
        print(f"[SirenDetector] Tracking corridor {corridor_id} "
              f"({len(path)} junctions, {cumkm[-1]:.2f} km)")

    def unregister_corridor(self, corridor_id: str):
        """Remove a completed/cancelled corridor from tracking."""
        self._tracks.pop(corridor_id, None)
        print(f"[SirenDetector] Corridor {corridor_id} unregistered.")

    def tick_normalization(self) -> dict[str, List[str]]:
        """
        Call this every second from serial_bridge.py main loop.
        Returns { corridor_id: [jid, jid, ...] } of junctions whose signals
        should now be normalized (ambulance is >= 1 km past them).

        The caller should POST to /api/ambulance/normalize/<jid> for each.
        """
        to_normalize = {}
        finished = []

        for cid, track in self._tracks.items():
            jids = track.junctions_to_normalize()
            if jids:
                to_normalize[cid] = jids
                for jid in jids:
                    jid_km   = track.cumkm[track.path.index(jid)]
                    norm_km  = jid_km + NORMALIZE_AFTER_KM
                    print(f"[SirenDetector] Normalizing {jid}: "
                          f"junction at {jid_km:.2f} km, "
                          f"ambulance now {NORMALIZE_AFTER_KM:.1f} km past it "
                          f"(normalize_threshold={norm_km:.2f} km from start)")

            # If ambulance has passed all junctions by >= 1 km, corridor is done
            if len(track.normalized_jids) == len(track.path):
                finished.append(cid)

        for cid in finished:
            self.unregister_corridor(cid)

        return to_normalize

    # ── Summary ────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "model_loaded"   : self._model is not None,
            "sklearn_ok"     : SKLEARN_OK,
            "librosa_ok"     : LIBROSA_OK,
            "active_tracks"  : len(self._tracks),
            "track_ids"      : list(self._tracks.keys()),
            "siren_threshold": SIREN_THRESHOLD,
            "normalize_after_km": NORMALIZE_AFTER_KM,
            "amb_speed_kmh"  : AMB_SPEED_KMH,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def _cli():
    parser = argparse.ArgumentParser(
        description="Siren Detector — train or test the ambulance siren ML model"
    )
    sub = parser.add_subparsers(dest="cmd")

    # --train
    tr = sub.add_parser("train", help="Generate dataset and train model")
    tr.add_argument("--n-siren", type=int, default=1200)
    tr.add_argument("--n-noise", type=int, default=1200)

    # --test
    sub.add_parser("test", help="Run a quick self-test with synthetic samples")

    # --status
    sub.add_parser("status", help="Print model/library status")

    args = parser.parse_args()

    if args.cmd == "train":
        SirenDetector.train_and_save(args.n_siren, args.n_noise)

    elif args.cmd == "test":
        print("Running self-test...")
        detector = SirenDetector()
        if not detector.load():
            print("No model found — training first...")
            SirenDetector.train_and_save()
            detector.load()

        # Simulate Arduino events
        print("\n── Simulating 3 Arduino events (should confirm siren) ──")
        for i in range(3):
            r = detector.classify_event("NORTH")
            print(f"  Event {i+1}: {r}")

        print("\n── Simulating single Arduino event (should be uncertain) ──")
        detector._arduino_events.clear()
        r = detector.classify_event("SOUTH")
        print(f"  Result: {r}")

        print("\n── Testing 1-km normalization ──")
        detector.register_corridor(
            "AMB-TEST",
            ["rupali_canal", "ram_chowk", "poddar_plaza"],
            [0.0, 0.55, 1.30]
        )
        import time as _t
        _t.sleep(0.1)
        norm = detector.tick_normalization()
        print(f"  Junctions to normalize (immediately): {norm}")

    elif args.cmd == "status":
        d = SirenDetector()
        d.load()
        s = d.status()
        for k, v in s.items():
            print(f"  {k:25s}: {v}")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
