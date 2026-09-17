from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """
    A conversation is either a direct 1:1 thread (is_group=False, exactly
    two participants, no name) or a named group chat with any number of
    participants — e.g. a teacher messaging every parent in a class.
    """

    name = models.CharField(
        max_length=150, blank=True,
        help_text="Required for group chats; ignored for 1:1 threads.",
    )
    is_group = models.BooleanField(default=False)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ConversationParticipant", related_name="conversations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="conversations_started",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        if self.is_group:
            return self.name or f"Group chat #{self.pk}"
        names = ", ".join(p.get_full_name() or p.username for p in self.participants.all())
        return f"Direct: {names}"

    def display_name(self, viewer):
        """What to show in the conversation list for a given viewer:
        the group name for group chats, or the other participant's name
        for 1:1 threads."""
        if self.is_group:
            return self.name or f"Group chat #{self.pk}"
        other = self.participants.exclude(pk=viewer.pk).first()
        return other.get_full_name() or other.username if other else "Conversation"

    def last_message(self):
        return self.messages.order_by("-created_at").first()

    def unread_count_for(self, user):
        try:
            participant = self.conversationparticipant_set.get(user=user)
        except ConversationParticipant.DoesNotExist:
            return 0
        qs = self.messages.exclude(sender=user)
        if participant.last_read_at:
            qs = qs.filter(created_at__gt=participant.last_read_at)
        return qs.count()


class ConversationParticipant(models.Model):
    """Through model so we can track, per user, when they last read a
    conversation (drives the unread-count badge)."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conversation", "user")

    def __str__(self):
        return f"{self.user} in {self.conversation_id}"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"
