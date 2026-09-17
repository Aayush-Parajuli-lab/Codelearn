from django.db import models


class Quiz(models.Model):
    topic = models.ForeignKey(
        "academics.Topic", on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=150)
    time_limit_minutes = models.PositiveIntegerField(default=15)
    due_date = models.DateTimeField(
        null=True, blank=True,
        help_text="Optional — shown on the calendar view alongside assignment deadlines.",
    )
    created_by = models.ForeignKey(
        "accounts.Teacher", on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    class QuestionType(models.TextChoices):
        MCQ = "MCQ", "Multiple Choice"
        OUTPUT_PREDICTION = "OUTPUT", "Output Prediction"
        DEBUGGING = "DEBUG", "Debugging"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_type = models.CharField(max_length=10, choices=QuestionType.choices)
    prompt = models.TextField()
    code_snippet = models.TextField(blank=True)
    correct_answer = models.TextField()
    marks = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Q{self.pk}: {self.prompt[:50]}"


class AnswerOption(models.Model):
    """Used for MCQ-type questions."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    score = models.FloatField(default=0.0)
    total_marks = models.FloatField(default=0.0)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student} - {self.quiz.title}"

    @property
    def percentage(self):
        return (self.score / self.total_marks * 100) if self.total_marks else 0


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    response = models.TextField()
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Answer for attempt #{self.attempt_id} / question #{self.question_id}"
