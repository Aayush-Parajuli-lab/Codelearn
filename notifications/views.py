from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from campus.views import _nav_for
from notifications.models import Notification


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)
    context = {
        "nav_items": _nav_for(request, "Dashboard"),
        "notifications": notifications,
        "unread_count": notifications.filter(is_read=False).count(),
    }
    return render(request, "notifications/list.html", context)


@login_required
def notification_open(request, pk):
    """Marks one notification read, then redirects to wherever it points."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect(notification.link or "notification_list")


@login_required
def notification_mark_all_read(request):
    if request.method == "POST":
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notification_list")
