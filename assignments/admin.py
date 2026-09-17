from django.contrib import admin
from .models import Assignment, TestCase, Submission, TestCaseResult

admin.site.register(Assignment)
admin.site.register(TestCase)
admin.site.register(Submission)
admin.site.register(TestCaseResult)
