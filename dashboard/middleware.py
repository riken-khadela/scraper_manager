from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings

class AdminRequiredMiddleware:
    """
    Middleware that requires all users to be authenticated and have staff status 
    (is_staff=True) to access any page, except for the admin login page and static files.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of URL names or paths that are exempt from the authentication check
        exempt_urls = [
            reverse('admin:login'),
            reverse('admin:logout'),
            # Add any other exempt URLs here if needed (e.g., API endpoints if they use separate auth)
        ]

        # Check if the requested path is for the admin site itself
        is_admin_path = request.path.startswith('/admin/')
        # Check if the requested path is for static files
        is_static_path = request.path.startswith(settings.STATIC_URL)

        # Allow access if:
        # 1. The path is explicitly exempt
        # 2. It's a static file
        # 3. The user is logged in AND is a staff member
        if request.path in exempt_urls or is_static_path:
            return self.get_response(request)

        if not request.user.is_authenticated:
            return redirect(f"{reverse('admin:login')}?next={request.path}")

        if not request.user.is_staff:
            # If authenticated but not staff, redirect to login (or could show a 403)
            # Redirecting to login is safer for preventing unauthorized users from even seeing the login status
            return redirect(f"{reverse('admin:login')}?next={request.path}")

        return self.get_response(request)
