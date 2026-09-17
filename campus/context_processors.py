def unread_notification_count(request):
    """Makes `unread_notification_count` available in every template
    without every view needing to add it to its context — the bell icon
    in base.html needs it site-wide, not just on specific pages."""
    if not request.user.is_authenticated:
        return {}
    from notifications.models import Notification
    return {
        "unread_notification_count": Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    }
