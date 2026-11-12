import unittest

from app.index import app
from app import db


class AppTests(unittest.TestCase):
    def test_home_page(self):
        with app.test_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Phòng mạch Nhịp Sống", response.get_data(as_text=True))
        self.assertIn('<html lang="vi">', response.get_data(as_text=True))

    def test_database_extension(self):
        self.assertIs(app.extensions["sqlalchemy"], db)

    def test_check_db_command(self):
        result = app.test_cli_runner().invoke(args=["check-db"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Database connection successful.", result.output)

    def test_static_file(self):
        with app.test_client() as client:
            with client.get("/static/css/.gitkeep") as response:
                self.assertEqual(response.status_code, 200)

    def test_header_logo_and_favicon(self):
        from flask import url_for

        with app.test_request_context():
            logo_url = url_for("static", filename="images/2.png")
            favicon_url = url_for("static", filename="images/2.png")
        with app.test_client() as client:
            for path in ("/", "/login", "/register"):
                html = client.get(path).get_data(as_text=True)
                self.assertIn(f'src="{logo_url}"', html)
                self.assertIn(f'href="{favicon_url}"', html)
                self.assertNotIn("An Tâm", html)
            for url in (logo_url, favicon_url):
                with client.get(url) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, "image/png")
                    self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
