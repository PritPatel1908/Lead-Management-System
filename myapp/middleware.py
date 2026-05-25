import re
from django.conf import settings
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    """Require login for all views except those listed in settings.LOGIN_EXEMPT_URLS.

    Add this middleware after Django's AuthenticationMiddleware so that
    ``request.user`` is available.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        exempt_urls = list(getattr(settings, 'LOGIN_EXEMPT_URLS', []))
        login_url = getattr(settings, 'LOGIN_URL', '/login/')
        if login_url:
            # ensure the login URL itself is exempt (strip leading slash)
            login_pattern = r'^' + login_url.lstrip('/')
            if login_pattern not in exempt_urls:
                exempt_urls.append(login_pattern)

        # always exempt static and media
        if r'^static/' not in exempt_urls:
            exempt_urls.append(r'^static/')
        if r'^media/' not in exempt_urls:
            exempt_urls.append(r'^media/')

        self.exempt_urls = [re.compile(expr) for expr in exempt_urls]

    def __call__(self, request):
        path = request.path_info.lstrip('/')

        # If user is authenticated, allow
        if getattr(request, 'user', None) and request.user.is_authenticated:
            return self.get_response(request)

        # Allow any exempt URL
        for pattern in self.exempt_urls:
            if pattern.match(path):
                return self.get_response(request)

        # Redirect to login with next parameter
        login_url = getattr(settings, 'LOGIN_URL', '/login/')
        return redirect(f"{login_url}?next={request.path}")
