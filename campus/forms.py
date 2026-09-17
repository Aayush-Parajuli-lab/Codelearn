import secrets
import string

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from academics.models import SchoolClass
from accounts.models import Student, User


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
