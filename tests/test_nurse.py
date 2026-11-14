import unittest
import re
from datetime import date
from decimal import Decimal

from flask import g
from flask.testing import FlaskClient
from sqlalchemy import create_engine, inspect, text

from app import dao, db
from app.index import app
from app.migration import upgrade_nurse_queue_schema
from app.models import DanhSachKham, QuyDinh, Role


class AuthClient(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


class NurseQueueTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        if db.engine.url.drivername != "sqlite" or db.engine.url.database != ":memory:":
            self.context.pop()
            raise RuntimeError("Nurse queue tests require DATABASE_URL=sqlite:///:memory:")
        app.config["TESTING"] = True
        self.previous_client_class = app.test_client_class
        app.test_client_class = AuthClient
        db.create_all()
        self.client = app.test_client()
        self.password = "Test-password-123!"
        self.nurse = dao.create_account({
            "tenDangNhap": "nurse_queue_test",
            "password": self.password,
            "role": Role.NURSE,
            "hoTen": "Y tá kiểm thử",
            "soDienThoai": "0900000000",
            "trangThai": True,
        })
        self.limit = QuyDinh(
            maQD="SO_BENH_NHAN_TOI_DA",
            tenQuyDinh="Số bệnh nhân tối đa trong ngày",
            giaTri=Decimal("40"),
        )
        db.session.add(self.limit)
        db.session.commit()
        self._sign_in(self.client, "nurse_queue_test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.test_client_class = self.previous_client_class

    def _sign_in(self, client, username):
        login_page = client.get("/login")
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            login_page.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        response = client.post("/login", data={
            "tenDangNhap": username,
            "matKhau": self.password,
            "csrf_token": match.group(1),
        })
        self.assertEqual(response.status_code, 302)
        client.get("/dashboard")

    def _api(self, method, path, payload=None):
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        return self.client.open(
            path,
            method=method,
            json=payload,
            headers={"X-CSRF-Token": token},
        )

    def _patient(self, index, exam_date="2026-11-14"):
        return {
            "date": exam_date,
            "name": f"Bệnh nhân {index}",
            "gender": "Nữ",
            "birthYear": 1990,
            "phone": f"0901234{index:04d}",
            "address": "Địa chỉ kiểm thử",
        }

    def test_forty_first_patient_is_persisted_in_waiting_list(self):
        responses = [
            self._api("POST", "/nurse/api/lists", self._patient(index))
            for index in range(1, 42)
        ]
        self.assertTrue(all(response.status_code == 201 for response in responses))
        accepted = db.session.scalars(
            db.select(DanhSachKham).where(DanhSachKham.trangThai == "CHO_KHAM")
        ).all()
        waiting = db.session.scalars(
            db.select(DanhSachKham).where(DanhSachKham.trangThai == "CHO_DUYET")
        ).all()
        self.assertEqual(len(accepted), 40)
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0].soThuTu, None)
        self.assertEqual(waiting[0].benhNhan.maTK, None)
        self.assertEqual(waiting[0].ngayKham, date(2026, 11, 14))
        self.assertIn("hàng chờ", responses[-1].get_json()["message"])

        page = self._api("GET", "/nurse/api/lists?date=2026-11-14")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.get_json()["active"]), 40)
        self.assertEqual(len(page.get_json()["waiting"]), 1)
        self.assertEqual(page.get_json()["limit"], 40)

    def test_waiting_patient_requires_a_freed_slot_before_approval(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        first = self._api("POST", "/nurse/api/lists", self._patient(1))
        waiting = self._api("POST", "/nurse/api/lists", self._patient(2))
        first_id = first.get_json()["patient"]["id"]
        waiting_id = waiting.get_json()["patient"]["id"]

        blocked = self._api("POST", f"/nurse/api/lists/{waiting_id}/approve", {})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(db.session.get(DanhSachKham, waiting_id).trangThai, "CHO_DUYET")

        cancelled = self._api("DELETE", f"/nurse/api/lists/{first_id}")
        self.assertEqual(cancelled.status_code, 200)
        approved = self._api("POST", f"/nurse/api/lists/{waiting_id}/approve", {})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.get_json()["patient"]["slot"], 1)
        self.assertEqual(db.session.get(DanhSachKham, waiting_id).trangThai, "CHO_KHAM")
        self.assertEqual(db.session.get(DanhSachKham, first_id).trangThai, "DA_HUY")

    def test_patient_self_registration_also_uses_the_waiting_queue(self):
        self.limit.giaTri = Decimal("1")
        db.session.commit()
        exam_date = date.today().isoformat()
        accepted = self._api(
            "POST", "/nurse/api/lists", self._patient(1, exam_date=exam_date)
        )
        self.assertEqual(accepted.status_code, 201)

        patient = dao.create_account({
            "tenDangNhap": "patient_queue_test",
            "password": self.password,
            "role": Role.PATIENT,
            "hoTen": "Bệnh nhân tự đăng ký",
            "soDienThoai": "09000000111",
            "trangThai": True,
            "namSinh": 1995,
            "gioiTinh": "Nam",
            "diaChi": "Địa chỉ kiểm thử",
        })
        patient_client = app.test_client()
        self._sign_in(patient_client, "patient_queue_test")
        with patient_client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]
        response = patient_client.post("/patient/exam-registrations", data={
            "hoTen": patient.benhNhan.hoTen,
            "gioiTinh": patient.benhNhan.gioiTinh,
            "namSinh": patient.benhNhan.namSinh,
            "diaChi": patient.benhNhan.diaChi,
            "csrf_token": csrf_token,
        })
        self.assertEqual(response.status_code, 302)
        registration = db.session.scalar(
            db.select(DanhSachKham).where(DanhSachKham.maBN == patient.benhNhan.maBN)
        )
        self.assertIsNotNone(registration)
        self.assertEqual(registration.trangThai, "CHO_DUYET")
        page = patient_client.get("/dashboard")
        self.assertIn("Chờ y tá duyệt", page.get_data(as_text=True))

    def test_nurse_endpoints_enforce_role_and_csrf(self):
        missing_csrf = self.client.post(
            "/nurse/api/lists",
            json=self._patient(1),
        )
        self.assertEqual(missing_csrf.status_code, 400)

        doctor_data = {
            "tenDangNhap": "doctor_queue_test",
            "password": self.password,
            "role": Role.DOCTOR,
            "hoTen": "Bác sĩ kiểm thử",
            "soDienThoai": "0900000001",
            "trangThai": True,
            "chuyenKhoa": "Nội khoa",
        }
        dao.create_account(doctor_data)
        doctor_client = app.test_client()
        self._sign_in(doctor_client, "doctor_queue_test")
        response = doctor_client.get("/nurse/api/lists?date=2026-11-14")
        self.assertEqual(response.status_code, 403)


class NurseQueueMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_rows_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'CREATE TABLE "TaiKhoan" ("MaTK" INTEGER PRIMARY KEY AUTOINCREMENT)'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "BenhNhan" ('
                '"MaBN" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
                '"HoTen" VARCHAR(100) NOT NULL, "GioiTinh" VARCHAR(10) NOT NULL, '
                '"NamSinh" INTEGER NOT NULL, "DiaChi" VARCHAR(255) NOT NULL, '
                '"SoDienThoai" VARCHAR(20) NOT NULL, "MaTK" INTEGER NOT NULL UNIQUE, '
                'FOREIGN KEY ("MaTK") REFERENCES "TaiKhoan" ("MaTK"))'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "DanhSachKham" ('
                '"MaDSKham" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
                '"MaBN" INTEGER NOT NULL, "HoTen" VARCHAR(100) NOT NULL, '
                '"GioiTinh" VARCHAR(10) NOT NULL, "NamSinh" INTEGER NOT NULL, '
                '"DiaChi" VARCHAR(255) NOT NULL, "NgayDangKy" DATETIME NOT NULL, '
                '"TrangThai" VARCHAR(20) NOT NULL, '
                'FOREIGN KEY ("MaBN") REFERENCES "BenhNhan" ("MaBN"))'
            )
            connection.exec_driver_sql(
                'CREATE TABLE "QuyDinh" ('
                '"MaQD" VARCHAR(30) PRIMARY KEY, "TenQuyDinh" VARCHAR(100) NOT NULL, '
                '"GiaTri" NUMERIC(15, 2) NOT NULL)'
            )
            connection.exec_driver_sql('INSERT INTO "TaiKhoan" ("MaTK") VALUES (1)')
            connection.exec_driver_sql(
                'INSERT INTO "BenhNhan" '
                '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "SoDienThoai", "MaTK") '
                'VALUES (1, "Bệnh nhân cũ", "Nữ", 1990, "Địa chỉ cũ", "0900000000", 1)'
            )
            connection.exec_driver_sql(
                'INSERT INTO "DanhSachKham" '
                '("MaBN", "HoTen", "GioiTinh", "NamSinh", "DiaChi", "NgayDangKy", "TrangThai") '
                'VALUES (1, "Bệnh nhân cũ", "Nữ", 1990, "Địa chỉ cũ", '
                '"2026-11-14 08:00:00", "CHO_KHAM")'
            )

        self.assertTrue(upgrade_nurse_queue_schema(engine))
        self.assertFalse(upgrade_nurse_queue_schema(engine))
        columns = {column["name"]: column for column in inspect(engine).get_columns("BenhNhan")}
        self.assertTrue(columns["MaTK"]["nullable"])
        with engine.connect() as connection:
            registration = connection.execute(text(
                'SELECT "NgayKham", "SoThuTu" FROM "DanhSachKham" WHERE "MaDSKham" = 1'
            )).one()
            patient_count = connection.execute(text(
                'SELECT COUNT(*) FROM "BenhNhan"'
            )).scalar_one()
            rule = connection.execute(text(
                'SELECT "GiaTri" FROM "QuyDinh" WHERE "MaQD" = :code'
            ), {"code": "SO_BENH_NHAN_TOI_DA"}).scalar_one()
            foreign_key_errors = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        self.assertEqual(registration.NgayKham, "2026-11-14")
        self.assertEqual(registration.SoThuTu, 1)
        self.assertEqual(patient_count, 1)
        self.assertEqual(rule, 40)
        self.assertEqual(foreign_key_errors, [])
        engine.dispose()
