import secrets
import string

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from academics.models import SchoolClass, Subject, Course, Topic, Lesson
from accounts.models import Student, User
from quizzes.models import Quiz, Question, AnswerOption
from assignments.models import Assignment, TestCase


def generate_temp_password(length: int = 12) -> str:
    """A readable-ish random password an admin can hand to a new user."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ProfileUpdateForm(forms.ModelForm):
    """Lets any logged-in user edit their own basic profile info."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone_number", "profile_picture"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "field-input"}),
            "last_name": forms.TextInput(attrs={"class": "field-input"}),
            "email": forms.EmailInput(attrs={"class": "field-input"}),
            "phone_number": forms.TextInput(attrs={"class": "field-input"}),
        }


class ThemeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["theme_preference"]


class NotificationsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email_notifications"]


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text="A .csv file with columns: role, username, first_name, last_name, "
                   "email, phone_number, password, employee_id, department, "
                   "roll_number, school_class, occupation, children. "
                   "Leave irrelevant columns blank for a given row's role."
    )

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if not f.name.lower().endswith(".csv"):
            raise ValidationError("Please upload a .csv file.")
        return f


class UserCreateForm(forms.Form):
    """
    Single form used by admins to create any of the four account types.
    Common fields are always required; role-specific fields are validated
    conditionally based on the chosen role. The template shows/hides the
    relevant field group with a small bit of JS, but validation here is
    authoritative regardless of what the client did.
    """

    ROLE_CHOICES = User.Role.choices

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    password = forms.CharField(
        widget=forms.TextInput, required=False,
        help_text="Leave blank to auto-generate a temporary password.",
    )

    # Teacher-only
    employee_id = forms.CharField(max_length=20, required=False)
    department = forms.CharField(max_length=100, required=False)

    # Student-only
    roll_number = forms.CharField(max_length=20, required=False)
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.objects.all(), required=False
    )

    # Parent-only
    occupation = forms.CharField(max_length=100, required=False)
    children = forms.ModelMultipleChoiceField(
        queryset=Student.objects.select_related("user"), required=False
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")

        if role == User.Role.TEACHER:
            if not cleaned.get("employee_id"):
                self.add_error("employee_id", "Employee ID is required for teachers.")
        elif role == User.Role.STUDENT:
            if not cleaned.get("roll_number"):
                self.add_error("roll_number", "Roll number is required for students.")
        # Parent has no strictly-required extra field (children can be linked later).

        return cleaned


class QuizCreateForm(forms.ModelForm):
    """Used by the in-app quiz builder (Teacher/Admin) — replaces needing /admin/ to make a quiz."""

    class Meta:
        model = Quiz
        fields = ["topic", "title", "time_limit_minutes", "due_date"]
        widgets = {
            "topic": forms.Select(attrs={"class": "field-input"}),
            "title": forms.TextInput(attrs={"class": "field-input"}),
            "time_limit_minutes": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "due_date": forms.DateTimeInput(
                attrs={"class": "field-input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, topic_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if topic_queryset is not None:
            self.fields["topic"].queryset = topic_queryset
        self.fields["due_date"].input_formats = ["%Y-%m-%dT%H:%M"]


class QuestionCreateForm(forms.ModelForm):
    """One question at a time, added to an existing quiz from the builder page."""

    class Meta:
        model = Question
        fields = ["question_type", "prompt", "code_snippet", "correct_answer", "marks"]
        widgets = {
            "question_type": forms.Select(attrs={"class": "field-input"}),
            "prompt": forms.Textarea(attrs={"class": "field-input", "rows": 2}),
            "code_snippet": forms.Textarea(
                attrs={"class": "field-input font-mono", "rows": 3,
                       "placeholder": "Optional — shown above the question, e.g. a code block to predict/debug"}
            ),
            "correct_answer": forms.TextInput(
                attrs={"class": "field-input",
                       "placeholder": "For MCQ, this can be left blank — correctness comes from the options below"}
            ),
            "marks": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code_snippet"].required = False
        self.fields["correct_answer"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("question_type") != Question.QuestionType.MCQ and not cleaned.get("correct_answer"):
            self.add_error(
                "correct_answer",
                "Required for Output Prediction / Debugging questions — this is matched "
                "exactly (case/whitespace-insensitive) against the student's answer.",
            )
        return cleaned


class AnswerOptionCreateForm(forms.ModelForm):
    """One answer option at a time, added to an existing MCQ question."""

    class Meta:
        model = AnswerOption
        fields = ["text", "is_correct"]
        widgets = {
            "text": forms.TextInput(attrs={"class": "field-input", "placeholder": "Option text"}),
        }


class SchoolClassCreateForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["name", "section", "academic_year"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "field-input", "placeholder": "e.g. BCA 5th Sem"}),
            "section": forms.TextInput(attrs={"class": "field-input", "placeholder": "Optional, e.g. A"}),
            "academic_year": forms.TextInput(attrs={"class": "field-input", "placeholder": "e.g. 2025-26"}),
        }


class SubjectCreateForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "field-input", "placeholder": "e.g. Programming Fundamentals"}),
            "code": forms.TextInput(attrs={"class": "field-input", "placeholder": "e.g. CSC101 (must be unique)"}),
        }


class CourseCreateForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "subject", "teacher", "school_classes", "programming_language", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "field-input"}),
            "subject": forms.Select(attrs={"class": "field-input"}),
            "teacher": forms.Select(attrs={"class": "field-input"}),
            "school_classes": forms.SelectMultiple(attrs={"class": "field-input", "size": 4}),
            "programming_language": forms.Select(attrs={"class": "field-input"}),
            "description": forms.Textarea(attrs={"class": "field-input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].required = False
        self.fields["school_classes"].required = False
        self.fields["description"].required = False


class TopicCreateForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["name", "order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "field-input", "placeholder": "e.g. Loops"}),
            "order": forms.NumberInput(attrs={"class": "field-input", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order"].required = False
        self.fields["order"].initial = 0


class LessonCreateForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ["title", "content", "example_code", "order"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "field-input"}),
            "content": forms.Textarea(attrs={"class": "field-input", "rows": 6, "placeholder": "Lesson text (plain text/markdown)"}),
            "example_code": forms.Textarea(attrs={"class": "field-input font-mono", "rows": 5}),
            "order": forms.NumberInput(attrs={"class": "field-input", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["example_code"].required = False
        self.fields["order"].required = False
        self.fields["order"].initial = 0


class AssignmentCreateForm(forms.ModelForm):
    """Used by the in-app assignment builder (Teacher/Admin) — replaces needing /admin/."""

    class Meta:
        model = Assignment
        fields = ["topic", "title", "description", "instructions", "programming_language", "max_marks", "deadline"]
        widgets = {
            "topic": forms.Select(attrs={"class": "field-input"}),
            "title": forms.TextInput(attrs={"class": "field-input"}),
            "description": forms.Textarea(attrs={"class": "field-input", "rows": 3}),
            "instructions": forms.Textarea(attrs={"class": "field-input", "rows": 3}),
            "programming_language": forms.Select(attrs={"class": "field-input"}),
            "max_marks": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "deadline": forms.DateTimeInput(
                attrs={"class": "field-input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, topic_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if topic_queryset is not None:
            self.fields["topic"].queryset = topic_queryset
        self.fields["instructions"].required = False
        self.fields["deadline"].input_formats = ["%Y-%m-%dT%H:%M"]


class TestCaseCreateForm(forms.ModelForm):
    """One test case at a time, added to an existing assignment from its detail page."""

    class Meta:
        model = TestCase
        fields = ["input_data", "expected_output", "is_hidden", "weight"]
        widgets = {
            "input_data": forms.Textarea(
                attrs={"class": "field-input font-mono", "rows": 2, "placeholder": "Optional — stdin fed to the program"}
            ),
            "expected_output": forms.Textarea(attrs={"class": "field-input font-mono", "rows": 2}),
            "weight": forms.NumberInput(attrs={"class": "field-input", "step": "0.1", "min": "0.1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["input_data"].required = False
        self.fields["weight"].initial = 1.0
