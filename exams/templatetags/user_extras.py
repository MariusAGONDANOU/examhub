from django import template
import re

register = template.Library()

@register.filter
def initials(user):
    # "Francois_TOGBEDJI" -> "FT"
    username = getattr(user, "username", "") or ""
    parts = re.split(r'[\s._-]+', username.strip())
    letters = [p[0].upper() for p in parts if p]
    if not letters and username:
        letters = [username[0].upper()]
    return "".join(letters[:2]) or "?"
