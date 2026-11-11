import unittest

from app.index import app
from app import db


class AppTests(unittest.TestCase):
    def test_home_page(self):
        with app.test_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Flask server đang chạy!", response.get_data(as_text=True))
        self.assertIn('<html lang="vi">', response.get_data(as_text=True))

    def test_database_extension(self):
        self.assertIs(app.extensions["sqlalchemy"], db)

    def test_static_file(self):
        with app.test_client() as client:
            with client.get("/static/css/.gitkeep") as response:
                self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
