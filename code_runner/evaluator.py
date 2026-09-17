"""
Algorithm 1 — Automated Code Evaluation
==========================================
Deterministic, rule-based algorithm (no ML needed here — evaluation must
be exact and reproducible).

Process
--------
1. Receive student code + selected language.
2. Validate language is supported.
3. For each TestCase attached to the assignment:
     a. Send code + test case input to the isolated Code Runner.
     b. Capture actual output.
     c. Compare actual vs expected output (whitespace-normalized).
4. Weighted score = sum(weight of passed cases) / sum(all weights) * 100
5. Persist a Submission + one TestCaseResult per test case.
6. Trigger ml_engine.feature_engineering to refresh the student's
   feature vector for the assignment's topic (feeds Algorithms 2 & 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from assignments.models import Submission, TestCaseResult
from code_runner.sandbox import execute


def _normalize(text: str) -> str:
    """Whitespace-insensitive comparison: trims trailing newlines/spaces
    per line so cosmetic differences (trailing spaces, final newline)
    don't fail an otherwise-correct solution."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


@dataclass
class EvaluationOutcome:
    passed: int = 0
    total: int = 0
    score: float = 0.0
    status: str = Submission.Status.FAILED
    results: list = field(default_factory=list)


def evaluate_submission(submission: Submission) -> EvaluationOutcome:
    """Runs every TestCase for `submission.assignment` against
    `submission.source_code` and records the outcome."""
    submission.status = Submission.Status.RUNNING
    submission.save(update_fields=["status"])

    test_cases = list(submission.assignment.test_cases.all())
    total_weight = sum(tc.weight for tc in test_cases) or 1.0
    passed_weight = 0.0
    passed_count = 0
    had_error = False
    had_timeout = False
    total_time_ms = 0.0

    outcome = EvaluationOutcome(total=len(test_cases))

    for tc in test_cases:
        result = execute(
            submission.assignment.programming_language,
            submission.source_code,
            stdin_data=tc.input_data,
        )
        total_time_ms += result.execution_time_ms

        passed = False
        error_message = ""

        if result.timed_out:
            had_timeout = True
            error_message = "Timeout"
        elif result.exit_code != 0:
            had_error = True
            error_message = result.stderr
        else:
            passed = _normalize(result.stdout) == _normalize(tc.expected_output)
            if not passed:
                error_message = (
                    f"Expected: {tc.expected_output!r}\nGot: {result.stdout!r}"
                )

        if passed:
            passed_weight += tc.weight
            passed_count += 1

        TestCaseResult.objects.create(
            submission=submission,
            test_case=tc,
            passed=passed,
            actual_output=result.stdout,
            error_message=error_message,
        )
        outcome.results.append({"test_case_id": tc.id, "passed": passed})

    outcome.passed = passed_count
    outcome.score = round(passed_weight / total_weight * 100, 2) if test_cases else 0.0

    if had_timeout:
        outcome.status = Submission.Status.TIMEOUT
    elif had_error and passed_count == 0:
        outcome.status = Submission.Status.ERROR
    elif passed_count == len(test_cases) and test_cases:
        outcome.status = Submission.Status.PASSED
    elif passed_count > 0:
        outcome.status = Submission.Status.PARTIAL
    else:
        outcome.status = Submission.Status.FAILED

    submission.status = outcome.status
    submission.score = outcome.score
    submission.passed_test_cases = outcome.passed
    submission.total_test_cases = outcome.total
    submission.execution_time_ms = round(total_time_ms, 2)
    submission.graded_at = timezone.now()
    submission.save()

    # Feed Algorithms 2 & 3: refresh this student's feature vector for the
    # topic so weak-topic detection and recommendations stay current.
    from ml_engine.services.feature_engineering import build_feature_vector
    build_feature_vector(submission.student, submission.assignment.topic)

    from notifications.models import notify, Notification
    notify(
        submission.student.user,
        f"Your submission for '{submission.assignment.title}' was graded: {outcome.score:.0f}%",
        category=Notification.Category.GRADE,
        link=f"/submissions/{submission.pk}/",
    )

    return outcome
