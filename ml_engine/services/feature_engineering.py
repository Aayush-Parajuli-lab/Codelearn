"""
Feature Engineering
====================
Turns raw activity data (quiz attempts, assignment submissions, coding
submissions, attendance) into the numeric feature vector used by the
weak-topic classifier and the KNN recommender.

This module is intentionally kept separate from the ML models so the
"algorithm" section of a report can point to one clean file per stage:

    raw data  -->  feature_engineering.py  -->  weak_topic_classifier.py -->  knn_recommender.py
"""
from django.db.models import Avg

from academics.models import Topic
from accounts.models import Student
from assignments.models import Submission
from attendance.models import AttendanceRecord
from ml_engine.models import StudentTopicFeature
from quizzes.models import QuizAttempt


def build_feature_vector(student: Student, topic: Topic) -> StudentTopicFeature:
    """
    Computes / updates the StudentTopicFeature row for a single
    (student, topic) pair.

    Feature definitions
    --------------------
    quiz_score                    : mean(QuizAttempt.percentage) for quizzes under this topic
    assignment_score              : mean(Submission.score) for assignments under this topic
    coding_score                  : pass-rate weighted score from coding submissions
                                     coding_score = (passed_test_cases / total_test_cases) * 100, averaged
    avg_attempts_before_pass      : mean number of submissions a student needed
                                     before first reaching status == PASSED
    avg_submission_time_seconds   : mean time between assignment creation and submission
                                     (proxy for how much a student struggles)
    attendance_rate               : AttendanceRecord.attendance_percentage() for the topic's course
    """
    feature, _ = StudentTopicFeature.objects.get_or_create(student=student, topic=topic)

    # --- Quiz score -------------------------------------------------------
    # Averaged as a percentage (score/total_marks * 100) per attempt, NOT
    # a raw average of `score` — quizzes can have any total_marks (e.g. 7),
    # so treating raw scores as already being 0-100 would silently produce
    # wrong feature values for any quiz whose total isn't literally 100.
    quiz_attempts = QuizAttempt.objects.filter(student=student, quiz__topic=topic)
    quiz_percentages = [a.percentage for a in quiz_attempts if a.total_marks]
    feature.quiz_score = round(sum(quiz_percentages) / len(quiz_percentages), 2) if quiz_percentages else 0.0

    # --- Assignment / coding score --------------------------------------
    submissions = Submission.objects.filter(student=student, assignment__topic=topic)
    if submissions.exists():
        feature.assignment_score = round(
            submissions.aggregate(avg=Avg("score"))["avg"] or 0.0, 2
        )

        # Coding score: average (passed/total) across submissions with test cases run
        scored = [
            (s.passed_test_cases / s.total_test_cases) * 100
            for s in submissions
            if s.total_test_cases > 0
        ]
        feature.coding_score = round(sum(scored) / len(scored), 2) if scored else 0.0

        # Average attempts before first PASSED submission, per assignment
        attempts_needed = []
        for assignment_id in submissions.values_list("assignment_id", flat=True).distinct():
            asg_subs = submissions.filter(assignment_id=assignment_id).order_by(
                "attempt_number"
            )
            passed = asg_subs.filter(status=Submission.Status.PASSED).first()
            if passed:
                attempts_needed.append(passed.attempt_number)
        feature.avg_attempts_before_pass = (
            round(sum(attempts_needed) / len(attempts_needed), 2)
            if attempts_needed
            else 0.0
        )

        # Average time-to-submit, in seconds, relative to assignment creation
        deltas = [
            (s.submitted_at - s.assignment.created_at).total_seconds()
            for s in submissions
        ]
        feature.avg_submission_time_seconds = (
            round(sum(deltas) / len(deltas), 2) if deltas else 0.0
        )

    # --- Attendance -------------------------------------------------------
    feature.attendance_rate = AttendanceRecord.attendance_percentage(
        student, course=topic.course
    )

    feature.save()
    return feature


def rebuild_all_features(topic: Topic = None):
    """Recomputes features for every student (optionally scoped to one topic).
    Call this after any new quiz/assignment/coding/attendance event, or on a
    scheduled job (e.g. nightly)."""
    topics = [topic] if topic else Topic.objects.all()
    updated = 0
    for t in topics:
        # Only students enrolled in the course this topic belongs to
        students = Student.objects.filter(enrollments__course=t.course).distinct()
        for student in students:
            build_feature_vector(student, t)
            updated += 1
    return updated
