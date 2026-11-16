from .models import UserSettings


def dark_mode(request):
    """Expose the signed-in user's dark mode preference to every template.

    Read-only: never creates a UserSettings row. Anonymous users and users
    without saved settings get the light theme.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'dark_mode': False}

    enabled = (
        UserSettings.objects.filter(user=user)
        .values_list('dark_mode', flat=True)
        .first()
    )
    return {'dark_mode': bool(enabled)}
