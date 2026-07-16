from django.shortcuts import redirect
from django.urls import reverse

from .models import UserProfile

EXEMPT_URL_NAMES = (
    'authentication:onboarding',
    'authentication:logout',
)
EXEMPT_PATH_PREFIXES = ('/static/', '/media/', '/admin/')


class OnboardingRequiredMiddleware:
    """Force authenticated, non-staff users to finish the onboarding survey
    before reaching any other page, regardless of which URL they land on."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = None

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user and user.is_authenticated and not user.is_staff:
            if self.exempt_paths is None:
                self.exempt_paths = {reverse(name) for name in EXEMPT_URL_NAMES}

            path = request.path
            is_exempt = path in self.exempt_paths or path.startswith(EXEMPT_PATH_PREFIXES)

            if not is_exempt:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if not profile.onboarding_completo:
                    onboarding_url = reverse('authentication:onboarding')
                    return redirect(f'{onboarding_url}?next={path}')

        return self.get_response(request)
