from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dashboard_url = reverse('dashboard')
        self.login_url = reverse('admin:login')
        
        # Create a staff user (admin)
        self.admin_user = User.objects.create_superuser(
            username='admin', 
            email='admin@example.com', 
            password='password123'
        )
        
        # Create a regular user (not staff)
        self.regular_user = User.objects.create_user(
            username='regular', 
            email='regular@example.com', 
            password='password123'
        )

    def test_unauthenticated_redirect(self):
        """Test that unauthenticated users are redirected to the login page."""
        response = self.client.get(self.dashboard_url)
        # Should redirect to login with next path
        expected_redirect = f"{self.login_url}?next={self.dashboard_url}"
        self.assertRedirects(response, expected_redirect)

    def test_non_staff_redirect(self):
        """Test that authenticated non-staff users are redirected to the login page."""
        self.client.login(username='regular', password='password123')
        response = self.client.get(self.dashboard_url)
        # Should redirect to login even if authenticated because not staff
        expected_redirect = f"{self.login_url}?next={self.dashboard_url}"
        self.assertRedirects(response, expected_redirect)

    def test_staff_access(self):
        """Test that staff users can access the dashboard."""
        self.client.login(username='admin', password='password123')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_admin_login_exempt(self):
        """Test that the admin login page is accessible without authentication."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_static_files_exempt(self):
        """Test that static files are accessible without authentication."""
        # Static files usually return 404 in tests if not found, but should NOT redirect
        response = self.client.get('/static/css/style.css')
        # We check that it doesn't redirect to login
        self.assertNotEqual(response.status_code, 302)
