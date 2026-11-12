import os
import secrets
import hashlib
from pathlib import Path
import ssl

import certifi
import click
from dotenv import load_dotenv
from flask import Flask, flash, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import URL, make_url, text


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = Flask(__name__)
secret_path = Path(app.instance_path) / "session-secret"
if not os.environ.get("SECRET_KEY"):
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with secret_path.open("x", encoding="utf-8") as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secret_path.read_text(encoding="utf-8")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=64 * 1024,
)
if os.environ.get("DATABASE_URL"):
    database_url = make_url(os.environ["DATABASE_URL"])
elif os.environ.get("MYSQL_HOST"):
    if not os.environ.get("MYSQL_PASSWORD"):
        raise RuntimeError("Set MYSQL_PASSWORD in .env before connecting to TiDB.")
    database_url = URL.create(
        "mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "4000")),
        database=os.environ["MYSQL_DATABASE"],
        query={"charset": "utf8mb4"},
    )
else:
    database_url = make_url("sqlite:///medical.db")

if database_url.drivername == "mysql":
    database_url = database_url.set(drivername="mysql+pymysql")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if database_url.drivername == "mysql+pymysql":
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "connect_args": {
            "ssl": ssl.create_default_context(cafile=certifi.where()),
            "connect_timeout": 10,
        },
    }

db = SQLAlchemy(app)
login = LoginManager(app)


@login.unauthorized_handler
def unauthorized():
    flash("Vui lòng đăng nhập để tiếp tục.", "info")
    return redirect(url_for("login_view"))


@login.user_loader
def load_user(account_id: str):
    from app.models import TaiKhoan
    if not account_id.isascii() or not account_id.isdecimal() or len(account_id) > 10:
        return None
    account = db.session.get(TaiKhoan, int(account_id))
    if not account or not account.trangThai:
        return None
    fingerprint = hashlib.sha256(account.matKhau.encode()).hexdigest()
    return account if secrets.compare_digest(session.get("auth_hash", ""), fingerprint) else None


@app.cli.command("check-db")
def check_db() -> None:
    """Verify connectivity without creating tables or modifying data."""
    with db.engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
    click.echo("Database connection successful.")


@app.cli.command("init-db")
def init_db() -> None:
    """Create missing tables only; never overwrite existing schema."""
    from app import models
    db.create_all()
    click.echo("Account and profile tables ready.")


@app.cli.command("create-admin")
@click.option("--username", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--name", prompt=True)
@click.option("--phone", default="", help="Optional employee phone number.")
def create_admin(username: str, password: str, name: str, phone: str) -> None:
    from app.dao import create_account
    from app.utils import account_data
    try:
        data = account_data({
            "tenDangNhap": username, "matKhau": password, "hoTen": name,
            "soDienThoai": phone, "role": "ADMIN", "trangThai": "on",
        })
        create_account(data)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    click.echo("Administrator created.")


@app.cli.command("migrate-account-ids")
@click.option("--maintenance", is_flag=True, help="Confirm all application writers are stopped.")
def migrate_account_ids_command(maintenance: bool) -> None:
    """Preserve old UUID tables and migrate account/profile keys to integers."""
    from sqlalchemy.exc import SQLAlchemyError
    from app.migration import migrate_account_ids
    if not maintenance:
        raise click.ClickException("Stop all application writers and pass --maintenance.")
    try:
        changed = migrate_account_ids(db.engine)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    except SQLAlchemyError as error:
        app.logger.error("Identifier migration failed: %s", type(error).__name__)
        raise click.ClickException(
            "Migration failed. Original/backup tables were not deleted; inspect before retrying."
        ) from error
    click.echo("Integer IDs ready; original tables retained as *_uuid_backup." if changed
               else "Identifiers are already integers; no changes made.")