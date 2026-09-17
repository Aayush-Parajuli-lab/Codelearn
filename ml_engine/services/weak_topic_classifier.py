"""
Algorithm 2 — Weak-Topic Classifier
=====================================
Supervised learning stage of CodeLearn's performance-analysis pipeline.

Problem framing
----------------
Given a student's feature vector for a topic:

    x = [quiz_score, assignment_score, coding_score,
         avg_attempts_before_pass, avg_submission_time_seconds,
         attendance_rate]

predict a binary label:

    y = 1  -> student is "weak" in this topic (needs intervention)
    y = 0  -> student is "strong" in this topic

Model
------
We use scikit-learn's LogisticRegression as the primary model (a linear
classifier that outputs a calibrated probability, which lets us rank how
weak a student is rather than just a 0/1 cut). GaussianNB is offered as an
alternative for comparison in the report (see `train(model_type=...)`).

Bootstrapping labels (cold start)
-----------------------------------
Early in the system's life there is no historical "did this student
struggle" ground truth to train on. We bootstrap labels using the same
weighted-score rule the original spec proposed:

    topic_score = quiz*0.30 + assignment*0.30 + coding*0.40
    label = 1 (weak) if topic_score < 50 else 0

Once real outcome data accumulates (e.g. did the student eventually pass
the topic's assignments, did their score improve after intervention), the
classifier can be retrained on the *actual* outcome instead of the
bootstrapped rule, which is the point of promoting this to a trained
model rather than leaving it as a hardcoded threshold.

Persistence
------------
`train()` saves the fitted model to disk with joblib after training
(`MODEL_PATH`, plus a small `MODEL_METADATA_PATH` JSON sidecar with the
training report and a timestamp) so that a separate prediction path —
e.g. scoring a single new feature row right after a submission, without
retraining the whole classifier — can load the already-trained model
via `load_model()` instead of paying the cost of retraining on every
request. Retraining is a deliberate, separate step (the
`retrain_models` management command — see README) rather than
something that happens inline during a web request.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from ml_engine.models import StudentTopicFeature, FEATURE_NAMES

WEAK_THRESHOLD = 50.0

MODEL_DIR = Path(settings.BASE_DIR) / "ml_models"
MODEL_PATH = MODEL_DIR / "weak_topic_classifier.joblib"
MODEL_METADATA_PATH = MODEL_DIR / "weak_topic_classifier.meta.json"


@dataclass
class TrainingReport:
    model_type: str
    n_samples: int
    accuracy: float
    precision: float
    recall: float
    f1: float


def bootstrap_label(feature: StudentTopicFeature) -> int:
    """Rule-based fallback label used before enough real outcomes exist."""
    topic_score = (
        feature.quiz_score * 0.30
        + feature.assignment_score * 0.30
        + feature.coding_score * 0.40
    )
    return 1 if topic_score < WEAK_THRESHOLD else 0


def save_model(model, report: "TrainingReport"):
    """Persists the fitted model + a small metadata sidecar to disk."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    MODEL_METADATA_PATH.write_text(json.dumps({
        "trained_at": datetime.now().isoformat(),
        "model_type": report.model_type,
        "n_samples": report.n_samples,
        "accuracy": report.accuracy,
        "precision": report.precision,
        "recall": report.recall,
        "f1": report.f1,
        "feature_names": FEATURE_NAMES,
    }, indent=2))


def load_model():
    """Returns the persisted model, or None if nothing has been trained
    and saved yet (falls back to the bootstrap rule at call sites)."""
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def load_model_metadata() -> dict | None:
    if not MODEL_METADATA_PATH.exists():
        return None
    return json.loads(MODEL_METADATA_PATH.read_text())


def _dataset(label_noise: float = 0.0, seed: int = 42):
    """
    label_noise: probability of flipping the bootstrapped label for a given
    row before training. Real "did this student actually need help" outcomes
    are noisy — some students with borderline-strong features still
    struggled, some borderline-weak ones caught up on their own. A small
    amount of label noise (e.g. 0.08) simulates that instead of training
    against a label that is a deterministic linear function of the exact
    same features being fed in, which would trivially reach ~100% accuracy
    and isn't representative of a real classifier's performance.
    """
    rng = np.random.RandomState(seed)
    features = list(StudentTopicFeature.objects.all())
    X = np.array([f.as_feature_vector() for f in features])
    y = np.array([bootstrap_label(f) for f in features])
    if label_noise > 0:
        flip_mask = rng.random(len(y)) < label_noise
        y = np.where(flip_mask, 1 - y, y)
    return features, X, y


def train(model_type: str = "logistic", label_noise: float = 0.15) -> TrainingReport:
    """
    Trains the classifier on all currently available StudentTopicFeature
    rows and returns evaluation metrics. In production this would be run
    as a scheduled/management-command job and the resulting model
    persisted (e.g. via joblib) rather than retrained on every request.

    `label_noise` (default 0.15) adds a small amount of randomness to the
    bootstrapped training labels — see `_dataset()` — so evaluation
    metrics reflect a realistic classifier rather than the trivial ~100%
    accuracy you'd get fitting a linear model to a label that's a
    deterministic linear function of the same inputs. Set to 0 to disable.
    """
    features, X, y = _dataset(label_noise=label_noise)
    if len(features) < 10:
        raise ValueError(
            "Not enough data to train (need >= 10 StudentTopicFeature rows). "
            "Seed the database first."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y if len(set(y)) > 1 else None
    )

    model = LogisticRegression(max_iter=1000) if model_type == "logistic" else GaussianNB()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    report = TrainingReport(
        model_type=model_type,
        n_samples=len(features),
        accuracy=round(accuracy_score(y_test, y_pred), 3),
        precision=round(precision_score(y_test, y_pred, zero_division=0), 3),
        recall=round(recall_score(y_test, y_pred, zero_division=0), 3),
        f1=round(f1_score(y_test, y_pred, zero_division=0), 3),
    )

    # Persist predictions back onto every feature row (probability + label).
    # Only notify on a *newly* flagged topic (was not weak before, or had
    # never been scored yet) — otherwise every retrain would re-notify
    # students who were already told, which trains people to ignore the
    # notification center.
    from notifications.models import notify, Notification

    all_probs = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else model.predict(X)
    for f, prob in zip(features, all_probs):
        was_weak = f.is_weak
        f.weak_probability = round(float(prob), 4)
        f.is_weak = bool(prob >= 0.5)
        f.save(update_fields=["weak_probability", "is_weak"])

        if f.is_weak and not was_weak:
            notify(
                f.student.user,
                f"You may need extra support in {f.topic.name} — check the recommended lesson.",
                category=Notification.Category.WEAK_TOPIC,
                link="/progress/",
            )

    save_model(model, report)

    return report


def predict_single(feature: StudentTopicFeature, model=None) -> float:
    """
    Predicts weak-probability for one feature row.

    If `model` isn't passed explicitly, tries the persisted model
    (`load_model()`) first — this is the path a real request handler
    would use, e.g. right after a new submission, without paying the
    cost of retraining. Falls back to the bootstrapped rule only if no
    trained model has ever been saved yet.
    """
    if model is None:
        model = load_model()
    if model is None:
        return 1.0 if bootstrap_label(feature) else 0.0
    x = np.array([feature.as_feature_vector()])
    return float(model.predict_proba(x)[:, 1][0])
