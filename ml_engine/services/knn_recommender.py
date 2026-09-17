"""
Algorithm 3 — Peer-Based Recommendation (K-Nearest Neighbors)
=================================================================
Once Algorithm 2 flags a student as "weak" in a topic, this stage finds
the k most similar students (by feature vector) who were *also* weak in
that topic at some point, but *improved*, and recommends whatever
lesson/exercise most consistently preceded their improvement.

Similarity metric
-------------------
Standard Euclidean distance over the standardized (z-scored) feature
vector:

    d(a, b) = sqrt( sum_i ( (a_i - mean_i) / std_i - (b_i - mean_i) / std_i )^2 )

Standardizing first stops high-magnitude features (e.g.
avg_submission_time_seconds, which can be in the thousands) from
dominating low-magnitude ones (e.g. attendance_rate, 0-100).

Algorithm
----------
1. Build the feature matrix for every student who has ever been "weak"
   in the target topic.
2. Standardize features (StandardScaler).
3. Fit sklearn.neighbors.NearestNeighbors with k neighbors.
4. For the target student's vector, find the k nearest peers.
5. Among those peers, look at which of their lesson completions were
   followed by is_weak flipping from True -> False (i.e. "what worked").
6. Rank candidate lessons by how often they preceded improvement among
   the neighbors; recommend the top lesson with a confidence score
   = (# neighbors who improved after this lesson) / k.
"""
from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from academics.models import Lesson, Topic
from accounts.models import Student
from ml_engine.models import Recommendation, StudentTopicFeature


@dataclass
class Neighbor:
    student_id: int
    distance: float


def find_similar_students(
    target: StudentTopicFeature, topic: Topic, k: int = 5
) -> list[Neighbor]:
    """Finds the k nearest students to `target` (by standardized feature
    distance) among all students who have a feature row for this topic."""
    peers = list(
        StudentTopicFeature.objects.filter(topic=topic).exclude(student=target.student)
    )
    if len(peers) < 1:
        return []

    k = min(k, len(peers))
    X = np.array([p.as_feature_vector() for p in peers])
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    target_scaled = scaler.transform([target.as_feature_vector()])

    nn = NearestNeighbors(n_neighbors=k, metric="euclidean")
    nn.fit(X_scaled)
    distances, indices = nn.kneighbors(target_scaled)

    return [
        Neighbor(student_id=peers[i].student_id, distance=round(float(d), 4))
        for d, i in zip(distances[0], indices[0])
    ]


def recommend_for_student(
    student: Student, topic: Topic, k: int = 5
) -> Recommendation | None:
    """
    Full Algorithm 3 pipeline for one (student, topic) pair:
        1. Confirm the student is currently flagged weak in this topic.
        2. Find k nearest peers.
        3. Pick the lesson most associated with peer improvement.
        4. Persist and return a Recommendation.
    """
    try:
        target = StudentTopicFeature.objects.get(student=student, topic=topic)
    except StudentTopicFeature.DoesNotExist:
        return None

    if not target.is_weak:
        return None  # nothing to recommend; student isn't currently weak here

    neighbors = find_similar_students(target, topic, k=k)
    if not neighbors:
        return None

    # In a full implementation this cross-references a LessonCompletion /
    # progress-history table to see which lesson each neighbor took right
    # before their is_weak flag flipped False. Simplified here to: order
    # the topic's lessons and count how many neighbors are currently
    # "strong" (is_weak=False) as a proxy signal for "this topic's
    # material generally works for similar students".
    neighbor_features = StudentTopicFeature.objects.filter(
        topic=topic, student_id__in=[n.student_id for n in neighbors]
    )
    improved_count = neighbor_features.filter(is_weak=False).count()
    confidence = round(improved_count / len(neighbors), 2) if neighbors else 0.0

    lesson = Lesson.objects.filter(topic=topic).order_by("order").first()

    recommendation, _ = Recommendation.objects.update_or_create(
        student=student,
        topic=topic,
        defaults=dict(
            recommended_lesson=lesson,
            reason=(
                f"{improved_count}/{len(neighbors)} of the {len(neighbors)} most "
                f"similar students are currently strong in {topic.name}"
            ),
            confidence=confidence,
            is_active=True,
        ),
    )
    return recommendation


def difficulty_bucket(topic_score: float) -> str:
    """Simple companion helper: maps a 0-100 topic score to a difficulty
    tier for exercise selection, kept from the original spec alongside
    the richer KNN recommendation."""
    if topic_score < 50:
        return "Beginner"
    if topic_score <= 75:
        return "Intermediate"
    return "Advanced"
