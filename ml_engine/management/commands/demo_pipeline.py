"""
Seeds a realistic demo dataset — admin, teachers, parents, multiple
courses/topics, students with varied ability — and runs the full
CodeLearn pipeline end to end:

    Algorithm 1 (Code Evaluation) -> feature engineering ->
    Algorithm 2 (Weak-Topic Classifier) -> Algorithm 3 (KNN Recommender)

Run with:  python manage.py demo_pipeline
Add --reset to wipe existing demo data first (drops & remigrates nothing;
just deletes the rows this command creates, safe to re-run).
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User, Student, Teacher, Parent
from academics.models import SchoolClass, Subject, Course, Topic, Lesson, Enrollment
from assignments.models import Assignment, TestCase, Submission
from attendance.models import AttendanceRecord
from quizzes.models import Quiz, Question, AnswerOption, QuizAttempt
from code_runner.evaluator import evaluate_submission
from ml_engine.models import StudentTopicFeature, Recommendation
from ml_engine.services import feature_engineering, weak_topic_classifier, knn_recommender

FIRST_NAMES = [
    "Aayush", "Sita", "Ram", "Anish", "Priya", "Bikash", "Sunita", "Rajesh",
    "Nisha", "Kiran", "Sabin", "Puja", "Arjun", "Sneha", "Prakash", "Rina",
    "Dinesh", "Manisha", "Suresh", "Anita", "Bibek", "Kritika", "Nabin", "Sabina",
]
LAST_NAMES = [
    "Sharma", "Thapa", "Gurung", "Shrestha", "Rai", "Tamang", "Adhikari",
    "Poudel", "Karki", "Basnet", "Magar", "Bhattarai",
]

PYTHON_CORRECT = "a, b = map(int, input().split())\nprint(a + b)\n"
PYTHON_BUGGY = "a, b = map(int, input().split())\nprint(a - b)\n"
PYTHON_FUNC_CORRECT = (
    "def is_even(n):\n    return n % 2 == 0\n\nn = int(input())\nprint('Even' if is_even(n) else 'Odd')\n"
)
PYTHON_FUNC_BUGGY = (
    "def is_even(n):\n    return n % 2 == 1\n\nn = int(input())\nprint('Even' if is_even(n) else 'Odd')\n"
)
PYTHON_PRODUCT_CORRECT = "a, b = map(int, input().split())\nprint(a * b)\n"
PYTHON_PRODUCT_BUGGY = "a, b = map(int, input().split())\nprint(a + b)\n"
PYTHON_SQUARE_CORRECT = "def square(n):\n    return n * n\n\nn = int(input())\nprint(square(n))\n"
PYTHON_SQUARE_BUGGY = "def square(n):\n    return n * 2\n\nn = int(input())\nprint(square(n))\n"


def _jitter(ability, sd=0.32):
    """Perturbs a 0-1 ability score with independent Gaussian noise,
    clipped back to [0, 1]. Used so different features (quiz, coding,
    attendance) aren't perfectly correlated for the same student."""
    return max(0.0, min(1.0, ability + random.gauss(0, sd)))


class Command(BaseCommand):
    help = "Seed a realistic demo dataset and run Algorithms 1, 2, and 3 end-to-end"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete existing demo data before seeding (matches on known demo usernames).",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        self.stdout.write(self.style.NOTICE("=== 1. Admin & staff ==="))
        admin = self._get_or_create_user("admin1", User.Role.ADMIN, is_superuser=True)
        self.stdout.write(f"  Admin: {admin.username} / pass1234")

        teachers = []
        for i, (first, dept) in enumerate([
            ("Hari", "Computer Science"), ("Gita", "Computer Science"),
        ]):
            u = self._get_or_create_user(f"teacher{i+1}", User.Role.TEACHER, first_name=first, last_name="Bhandari")
            t, _ = Teacher.objects.get_or_create(
                user=u, defaults={"employee_id": f"T00{i+1}", "department": dept}
            )
            teachers.append(t)
            self.stdout.write(f"  Teacher: {u.username} / pass1234 ({dept})")

        school_class = SchoolClass.objects.get_or_create(
            name="BCA 5th Sem", defaults={"academic_year": "2026"}
        )[0]

        self.stdout.write(self.style.NOTICE("=== 2. Courses, topics & lessons ==="))
        python_subject = Subject.objects.get_or_create(name="Python Programming", code="PY101")[0]
        python_course = Course.objects.get_or_create(
            title="Python Programming", subject=python_subject,
            defaults={"teacher": teachers[0], "programming_language": "PYTHON"},
        )[0]
        python_course.school_classes.add(school_class)

        c_subject = Subject.objects.get_or_create(name="C Programming", code="C101")[0]
        c_course = Course.objects.get_or_create(
            title="C Programming", subject=c_subject,
            defaults={"teacher": teachers[1], "programming_language": "C"},
        )[0]
        c_course.school_classes.add(school_class)

        loops_topic = Topic.objects.get_or_create(course=python_course, name="Loops", defaults={"order": 1})[0]
        functions_topic = Topic.objects.get_or_create(course=python_course, name="Functions", defaults={"order": 2})[0]
        arrays_topic = Topic.objects.get_or_create(course=c_course, name="Arrays", defaults={"order": 1})[0]

        for topic, title in [
            (loops_topic, "Intro to Loops"), (functions_topic, "Intro to Functions"),
            (arrays_topic, "Intro to Arrays"),
        ]:
            Lesson.objects.get_or_create(topic=topic, title=title, defaults={"content": "...", "order": 1})

        self.stdout.write(self.style.NOTICE("=== 3. Assignments & test cases ==="))
        sum_assignment = Assignment.objects.get_or_create(
            topic=loops_topic, title="Sum of two numbers",
            defaults={
                "description": "Read two integers and print their sum.",
                "programming_language": "PYTHON", "max_marks": 100,
                "deadline": timezone.now() + timedelta(days=7), "created_by": teachers[0],
            },
        )[0]
        for inp, out in [("2 3", "5"), ("10 20", "30"), ("-5 8", "3")]:
            TestCase.objects.get_or_create(assignment=sum_assignment, input_data=inp, expected_output=out)

        parity_assignment = Assignment.objects.get_or_create(
            topic=functions_topic, title="Even or odd",
            defaults={
                "description": "Write a function is_even(n) and print 'Even' or 'Odd'.",
                "programming_language": "PYTHON", "max_marks": 100,
                "deadline": timezone.now() + timedelta(days=10), "created_by": teachers[0],
            },
        )[0]
        for inp, out in [("4", "Even"), ("7", "Odd"), ("0", "Even")]:
            TestCase.objects.get_or_create(assignment=parity_assignment, input_data=inp, expected_output=out)

        # A second assignment per topic gives coding_score real granularity
        # (0/50/100 averaged across two independent attempts) instead of a
        # single pass/fail draw, which would otherwise make every student's
        # coding_score a hard 0 or 100 with no middle ground.
        product_assignment = Assignment.objects.get_or_create(
            topic=loops_topic, title="Product of two numbers",
            defaults={
                "description": "Read two integers and print their product.",
                "programming_language": "PYTHON", "max_marks": 100,
                "deadline": timezone.now() + timedelta(days=7), "created_by": teachers[0],
            },
        )[0]
        for inp, out in [("2 3", "6"), ("4 5", "20"), ("-2 6", "-12")]:
            TestCase.objects.get_or_create(assignment=product_assignment, input_data=inp, expected_output=out)

        square_assignment = Assignment.objects.get_or_create(
            topic=functions_topic, title="Square a number",
            defaults={
                "description": "Write a function square(n) and print the result.",
                "programming_language": "PYTHON", "max_marks": 100,
                "deadline": timezone.now() + timedelta(days=10), "created_by": teachers[0],
            },
        )[0]
        for inp, out in [("3", "9"), ("5", "25"), ("0", "0")]:
            TestCase.objects.get_or_create(assignment=square_assignment, input_data=inp, expected_output=out)

        self.stdout.write(self.style.NOTICE("=== 4. Students (varied ability) ==="))
        students = self._seed_students(n=24, school_class=school_class)
        for s in students:
            Enrollment.objects.get_or_create(student=s, course=python_course)
        # Half also take the C course, for a second topic profile
        for s in students[::2]:
            Enrollment.objects.get_or_create(student=s, course=c_course)

        self.stdout.write(self.style.NOTICE("=== 5. Parents ==="))
        self._seed_parents(students[:6])

        self.stdout.write(self.style.NOTICE("=== 6. Algorithm 1: Automated Code Evaluation ==="))
        quiz = Quiz.objects.get_or_create(
            topic=loops_topic, title="Loops Quiz",
            defaults={"created_by": teachers[0], "due_date": timezone.now() + timedelta(days=10)},
        )[0]
        self._seed_quiz_questions(quiz)

        for student in students:
            ability = student._demo_ability  # 0.0 (struggling) - 1.0 (excellent), set in _seed_students

            # Each metric gets its own noisy draw around the student's overall
            # ability instead of all deriving from one scalar — otherwise every
            # feature is perfectly correlated and the classifier/KNN neighbor
            # sets become trivially separable (100% accuracy, 0% mixed
            # neighborhoods), which isn't realistic.
            coding_ability = _jitter(ability)
            quiz_ability = _jitter(ability)
            attendance_ability = _jitter(ability)

            self._submit_and_grade(sum_assignment, student, coding_ability, PYTHON_CORRECT, PYTHON_BUGGY)
            self._submit_and_grade(product_assignment, student, coding_ability, PYTHON_PRODUCT_CORRECT, PYTHON_PRODUCT_BUGGY)
            self._submit_and_grade(parity_assignment, student, coding_ability, PYTHON_FUNC_CORRECT, PYTHON_FUNC_BUGGY)
            self._submit_and_grade(square_assignment, student, coding_ability, PYTHON_SQUARE_CORRECT, PYTHON_SQUARE_BUGGY)

            QuizAttempt.objects.create(
                quiz=quiz, student=student,
                score=max(0, min(100, round(30 + quiz_ability * 65 + random.uniform(-6, 6)))),
                total_marks=100, submitted_at=timezone.now(),
            )

            for d in range(15):
                present_chance = 0.5 + attendance_ability * 0.4
                AttendanceRecord.objects.get_or_create(
                    student=student, course=python_course,
                    date=timezone.now().date() - timedelta(days=d),
                    defaults={
                        "status": AttendanceRecord.Status.PRESENT
                        if random.random() < present_chance else AttendanceRecord.Status.ABSENT,
                        "marked_by": teachers[0],
                    },
                )

        self.stdout.write(f"  Graded {len(students)} students x 4 assignments")

        self.stdout.write(self.style.NOTICE("=== 7. Feature Engineering ==="))
        n = feature_engineering.rebuild_all_features()
        self.stdout.write(f"  Rebuilt {n} student-topic feature rows")

        self.stdout.write(self.style.NOTICE("=== 8. Algorithm 2: Weak-Topic Classifier ==="))
        report = weak_topic_classifier.train(model_type="logistic")
        self.stdout.write(self.style.SUCCESS(
            f"  Trained on {report.n_samples} samples | "
            f"accuracy={report.accuracy} precision={report.precision} "
            f"recall={report.recall} f1={report.f1}"
        ))

        weak_count = StudentTopicFeature.objects.filter(is_weak=True).count()
        total_count = StudentTopicFeature.objects.count()
        self.stdout.write(f"  Flagged weak: {weak_count}/{total_count}")

        self.stdout.write(self.style.NOTICE("=== 9. Algorithm 3: KNN Recommendation ==="))
        recs_made = 0
        for f in StudentTopicFeature.objects.filter(is_weak=True):
            rec = knn_recommender.recommend_for_student(f.student, f.topic, k=4)
            if rec:
                recs_made += 1
        self.stdout.write(f"  Generated {recs_made} recommendations")

        self.stdout.write(self.style.SUCCESS("\nPipeline complete.\n"))
        self._print_login_summary(admin, teachers, students)

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _get_or_create_user(self, username, role, is_superuser=False, first_name="", last_name=""):
        if User.objects.filter(username=username).exists():
            return User.objects.get(username=username)
        if is_superuser:
            u = User.objects.create_superuser(username, f"{username}@codelearn.local", "pass1234")
        else:
            u = User.objects.create_user(username, password="pass1234")
        u.role = role
        if first_name:
            u.first_name = first_name
        if last_name:
            u.last_name = last_name
        u.save()
        return u

    def _seed_students(self, n, school_class):
        students = []
        existing = Student.objects.count()
        for i in range(existing, existing + n):
            first = FIRST_NAMES[i % len(FIRST_NAMES)]
            last = LAST_NAMES[i % len(LAST_NAMES)]
            username = f"student{i}"
            u = self._get_or_create_user(
                username, User.Role.STUDENT, first_name=first, last_name=last
            )
            s, _ = Student.objects.get_or_create(
                user=u, defaults={"roll_number": f"S{i:03d}", "school_class": school_class}
            )
            # Ability is a smooth distribution, not a coin flip, so features
            # have real spread instead of two identical clusters.
            s._demo_ability = max(0.0, min(1.0, random.gauss(0.55, 0.28)))
            students.append(s)
        return students

    def _seed_quiz_questions(self, quiz):
        if quiz.questions.exists():
            return  # already seeded on a previous run

        q1 = Question.objects.create(
            quiz=quiz, question_type="MCQ",
            prompt="What does the following loop print?",
            code_snippet="for i in range(3):\n    print(i)",
            correct_answer="", marks=2,
        )
        AnswerOption.objects.create(question=q1, text="0 1 2", is_correct=True)
        AnswerOption.objects.create(question=q1, text="1 2 3", is_correct=False)
        AnswerOption.objects.create(question=q1, text="0 1 2 3", is_correct=False)
        AnswerOption.objects.create(question=q1, text="Nothing — this is a syntax error", is_correct=False)

        q2 = Question.objects.create(
            quiz=quiz, question_type="MCQ",
            prompt="Which loop is guaranteed to run at least once?",
            correct_answer="", marks=1,
        )
        AnswerOption.objects.create(question=q2, text="for", is_correct=False)
        AnswerOption.objects.create(question=q2, text="while", is_correct=False)
        AnswerOption.objects.create(question=q2, text="do-while", is_correct=True)

        Question.objects.create(
            quiz=quiz, question_type="OUTPUT",
            prompt="What is the output of this code? (type the exact output)",
            code_snippet="total = 0\nfor i in range(1, 5):\n    total += i\nprint(total)",
            correct_answer="10", marks=2,
        )

        Question.objects.create(
            quiz=quiz, question_type="DEBUG",
            prompt="This loop is supposed to print 1 through 5 but has an off-by-one "
                   "bug. What should `range(...)` be changed to? (e.g. range(1, 6))",
            code_snippet="for i in range(1, 5):\n    print(i)",
            correct_answer="range(1, 6)", marks=2,
        )

    def _seed_parents(self, children):
        for i, child in enumerate(children):
            username = f"parent{i+1}"
            u = self._get_or_create_user(
                username, User.Role.PARENT,
                first_name=f"{child.user.first_name} (Guardian)", last_name=child.user.last_name,
            )
            p, _ = Parent.objects.get_or_create(user=u)
            p.children.add(child)

    def _submit_and_grade(self, assignment, student, ability, correct_code, buggy_code):
        prior = Submission.objects.filter(assignment=assignment, student=student).count()
        code = correct_code if random.random() < ability else buggy_code
        submission = Submission.objects.create(
            assignment=assignment, student=student, source_code=code,
            attempt_number=prior + 1,
        )
        evaluate_submission(submission)

    def _reset(self):
        self.stdout.write(self.style.WARNING("Resetting demo data..."))
        Submission.objects.all().delete()
        QuizAttempt.objects.all().delete()
        AttendanceRecord.objects.all().delete()
        Recommendation.objects.all().delete()
        StudentTopicFeature.objects.all().delete()
        User.objects.filter(username__startswith="student").delete()
        User.objects.filter(username__startswith="parent").delete()
        User.objects.filter(username__startswith="teacher").delete()
        User.objects.filter(username="admin1").delete()

    def _print_login_summary(self, admin, teachers, students):
        self.stdout.write("Demo accounts (all passwords: pass1234):")
        self.stdout.write(f"  Admin:    {admin.username}")
        for t in teachers:
            self.stdout.write(f"  Teacher:  {t.user.username} ({t.department})")
        self.stdout.write("  Parents:  parent1 .. parent6")
        usernames = sorted(s.user.username for s in students)
        self.stdout.write(f"  Students: {usernames[0]} .. {usernames[-1]} ({len(students)} total)")
