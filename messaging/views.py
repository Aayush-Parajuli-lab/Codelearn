from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from campus.views import _nav_for
from messaging.avatars import avatar_context
from messaging.models import Conversation, ConversationParticipant, Message
from messaging.permissions import allowed_recipients


def _send_message(conversation, sender, body):
    """Creates a Message and notifies every other participant — keeps
    the notification center in sync with new messages without every
    call site having to remember to do both."""
    from notifications.models import notify, Notification

    message = Message.objects.create(conversation=conversation, sender=sender, body=body)
    name = sender.get_full_name() or sender.username
    for participant in conversation.participants.exclude(pk=sender.pk):
        notify(
            participant,
            f"New message from {name}",
            category=Notification.Category.MESSAGE,
            link=f"/messages/{conversation.pk}/",
        )
    return message


def _conversation_rows(user, active_id=None):
    """Builds the left-pane conversation list shared by the inbox and
    conversation-detail views, so both render an identical list with
    the current thread (if any) highlighted."""
    conversations = (
        Conversation.objects.filter(participants=user)
        .annotate(last_activity=Max("messages__created_at"))
        .order_by("-last_activity", "-created_at")
    )
    rows = []
    for c in conversations:
        other = None if c.is_group else c.participants.exclude(pk=user.pk).first()
        rows.append({
            "conversation": c,
            "display_name": c.display_name(user),
            "last_message": c.last_message(),
            "unread_count": c.unread_count_for(user),
            "is_active": c.pk == active_id,
            "avatar": avatar_context(other) if other else None,
        })
    return rows


@login_required
def inbox(request):
    rows = _conversation_rows(request.user)
    context = {
        "nav_items": _nav_for(request, "Messages"),
        "rows": rows,
        "active_conversation": None,
        "has_unread": any(row["unread_count"] for row in rows),
    }
    return render(request, "messaging/inbox.html", context)


@login_required
def mark_all_read(request):
    if request.method == "POST":
        ConversationParticipant.objects.filter(
            conversation__participants=request.user, user=request.user
        ).update(last_read_at=timezone.now())
    return redirect("inbox")


@login_required
def conversation_detail(request, pk):
    conversation = get_object_or_404(
        Conversation.objects.filter(participants=request.user), pk=pk
    )

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            _send_message(conversation, request.user, body)
        return redirect("conversation_detail", pk=pk)

    # Mark as read
    ConversationParticipant.objects.filter(
        conversation=conversation, user=request.user
    ).update(last_read_at=timezone.now())

    other = None if conversation.is_group else conversation.participants.exclude(pk=request.user.pk).first()
    messages_qs = conversation.messages.select_related("sender").all()

    # Attach avatar context to each message's sender for the bubble UI.
    messages_with_avatars = [
        {"message": m, "is_mine": m.sender_id == request.user.pk, "avatar": avatar_context(m.sender)}
        for m in messages_qs
    ]

    rows = _conversation_rows(request.user, active_id=conversation.pk)
    context = {
        "nav_items": _nav_for(request, "Messages"),
        "rows": rows,
        "active_conversation": conversation,
        "conversation": conversation,
        "display_name": conversation.display_name(request.user),
        "header_avatar": avatar_context(other) if other else None,
        "messages_with_avatars": messages_with_avatars,
        "participants": conversation.participants.exclude(pk=request.user.pk),
        "has_unread": any(row["unread_count"] for row in rows),
    }
    return render(request, "messaging/conversation_detail.html", context)


@login_required
def conversation_start(request):
    recipients_qs = allowed_recipients(request.user).select_related(
        "teacher_profile", "student_profile", "parent_profile"
    )

    def _recipient_rows(qs):
        return [{"user": u, "avatar": avatar_context(u)} for u in qs]

    if request.method == "POST":
        recipient_ids = request.POST.getlist("recipients")
        group_name = request.POST.get("group_name", "").strip()
        first_message = request.POST.get("body", "").strip()

        recipients = list(recipients_qs.filter(pk__in=recipient_ids))
        if not recipients:
            context = {
                "nav_items": _nav_for(request, "Messages"),
                "recipient_rows": _recipient_rows(recipients_qs),
                "error": "Pick at least one valid recipient.",
            }
            return render(request, "messaging/conversation_start.html", context)

        is_group = len(recipients) > 1

        # Reuse an existing 1:1 thread instead of creating a duplicate.
        if not is_group:
            existing = (
                Conversation.objects.filter(is_group=False, participants=request.user)
                .filter(participants=recipients[0])
                .first()
            )
            if existing:
                if first_message:
                    _send_message(existing, request.user, first_message)
                return redirect("conversation_detail", pk=existing.pk)

        conversation = Conversation.objects.create(
            name=group_name if is_group else "",
            is_group=is_group,
            created_by=request.user,
        )
        all_participants = [request.user] + recipients
        for p in all_participants:
            ConversationParticipant.objects.create(conversation=conversation, user=p)

        if first_message:
            _send_message(conversation, request.user, first_message)

        return redirect("conversation_detail", pk=conversation.pk)

    context = {
        "nav_items": _nav_for(request, "Messages"),
        "recipient_rows": _recipient_rows(recipients_qs),
    }
    return render(request, "messaging/conversation_start.html", context)
