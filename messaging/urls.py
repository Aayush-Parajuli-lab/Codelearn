from django.urls import path

from . import views

urlpatterns = [
    path("messages/", views.inbox, name="inbox"),
    path("messages/mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("messages/new/", views.conversation_start, name="conversation_start"),
    path("messages/<int:pk>/", views.conversation_detail, name="conversation_detail"),
]
