"""
Smoke tests — not exhaustive unit tests, but enough to catch "the app
doesn't start" or "this page 500s" regressions in CI. Seeds the same
demo data every developer already uses locally (`demo_pipeline`), then
hits every role's dashboard and a handful of key pages.
"""
from django.core.management import call_command
from django.test import Client, TestCase


class SmokeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_pipeline")

    def _login(self, username):
        client = Client()
        logged_in = client.login(username=username, password="pass1234")
        self.assertTrue(logged_in, f"login failed for {username}")
        return client

    def test_admin_dashboard_and_pages(self):
        c = self._login("admin1")
        for path in ["/dashboard/", "/students/", "/teachers/", "/courses/", "/reports/", "/users/add/", "/calendar/"]:
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)

    def test_teacher_dashboard_and_pages(self):
        c = self._login("teacher1")
        for path in ["/dashboard/", "/courses/", "/assignments/", "/attendance/", "/submissions/", "/calendar/"]:
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)

    def test_student_dashboard_and_pages(self):
        c = self._login("student0")
        for path in ["/dashboard/", "/courses/", "/assignments/", "/quizzes/", "/progress/", "/attendance/", "/calendar/"]:
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)

    def test_parent_dashboard_and_pages(self):
        c = self._login("parent1")
        for path in ["/dashboard/", "/children/", "/attendance/", "/progress/", "/calendar/"]:
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)

    def test_messaging(self):
        c = self._login("student0")
        self.assertEqual(c.get("/messages/").status_code, 200)
        self.assertEqual(c.get("/messages/new/").status_code, 200)

    def test_notifications(self):
        c = self._login("student0")
        self.assertEqual(c.get("/notifications/").status_code, 200)

    def test_login_page_and_logout(self):
        c = Client()
        self.assertEqual(c.get("/login/").status_code, 200)
        c.login(username="admin1", password="pass1234")
        response = c.post("/logout/")
        self.assertIn(response.status_code, (200, 302))

    def test_unauthenticated_redirects_to_login(self):
        c = Client()
        response = c.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
