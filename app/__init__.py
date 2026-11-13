import os
import secrets
import hashlib
from pathlib import Path
import ssl
from datetime import datetime, timedelta, timezone

import certifi
import click
from dotenv import load_dotenv
from flask import Flask, flash, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import URL, make_url, text
from sqlalchemy.exc import SQLAlchemyError


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
    """Create tables missing from the current models; never alter existing schema."""
    from app import models
    db.create_all()
    click.echo("Tables missing from the current models are ready.")


@app.cli.command("upgrade-clinical-schema")
def upgrade_clinical_schema() -> None:
    """Add the draft/final status column without changing existing exam rows."""
    from sqlalchemy import inspect

    inspector = inspect(db.engine)
    if "PhieuKham" not in inspector.get_table_names():
        raise click.ClickException("PhieuKham is missing; run init-db first.")
    if any(column["name"] == "trangThai" for column in inspector.get_columns("PhieuKham")):
        click.echo("PhieuKham.trangThai already exists; no changes made.")
        return

    quote = db.engine.dialect.identifier_preparer.quote
    statement = (
        f"ALTER TABLE {quote('PhieuKham')} ADD COLUMN {quote('trangThai')} "
        "VARCHAR(20) NOT NULL DEFAULT 'DA_LAP'"
    )
    try:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(statement)
    except SQLAlchemyError:
        app.logger.exception("Clinical schema upgrade failed.")
        raise click.ClickException(
            "Could not add PhieuKham.trangThai; inspect the database before retrying."
        ) from None
    click.echo("PhieuKham.trangThai added; existing exams default to DA_LAP.")


@app.cli.command("seed-doctor-demo")
def seed_doctor_demo() -> None:
    """Create clearly labeled sample records for the doctor workflow."""
    from sqlalchemy import inspect
    from app.models import (
        BacSi, BenhNhan, DonViThuoc, NhanVien, PhieuKham, Role, TaiKhoan, Thuoc,
    )

    required = {"TaiKhoan", "NhanVien", "BacSi", "BenhNhan",
                "DonViThuoc", "Thuoc", "PhieuKham", "ChiTietDonThuoc"}
    missing = required - set(inspect(db.engine).get_table_names())
    if missing:
        raise click.ClickException(
            "Missing tables: " + ", ".join(sorted(missing)) + ". Run init-db first."
        )

    username = "demo_quynh_test"
    account = db.session.scalar(
        db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == username)
    )
    if account is None:
        account = TaiKhoan(
            tenDangNhap=username, role=Role.PATIENT, trangThai=False,
        )
        account.set_password(secrets.token_urlsafe(32))
        account.benhNhan = BenhNhan(
            hoTen="Nguyễn Khánh Như Quỳnh",
            gioiTinh="Khác",
            namSinh=2000,
            diaChi="Hồ sơ kiểm thử - không phải địa chỉ thật",
            soDienThoai="0000000000",
        )
        db.session.add(account)
    elif (
        account.role != Role.PATIENT or account.benhNhan is None
        or account.benhNhan.hoTen != "Nguyễn Khánh Như Quỳnh"
    ):
        raise click.ClickException(
            "demo_quynh_test is not the expected demo patient; refusing to modify it."
        )

    demo_units = (
        ("DEMO-UNIT", "Đơn vị kiểm thử"),
    )
    for code, name in demo_units:
        unit = db.session.get(DonViThuoc, code)
        if unit is None:
            db.session.add(DonViThuoc(maDonVi=code, tenDonVi=name))
        elif unit.tenDonVi != name:
            raise click.ClickException(f"Unit code {code} already belongs to other data.")

    demo_medicines = (
        ("DEMO-T001", "DEMO - Viên nén thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T002", "DEMO - Dung dịch thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T003", "DEMO - Gói bột thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T004", "DEMO - Viên nang thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T005", "DEMO - Lọ mẫu thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T006", "DEMO - Tuýp mẫu thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T007", "DEMO - Ống mẫu thử nghiệm (không dùng điều trị)", 100),
        ("DEMO-T008", "DEMO - Hộp mẫu thử nghiệm (không dùng điều trị)", 100),
    )
    for code, name, stock in demo_medicines:
        medicine = db.session.get(Thuoc, code)
        if medicine is None:
            db.session.add(Thuoc(
                maThuoc=code, tenThuoc=name, donGia=0,
                soLuongTon=stock, maDonVi="DEMO-UNIT",
            ))
        elif not medicine.tenThuoc.startswith("DEMO -"):
            raise click.ClickException(f"Medicine code {code} already belongs to non-demo data.")

    additional_patients = (
        ("demo_patient_01", "DEMO - Nguyễn Minh An"),
        ("demo_patient_02", "DEMO - Trần Gia Bảo"),
        ("demo_patient_03", "DEMO - Lê Hoàng Mai"),
        ("demo_patient_04", "DEMO - Phạm Đức Minh"),
        ("demo_patient_05", "DEMO - Võ Thanh Hà"),
        ("demo_patient_06", "DEMO - Đặng Quốc Huy"),
        ("demo_patient_07", "DEMO - Bùi Ngọc Lan"),
        ("demo_patient_08", "DEMO - Đỗ Tuấn Kiệt"),
        ("demo_patient_09", "DEMO - Hồ Khánh Linh"),
        ("demo_patient_10", "DEMO - Phan Nhật Nam"),
    )
    for index, (patient_username, patient_name) in enumerate(additional_patients, 1):
        demo_account = db.session.scalar(
            db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == patient_username)
        )
        if demo_account is None:
            demo_account = TaiKhoan(
                tenDangNhap=patient_username, role=Role.PATIENT, trangThai=False,
            )
            demo_account.set_password(secrets.token_urlsafe(32))
            demo_account.benhNhan = BenhNhan(
                hoTen=patient_name,
                gioiTinh="Khác",
                namSinh=1990 + index,
                diaChi="Hồ sơ kiểm thử - không phải địa chỉ thật",
                soDienThoai="0000000000",
            )
            db.session.add(demo_account)
        elif (
            demo_account.role != Role.PATIENT or demo_account.benhNhan is None
            or demo_account.benhNhan.hoTen != patient_name
        ):
            raise click.ClickException(
                f"{patient_username} is not the expected demo patient; refusing to modify it."
            )

    clinic_timezone = timezone(timedelta(hours=7))
    today = datetime.now(clinic_timezone).date()
    patient = account.benhNhan
    if patient is None:
        raise click.ClickException("Demo patient profile is missing.")
    marker = "DỮ LIỆU KIỂM THỬ - không phải thông tin y tế thật."
    existing_exam = db.session.scalar(
        db.select(PhieuKham).where(
            PhieuKham.maBN == patient.maBN,
            PhieuKham.trieuChung == marker,
        )
    )
    doctor = db.session.scalar(
        db.select(BacSi)
        .join(NhanVien)
        .join(TaiKhoan)
        .where(TaiKhoan.role == Role.DOCTOR, TaiKhoan.trangThai.is_(True))
        .order_by(BacSi.maNV)
    )
    existing_demo_exam_id = db.session.get(PhieuKham, "DEMO-PK-QUYNH")
    if (
        existing_demo_exam_id is not None
        and (existing_demo_exam_id.maBN != patient.maBN
             or existing_demo_exam_id.trieuChung != marker)
    ):
        raise click.ClickException(
            "Demo exam ID already belongs to other data; refusing to modify it."
        )
    if existing_exam is None and existing_demo_exam_id is None and doctor is not None:
        db.session.add(PhieuKham(
            maPhieuKham="DEMO-PK-QUYNH",
            ngayKham=today - timedelta(days=1),
            trieuChung=marker,
            benhNhan=patient,
            bacSi=doctor,
        ))

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Doctor demo seed failed.")
        raise click.ClickException("Could not save demo records; see application log.") from None

    click.echo(f"Demo patient ready: {patient.maHienThi}")
    click.echo("Eleven demo patient profiles and eight demo medicines are ready.")
    click.echo("All demo patient accounts are disabled; inventory was not changed.")
    click.echo("Demo history record is ready." if doctor else
               "No active doctor profile exists; history record was not created.")


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