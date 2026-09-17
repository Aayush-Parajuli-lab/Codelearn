"""
Recipient rules
================
Keeps messaging sensible for a school context instead of "any user can
DM any other user":

  - Admin        -> anyone
  - Teacher      -> students & parents in their own courses, other
                     teachers, and admins
  - Student      -> teachers of courses they're enrolled in, and admins
  - Parent       -> teachers of their children's courses, and admins

Group chats reuse the same allowed-recipient set — a teacher can only
start a group with people individually messageable.
"""
from django.db.models import Q

from accounts.models import User


def allowed_recipients(user):
    """Returns a queryset of Users `user` is allowed to start a
    conversation with (never includes `user` themself)."""
    if user.role == User.Role.ADMIN:
        return User.objects.exclude(pk=user.pk)

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)
        if not teacher:
            return User.objects.none()
        courses = teacher.courses.all()
        student_user_ids = User.objects.filter(
            student_profile__enrollments__course__in=courses
        ).values_list("pk", flat=True)
        parent_user_ids = User.objects.filter(
            parent_profile__children__enrollments__course__in=courses
        ).values_list("pk", flat=True)
        return User.objects.filter(
            Q(pk__in=student_user_ids)
            | Q(pk__in=parent_user_ids)
            | Q(role=User.Role.TEACHER)
            | Q(role=User.Role.ADMIN)
        ).exclude(pk=user.pk).distinct()

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)
        if not student:
            return User.objects.none()
        teacher_user_ids = User.objects.filter(
            teacher_profile__courses__enrollments__student=student
        ).values_list("pk", flat=True)
        return User.objects.filter(
            Q(pk__in=teacher_user_ids) | Q(role=User.Role.ADMIN)
        ).exclude(pk=user.pk).distinct()

    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)
        if not parent:
            return User.objects.none()
        teacher_user_ids = User.objects.filter(
            teacher_profile__courses__enrollments__student__in=parent.children.all()
        ).values_list("pk", flat=True)
        return User.objects.filter(
            Q(pk__in=teacher_user_ids) | Q(role=User.Role.ADMIN)
        ).exclude(pk=user.pk).distinct()

    return User.objects.none()


def can_message(user, other_user):
    return allowed_recipients(user).filter(pk=other_user.pk).exists()
