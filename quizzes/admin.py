from django.contrib import admin
from .models import Quiz, Question, AnswerOption, QuizAttempt, StudentAnswer

admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(AnswerOption)
admin.site.register(QuizAttempt)
admin.site.register(StudentAnswer)
