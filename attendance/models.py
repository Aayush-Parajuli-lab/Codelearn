from django.db import models
from django.db.models import Count, Q


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"
        EXCUSED = "EXCUSED", "Excused"

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="attendance_records"
    )
    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PRESENT
    )
    marked_by = models.ForeignKey(
        "accounts.Teacher", on_delete=models.SET_NULL, null=True
    )

    class Meta:
        unique_together = ("student", "course", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} - {self.course} - {self.date} - {self.status}"

    @staticmethod
    def attendance_percentage(student, course=None):
        """Calculates: (Present classes / Total classes) * 100"""
        qs = AttendanceRecord.objects.filter(student=student)
        if course:
            qs = qs.filter(course=course)
        stats = qs.aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
        )
        if not stats["total"]:
            return 0.0
        return round(stats["present"] / stats["total"] * 100, 2)
