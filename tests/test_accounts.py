import unittest
from unittest.mock import patch

from flask import g
from flask.testing import FlaskClient
from sqlalchemy.exc import OperationalError

from app.index import app
from app import dao, db
from app.models import BacSi, BenhNhan, NhanVien, Role, TaiKhoan


class AuthClient(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        if db.engine.url.drivername != "sqlite" or db.engine.url.database != ":memory:":
            self.context.pop()
            raise RuntimeError("Account tests require DATABASE_URL=sqlite:///:memory:")
        app.config["TESTING"] = True
        app.test_client_class = AuthClient
        db.create_all()
        self.client = app.test_client()
        self.password = "Test-password-123!"
        self.admin = dao.create_account(self.data("admin", Role.ADMIN))

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app.test_client_class = FlaskClient

    def data(self, username="patient", role=Role.PATIENT):
        return {
            "tenDangNhap": username, "password": self.password, "role": role,
            "hoTen": "Người dùng kiểm thử", "soDienThoai": "0900000000",
            "trangThai": True, "namSinh": 2000, "gioiTinh": "Khác",
            "diaChi": "Địa chỉ kiểm thử", "chuyenKhoa": "Nội khoa",
        }

    def form(self, username="patient", role="PATIENT"):
        return {
            "tenDangNhap": username, "matKhau": self.password,
            "xacNhanMatKhau": self.password, "role": role, "hoTen": "Người dùng kiểm thử",
            "soDienThoai": "0900000000", "namSinh": "2000", "gioiTinh": "Khác",
            "diaChi": "Địa chỉ kiểm thử", "chuyenKhoa": "Nội khoa", "trangThai": "on",
        }

    def post(self, url, data=None, client=None):
        client = client or self.client
        client.get("/login", follow_redirects=True)
        with client.session_transaction() as session:
            token = session["csrf_token"]
        return client.post(url, data={**(data or {}), "csrf_token": token})

    def sign_in(self, username="admin", client=None):
        return self.post("/login", {
            "tenDangNhap": username, "matKhau": self.password,
        }, client=client)

    def test_registration_forces_patient_and_hashes_password(self):
        response = self.post("/register", self.form(role="ADMIN"))
        self.assertEqual(response.status_code, 302)
        account = db.session.scalar(db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == "patient"))
        self.assertEqual(account.role, Role.PATIENT)
        self.assertIsNotNone(account.benhNhan)
        self.assertIsNone(account.nhanVien)
        self.assertNotEqual(account.matKhau, self.password)
        self.assertTrue(account.dangNhap("patient", self.password))

    def test_csrf_required_for_all_mutations(self):
        self.assertEqual(self.client.post("/register", data=self.form()).status_code, 400)
        self.assertEqual(self.client.post(
            "/register", data={**self.form(), "csrf_token": "không-hợp-lệ"}
        ).status_code, 400)
        self.sign_in()
        self.assertEqual(self.client.post("/admin/accounts/new", data=self.form()).status_code, 400)
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_non_admin_cannot_read_or_write_accounts(self):
        dao.create_account(self.data())
        self.sign_in("patient")
        self.assertEqual(self.client.get("/admin/accounts").status_code, 403)
        self.assertEqual(self.post("/admin/accounts/new", self.form("intruder")).status_code, 403)
        self.assertEqual(self.post(f"/admin/accounts/{self.admin.maTK}/edit", self.form()).status_code, 403)

    def test_all_roles_and_role_specific_templates(self):
        self.sign_in()
        for role in Role:
            name = role.value.lower() + "_test"
            response = self.post("/admin/accounts/new", self.form(name, role.value))
            self.assertEqual(response.status_code, 302)
            account = db.session.scalar(db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == name))
            self.assertEqual(account.role, role)
            if role == Role.PATIENT:
                self.assertIsNotNone(account.benhNhan)
            else:
                self.assertIsNotNone(account.nhanVien)
            if role == Role.DOCTOR:
                self.assertEqual(account.nhanVien.bacSi.chuyenKhoa, "Nội khoa")
            other_client = app.test_client()
            self.sign_in(name, client=other_client)
            page = other_client.get("/dashboard", follow_redirects=True)
            self.assertEqual(page.status_code, 200)
            self.assertIn(role.label, page.get_data(as_text=True))
            for part in ('class="sidebar"', 'class="topbar"', 'class="app-footer"'):
                self.assertIn(part, page.get_data(as_text=True))

    def test_role_changes_keep_previous_profiles(self):
        account = dao.create_account(self.data())
        patient_id = account.benhNhan.maBN
        self.sign_in()
        self.post(f"/admin/accounts/{account.maTK}/edit", self.form(role="DOCTOR"))
        self.assertEqual(account.role, Role.DOCTOR)
        self.assertEqual(account.benhNhan.maBN, patient_id)
        employee_id = account.nhanVien.maNV
        self.assertEqual(account.nhanVien.bacSi.chuyenKhoa, "Nội khoa")
        self.post(f"/admin/accounts/{account.maTK}/edit", self.form(role="PATIENT"))
        self.assertEqual(account.nhanVien.maNV, employee_id)
        self.assertEqual(account.benhNhan.maBN, patient_id)

    def test_admin_cannot_disable_or_demote_self(self):
        self.sign_in()
        for changes in ({"role": "NURSE"}, {"trangThai": ""}):
            response = self.post(
                f"/admin/accounts/{self.admin.maTK}/edit",
                {**self.form("admin", "ADMIN"), **changes},
            )
            self.assertIn("Không được tự khóa", response.get_data(as_text=True))
            self.assertEqual(self.admin.role, Role.ADMIN)
            self.assertTrue(self.admin.trangThai)

    def test_lock_and_role_change_apply_to_existing_sessions(self):
        second = dao.create_account(self.data("second", Role.ADMIN))
        other_client = app.test_client()
        self.sign_in("second", other_client)
        self.sign_in()
        self.post(f"/admin/accounts/{second.maTK}/edit", {
            **self.form("second", "NURSE"), "matKhau": "", "xacNhanMatKhau": "",
        })
        db.session.expire_all()
        self.assertEqual(other_client.get("/admin/accounts").status_code, 403)
        self.post(f"/admin/accounts/{second.maTK}/edit", {
            **self.form("second", "NURSE"), "trangThai": "", "matKhau": "", "xacNhanMatKhau": "",
        })
        db.session.expire_all()
        self.assertEqual(other_client.get("/dashboard").status_code, 302)
        self.assertIsNone(dao.authenticate("second", self.password))

    def test_duplicate_and_invalid_role_do_not_leave_profiles(self):
        self.post("/register", self.form())
        duplicate = self.post("/register", self.form())
        self.assertIn("Tên đăng nhập đã tồn tại", duplicate.get_data(as_text=True))
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(BenhNhan)), 1)
        self.sign_in()
        response = self.post("/admin/accounts/new", self.form("invalid", "SUPER_ADMIN"))
        self.assertIn("Vai trò không hợp lệ", response.get_data(as_text=True))
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(NhanVien)), 1)

    def test_password_reset_and_blank_password_preserve_hash(self):
        account = dao.create_account(self.data())
        other_client = app.test_client()
        self.sign_in("patient", other_client)
        original_hash = account.matKhau
        self.sign_in()
        self.post(f"/admin/accounts/{account.maTK}/edit", {
            **self.form(), "matKhau": "", "xacNhanMatKhau": "",
        })
        self.assertEqual(original_hash, account.matKhau)
        self.post(f"/admin/accounts/{account.maTK}/edit", {
            **self.form(), "matKhau": "Replacement-123!", "xacNhanMatKhau": "Replacement-123!",
        })
        self.assertIsNone(dao.authenticate("patient", self.password))
        self.assertIsNotNone(dao.authenticate("patient", "Replacement-123!"))
        self.assertEqual(other_client.get("/dashboard").status_code, 302)

    def test_invalid_patient_or_doctor_fields_are_rejected(self):
        self.sign_in()
        for changes in ({"namSinh": "3000"}, {"chuyenKhoa": "", "role": "DOCTOR"},
                        {"matKhau": "short"}, {"soDienThoai": "oops"}):
            response = self.post("/admin/accounts/new", {**self.form(), **changes})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(TaiKhoan)), 1)

    def test_account_list_filters_and_pagination(self):
        for i in range(12):
            dao.create_account(self.data(f"patient{i}"))
        self.sign_in()
        first = self.client.get("/admin/accounts?role=PATIENT")
        self.assertIn("12 tài khoản", first.get_data(as_text=True))
        second = self.client.get("/admin/accounts?role=PATIENT&page=2")
        self.assertEqual(second.status_code, 200)
        filtered = self.client.get("/admin/accounts?q=patient11")
        self.assertIn("1 tài khoản", filtered.get_data(as_text=True))
        self.assertNotIn(self.password, filtered.get_data(as_text=True))

    def test_logout_invalidates_session(self):
        self.sign_in()
        self.assertEqual(self.post("/logout").status_code, 302)
        self.assertEqual(self.client.get("/admin/accounts").status_code, 302)

    def test_failed_write_rolls_back(self):
        with self.assertLogs(app.logger, level="ERROR"), patch.object(
            db.session, "commit", side_effect=OperationalError("insert", {}, Exception("test"))
        ):
            with self.assertRaises(OperationalError):
                dao.create_account(self.data())
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(TaiKhoan)), 1)

    def test_database_failure_returns_explicit_error_page(self):
        with self.assertLogs(app.logger, level="ERROR"), patch.object(
            dao, "authenticate", side_effect=OperationalError("select", {}, Exception("test"))
        ):
            response = self.sign_in()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Không thể xử lý dữ liệu", response.get_data(as_text=True))

    def test_model_tables_match_account_schema(self):
        self.assertEqual(set(db.metadata.tables), {"TaiKhoan", "BenhNhan", "NhanVien", "BacSi"})
        self.assertEqual(BacSi.__table__.primary_key.columns.keys(), ["MaNV"])

    def test_modal_edit_validates_confirmation_and_preserves_password(self):
        account = dao.create_account(self.data())
        self.sign_in()
        url = f"/admin/accounts/{account.maTK}/edit?modal=1"
        dialog = self.client.get(url).get_data(as_text=True)
        self.assertIn("modal-header", dialog)
        self.assertNotIn("<html", dialog)
        self.assertNotIn(account.matKhau, dialog)
        original_hash = account.matKhau
        response = self.post(url, {**self.form(), "xacNhanMatKhau": "Mismatch-123!"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Mật khẩu xác nhận không khớp", response.get_data(as_text=True))
        self.assertEqual(account.matKhau, original_hash)
        response = self.post(url, {
            **self.form(), "matKhau": "", "xacNhanMatKhau": "", "hoTen": "Tên đã sửa",
        })
        self.assertEqual(response.status_code, 204)
        self.assertEqual(account.hoTen, "Tên đã sửa")
        self.assertEqual(account.matKhau, original_hash)

    def test_modal_create_and_authorization(self):
        self.assertEqual(self.client.get("/admin/accounts/new?modal=1").status_code, 302)
        self.sign_in()
        self.assertEqual(self.post("/admin/accounts/new?modal=1", self.form()).status_code, 204)
        patient_client = app.test_client()
        self.sign_in("patient", patient_client)
        self.assertEqual(patient_client.get("/admin/accounts/new?modal=1").status_code, 403)

    def test_inline_status_is_explicit_protected_and_invalidates_sessions(self):
        account = dao.create_account(self.data())
        url = f"/admin/accounts/{account.maTK}/status"
        other_client = app.test_client()
        self.sign_in("patient", other_client)
        self.assertEqual(self.post(url, {"active": "0"}, other_client).status_code, 403)
        self.sign_in()
        self.assertEqual(self.client.post(url, data={"active": "0"}).status_code, 400)
        self.assertEqual(self.post(url, {"active": "invalid"}).status_code, 400)
        self.assertTrue(account.trangThai)
        for _ in range(2):
            self.assertEqual(self.post(url, {"active": "0"}).status_code, 302)
            self.assertFalse(account.trangThai)
        self.assertEqual(other_client.get("/dashboard").status_code, 302)
        self.post(url, {"active": "1"})
        self.assertTrue(account.trangThai)
        self.post(f"/admin/accounts/{self.admin.maTK}/status", {"active": "0"})
        self.assertTrue(self.admin.trangThai)
        self.assertIn("Không được tự khóa", self.client.get("/admin/accounts").get_data(as_text=True))

    def test_search_matches_profile_name(self):
        dao.create_account(self.data())
        self.sign_in()
        response = self.client.get("/admin/accounts", query_string={"q": "Người dùng"})
        self.assertIn("patient", response.get_data(as_text=True))

    def test_numeric_ids_and_profile_codes_expand_without_reuse(self):
        first = dao.create_account(self.data())
        self.assertIsInstance(first.maTK, int)
        self.assertIsInstance(first.benhNhan.maBN, int)
        self.assertEqual(first.benhNhan.maHienThi, "BN-0001")
        first.benhNhan.maBN = 9999
        db.session.commit()
        second = dao.create_account(self.data("next_patient"))
        self.assertEqual(second.maHoSo, "BN-10000")
        self.assertNotEqual(first.maTK, second.maTK)
        deleted_id = second.benhNhan.maBN
        db.session.delete(second.benhNhan)
        db.session.delete(second)
        db.session.commit()
        third = dao.create_account(self.data("third_patient"))
        self.assertGreater(third.benhNhan.maBN, deleted_id)
        self.assertEqual(self.admin.maHoSo, "QT-0001")

    def test_employee_role_prefix_changes_but_id_stays(self):
        account = dao.create_account(self.data("cashier", Role.CASHIER))
        employee_id = account.nhanVien.maNV
        self.assertEqual(account.maHoSo, f"TN-{employee_id:04d}")
        for role, prefix in ((Role.DOCTOR, "BS"), (Role.NURSE, "YT"), (Role.ADMIN, "QT")):
            dao.update_account(self.admin.maTK, account.maTK, self.data("cashier", role))
            self.assertEqual(account.nhanVien.maNV, employee_id)
            self.assertEqual(account.maHoSo, f"{prefix}-{employee_id:04d}")
            self.assertEqual(account.nhanVien.bacSi.maNV, employee_id)

    def test_legacy_session_and_non_integer_routes_are_rejected(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = "old-uuid-session"
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.sign_in()
        self.assertEqual(self.client.get("/admin/accounts/uuid/edit").status_code, 404)
        self.assertEqual(self.client.get("/admin/accounts/999999/edit").status_code, 404)


if __name__ == "__main__":
    unittest.main()
