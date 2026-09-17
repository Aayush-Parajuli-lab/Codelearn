from django.db import models


class Assignment(models.Model):
    topic = models.ForeignKey(
        "academics.Topic", on_delete=models.CASCADE, related_name="assignments"
    )
    title = models.CharField(max_length=150)
    description = models.TextField()
    instructions = models.TextField(blank=True)
    programming_language = models.CharField(
        max_length=10,
        choices=[("PYTHON", "Python"), ("C", "C"), ("JAVA", "Java")],
        default="PYTHON",
    )
    max_marks = models.PositiveIntegerField(default=100)
    deadline = models.DateTimeField()
    created_by = models.ForeignKey(
        "accounts.Teacher", on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class TestCase(models.Model):
    """Hidden or visible test case used by the automated evaluation engine."""

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="test_cases"
    )
    input_data = models.TextField(blank=True)
    expected_output = models.TextField()
    is_hidden = models.BooleanField(default=True)
    weight = models.FloatField(
        default=1.0, help_text="Relative weight of this test case in scoring"
    )

    def __str__(self):
        visibility = "hidden" if self.is_hidden else "visible"
        return f"TestCase #{self.pk} ({visibility}) - {self.assignment.title}"


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        PASSED = "PASSED", "Passed"
        PARTIAL = "PARTIAL", "Partially Passed"
        FAILED = "FAILED", "Failed"
        ERROR = "ERROR", "Compile/Runtime Error"
        TIMEOUT = "TIMEOUT", "Timeout"

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="submissions"
    )
    source_code = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    score = models.FloatField(default=0.0)
    passed_test_cases = models.PositiveIntegerField(default=0)
    total_test_cases = models.PositiveIntegerField(default=0)
    execution_time_ms = models.FloatField(null=True, blank=True)
    attempt_number = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.student} - {self.assignment.title} ({self.status})"

    @property
    def is_late(self):
        return self.submitted_at > self.assignment.deadline


class TestCaseResult(models.Model):
    """Result of running a single test case against a submission."""

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="test_results"
    )
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE)
    passed = models.BooleanField(default=False)
    actual_output = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"Result for submission #{self.submission_id} / test #{self.test_case_id}"
