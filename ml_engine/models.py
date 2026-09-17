from django.db import models


class StudentTopicFeature(models.Model):
    """
    Feature vector for one (student, topic) pair — this is the row-level
    input to Algorithm 2 (Weak-Topic Classifier) and Algorithm 3
    (KNN Recommender). Recomputed after each new quiz/assignment/coding
    activity via ml_engine.services.feature_engineering.
    """

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="topic_features"
    )
    topic = models.ForeignKey(
        "academics.Topic", on_delete=models.CASCADE, related_name="student_features"
    )

    quiz_score = models.FloatField(default=0.0)          # 0-100
    assignment_score = models.FloatField(default=0.0)     # 0-100
    coding_score = models.FloatField(default=0.0)         # 0-100
    avg_attempts_before_pass = models.FloatField(default=0.0)
    avg_submission_time_seconds = models.FloatField(default=0.0)
    attendance_rate = models.FloatField(default=0.0)      # 0-100

    # Derived label, filled in by the classifier
    is_weak = models.BooleanField(null=True, blank=True)
    weak_probability = models.FloatField(null=True, blank=True)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "topic")

    def __str__(self):
        return f"{self.student} - {self.topic}"

    def as_feature_vector(self):
        """Ordered numeric feature vector consumed by the ML models."""
        return [
            self.quiz_score,
            self.assignment_score,
            self.coding_score,
            self.avg_attempts_before_pass,
            self.avg_submission_time_seconds,
            self.attendance_rate,
        ]


FEATURE_NAMES = [
    "quiz_score",
    "assignment_score",
    "coding_score",
    "avg_attempts_before_pass",
    "avg_submission_time_seconds",
    "attendance_rate",
]


class Recommendation(models.Model):
    """Output of Algorithm 3 (KNN): exercises recommended to a student
    for a weak topic, based on what helped similar students improve."""

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="recommendations"
    )
    topic = models.ForeignKey("academics.Topic", on_delete=models.CASCADE)
    recommended_lesson = models.ForeignKey(
        "academics.Lesson", on_delete=models.SET_NULL, null=True, blank=True
    )
    reason = models.CharField(
        max_length=255,
        help_text="Human-readable explanation, e.g. 'Recommended based on 5 similar students'",
    )
    confidence = models.FloatField(
        default=0.0, help_text="Fraction of nearest neighbors who improved after this lesson"
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Recommend '{self.recommended_lesson}' to {self.student} for {self.topic}"
