from django.db import models


class SchoolClass(models.Model):
    """e.g. 'BCA 5th Sem', 'BSc CSIT 3rd Sem' — a cohort of students."""

    name = models.CharField(max_length=100)
    section = models.CharField(max_length=20, blank=True)
    academic_year = models.CharField(max_length=20)

    class Meta:
        verbose_name_plural = "School Classes"

    def __str__(self):
        return f"{self.name} {self.section}".strip()


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name


class Course(models.Model):
    """A course maps a Subject to a set of programming languages / topics,
    taught by a Teacher, to one or more SchoolClasses."""

    LANGUAGE_CHOICES = [
        ("PYTHON", "Python"),
        ("C", "C"),
        ("JAVA", "Java"),
    ]

    title = models.CharField(max_length=150)
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="courses"
    )
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.SET_NULL, null=True, related_name="courses"
    )
    school_classes = models.ManyToManyField(SchoolClass, related_name="courses")
    programming_language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default="PYTHON"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student} -> {self.course}"


class Topic(models.Model):
    """A topic within a course (e.g. 'Loops', 'Functions', 'Arrays').
    Used as the unit of measurement for the performance/recommendation
    algorithms."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="topics"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} ({self.course.title})"


class ForumPost(models.Model):
    """A discussion post under a Topic. Two levels only: a top-level
    question/post, and flat replies to it (no nested reply-to-reply
    threading) — simple enough for a class Q&A board without needing a
    tree-rendering template."""

    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="forum_posts"
    )
    author = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="forum_posts"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author} on {self.topic}: {self.body[:40]}"


class Lesson(models.Model):
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(max_length=150)
    content = models.TextField(help_text="Lesson text / markdown content")
    example_code = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title
