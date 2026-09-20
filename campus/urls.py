from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    # Admin
    path("students/", views.student_list, name="student_list"),
    path("students/export/", views.student_export, name="student_export"),
    path("teachers/", views.teacher_list, name="teacher_list"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/", views.reports_export, name="reports_export"),
    path("users/add/", views.user_create, name="user_create"),
    path("users/import/", views.user_import, name="user_import"),
    path("users/import/template/", views.user_import_template, name="user_import_template"),

    # Courses (admin/teacher/student, filtered by role in the view)
    path("classes/manage/", views.class_subject_manage, name="class_subject_manage"),
    path("courses/create/", views.course_create, name="course_create"),
    path("courses/", views.course_list, name="course_list"),
    path("courses/<int:pk>/topics/", views.course_topics, name="course_topics"),
    path("courses/<int:pk>/roster/", views.course_roster, name="course_roster"),
    path("topics/<int:pk>/forum/", views.topic_forum, name="topic_forum"),
    path("topics/<int:pk>/lessons/", views.topic_lessons, name="topic_lessons"),
    path("lessons/<int:pk>/", views.lesson_detail, name="lesson_detail"),

    # Assignments
    path("assignments/create/", views.assignment_create, name="assignment_create"),
    path("assignments/", views.assignment_list, name="assignment_list"),
    path("assignments/<int:pk>/", views.assignment_detail, name="assignment_detail"),
    path("assignments/<int:pk>/plagiarism/", views.plagiarism_check, name="plagiarism_check"),
    path("assignments/<int:pk>/submit/", views.assignment_submit, name="assignment_submit"),

    # Submissions
    path("submissions/", views.submission_list, name="submission_list"),
    path("submissions/<int:pk>/", views.submission_detail, name="submission_detail"),

    # Attendance
    path("attendance/", views.attendance_view, name="attendance_view"),
    path("attendance/mark/", views.mark_attendance, name="mark_attendance"),
    path("attendance/export/", views.attendance_export, name="attendance_export"),

    # Progress
    path("progress/", views.progress_view, name="progress_view"),

    # Calendar
    path("calendar/", views.calendar_view, name="calendar_view"),

    # Quizzes
    path("quizzes/manage/", views.quiz_manage_list, name="quiz_manage_list"),
    path("quizzes/manage/create/", views.quiz_create, name="quiz_create"),
    path("quizzes/manage/<int:pk>/", views.quiz_manage_detail, name="quiz_manage_detail"),
    path("quizzes/", views.quiz_list, name="quiz_list"),
    path("quizzes/<int:pk>/take/", views.quiz_take, name="quiz_take"),
    path("quizzes/attempts/<int:pk>/", views.quiz_result, name="quiz_result"),

    # PDF exports
    path("students/<int:student_id>/report-card.pdf", views.report_card_pdf, name="report_card_pdf"),
    path("students/<int:student_id>/certificate/<int:course_id>.pdf", views.certificate_pdf, name="certificate_pdf"),

    # Parent
    path("children/", views.children_list, name="children_list"),

    # Account
    path("account/password/", views.change_password, name="change_password"),
    path("account/settings/", views.account_settings, name="account_settings"),
]
