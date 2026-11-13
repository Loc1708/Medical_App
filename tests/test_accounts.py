import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from flask import g
from flask.testing import FlaskClient
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.index import app
from app import dao, db
from app.models import (
    BacSi, BenhNhan, ChiTietDonThuoc, DanhSachKham, DonViThuoc, NhanVien,
    PhieuKham, Role, TaiKhoan, Thuoc,
)


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

    def test_patient_can_register_exam_and_view_own_registration(self):
        patient = dao.create_account(self.data("registered_patient"))
        self.sign_in("registered_patient")

        page = self.client.get("/dashboard")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('action="/patient/exam-registrations"', html)
        self.assertIn("Danh sách đăng ký khám của tôi", html)

        response = self.post("/patient/exam-registrations", {
            "hoTen": "Tên khi đăng ký",
            "gioiTinh": "Nữ",
            "namSinh": "1998",
            "diaChi": "Địa chỉ khi đăng ký",
        })
        self.assertEqual(response.status_code, 302)

        registration = db.session.scalar(db.select(DanhSachKham))
        self.assertIsNotNone(registration)
        self.assertEqual(registration.maBN, patient.benhNhan.maBN)
        self.assertEqual(registration.hoTen, "Tên khi đăng ký")
        self.assertEqual(registration.gioiTinh, "Nữ")
        self.assertEqual(registration.namSinh, 1998)
        self.assertEqual(registration.diaChi, "Địa chỉ khi đăng ký")
        self.assertEqual(registration.trangThai, "CHO_KHAM")

        page = self.client.get("/dashboard")
        html = page.get_data(as_text=True)
        self.assertIn("Đăng ký khám thành công. Hồ sơ đã được thêm vào danh sách khám.", html)
        self.assertIn("Tên khi đăng ký", html)
        self.assertEqual(len(dao.patient_exam_registrations(patient.benhNhan.maBN)), 1)

    def test_patient_exam_registration_validates_data_and_requires_patient(self):
        dao.create_account(self.data("registration_patient"))
        self.sign_in("registration_patient")

        invalid = self.post("/patient/exam-registrations", {
            "hoTen": "Tên hợp lệ",
            "gioiTinh": "Nam",
            "namSinh": "2200",
            "diaChi": "Địa chỉ hợp lệ",
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("Năm sinh phải từ 1900 đến năm hiện tại.", invalid.get_data(as_text=True))
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(DanhSachKham)), 0)

        dao.create_account(self.data("registration_doctor", Role.DOCTOR))
        doctor_client = app.test_client()
        self.sign_in("registration_doctor", client=doctor_client)
        forbidden = self.post("/patient/exam-registrations", {
            "hoTen": "Tên hợp lệ",
            "gioiTinh": "Nam",
            "namSinh": "2000",
            "diaChi": "Địa chỉ hợp lệ",
        }, client=doctor_client)
        self.assertEqual(forbidden.status_code, 403)

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

    def test_doctor_dashboard_matches_consultation_mockup_without_fake_records(self):
        dao.create_account(self.data("doctor_ui", Role.DOCTOR))
        self.sign_in("doctor_ui")

        response = self.client.get("/dashboard")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for label in (
            "Lập phiếu khám", "Thông tin bệnh nhân", "Tra cứu thuốc",
            "Thông tin khám", "Đơn thuốc", "Xem lịch sử khám",
        ):
            self.assertIn(label, html)
        self.assertIn("Nhập ít nhất 2 ký tự để tìm thuốc.", html)
        self.assertIn("Dữ liệu thử nghiệm", html)
        self.assertNotIn("Nguyễn Văn An", html)
        self.assertIn(
            "Chưa nhập mã bệnh nhân. Vui lòng nhập mã bệnh nhân để xem danh sách phiếu khám.",
            html,
        )
        self.assertEqual(html.count("Xem lịch sử khám"), 1)
        self.assertIn("data-patient-search", html)
        self.assertIn("data-patient-history", html)
        self.assertIn("data-save-draft", html)
        self.assertIn("data-toggle-drafts", html)
        self.assertIn('id="doctor-drafts"', html)
        self.assertIn("BN-60001", html)
        self.assertIn(
            datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y"), html
        )
        self.assertIn('id="exam-date"', html)
        self.assertNotIn('id="exam-date" type="date"', html)

    def test_doctor_can_search_patient_medicines_history_and_create_exam(self):
        doctor = dao.create_account(self.data("doctor_flow", Role.DOCTOR))
        patient = dao.create_account(self.data("patient_flow", Role.PATIENT))
        unit = DonViThuoc(maDonVi="UNIT", tenDonVi="Viên")
        medicine = Thuoc(
            maThuoc="MED-1", tenThuoc="Thuốc kiểm thử", donGia=1000,
            soLuongTon=10, donVi=unit,
        )
        prior_exam = PhieuKham(
            maPhieuKham="PRIOR-1", ngayKham=date(2026, 1, 1),
            trieuChung="Lượt khám kiểm thử trước", benhNhan=patient.benhNhan,
            bacSi=doctor.nhanVien.bacSi,
        )
        db.session.add_all([unit, medicine, prior_exam])
        db.session.commit()
        self.sign_in("doctor_flow")

        patient_code = patient.benhNhan.maHienThi
        found = self.client.get(f"/doctor/api/patients?code={patient_code}")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json["patient"]["name"], patient.benhNhan.hoTen)
        numeric_code = str(patient.benhNhan.maBN)
        found_by_number = self.client.get(
            f"/doctor/api/patients?code={numeric_code}"
        )
        self.assertEqual(found_by_number.status_code, 200)
        self.assertEqual(found_by_number.json["patient"]["code"], patient_code)
        self.assertEqual(
            self.client.get("/doctor/api/patients?code=BN-999999").status_code, 404
        )
        numeric_history = self.client.get(
            f"/doctor/api/patients/{numeric_code}/history"
        )
        self.assertEqual(
            [row["id"] for row in numeric_history.json["exams"]], ["PRIOR-1"]
        )

        history = self.client.get(f"/doctor/api/patients/{patient_code}/history")
        self.assertEqual([row["id"] for row in history.json["exams"]], ["PRIOR-1"])
        medicines = self.client.get("/doctor/api/medicines?q=kiểm thử")
        self.assertEqual([row["code"] for row in medicines.json["medicines"]], ["MED-1"])

        dashboard = self.client.get("/dashboard")
        csrf = dashboard.get_data(as_text=True).split(
            '<meta name="csrf-token" content="', 1
        )[1].split('"', 1)[0]
        saved = self.client.post(
            "/doctor/api/exams",
            headers={"X-CSRF-Token": csrf},
            json={
                "patient_code": patient_code,
                "symptoms": "Nội dung phiếu khám kiểm thử",
                "prescriptions": [{
                    "medicine_code": "MED-1", "quantity": 2,
                    "instructions": "Cách dùng kiểm thử",
                }],
            },
        )
        self.assertEqual(saved.status_code, 201, saved.get_data(as_text=True))
        self.assertEqual(
            len(self.client.get(f"/doctor/api/patients/{patient_code}/history").json["exams"]),
            2,
        )

    def test_doctor_can_save_resume_update_and_finalize_only_own_draft(self):
        doctor = dao.create_account(self.data("draft_doctor", Role.DOCTOR))
        other_doctor = dao.create_account(self.data("other_draft_doctor", Role.DOCTOR))
        patient = dao.create_account(self.data("draft_patient", Role.PATIENT))
        unit = DonViThuoc(maDonVi="DRAFT-UNIT", tenDonVi="Viên")
        medicines = [
            Thuoc(maThuoc="DRAFT-M1", tenThuoc="Thuốc nháp một", donGia=1000,
                  soLuongTon=10, donVi=unit),
            Thuoc(maThuoc="DRAFT-M2", tenThuoc="Thuốc nháp hai", donGia=2000,
                  soLuongTon=8, donVi=unit),
        ]
        db.session.add_all([unit, *medicines])
        db.session.commit()
        patient_code = patient.benhNhan.maHienThi
        self.sign_in("draft_doctor")

        def csrf_for(client):
            html = client.get("/dashboard").get_data(as_text=True)
            return html.split('<meta name="csrf-token" content="', 1)[1].split('"', 1)[0]

        def save(client, token, body):
            return client.post(
                "/doctor/api/exams",
                headers={"X-CSRF-Token": token},
                json=body,
            )

        first = save(self.client, csrf_for(self.client), {
            "patient_code": patient_code,
            "symptoms": "",
            "status": "NHAP",
            "prescriptions": [{
                "medicine_code": "DRAFT-M1", "quantity": 2, "instructions": "",
            }],
        })
        self.assertEqual(first.status_code, 201, first.get_data(as_text=True))
        draft_id = first.json["exam_id"]
        draft = db.session.get(PhieuKham, draft_id)
        self.assertEqual(draft.trangThai, "NHAP")
        self.assertEqual(draft.trieuChung, "")
        self.assertEqual([detail.maThuoc for detail in draft.chiTietDonThuocs], ["DRAFT-M1"])

        resumed = self.client.get(f"/doctor/api/exams/{draft_id}")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json["exam"]["patient_code"], patient_code)
        self.assertEqual(resumed.json["exam"]["prescriptions"][0]["quantity"], 2)
        draft_list = self.client.get("/doctor/api/drafts")
        self.assertEqual([item["id"] for item in draft_list.json["drafts"]], [draft_id])
        self.assertEqual(draft_list.json["drafts"][0]["patient_code"], patient_code)
        csrf = csrf_for(self.client)

        other_client = app.test_client()
        self.sign_in("other_draft_doctor", other_client)
        other_csrf = csrf_for(other_client)
        self.assertEqual(other_client.get("/doctor/api/drafts").json["drafts"], [])
        self.assertEqual(other_client.get(f"/doctor/api/exams/{draft_id}").status_code, 404)
        self.assertEqual(other_client.delete(
            f"/doctor/api/drafts/{draft_id}",
            headers={"X-CSRF-Token": other_csrf},
        ).status_code, 404)
        self.assertEqual(save(other_client, other_csrf, {
            "patient_code": patient_code, "symptoms": "Không được sửa",
            "status": "NHAP", "draft_id": draft_id, "prescriptions": [],
        }).status_code, 404)

        updated = save(self.client, csrf_for(self.client), {
            "patient_code": patient_code,
            "symptoms": "Đã cập nhật bản nháp",
            "status": "NHAP",
            "draft_id": draft_id,
            "prescriptions": [{
                "medicine_code": "DRAFT-M2", "quantity": 3, "instructions": "",
            }],
        })
        self.assertEqual(updated.status_code, 201, updated.get_data(as_text=True))
        self.assertEqual(updated.json["exam_id"], draft_id)
        db.session.expire_all()
        draft = db.session.get(PhieuKham, draft_id)
        self.assertEqual(draft.trieuChung, "Đã cập nhật bản nháp")
        self.assertEqual([detail.maThuoc for detail in draft.chiTietDonThuocs], ["DRAFT-M2"])

        finalized = save(self.client, csrf_for(self.client), {
            "patient_code": patient_code,
            "symptoms": "Phiếu đã hoàn chỉnh",
            "status": "DA_LAP",
            "draft_id": draft_id,
            "prescriptions": [{
                "medicine_code": "DRAFT-M2", "quantity": 3,
                "instructions": "Cách dùng kiểm thử",
            }],
        })
        self.assertEqual(finalized.status_code, 201, finalized.get_data(as_text=True))
        self.assertEqual(finalized.json["exam_id"], draft_id)
        db.session.expire_all()
        saved_exam = db.session.get(PhieuKham, draft_id)
        self.assertEqual(saved_exam.trangThai, "DA_LAP")
        self.assertEqual(saved_exam.trieuChung, "Phiếu đã hoàn chỉnh")
        self.assertEqual(len(saved_exam.chiTietDonThuocs), 1)
        self.assertEqual(saved_exam.chiTietDonThuocs[0].maThuoc, "DRAFT-M2")
        self.assertEqual(medicines[0].soLuongTon, 10)
        self.assertEqual(medicines[1].soLuongTon, 8)

        deleted = self.client.delete(
            f"/doctor/api/drafts/{draft_id}",
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(deleted.status_code, 404)
        self.assertEqual(self.client.delete(
            f"/doctor/api/drafts/{draft_id}",
            headers={"X-CSRF-Token": csrf},
        ).status_code, 404)
        self.assertEqual(
            self.client.delete("/doctor/api/drafts/unknown", headers={
                "X-CSRF-Token": csrf,
            }).status_code,
            404,
        )

        removable = save(self.client, csrf, {
            "patient_code": patient_code,
            "symptoms": "Bản nháp cần xóa",
            "status": "NHAP",
            "prescriptions": [{
                "medicine_code": "DRAFT-M1", "quantity": 1, "instructions": "",
            }],
        })
        self.assertEqual(removable.status_code, 201)
        removable_id = removable.json["exam_id"]
        removable_response = self.client.delete(
            f"/doctor/api/drafts/{removable_id}",
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(removable_response.status_code, 200)
        self.assertIsNone(db.session.get(PhieuKham, removable_id))
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count()).select_from(
                    ChiTietDonThuoc
                ).where(ChiTietDonThuoc.maPhieuKham == removable_id)
            ),
            0,
        )

        history = self.client.get(f"/doctor/api/patients/{patient_code}/history")
        self.assertEqual(len(history.json["exams"]), 1)
        self.assertEqual(history.json["exams"][0]["status"], "DA_LAP")
        self.assertFalse(history.json["exams"][0]["can_resume"])
        self.assertEqual(self.client.get(f"/doctor/api/exams/{draft_id}").status_code, 404)
        self.assertEqual(self.client.get("/doctor/api/drafts").json["drafts"], [])

    def test_doctor_api_requires_doctor_role_and_csrf_for_writes(self):
        self.sign_in()
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-csrf-token"
            csrf = session["csrf_token"]
        self.assertEqual(self.client.get("/doctor/api/medicines?q=test").status_code, 403)
        self.assertEqual(self.client.get("/doctor/api/drafts").status_code, 403)
        self.assertEqual(self.client.delete("/doctor/api/drafts/unknown").status_code, 400)
        self.assertEqual(
            self.client.post("/doctor/api/exams", json={}).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                "/doctor/api/exams", headers={"X-CSRF-Token": csrf}, json={}
            ).status_code,
            403,
        )

    def test_doctor_demo_seed_is_repeatable(self):
        runner = app.test_cli_runner()
        first = runner.invoke(args=["seed-doctor-demo"])
        self.assertEqual(first.exit_code, 0, first.output)
        second = runner.invoke(args=["seed-doctor-demo"])
        self.assertEqual(second.exit_code, 0, second.output)

        patient_account = db.session.scalar(
            db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == "demo_quynh_test")
        )
        self.assertEqual(patient_account.benhNhan.hoTen, "Nguyễn Khánh Như Quỳnh")
        self.assertFalse(patient_account.trangThai)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count()).select_from(Thuoc)
                              .where(Thuoc.maThuoc.like("DEMO-%"))),
            8,
        )
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count()).select_from(BenhNhan)
                .join(TaiKhoan).where(TaiKhoan.tenDangNhap.like("demo_patient_%"))
            ),
            10,
        )

    def test_clinical_schema_upgrade_is_idempotent(self):
        runner = app.test_cli_runner()
        first = runner.invoke(args=["upgrade-clinical-schema"])
        second = runner.invoke(args=["upgrade-clinical-schema"])
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("already exists", second.output)

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

    def test_model_tables_match_schema(self):
        self.assertEqual(
            set(db.metadata.tables),
            {
                "TaiKhoan", "BenhNhan", "NhanVien", "BacSi",
                "DonViThuoc", "Thuoc", "PhieuKham", "ChiTietDonThuoc",
                "DanhSachKham",
            },
        )
        self.assertEqual(BacSi.__table__.primary_key.columns.keys(), ["MaNV"])

    def test_patient_registration_table_command_is_idempotent(self):
        DanhSachKham.__table__.drop(db.engine, checkfirst=True)
        runner = app.test_cli_runner()

        first = runner.invoke(args=["create-patient-registration-table"])
        second = runner.invoke(args=["create-patient-registration-table"])

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("DanhSachKham", inspect(db.engine).get_table_names())

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
