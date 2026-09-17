from django.contrib import admin
from .models import SchoolClass, Subject, Course, Enrollment, Topic, Lesson, ForumPost

admin.site.register(SchoolClass)
admin.site.register(Subject)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Topic)
admin.site.register(Lesson)
admin.site.register(ForumPost)
