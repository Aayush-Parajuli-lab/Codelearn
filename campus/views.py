import csv

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User, Student, Teacher, Parent
from academics.models import Course, SchoolClass, Subject, Topic, Lesson, Enrollment, ForumPost
from assignments.models import Assignment, Submission, TestCase
from attendance.models import AttendanceRecord
from ml_engine.models import StudentTopicFeature, Recommendation
from campus.forms import (
    UserCreateForm, generate_temp_password, ProfileUpdateForm, ThemeForm,
    NotificationsForm, CSVImportForm, QuizCreateForm, QuestionCreateForm,
    AnswerOptionCreateForm, SchoolClassCreateForm, SubjectCreateForm,
    CourseCreateForm, TopicCreateForm, LessonCreateForm,
    AssignmentCreateForm, TestCaseCreateForm,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from messaging.avatars import avatar_context

REMEMBER_ME_DAYS = 30

NAV_URLS = {
    "Dashboard": "dashboard",
    "Students": "student_list",
    "Teachers": "teacher_list",
    "Courses": "course_list",
    "Reports": "reports",
    "Add user": "user_create",
    "My courses": "course_list",
    "Assignments": "assignment_list",
    "Attendance": "attendance_view",
    "Submissions": "submission_list",
    "Progress": "progress_view",
    "My children": "children_list",
    "Academic performance": "progress_view",
    "Messages": "inbox",
    "Quizzes": "quiz_list",
    "Manage quizzes": "quiz_manage_list",
    "Calendar": "calendar_view",
}


def _nav_for(request, active):
    """Builds the sidebar nav list per role, marking the active item and
    resolving each label to its real URL. The "Messages" item also gets
    a `badge` count of total unread messages across all conversations."""
    role = request.user.role
    items_by_role = {
        User.Role.ADMIN: ["Dashboard", "Students", "Teachers", "Courses", "Manage quizzes", "Reports", "Add user", "Calendar", "Messages"],
        User.Role.TEACHER: ["Dashboard", "My courses", "Assignments", "Manage quizzes", "Attendance", "Submissions", "Calendar", "Messages"],
        User.Role.STUDENT: ["Dashboard", "My courses", "Assignments", "Quizzes", "Progress", "Attendance", "Calendar", "Messages"],
        User.Role.PARENT: ["Dashboard", "My children", "Attendance", "Academic performance", "Calendar", "Messages"],
    }
    from django.urls import reverse

    unread_total = None
    if "Messages" in items_by_role.get(role, []):
        from messaging.models import Conversation
        unread_total = sum(
            c.unread_count_for(request.user)
            for c in Conversation.objects.filter(participants=request.user)
        ) or None

    nav = []
    for label in items_by_role.get(role, []):
        item = {"label": label, "url": reverse(NAV_URLS[label]), "active": label == active}
        if label == "Messages" and unread_total:
            item["badge"] = unread_total
        nav.append(item)
    return nav


def _role_required(user, *roles):
    return user.is_authenticated and user.role in roles


# ---------------------------------------------------------------------------
# Dashboards (one per role)
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    role = request.user.role
    if role == User.Role.ADMIN:
        return admin_dashboard(request)
    if role == User.Role.TEACHER:
        return teacher_dashboard(request)
    if role == User.Role.STUDENT:
        return student_dashboard(request)
    if role == User.Role.PARENT:
        return parent_dashboard(request)
    return render(request, "campus/no_role.html")


@login_required
def admin_dashboard(request):
    top_courses = Course.objects.annotate(student_count=Count("enrollments")).order_by("-student_count")[:5]
    recent_submissions = Submission.objects.select_related("student__user", "assignment").order_by("-submitted_at")[:6]

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "total_students": Student.objects.count(),
        "total_teachers": Teacher.objects.count(),
        "total_parents": Parent.objects.count(),
        "total_courses": Course.objects.count(),
        "top_courses": top_courses,
        "recent_submissions": recent_submissions,
    }
    return render(request, "campus/admin_dashboard.html", context)


@login_required
def teacher_dashboard(request):
    teacher = getattr(request.user, "teacher_profile", None)
    courses = Course.objects.filter(teacher=teacher) if teacher else Course.objects.none()
    student_ids = Student.objects.filter(enrollments__course__in=courses).distinct()
    assignments = Assignment.objects.filter(topic__course__in=courses)
    pending_submissions = Submission.objects.filter(assignment__in=assignments, status=Submission.Status.PENDING).count()
    recent_submissions = (
        Submission.objects.filter(assignment__in=assignments)
        .select_related("student__user", "assignment").order_by("-submitted_at")[:6]
    )
    upcoming = assignments.filter(deadline__gte=timezone.now()).order_by("deadline")[:5]
    weak_topic_alerts = (
        StudentTopicFeature.objects.filter(topic__course__in=courses, is_weak=True)
        .select_related("student__user", "topic").order_by("-weak_probability")[:6]
    )

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "my_courses_count": courses.count(),
        "my_students_count": student_ids.count(),
        "pending_submissions": pending_submissions,
        "recent_submissions": recent_submissions,
        "upcoming_assignments": upcoming,
        "weak_topic_alerts": weak_topic_alerts,
    }
    return render(request, "campus/teacher_dashboard.html", context)


@login_required
def student_dashboard(request):
    student = getattr(request.user, "student_profile", None)
    enrollments = student.enrollments.select_related("course") if student else Student.objects.none()
    submissions = (
        Submission.objects.filter(student=student).select_related("assignment").order_by("-submitted_at")[:6]
        if student else Submission.objects.none()
    )
    avg_score = Submission.objects.filter(student=student).aggregate(avg=Avg("score"))["avg"] if student else None
    attendance_pct = AttendanceRecord.attendance_percentage(student) if student else 0
    topic_features = (
        StudentTopicFeature.objects.filter(student=student).select_related("topic") if student
        else StudentTopicFeature.objects.none()
    )
    recommendations = (
        Recommendation.objects.filter(student=student, is_active=True).select_related("topic", "recommended_lesson")
        if student else Recommendation.objects.none()
    )
    upcoming_assignments = (
        Assignment.objects.filter(topic__course__enrollments__student=student, deadline__gte=timezone.now()).order_by("deadline")[:5]
        if student else Assignment.objects.none()
    )

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "courses_enrolled": enrollments.count(),
        "assignments_done": submissions.count(),
        "average_score": round(avg_score, 1) if avg_score else 0,
        "attendance_pct": attendance_pct,
        "recent_submissions": submissions,
        "topic_features": topic_features,
        "recommendations": recommendations,
        "upcoming_assignments": upcoming_assignments,
    }
    return render(request, "campus/student_dashboard.html", context)


@login_required
def parent_dashboard(request):
    parent = getattr(request.user, "parent_profile", None)
    children = list(parent.children.select_related("user").all()) if parent else []
    child = _selected_child(request, children)

    topic_features = (
        StudentTopicFeature.objects.filter(student=child).select_related("topic") if child
        else StudentTopicFeature.objects.none()
    )
    attendance_pct = AttendanceRecord.attendance_percentage(child) if child else 0
    submissions = (
        Submission.objects.filter(student=child).select_related("assignment").order_by("-submitted_at")[:5]
        if child else Submission.objects.none()
    )
    notifications = []
    if child:
        weak = StudentTopicFeature.objects.filter(student=child, is_weak=True).select_related("topic")
        name = child.user.get_full_name() or child.user.username
        notifications = [f"{name} needs extra support in {f.topic.name}" for f in weak]

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "children": children,
        "child": child,
        "topic_features": topic_features,
        "attendance_pct": attendance_pct,
        "recent_submissions": submissions,
        "notifications": notifications,
    }
    return render(request, "campus/parent_dashboard.html", context)


def _selected_child(request, children):
    if not children:
        return None
    selected_id = request.GET.get("child")
    return next((c for c in children if str(c.id) == selected_id), children[0])


def _paginate(request, queryset_or_list, per_page=15):
    """Paginates a queryset/list using the ?page= query param, and
    returns (page_obj, extra_qs) where extra_qs is the current query
    string with `page` stripped out — so pagination links can preserve
    search/filter params: `?page=N&{{ extra_qs }}`."""
    from django.core.paginator import Paginator

    paginator = Paginator(queryset_or_list, per_page)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    qs = request.GET.copy()
    qs.pop("page", None)
    extra_qs = qs.urlencode()

    return page_obj, extra_qs


def _csv_response(filename, header, rows):
    """Builds a downloadable CSV HttpResponse from a header row and an
    iterable of row tuples/lists."""
    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


# ---------------------------------------------------------------------------
# Admin sub-pages
# ---------------------------------------------------------------------------

def _student_rows(request):
    """Shared by student_list and student_export: applies the ?q= search
    filter and builds per-student summary rows."""
    query = request.GET.get("q", "").strip()
    students = Student.objects.select_related("user", "school_class").order_by(
        "user__first_name", "user__username"
    )
    if query:
        students = students.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(roll_number__icontains=query)
        )

    rows = []
    for s in students:
        avg_score = Submission.objects.filter(student=s).aggregate(avg=Avg("score"))["avg"]
        rows.append({
            "student": s,
            "avg_score": round(avg_score, 1) if avg_score else None,
            "attendance_pct": AttendanceRecord.attendance_percentage(s),
        })
    return query, students, rows


@login_required
def student_list(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    query, students, rows = _student_rows(request)
    page_obj, extra_qs = _paginate(request, rows, per_page=15)

    context = {
        "nav_items": _nav_for(request, "Students"),
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "extra_qs": extra_qs,
        "query": query,
        "total_count": students.count(),
    }
    return render(request, "campus/student_list.html", context)


@login_required
def student_export(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    _, _, rows = _student_rows(request)
    csv_rows = [
        (
            r["student"].user.get_full_name() or r["student"].user.username,
            r["student"].roll_number,
            str(r["student"].school_class) if r["student"].school_class else "",
            r["avg_score"] if r["avg_score"] is not None else "",
            r["attendance_pct"],
        )
        for r in rows
    ]
    return _csv_response(
        "students.csv",
        ["Name", "Roll number", "Class", "Average score (%)", "Attendance (%)"],
        csv_rows,
    )


@login_required
def teacher_list(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    query = request.GET.get("q", "").strip()
    teachers = Teacher.objects.select_related("user").annotate(
        course_count=Count("courses")
    ).order_by("user__first_name")
    if query:
        teachers = teachers.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(employee_id__icontains=query)
            | Q(department__icontains=query)
        )

    page_obj, extra_qs = _paginate(request, teachers, per_page=15)

    context = {
        "nav_items": _nav_for(request, "Teachers"),
        "page_obj": page_obj,
        "teachers": page_obj.object_list,
        "extra_qs": extra_qs,
        "query": query,
        "total_count": teachers.count(),
    }
    return render(request, "campus/teacher_list.html", context)


@login_required
def reports(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    total_features = StudentTopicFeature.objects.count()
    weak_count = StudentTopicFeature.objects.filter(is_weak=True).count()
    avg_attendance = None
    students = Student.objects.all()
    pct_list = [AttendanceRecord.attendance_percentage(s) for s in students]
    pct_list = [p for p in pct_list if p is not None]
    if pct_list:
        avg_attendance = round(sum(pct_list) / len(pct_list), 1)

    by_class = (
        SchoolClass.objects.annotate(student_count=Count("students")).order_by("name")
    )

    submission_status_counts = (
        Submission.objects.values("status").annotate(count=Count("id")).order_by("-count")
    )

    context = {
        "nav_items": _nav_for(request, "Reports"),
        "total_features": total_features,
        "weak_count": weak_count,
        "weak_pct": round(weak_count / total_features * 100, 1) if total_features else 0,
        "avg_attendance": avg_attendance,
        "by_class": by_class,
        "submission_status_counts": submission_status_counts,
    }
    return render(request, "campus/reports.html", context)


@login_required
def reports_export(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    from django.http import HttpResponse

    by_class = SchoolClass.objects.annotate(student_count=Count("students")).order_by("name")
    submission_status_counts = (
        Submission.objects.values("status").annotate(count=Count("id")).order_by("-count")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="reports.csv"'
    writer = csv.writer(response)

    writer.writerow(["Students by class"])
    writer.writerow(["Class", "Students"])
    for c in by_class:
        writer.writerow([str(c), c.student_count])

    writer.writerow([])
    writer.writerow(["Submissions by status"])
    writer.writerow(["Status", "Count"])
    for row in submission_status_counts:
        writer.writerow([row["status"], row["count"]])

    return response


@login_required
def user_create(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    generated_password = None

    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            password = data["password"] or generate_temp_password()
            if not data["password"]:
                generated_password = password

            user = User.objects.create_user(
                username=data["username"],
                password=password,
                first_name=data["first_name"],
                last_name=data["last_name"],
                email=data["email"],
                phone_number=data["phone_number"],
                role=data["role"],
            )

            if data["role"] == User.Role.TEACHER:
                Teacher.objects.create(
                    user=user,
                    employee_id=data["employee_id"],
                    department=data["department"],
                )
            elif data["role"] == User.Role.STUDENT:
                Student.objects.create(
                    user=user,
                    roll_number=data["roll_number"],
                    school_class=data["school_class"],
                )
            elif data["role"] == User.Role.PARENT:
                parent = Parent.objects.create(user=user, occupation=data["occupation"])
                if data["children"]:
                    parent.children.set(data["children"])
            # ADMIN role needs no extra profile row.

            if generated_password:
                messages.success(
                    request,
                    f"Account '{user.username}' created. Temporary password: {generated_password} "
                    "— share this with them securely; they can change it after signing in.",
                )
            else:
                messages.success(request, f"Account '{user.username}' created.")

            return redirect("user_create")
    else:
        form = UserCreateForm()

    context = {
        "nav_items": _nav_for(request, "Add user"),
        "form": form,
    }
    return render(request, "campus/user_create.html", context)


def _create_account_from_row(row: dict):
    """
    Creates one account from a raw CSV row (dict of strings). Used by
    the bulk importer. Returns (username_or_None, generated_password_or_None,
    error_or_None) — exactly one of the first and third is set.
    """
    role = (row.get("role") or "").strip().upper()
    username = (row.get("username") or "").strip()
    first_name = (row.get("first_name") or "").strip()

    if role not in User.Role.values:
        return None, None, f"Invalid role '{role}' (must be one of {', '.join(User.Role.values)})"
    if not username:
        return None, None, "Missing username"
    if User.objects.filter(username=username).exists():
        return None, None, f"Username '{username}' already exists"
    if not first_name:
        return None, None, "Missing first_name"

    if role == User.Role.TEACHER and not (row.get("employee_id") or "").strip():
        return None, None, "Teachers require employee_id"
    if role == User.Role.STUDENT and not (row.get("roll_number") or "").strip():
        return None, None, "Students require roll_number"

    password = (row.get("password") or "").strip()
    generated_password = None
    if not password:
        password = generate_temp_password()
        generated_password = password
    else:
        try:
            validate_password(password)
        except ValidationError as e:
            return None, None, f"Password error: {'; '.join(e.messages)}"

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=(row.get("last_name") or "").strip(),
        email=(row.get("email") or "").strip(),
        phone_number=(row.get("phone_number") or "").strip(),
        role=role,
    )

    if role == User.Role.TEACHER:
        Teacher.objects.create(
            user=user,
            employee_id=(row.get("employee_id") or "").strip(),
            department=(row.get("department") or "").strip(),
        )
    elif role == User.Role.STUDENT:
        school_class = None
        class_name = (row.get("school_class") or "").strip()
        if class_name:
            school_class = SchoolClass.objects.filter(name__iexact=class_name).first()
        Student.objects.create(
            user=user,
            roll_number=(row.get("roll_number") or "").strip(),
            school_class=school_class,
        )
    elif role == User.Role.PARENT:
        parent = Parent.objects.create(user=user, occupation=(row.get("occupation") or "").strip())
        roll_numbers = [r.strip() for r in (row.get("children") or "").split(";") if r.strip()]
        if roll_numbers:
            children = Student.objects.filter(roll_number__in=roll_numbers)
            parent.children.set(children)

    return username, generated_password, None


@login_required
def user_import_template(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    return _csv_response(
        "codelearn_import_template.csv",
        ["role", "username", "first_name", "last_name", "email", "phone_number",
         "password", "employee_id", "department", "roll_number", "school_class",
         "occupation", "children"],
        [
            ["STUDENT", "jdoe1", "Jane", "Doe", "", "", "", "", "", "S100", "BCA 5th Sem", "", ""],
            ["TEACHER", "asmith", "Alex", "Smith", "", "", "", "T100", "Computer Science", "", "", "", ""],
        ],
    )


@login_required
def user_import(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    results = None

    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            import io

            f = form.cleaned_data["csv_file"]
            decoded = io.TextIOWrapper(f.file, encoding="utf-8-sig")
            reader = csv.DictReader(decoded)

            results = []
            for i, row in enumerate(reader, start=2):  # row 1 is the header
                username, generated_password, error = _create_account_from_row(row)
                results.append({
                    "row": i,
                    "username": username or row.get("username", ""),
                    "ok": error is None,
                    "message": error or (
                        f"Created. Temporary password: {generated_password}"
                        if generated_password else "Created."
                    ),
                })
    else:
        form = CSVImportForm()

    context = {
        "nav_items": _nav_for(request, "Add user"),
        "form": form,
        "results": results,
    }
    return render(request, "campus/user_import.html", context)


# ---------------------------------------------------------------------------
# Courses (Admin sees all, Teacher sees their own)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Course / class / subject creation (Admin) — previously /admin/-only
# ---------------------------------------------------------------------------

@login_required
def class_subject_manage(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    class_form = SchoolClassCreateForm()
    subject_form = SubjectCreateForm()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_class":
            class_form = SchoolClassCreateForm(request.POST)
            if class_form.is_valid():
                class_form.save()
                messages.success(request, "Class added.")
                return redirect("class_subject_manage")

        elif action == "delete_class":
            SchoolClass.objects.filter(pk=request.POST.get("class_id")).delete()
            return redirect("class_subject_manage")

        elif action == "add_subject":
            subject_form = SubjectCreateForm(request.POST)
            if subject_form.is_valid():
                subject_form.save()
                messages.success(request, "Subject added.")
                return redirect("class_subject_manage")

        elif action == "delete_subject":
            Subject.objects.filter(pk=request.POST.get("subject_id")).delete()
            return redirect("class_subject_manage")

    context = {
        "nav_items": _nav_for(request, "Courses"),
        "classes": SchoolClass.objects.all(),
        "subjects": Subject.objects.all(),
        "class_form": class_form,
        "subject_form": subject_form,
    }
    return render(request, "campus/class_subject_manage.html", context)


@login_required
def course_create(request):
    if not _role_required(request.user, User.Role.ADMIN):
        return redirect("dashboard")

    if request.method == "POST":
        form = CourseCreateForm(request.POST)
        if form.is_valid():
            course = form.save()
            messages.success(request, f"Course \u201c{course.title}\u201d created \u2014 now add some topics.")
            return redirect("course_topics", pk=course.pk)
    else:
        form = CourseCreateForm()

    no_subjects = not Subject.objects.exists()
    no_teachers = not Teacher.objects.exists()
    context = {
        "nav_items": _nav_for(request, "Courses"),
        "form": form,
        "no_subjects": no_subjects,
        "no_teachers": no_teachers,
    }
    return render(request, "campus/course_create.html", context)


@login_required
def course_list(request):
    role = request.user.role
    if role == User.Role.ADMIN:
        courses = Course.objects.select_related("subject", "teacher__user").annotate(student_count=Count("enrollments"))
    elif role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        courses = Course.objects.filter(teacher=teacher).annotate(student_count=Count("enrollments"))
    elif role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        courses = Course.objects.filter(enrollments__student=student).annotate(student_count=Count("enrollments"))
    else:
        return redirect("dashboard")

    active_label = "Courses" if role == User.Role.ADMIN else "My courses"
    context = {"nav_items": _nav_for(request, active_label), "courses": courses, "role": role}
    return render(request, "campus/course_list.html", context)


def _user_can_access_course(user, course):
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TEACHER:
        return getattr(user, "teacher_profile", None) and course.teacher_id == user.teacher_profile.id
    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)
        return student is not None and course.enrollments.filter(student=student).exists()
    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)
        return parent is not None and course.enrollments.filter(student__in=parent.children.all()).exists()
    return False


@login_required
def course_roster(request, pk):
    course = get_object_or_404(Course, pk=pk)

    if not _role_required(request.user, User.Role.ADMIN, User.Role.TEACHER):
        return redirect("dashboard")
    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None or course.teacher_id != teacher.id:
            return redirect("dashboard")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enroll":
            student = Student.objects.filter(pk=request.POST.get("student_id")).first()
            if student is not None:
                Enrollment.objects.get_or_create(student=student, course=course)
                messages.success(request, f"{student.user.get_full_name() or student.user.username} enrolled.")
            return redirect("course_roster", pk=course.pk)
        elif action == "unenroll":
            Enrollment.objects.filter(course=course, student_id=request.POST.get("student_id")).delete()
            messages.success(request, "Student removed from the course.")
            return redirect("course_roster", pk=course.pk)

    enrolled_ids = course.enrollments.values_list("student_id", flat=True)
    enrolled_students = Student.objects.filter(id__in=enrolled_ids).select_related("user").order_by("user__first_name")
    available_students = (
        Student.objects.exclude(id__in=enrolled_ids).select_related("user").order_by("user__first_name")
    )

    active_label = "Courses" if request.user.role == User.Role.ADMIN else "My courses"
    context = {
        "nav_items": _nav_for(request, active_label),
        "course": course,
        "enrolled_students": enrolled_students,
        "available_students": available_students,
    }
    return render(request, "campus/course_roster.html", context)


@login_required
def course_topics(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not _user_can_access_course(request.user, course):
        return redirect("dashboard")

    can_manage = request.user.role in (User.Role.ADMIN, User.Role.TEACHER)
    topic_form = TopicCreateForm()

    if request.method == "POST" and can_manage:
        action = request.POST.get("action")
        if action == "add_topic":
            topic_form = TopicCreateForm(request.POST)
            if topic_form.is_valid():
                topic = topic_form.save(commit=False)
                topic.course = course
                topic.save()
                messages.success(request, f"Topic \u201c{topic.name}\u201d added.")
                return redirect("course_topics", pk=course.pk)
        elif action == "delete_topic":
            Topic.objects.filter(pk=request.POST.get("topic_id"), course=course).delete()
            messages.success(request, "Topic removed.")
            return redirect("course_topics", pk=course.pk)

    topics = course.topics.annotate(
        lesson_count=Count("lessons", distinct=True),
        post_count=Count("forum_posts", distinct=True),
    )
    active_label = "Courses" if request.user.role == User.Role.ADMIN else "My courses"
    context = {
        "nav_items": _nav_for(request, active_label),
        "course": course,
        "topics": topics,
        "can_manage": can_manage,
        "topic_form": topic_form,
    }
    return render(request, "campus/course_topics.html", context)


@login_required
def topic_lessons(request, pk):
    topic = get_object_or_404(Topic.objects.select_related("course"), pk=pk)
    if not _user_can_access_course(request.user, topic.course):
        return redirect("dashboard")

    can_manage = request.user.role in (User.Role.ADMIN, User.Role.TEACHER)
    lesson_form = LessonCreateForm()

    if request.method == "POST" and can_manage:
        action = request.POST.get("action")
        if action == "add_lesson":
            lesson_form = LessonCreateForm(request.POST)
            if lesson_form.is_valid():
                lesson = lesson_form.save(commit=False)
                lesson.topic = topic
                lesson.save()
                messages.success(request, f"Lesson \u201c{lesson.title}\u201d added.")
                return redirect("topic_lessons", pk=topic.pk)
        elif action == "delete_lesson":
            Lesson.objects.filter(pk=request.POST.get("lesson_id"), topic=topic).delete()
            messages.success(request, "Lesson removed.")
            return redirect("topic_lessons", pk=topic.pk)

    lessons = topic.lessons.all()
    active_label = "Courses" if request.user.role == User.Role.ADMIN else "My courses"
    context = {
        "nav_items": _nav_for(request, active_label),
        "topic": topic,
        "lessons": lessons,
        "can_manage": can_manage,
        "lesson_form": lesson_form,
    }
    return render(request, "campus/topic_lessons.html", context)


@login_required
def lesson_detail(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related("topic__course"), pk=pk)
    if not _user_can_access_course(request.user, lesson.topic.course):
        return redirect("dashboard")

    active_label = "Courses" if request.user.role == User.Role.ADMIN else "My courses"
    context = {"nav_items": _nav_for(request, active_label), "lesson": lesson}
    return render(request, "campus/lesson_detail.html", context)


@login_required
def topic_forum(request, pk):
    topic = get_object_or_404(Topic.objects.select_related("course"), pk=pk)
    if not _user_can_access_course(request.user, topic.course):
        return redirect("dashboard")

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        parent_id = request.POST.get("parent_id")
        if body:
            ForumPost.objects.create(
                topic=topic, author=request.user, body=body,
                parent_id=parent_id if parent_id else None,
            )
        return redirect("topic_forum", pk=topic.pk)

    posts = (
        topic.forum_posts.filter(parent__isnull=True)
        .select_related("author")
        .prefetch_related("replies__author")
    )
    active_label = "Courses" if request.user.role == User.Role.ADMIN else "My courses"
    context = {"nav_items": _nav_for(request, active_label), "topic": topic, "posts": posts}
    return render(request, "campus/topic_forum.html", context)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

@login_required
def assignment_create(request):
    if not _role_required(request.user, User.Role.TEACHER, User.Role.ADMIN):
        return redirect("dashboard")

    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        topic_qs = Topic.objects.filter(course__teacher=teacher).select_related("course")
    else:
        teacher = None
        topic_qs = Topic.objects.select_related("course").all()

    if request.method == "POST":
        form = AssignmentCreateForm(request.POST, topic_queryset=topic_qs)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.created_by = teacher
            assignment.save()
            messages.success(request, f"Assignment \u201c{assignment.title}\u201d created \u2014 now add some test cases.")
            return redirect("assignment_detail", pk=assignment.pk)
    else:
        form = AssignmentCreateForm(topic_queryset=topic_qs)

    context = {"nav_items": _nav_for(request, "Assignments"), "form": form}
    return render(request, "campus/assignment_create.html", context)


@login_required
def assignment_list(request):
    role = request.user.role
    if role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        courses = Course.objects.filter(teacher=teacher)
        assignments = (
            Assignment.objects.filter(topic__course__in=courses)
            .select_related("topic__course")
            .annotate(submission_count=Count("submissions"))
            .order_by("deadline")
        )
    elif role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        assignments = (
            Assignment.objects.filter(topic__course__enrollments__student=student)
            .select_related("topic__course").order_by("deadline")
        )
        my_submissions = {
            s.assignment_id: s for s in Submission.objects.filter(student=student).order_by("-submitted_at")
        }
        rows = [{"assignment": a, "submission": my_submissions.get(a.id)} for a in assignments]
        context = {"nav_items": _nav_for(request, "Assignments"), "rows": rows}
        return render(request, "campus/assignment_list_student.html", context)
    else:
        return redirect("dashboard")

    context = {"nav_items": _nav_for(request, "Assignments"), "assignments": assignments}
    return render(request, "campus/assignment_list_teacher.html", context)


def _assignment_manage_access(user, assignment):
    """Teachers may only manage test cases on their own courses' assignments; admins may manage any."""
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)
        return teacher is not None and assignment.topic.course.teacher_id == teacher.id
    return False


@login_required
def assignment_detail(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related("topic__course"), pk=pk)
    role = request.user.role

    if role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        my_submissions = Submission.objects.filter(assignment=assignment, student=student).order_by("-attempt_number")
        context = {
            "nav_items": _nav_for(request, "Assignments"),
            "assignment": assignment,
            "test_cases": assignment.test_cases.filter(is_hidden=False),
            "my_submissions": my_submissions,
        }
        return render(request, "campus/assignment_detail_student.html", context)

    can_manage = _assignment_manage_access(request.user, assignment)
    test_case_form = TestCaseCreateForm()

    if request.method == "POST" and can_manage:
        action = request.POST.get("action")
        if action == "add_test_case":
            test_case_form = TestCaseCreateForm(request.POST)
            if test_case_form.is_valid():
                tc = test_case_form.save(commit=False)
                tc.assignment = assignment
                tc.save()
                messages.success(request, "Test case added.")
                return redirect("assignment_detail", pk=assignment.pk)
            messages.error(request, "Couldn\u2019t add that test case \u2014 expected output is required.")
        elif action == "delete_test_case":
            TestCase.objects.filter(pk=request.POST.get("test_case_id"), assignment=assignment).delete()
            messages.success(request, "Test case removed.")
            return redirect("assignment_detail", pk=assignment.pk)

    submissions = (
        Submission.objects.filter(assignment=assignment).select_related("student__user").order_by("-submitted_at")
    )
    active = "Assignments" if role == User.Role.TEACHER else "Dashboard"
    context = {
        "nav_items": _nav_for(request, active),
        "assignment": assignment,
        "test_cases": assignment.test_cases.all(),
        "submissions": submissions,
        "can_manage": can_manage,
        "test_case_form": test_case_form,
    }
    return render(request, "campus/assignment_detail_teacher.html", context)


@login_required
def plagiarism_check(request, pk):
    if not _role_required(request.user, User.Role.TEACHER, User.Role.ADMIN):
        return redirect("dashboard")

    from code_runner.plagiarism import find_similar_pairs

    assignment = get_object_or_404(Assignment.objects.select_related("topic__course"), pk=pk)
    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        if assignment.topic.course.teacher_id != getattr(teacher, "id", None):
            return redirect("dashboard")

    pairs = find_similar_pairs(assignment)

    context = {
        "nav_items": _nav_for(request, "Assignments"),
        "assignment": assignment,
        "pairs": pairs,
    }
    return render(request, "campus/plagiarism_check.html", context)


STARTER_CODE = {
    "PYTHON": "# Write your solution below\n",
    "C": "#include <stdio.h>\n\nint main(void) {\n    // Write your solution below\n    return 0;\n}\n",
    "JAVA": "public class Main {\n    public static void main(String[] args) {\n        // Write your solution below\n    }\n}\n",
}


@login_required
def assignment_submit(request, pk):
    if request.user.role != User.Role.STUDENT:
        return redirect("assignment_detail", pk=pk)

    assignment = get_object_or_404(Assignment.objects.select_related("topic__course"), pk=pk)
    student = request.user.student_profile

    if request.method == "POST":
        source_code = request.POST.get("source_code", "")
        prior_attempts = Submission.objects.filter(assignment=assignment, student=student).count()

        submission = Submission.objects.create(
            assignment=assignment,
            student=student,
            source_code=source_code,
            attempt_number=prior_attempts + 1,
        )

        from code_runner.evaluator import evaluate_submission
        evaluate_submission(submission)

        return redirect("submission_detail", pk=submission.pk)

    last_submission = (
        Submission.objects.filter(assignment=assignment, student=student).order_by("-attempt_number").first()
    )
    starter = last_submission.source_code if last_submission else STARTER_CODE.get(
        assignment.programming_language, ""
    )

    context = {
        "nav_items": _nav_for(request, "Assignments"),
        "assignment": assignment,
        "test_cases": assignment.test_cases.filter(is_hidden=False),
        "starter_code": starter,
    }
    return render(request, "campus/assignment_submit.html", context)


# ---------------------------------------------------------------------------
# Submissions (teacher review)
# ---------------------------------------------------------------------------

@login_required
def submission_list(request):
    if not _role_required(request.user, User.Role.TEACHER):
        return redirect("dashboard")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    teacher = getattr(request.user, "teacher_profile", None)
    courses = Course.objects.filter(teacher=teacher)
    submissions = (
        Submission.objects.filter(assignment__topic__course__in=courses)
        .select_related("student__user", "assignment").order_by("-submitted_at")
    )
    if query:
        submissions = submissions.filter(
            Q(student__user__first_name__icontains=query)
            | Q(student__user__last_name__icontains=query)
            | Q(student__user__username__icontains=query)
            | Q(assignment__title__icontains=query)
        )
    if status:
        submissions = submissions.filter(status=status)

    page_obj, extra_qs = _paginate(request, submissions, per_page=20)

    context = {
        "nav_items": _nav_for(request, "Submissions"),
        "page_obj": page_obj,
        "submissions": page_obj.object_list,
        "extra_qs": extra_qs,
        "query": query,
        "status": status,
        "status_choices": Submission.Status.choices,
        "total_count": submissions.count(),
    }
    return render(request, "campus/submission_list.html", context)


@login_required
def submission_detail(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related("student__user", "assignment"), pk=pk
    )
    role = request.user.role
    if role == User.Role.STUDENT and submission.student.user_id != request.user.id:
        return redirect("dashboard")

    results = submission.test_results.select_related("test_case").all()
    active = "Submissions" if role == User.Role.TEACHER else "Assignments"
    context = {
        "nav_items": _nav_for(request, active),
        "submission": submission,
        "results": results,
    }
    return render(request, "campus/submission_detail.html", context)


# ---------------------------------------------------------------------------
# Attendance (teacher marks, student/parent/admin view)
# ---------------------------------------------------------------------------

@login_required
def attendance_view(request):
    role = request.user.role

    if role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        courses = Course.objects.filter(teacher=teacher)
        course_id = request.GET.get("course") or (courses.first().id if courses.exists() else None)
        course = courses.filter(id=course_id).first()

        roster = []
        if course:
            today = timezone.now().date()
            existing = {
                r.student_id: r.status
                for r in AttendanceRecord.objects.filter(course=course, date=today)
            }
            students = Student.objects.filter(enrollments__course=course).select_related("user")
            for s in students:
                roster.append({
                    "student": s,
                    "current_status": existing.get(s.id, "PRESENT"),
                    "attendance_pct": AttendanceRecord.attendance_percentage(s, course=course),
                })

        context = {
            "nav_items": _nav_for(request, "Attendance"),
            "courses": courses,
            "course": course,
            "roster": roster,
            "today": timezone.now().date(),
            "status_choices": AttendanceRecord.Status.choices,
        }
        return render(request, "campus/attendance_teacher.html", context)

    if role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        records = AttendanceRecord.objects.filter(student=student).select_related("course").order_by("-date")[:30]
        context = {
            "nav_items": _nav_for(request, "Attendance"),
            "records": records,
            "attendance_pct": AttendanceRecord.attendance_percentage(student),
        }
        return render(request, "campus/attendance_student.html", context)

    if role == User.Role.PARENT:
        parent = getattr(request.user, "parent_profile", None)
        children = list(parent.children.select_related("user").all()) if parent else []
        child = _selected_child(request, children)
        records = (
            AttendanceRecord.objects.filter(student=child).select_related("course").order_by("-date")[:30]
            if child else AttendanceRecord.objects.none()
        )
        context = {
            "nav_items": _nav_for(request, "Attendance"),
            "children": children,
            "child": child,
            "records": records,
            "attendance_pct": AttendanceRecord.attendance_percentage(child) if child else 0,
        }
        return render(request, "campus/attendance_parent.html", context)

    return redirect("dashboard")


@login_required
def mark_attendance(request):
    if request.method != "POST" or request.user.role != User.Role.TEACHER:
        return redirect("attendance_view")

    teacher = request.user.teacher_profile
    course = get_object_or_404(Course, pk=request.POST.get("course_id"), teacher=teacher)
    today = timezone.now().date()

    for key, value in request.POST.items():
        if key.startswith("status_"):
            student_id = key.replace("status_", "")
            AttendanceRecord.objects.update_or_create(
                student_id=student_id, course=course, date=today,
                defaults={"status": value, "marked_by": teacher},
            )

    return redirect(f"/attendance/?course={course.id}")


@login_required
def attendance_export(request):
    if not _role_required(request.user, User.Role.TEACHER):
        return redirect("dashboard")

    teacher = request.user.teacher_profile
    course = get_object_or_404(Course, pk=request.GET.get("course"), teacher=teacher)
    students = Student.objects.filter(enrollments__course=course).select_related("user")

    rows = [
        (
            s.user.get_full_name() or s.user.username,
            s.roll_number,
            AttendanceRecord.attendance_percentage(s, course=course),
        )
        for s in students
    ]
    return _csv_response(
        f"attendance_{course.title.replace(' ', '_').lower()}.csv",
        ["Name", "Roll number", "Attendance (%)"],
        rows,
    )


# ---------------------------------------------------------------------------
# Progress (student's own detailed breakdown; also used for parent's
# "Academic performance" link)
# ---------------------------------------------------------------------------

@login_required
def progress_view(request):
    role = request.user.role

    if role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        features = StudentTopicFeature.objects.filter(student=student).select_related("topic__course")
        context = {"nav_items": _nav_for(request, "Progress"), "features": features}
        return render(request, "campus/progress_student.html", context)

    if role == User.Role.PARENT:
        parent = getattr(request.user, "parent_profile", None)
        children = list(parent.children.select_related("user").all()) if parent else []
        child = _selected_child(request, children)
        features = (
            StudentTopicFeature.objects.filter(student=child).select_related("topic__course") if child
            else StudentTopicFeature.objects.none()
        )
        context = {
            "nav_items": _nav_for(request, "Academic performance"),
            "children": children, "child": child, "features": features,
        }
        return render(request, "campus/progress_parent.html", context)

    return redirect("dashboard")


# ---------------------------------------------------------------------------
# Parent: My children
# ---------------------------------------------------------------------------

@login_required
def children_list(request):
    if not _role_required(request.user, User.Role.PARENT):
        return redirect("dashboard")

    parent = request.user.parent_profile
    children = list(parent.children.select_related("user", "school_class").all())
    rows = []
    for c in children:
        avg_score = Submission.objects.filter(student=c).aggregate(avg=Avg("score"))["avg"]
        rows.append({
            "student": c,
            "avg_score": round(avg_score, 1) if avg_score else None,
            "attendance_pct": AttendanceRecord.attendance_percentage(c),
        })

    context = {"nav_items": _nav_for(request, "My children"), "rows": rows}
    return render(request, "campus/children_list.html", context)


# ---------------------------------------------------------------------------
# Change password (any role)
# ---------------------------------------------------------------------------

@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep the user signed in
            messages.success(request, "Your password has been updated.")
            return redirect("change_password")
    else:
        form = PasswordChangeForm(user=request.user)

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "form": form,
    }
    return render(request, "campus/change_password.html", context)


# ---------------------------------------------------------------------------
# Account settings (profile, appearance, notifications — any role)
# ---------------------------------------------------------------------------

@login_required
def calendar_view(request):
    import calendar as cal_module
    from datetime import date

    from assignments.models import Assignment
    from quizzes.models import Quiz

    role = request.user.role
    children = None
    child = None
    if role == User.Role.STUDENT:
        student = request.user.student_profile
        assignments = Assignment.objects.filter(topic__course__enrollments__student=student)
        quizzes = Quiz.objects.filter(topic__course__enrollments__student=student, due_date__isnull=False)
    elif role == User.Role.TEACHER:
        teacher = request.user.teacher_profile
        assignments = Assignment.objects.filter(topic__course__teacher=teacher)
        quizzes = Quiz.objects.filter(topic__course__teacher=teacher, due_date__isnull=False)
    elif role == User.Role.PARENT:
        parent = request.user.parent_profile
        children = list(parent.children.all())
        child = _selected_child(request, children)
        if child:
            assignments = Assignment.objects.filter(topic__course__enrollments__student=child)
            quizzes = Quiz.objects.filter(topic__course__enrollments__student=child, due_date__isnull=False)
        else:
            assignments = Assignment.objects.none()
            quizzes = Quiz.objects.none()
    elif role == User.Role.ADMIN:
        assignments = Assignment.objects.all()
        quizzes = Quiz.objects.filter(due_date__isnull=False)
    else:
        return redirect("dashboard")

    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except ValueError:
        year, month = today.year, today.month

    events_by_day = {}
    for a in assignments.select_related("topic__course"):
        d = timezone.localtime(a.deadline).date()
        events_by_day.setdefault(d, []).append({"title": a.title, "kind": "assignment", "url": f"/assignments/{a.pk}/"})
    for q in quizzes.select_related("topic__course"):
        d = timezone.localtime(q.due_date).date()
        events_by_day.setdefault(d, []).append({"title": q.title, "kind": "quiz", "url": "/quizzes/"})

    cal = cal_module.Calendar(firstweekday=6)  # Sunday-first
    raw_weeks = cal.monthdatescalendar(year, month)
    weeks = [
        [
            {
                "date": d,
                "in_month": d.month == month,
                "is_today": d == today,
                "events": events_by_day.get(d, []),
            }
            for d in week
        ]
        for week in raw_weeks
    ]

    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month % 12 + 1
    next_year = year + 1 if month == 12 else year

    context = {
        "nav_items": _nav_for(request, "Calendar"),
        "weeks": weeks,
        "current_month_name": date(year, month, 1).strftime("%B %Y"),
        "current_year": year,
        "current_month": month,
        "prev_year": prev_year, "prev_month": prev_month,
        "next_year": next_year, "next_month": next_month,
        "children": children,
        "child": child,
    }
    return render(request, "campus/calendar.html", context)


@login_required
def account_settings(request):
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "profile":
            profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("account_settings")

        elif action == "theme":
            theme_form = ThemeForm(request.POST, instance=request.user)
            if theme_form.is_valid():
                theme_form.save()
                return redirect("account_settings")

        elif action == "notifications":
            notif_form = NotificationsForm(request.POST, instance=request.user)
            if notif_form.is_valid():
                notif_form.save()
                return redirect("account_settings")

    profile_form = ProfileUpdateForm(instance=request.user)
    theme_form = ThemeForm(instance=request.user)
    notif_form = NotificationsForm(instance=request.user)

    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "profile_form": profile_form,
        "theme_form": theme_form,
        "notif_form": notif_form,
        "avatar": avatar_context(request.user),
    }
    return render(request, "campus/account_settings.html", context)


# ---------------------------------------------------------------------------
# Login (adds a "Remember me" option on top of Django's built-in view)
# ---------------------------------------------------------------------------

class RememberMeLoginView(auth_views.LoginView):
    """
    Same as Django's LoginView, except: if "Remember me" wasn't checked,
    the session expires when the browser closes (Django's default is a
    fixed SESSION_COOKIE_AGE regardless of user choice). Checking it
    keeps the session alive for REMEMBER_ME_DAYS days instead.
    """
    template_name = "campus/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * REMEMBER_ME_DAYS)
        else:
            self.request.session.set_expiry(0)  # expires at browser close
        return response


# ---------------------------------------------------------------------------
# Quizzes (student-facing: list, take, view result)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Quiz management (Teacher/Admin) — an in-app builder, so quizzes no longer
# have to be created through Django's /admin/ panel.
# ---------------------------------------------------------------------------

@login_required
def quiz_manage_list(request):
    if not _role_required(request.user, User.Role.TEACHER, User.Role.ADMIN):
        return redirect("dashboard")

    from quizzes.models import Quiz

    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        quizzes = Quiz.objects.filter(topic__course__teacher=teacher)
    else:
        quizzes = Quiz.objects.all()

    quizzes = (
        quizzes.select_related("topic__course")
        .annotate(question_count=Count("questions"), attempt_count=Count("attempts"))
        .order_by("-created_at")
    )

    context = {"nav_items": _nav_for(request, "Manage quizzes"), "quizzes": quizzes}
    return render(request, "campus/quiz_manage_list.html", context)


@login_required
def quiz_create(request):
    if not _role_required(request.user, User.Role.TEACHER, User.Role.ADMIN):
        return redirect("dashboard")

    teacher = None
    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        topic_qs = Topic.objects.filter(course__teacher=teacher).select_related("course")
    else:
        topic_qs = Topic.objects.select_related("course").all()

    if request.method == "POST":
        form = QuizCreateForm(request.POST, topic_queryset=topic_qs)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.created_by = teacher
            quiz.save()
            messages.success(request, f"Quiz \u201c{quiz.title}\u201d created \u2014 now add some questions below.")
            return redirect("quiz_manage_detail", pk=quiz.pk)
    else:
        form = QuizCreateForm(topic_queryset=topic_qs)

    context = {"nav_items": _nav_for(request, "Manage quizzes"), "form": form}
    return render(request, "campus/quiz_create.html", context)


def _quiz_manage_access(user, quiz):
    """Teachers may only manage quizzes on courses they teach; admins may manage any quiz."""
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)
        return teacher is not None and quiz.topic.course.teacher_id == teacher.id
    return False


@login_required
def quiz_manage_detail(request, pk):
    from quizzes.models import Quiz, Question, AnswerOption

    quiz = get_object_or_404(Quiz.objects.select_related("topic__course"), pk=pk)
    if not _quiz_manage_access(request.user, quiz):
        return redirect("dashboard")

    question_form = QuestionCreateForm()
    option_form = AnswerOptionCreateForm()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_question":
            question_form = QuestionCreateForm(request.POST)
            if question_form.is_valid():
                question = question_form.save(commit=False)
                question.quiz = quiz
                question.save()
                messages.success(request, "Question added.")
                return redirect("quiz_manage_detail", pk=quiz.pk)
            messages.error(request, "Couldn\u2019t add that question \u2014 check the fields below.")

        elif action == "delete_question":
            Question.objects.filter(pk=request.POST.get("question_id"), quiz=quiz).delete()
            messages.success(request, "Question removed.")
            return redirect("quiz_manage_detail", pk=quiz.pk)

        elif action == "add_option":
            question = get_object_or_404(Question, pk=request.POST.get("question_id"), quiz=quiz)
            o_form = AnswerOptionCreateForm(request.POST)
            if o_form.is_valid():
                option = o_form.save(commit=False)
                option.question = question
                option.save()
            else:
                messages.error(request, "Couldn\u2019t add that option \u2014 option text is required.")
            return redirect("quiz_manage_detail", pk=quiz.pk)

        elif action == "delete_option":
            AnswerOption.objects.filter(pk=request.POST.get("option_id"), question__quiz=quiz).delete()
            return redirect("quiz_manage_detail", pk=quiz.pk)

        elif action == "delete_quiz":
            quiz.delete()
            messages.success(request, "Quiz deleted.")
            return redirect("quiz_manage_list")

    questions = quiz.questions.prefetch_related("options").order_by("id")

    context = {
        "nav_items": _nav_for(request, "Manage quizzes"),
        "quiz": quiz,
        "questions": questions,
        "question_form": question_form,
        "option_form": option_form,
    }
    return render(request, "campus/quiz_manage_detail.html", context)


@login_required
def quiz_list(request):
    if not _role_required(request.user, User.Role.STUDENT):
        return redirect("dashboard")

    from quizzes.models import Quiz, QuizAttempt

    student = request.user.student_profile
    quizzes = (
        Quiz.objects.filter(topic__course__enrollments__student=student)
        .select_related("topic__course")
        .distinct()
        .order_by("-created_at")
    )
    attempts_by_quiz = {
        a.quiz_id: a
        for a in QuizAttempt.objects.filter(student=student, quiz__in=quizzes)
    }

    rows = [{"quiz": q, "attempt": attempts_by_quiz.get(q.id)} for q in quizzes]

    context = {"nav_items": _nav_for(request, "Quizzes"), "rows": rows}
    return render(request, "campus/quiz_list.html", context)


@login_required
def quiz_take(request, pk):
    if not _role_required(request.user, User.Role.STUDENT):
        return redirect("dashboard")

    from quizzes.models import Quiz, QuizAttempt, StudentAnswer

    quiz = get_object_or_404(
        Quiz.objects.select_related("topic__course").prefetch_related("questions__options"),
        pk=pk, topic__course__enrollments__student=request.user.student_profile,
    )
    student = request.user.student_profile

    existing = QuizAttempt.objects.filter(quiz=quiz, student=student).first()
    if existing:
        return redirect("quiz_result", pk=existing.pk)

    if request.method == "POST":
        questions = list(quiz.questions.select_related().prefetch_related("options"))
        total_marks = sum(q.marks for q in questions)
        score = 0.0
        answers_to_create = []

        for q in questions:
            field_name = f"question_{q.id}"
            response_value = request.POST.get(field_name, "").strip()

            if q.question_type == "MCQ":
                is_correct = q.options.filter(pk=response_value, is_correct=True).exists()
                selected = q.options.filter(pk=response_value).first()
                response_text = selected.text if selected else ""
            else:
                is_correct = response_value.strip().lower() == q.correct_answer.strip().lower()
                response_text = response_value

            if is_correct:
                score += q.marks

            answers_to_create.append(StudentAnswer(
                attempt=None,  # filled in after the attempt is created
                question=q,
                response=response_text,
                is_correct=is_correct,
            ))

        attempt = QuizAttempt.objects.create(
            quiz=quiz, student=student, score=score, total_marks=total_marks,
            submitted_at=timezone.now(),
        )
        for a in answers_to_create:
            a.attempt = attempt
        StudentAnswer.objects.bulk_create(answers_to_create)

        # Feed Algorithms 2 & 3: refresh this student's feature vector for
        # the topic, same as an assignment submission does.
        from ml_engine.services.feature_engineering import build_feature_vector
        build_feature_vector(student, quiz.topic)

        return redirect("quiz_result", pk=attempt.pk)

    context = {
        "nav_items": _nav_for(request, "Quizzes"),
        "quiz": quiz,
        "questions": quiz.questions.prefetch_related("options").all(),
    }
    return render(request, "campus/quiz_take.html", context)


@login_required
def quiz_result(request, pk):
    from quizzes.models import QuizAttempt

    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz__topic__course", "student__user"),
        pk=pk,
    )
    if attempt.student.user_id != request.user.id and not _role_required(request.user, User.Role.ADMIN, User.Role.TEACHER):
        return redirect("dashboard")

    answers = attempt.answers.select_related("question").prefetch_related("question__options")

    context = {
        "nav_items": _nav_for(request, "Quizzes"),
        "attempt": attempt,
        "answers": answers,
    }
    return render(request, "campus/quiz_result.html", context)


# ---------------------------------------------------------------------------
# PDF exports: report card and certificate of completion
# ---------------------------------------------------------------------------

def _can_view_student_records(request, student):
    """Admin/teacher can view any student's records; a student can view
    their own; a parent can view their own children's."""
    user = request.user
    if user.role in (User.Role.ADMIN, User.Role.TEACHER):
        return True
    if user.role == User.Role.STUDENT:
        return getattr(user, "student_profile", None) == student
    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)
        return parent is not None and parent.children.filter(pk=student.pk).exists()
    return False


@login_required
def report_card_pdf(request, student_id):
    from io import BytesIO

    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    student = get_object_or_404(Student.objects.select_related("user", "school_class"), pk=student_id)
    if not _can_view_student_records(request, student):
        return redirect("dashboard")

    features = StudentTopicFeature.objects.filter(student=student).select_related("topic__course")
    attendance_pct = AttendanceRecord.attendance_percentage(student)
    avg_score = Submission.objects.filter(student=student).aggregate(avg=Avg("score"))["avg"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("CodeLearn — Report Card", styles["Title"]))
    story.append(Spacer(1, 4))
    student_name = student.user.get_full_name() or student.user.username
    story.append(Paragraph(
        f"{student_name} &nbsp;&middot;&nbsp; Roll {student.roll_number} "
        f"&nbsp;&middot;&nbsp; {student.school_class or 'No class assigned'}",
        styles["Normal"],
    ))
    story.append(Paragraph(f"Generated {timezone.now().strftime('%B %d, %Y')}", styles["Normal"]))
    story.append(Spacer(1, 16))

    summary_data = [
        ["Overall average score", f"{avg_score:.1f}%" if avg_score else "No submissions yet"],
        ["Overall attendance", f"{attendance_pct:.1f}%"],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 3 * inch])
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e1d7")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Progress by topic", styles["Heading2"]))
    story.append(Spacer(1, 6))

    table_data = [["Topic", "Course", "Quiz", "Assignment", "Coding", "Status"]]
    for f in features:
        status = "Needs support" if f.is_weak else ("On track" if f.is_weak is False else "Not yet scored")
        table_data.append([
            f.topic.name, f.topic.course.title,
            f"{f.quiz_score:.0f}%", f"{f.assignment_score:.0f}%", f"{f.coding_score:.0f}%",
            status,
        ])
    if len(table_data) == 1:
        table_data.append(["No topic data yet.", "", "", "", "", ""])

    topic_table = Table(table_data, colWidths=[1.1 * inch, 1.5 * inch, 0.7 * inch, 0.9 * inch, 0.7 * inch, 1.1 * inch])
    topic_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#181a20")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e1d7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1efe8")]),
    ]))
    story.append(topic_table)

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="report_card_{student.roll_number}.pdf"'
    return response


def _course_completion_percent(student, course):
    """Simple, documented completion metric: the average of the
    student's coding_score across every topic in the course. Not tied
    to a specific pass/fail policy the school might use — just a
    reasonable default a real deployment would likely want to
    customize."""
    features = StudentTopicFeature.objects.filter(student=student, topic__course=course)
    if not features.exists():
        return 0.0
    return sum(f.coding_score for f in features) / features.count()


COMPLETION_THRESHOLD = 60.0


@login_required
def certificate_pdf(request, student_id, course_id):
    from io import BytesIO

    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    course = get_object_or_404(Course, pk=course_id)
    if not _can_view_student_records(request, student):
        return redirect("dashboard")

    completion_pct = _course_completion_percent(student, course)
    if completion_pct < COMPLETION_THRESHOLD:
        messages.error(
            request,
            f"{student.user.get_full_name() or student.user.username} hasn't reached the "
            f"{COMPLETION_THRESHOLD:.0f}% completion threshold for {course.title} yet "
            f"(currently {completion_pct:.0f}%).",
        )
        return redirect("student_list")

    buffer = BytesIO()
    page_size = landscape(letter)
    c = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    ink = colors.HexColor("#181a20")
    primary = colors.HexColor("#3452e1")
    muted = colors.HexColor("#6b7280")

    c.setStrokeColor(ink)
    c.setLineWidth(2)
    c.rect(0.5 * inch, 0.5 * inch, width - 1 * inch, height - 1 * inch)
    c.setLineWidth(0.75)
    c.rect(0.6 * inch, 0.6 * inch, width - 1.2 * inch, height - 1.2 * inch)

    c.setFont("Helvetica", 11)
    c.setFillColor(muted)
    c.drawCentredString(width / 2, height - 1.4 * inch, "CODELEARN")

    c.setFont("Times-Bold", 34)
    c.setFillColor(ink)
    c.drawCentredString(width / 2, height - 2.2 * inch, "Certificate of Completion")

    c.setFont("Helvetica", 13)
    c.setFillColor(muted)
    c.drawCentredString(width / 2, height - 2.9 * inch, "This certifies that")

    student_name = student.user.get_full_name() or student.user.username
    c.setFont("Times-BoldItalic", 28)
    c.setFillColor(primary)
    c.drawCentredString(width / 2, height - 3.6 * inch, student_name)

    c.setFont("Helvetica", 13)
    c.setFillColor(muted)
    c.drawCentredString(width / 2, height - 4.2 * inch, "has successfully completed the course")

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(ink)
    c.drawCentredString(width / 2, height - 4.8 * inch, course.title)

    c.setFont("Helvetica", 11)
    c.setFillColor(muted)
    c.drawCentredString(
        width / 2, height - 5.4 * inch,
        f"Issued {timezone.now().strftime('%B %d, %Y')} — final performance: {completion_pct:.0f}%",
    )

    c.showPage()
    c.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    safe_name = student.roll_number.replace(" ", "_")
    response["Content-Disposition"] = f'attachment; filename="certificate_{safe_name}.pdf"'
    return response

