from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    A single in-app notification for one user. Deliberately event-driven
    (created at the moment something real happens — a submission is
    graded, the classifier flags a topic weak) rather than a generic
    reminder system requiring a scheduler — this project has no
    Celery/cron set up, so anything time-based (e.g. "assignment due
    tomorrow") would need that infrastructure first. See README for
    where a scheduled job would plug in.
    """

    class Category(models.TextChoices):
        GRADE = "GRADE", "Grade posted"
        WEAK_TOPIC = "WEAK_TOPIC", "Weak topic flagged"
        MESSAGE = "MESSAGE", "New message"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.SYSTEM)
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, help_text="Relative URL to navigate to")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.message[:50]}"


def notify(user, message, category=Notification.Category.SYSTEM, link=""):
    """Small helper so call sites read as one line: notify(student, '...')."""
    return Notification.objects.create(user=user, message=message, category=category, link=link)
