from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Teacher, Student, Parent


class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Role", {"fields": ("role", "phone_number", "profile_picture")}),
    )


admin.site.register(User, UserAdmin)
admin.site.register(Teacher)
admin.site.register(Student)
admin.site.register(Parent)
