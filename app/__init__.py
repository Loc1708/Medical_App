from flask import Flask


def create_app():
    app = Flask(__name__)

    @app.get("/")
    def index():
        return "<h1>Flask server đang chạy!</h1>"

    return app