from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model. Every account in CodeLearn (Admin, Teacher,
    Student, Parent) is a User first, then linked to a role-specific
    profile (Student, Teacher, Parent) via a one-to-one relationship.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"
        PARENT = "PARENT", "Parent"

    class Theme(models.TextChoices):
        LIGHT = "LIGHT", "Light"
        DARK = "DARK", "Dark"
        SYSTEM = "SYSTEM", "Match system"

    role = models.CharField(max_length=10, choices=Role.choices)
    phone_number = models.CharField(max_length=20, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile_pictures/", blank=True, null=True
    )
    date_joined_platform = models.DateTimeField(auto_now_add=True)

    theme_preference = models.CharField(
        max_length=10, choices=Theme.choices, default=Theme.SYSTEM
    )
    email_notifications = models.BooleanField(
        default=True,
        help_text="Whether this user wants email notifications for new messages, "
                   "assignments, etc. (UI preference only — no email backend is "
                   "configured in this project yet.)",
    )

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class Teacher(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Student(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="student_profile"
    )
    roll_number = models.CharField(max_length=20, unique=True)
    school_class = models.ForeignKey(
        "academics.SchoolClass",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    enrollment_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Parent(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="parent_profile"
    )
    children = models.ManyToManyField(Student, related_name="parents", blank=True)
    occupation = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username
