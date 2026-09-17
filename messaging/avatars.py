"""Small helpers for the chat UI: initials + a deterministic color per
user, so avatars look consistent across the inbox and thread views
without needing actual profile photos."""

AVATAR_COLORS = [
    "#3452E1", "#1F9D55", "#D64545", "#B8791A",
    "#7C3AED", "#0EA5A5", "#DB2777", "#4B5563",
]


def initials_for(user) -> str:
    first = (user.first_name or "")[:1]
    last = (user.last_name or "")[:1]
    if first or last:
        return (first + last).upper()
    return (user.username or "?")[:2].upper()


def avatar_color_for(user) -> str:
    return AVATAR_COLORS[user.pk % len(AVATAR_COLORS)]


def avatar_context(user) -> dict:
    return {"initials": initials_for(user), "color": avatar_color_for(user)}
