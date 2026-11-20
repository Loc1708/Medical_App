import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from flask import g
from flask.testing import FlaskClient
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.index import app
from app import dao, db
from app.models import (
    BacSi, BenhNhan, ChiTietDanhSachKham, ChiTietDonThuoc, DanhSachKham,
    DonViThuoc, HoaDon, NhanVien, PhieuKham, QuyDinh, Role, TaiKhoan, Thuoc,
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
        self.admin = dao.taoTaiKhoan(self.data("admin", Role.ADMIN))
        db.session.add_all([
            QuyDinh(
                maQD="SO_BENH_NHAN_TOI_DA",
                tenQuyDinh="Số bệnh nhân tối đa trong ngày",
                giaTri=Decimal("40"),
            ),
            QuyDinh(
                maQD="TIEN_KHAM",
                tenQuyDinh="Tiền khám",
                giaTri=Decimal("100000"),
            ),
        ])
        db.session.commit()

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
        patient = dao.taoTaiKhoan(self.data("registered_patient"))
        self.sign_in("registered_patient")

        page = self.client.get("/dashboard")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('action="/patient/exam-registrations"', html)
        self.assertIn("Danh sách đăng ký khám của tôi", html)
        for field in ('name="hoTen"', 'name="gioiTinh"', 'name="namSinh"', 'name="diaChi"'):
            self.assertNotIn(field, html)

        response = self.post("/patient/exam-registrations", {
            "hoTen": "Thông tin giả mạo",
            "gioiTinh": "Khác",
            "namSinh": "2200",
            "diaChi": "Địa chỉ giả mạo",
        })
        self.assertEqual(response.status_code, 302)

        registration = db.session.scalar(db.select(ChiTietDanhSachKham))
        self.assertIsNotNone(registration)
        self.assertEqual(registration.maBN, patient.benhNhan.maBN)
        self.assertEqual(registration.benhNhan.hoTen, patient.benhNhan.hoTen)
        self.assertEqual(registration.benhNhan.gioiTinh, patient.benhNhan.gioiTinh)
        self.assertEqual(registration.benhNhan.namSinh, patient.benhNhan.namSinh)
        self.assertEqual(registration.benhNhan.diaChi, patient.benhNhan.diaChi)
        self.assertEqual(registration.trangThai, "CHO_KHAM")
        self.assertEqual(registration.ngayKham, date.today())
        self.assertIsNone(registration.danhSachKham.maNV)

        page = self.client.get("/dashboard")
        html = page.get_data(as_text=True)
        self.assertIn("Đăng ký khám thành công. Hồ sơ đã được thêm vào danh sách khám.", html)
        self.assertIn(patient.benhNhan.hoTen, html)
        exam_date = registration.ngayKham.strftime("%d/%m/%Y")
        self.assertNotIn(exam_date, html)
        registration.trangThai = "DA_XAC_NHAN"
        db.session.commit()
        confirmed_html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn(exam_date, confirmed_html)
        self.assertEqual(len(dao.layDangKyKhamCuaBenhNhan(patient.benhNhan.maBN)), 1)

    def test_patient_profile_page_shows_own_details_and_restricts_other_roles(self):
        patient = dao.taoTaiKhoan(self.data("profile_patient"))
        patient.benhNhan.hoTen = "Hồ sơ bệnh nhân riêng"
        db.session.commit()
        self.sign_in("profile_patient")

        response = self.client.get("/patient/profile")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for value in (
            patient.benhNhan.maHienThi,
            patient.benhNhan.hoTen,
            str(patient.benhNhan.namSinh),
            patient.benhNhan.gioiTinh,
            patient.benhNhan.soDienThoai,
            patient.benhNhan.diaChi,
        ):
            self.assertIn(value, html)
        self.assertIn('href="/patient/profile"', html)
        self.assertIn('class="nav-item active" href="/patient/profile"', html)

        doctor = dao.taoTaiKhoan(self.data("profile_doctor", Role.DOCTOR))
        doctor_client = app.test_client()
        self.sign_in("profile_doctor", client=doctor_client)
        denied = doctor_client.get("/patient/profile")
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn(patient.benhNhan.hoTen, denied.get_data(as_text=True))

    def test_patient_can_edit_contact_details_but_not_gender_or_birth_year(self):
        patient = dao.taoTaiKhoan(self.data("editable_profile_patient"))
        original = {
            "gender": patient.benhNhan.gioiTinh,
            "birth_year": patient.benhNhan.namSinh,
        }
        registration = dao.dangKyKham(patient.benhNhan)
        self.sign_in("editable_profile_patient")

        page = self.client.get("/patient/profile").get_data(as_text=True)
        self.assertIn('name="hoTen"', page)
        self.assertIn('name="soDienThoai"', page)
        self.assertIn('name="diaChi"', page)
        self.assertIn('id="patient-profile-birth-year" type="number"', page)
        self.assertIn('id="patient-profile-gender" disabled', page)

        response = self.post("/patient/profile", {
            "hoTen": "Tên đã cập nhật",
            "soDienThoai": "+84901234567",
            "diaChi": "Địa chỉ mới",
            "gioiTinh": "Khác",
            "namSinh": "1980",
        })
        self.assertEqual(response.status_code, 302)
        db.session.refresh(patient.benhNhan)
        self.assertEqual(patient.benhNhan.hoTen, "Tên đã cập nhật")
        self.assertEqual(patient.benhNhan.soDienThoai, "+84901234567")
        self.assertEqual(patient.benhNhan.diaChi, "Địa chỉ mới")
        self.assertEqual(patient.benhNhan.gioiTinh, original["gender"])
        self.assertEqual(patient.benhNhan.namSinh, original["birth_year"])
        self.assertEqual(registration.benhNhan.hoTen, "Tên đã cập nhật")
        self.assertEqual(registration.benhNhan.diaChi, "Địa chỉ mới")

        invalid = self.post("/patient/profile", {
            "hoTen": "Tên khác",
            "soDienThoai": "không phải số",
            "diaChi": "Địa chỉ khác",
        })
        self.assertEqual(invalid.status_code, 400)
        db.session.refresh(patient.benhNhan)
        self.assertEqual(patient.benhNhan.hoTen, "Tên đã cập nhật")

    def test_patient_exam_registration_uses_profile_and_requires_patient(self):
        patient = dao.taoTaiKhoan(self.data("registration_patient"))
        self.sign_in("registration_patient")

        response = self.post("/patient/exam-registrations", {
            "hoTen": "Thông tin không lấy từ hồ sơ",
            "gioiTinh": "Không hợp lệ",
            "namSinh": "2200",
            "diaChi": "Địa chỉ không lấy từ hồ sơ",
        })
        self.assertEqual(response.status_code, 302)
        registration = db.session.scalar(db.select(ChiTietDanhSachKham))
        self.assertIsNotNone(registration)
        self.assertEqual(registration.benhNhan.hoTen, patient.benhNhan.hoTen)
        self.assertEqual(registration.benhNhan.gioiTinh, patient.benhNhan.gioiTinh)
        self.assertEqual(registration.benhNhan.namSinh, patient.benhNhan.namSinh)
        self.assertEqual(registration.benhNhan.diaChi, patient.benhNhan.diaChi)

        dao.taoTaiKhoan(self.data("registration_doctor", Role.DOCTOR))
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
        self.assertEqual(self.client.post("/patient/profile", data={}).status_code, 400)
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_non_admin_cannot_read_or_write_accounts(self):
        dao.taoTaiKhoan(self.data())
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
            page_html = page.get_data(as_text=True)
            self.assertIn(role.tenVaiTro, page_html)
            for part in ('class="sidebar"', 'class="topbar"', 'class="app-footer"'):
                self.assertIn(part, page_html)
            if role == Role.NURSE:
                self.assertIn("Danh sách bệnh nhân", page_html)
                self.assertIn("Xác nhận danh sách", page_html)
                self.assertIn('data-nurse-app', page_html)
                self.assertIn("Thêm bệnh nhân", page_html)
                self.assertIn('data-patient-lookup-form', page_html)
                self.assertNotIn('data-patient-form', page_html)
                self.assertIn("/static/js/nurse.js", page_html)
                self.assertNotIn('data-waiting-rows', page_html)
                self.assertIn('data-patient-rows', page_html)
                self.assertNotIn("data-preview-control", page_html)

    def test_doctor_dashboard_matches_consultation_mockup_without_fake_records(self):
        dao.taoTaiKhoan(self.data("doctor_ui", Role.DOCTOR))
        self.sign_in("doctor_ui")

        response = self.client.get("/dashboard")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        sidebar_start = html.index('<aside class="sidebar"')
        sidebar_end = html.index("</aside>", sidebar_start)
        sidebar = html[sidebar_start:sidebar_end]
        self.assertIn(">Lập phiếu khám</a>", sidebar)
        self.assertEqual(sidebar.count('class="nav-item'), 1)
        for label in (
            "Lập phiếu khám", "Thông tin bệnh nhân", "Tra cứu thuốc",
            "Thông tin khám", "Đơn thuốc", "Xem lịch sử khám",
        ):
            self.assertIn(label, html)
        self.assertIn("Danh sách thuốc còn hàng được tải tự động.", html)
        self.assertIn("data-medicine-pagination", html)
        self.assertIn("data-patient-history-pagination", html)
        self.assertNotIn("Dữ liệu thử nghiệm", html)
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

    def test_cashier_can_load_and_pay_unpaid_receipt(self):
        doctor = dao.taoTaiKhoan(self.data("receipt_doctor", Role.DOCTOR))
        patient = dao.taoTaiKhoan(self.data("receipt_patient"))
        dao.taoTaiKhoan(self.data("receipt_cashier", Role.CASHIER))
        exam = PhieuKham(
            maPhieuKham="CASHIER-EXAM", ngayKham=date(2026, 11, 20),
            trieuChung="Kiểm thử", benhNhan=patient.benhNhan,
            bacSi=doctor.nhanVien.bacSi,
        )
        invoice = HoaDon(
            ngayLap=datetime.now(), tienKham=100000, tienThuoc=1000,
            tongTien=101000, phieuKham=exam, maNV=doctor.nhanVien.maNV,
        )
        db.session.add_all([exam, invoice])
        db.session.commit()
        self.sign_in("receipt_cashier")

        response = self.client.get(
            "/cashier/api/receipts", query_string={"ma_bn": patient.benhNhan.maHienThi}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["receipts"][0]["id"], invoice.maHoaDon)
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            csrf = session["csrf_token"]
        paid = self.client.post(
            "/cashier/api/receipts/pay", json={"id": invoice.maHoaDon},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(invoice.trangThai, "DA_THANH_TOAN")
        self.assertEqual(self.client.get(
            "/cashier/api/receipts", query_string={"ma_bn": patient.benhNhan.maHienThi}
        ).status_code, 404)

    def test_doctor_can_search_patient_medicines_history_and_create_exam(self):
        doctor = dao.taoTaiKhoan(self.data("doctor_flow", Role.DOCTOR))
        patient = dao.taoTaiKhoan(self.data("patient_flow", Role.PATIENT))
        unit = DonViThuoc(maDonVi="UNIT", tenDonVi="Viên")
        medicine = Thuoc(
            maThuoc="MED-1", tenThuoc="Thuốc kiểm thử", donGia=1000,
            soLuongTon=10, donVi=unit,
        )
        out_of_stock = Thuoc(
            maThuoc="MED-2", tenThuoc="Thuốc kiểm thử hết hàng", donGia=2000,
            soLuongTon=0, donVi=unit,
        )
        prior_exam = PhieuKham(
            maPhieuKham="PRIOR-1", ngayKham=date(2026, 1, 1),
            trieuChung="Lượt khám kiểm thử trước", benhNhan=patient.benhNhan,
            bacSi=doctor.nhanVien.bacSi,
        )
        db.session.add_all([unit, medicine, out_of_stock, prior_exam])
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
        self.assertEqual(history.json["page_size"], 5)
        medicines = self.client.get("/doctor/api/medicines?q=kiểm thử")
        self.assertEqual([row["code"] for row in medicines.json["medicines"]], ["MED-1"])
        partial_name = self.client.get("/doctor/api/medicines?q=kiểm")
        self.assertEqual([row["code"] for row in partial_name.json["medicines"]], ["MED-1"])
        single_character = self.client.get("/doctor/api/medicines?q=t")
        self.assertEqual(
            [row["code"] for row in single_character.json["medicines"]], ["MED-1"]
        )
        partial_code = self.client.get("/doctor/api/medicines?q=ed-1")
        self.assertEqual([row["code"] for row in partial_code.json["medicines"]], ["MED-1"])
        self.assertEqual(partial_code.json["medicines"][0]["price"], 1000)
        all_medicines = self.client.get("/doctor/api/medicines")
        self.assertEqual(all_medicines.json["total"], 1)
        self.assertEqual(all_medicines.json["pages"], 1)
        self.assertEqual(
            self.client.get("/doctor/api/medicines?page=0").status_code, 400
        )

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
                "diagnosis": "Viêm đường hô hấp trên",
                "prescriptions": [{
                    "medicine_code": "MED-1", "quantity": 2,
                    "instructions": "Cách dùng kiểm thử",
                }],
            },
        )
        self.assertEqual(saved.status_code, 201, saved.get_data(as_text=True))
        invoice = db.session.scalar(
            db.select(HoaDon).where(HoaDon.maPhieuKham == saved.json["exam_id"])
        )
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.tienKham, 100000)
        self.assertEqual(invoice.tienThuoc, 2000)
        self.assertEqual(invoice.tongTien, 102000)
        self.assertEqual(invoice.trangThai, "CHUA_THANH_TOAN")
        self.assertEqual(saved.json["invoice_id"], invoice.maHoaDon)
        self.assertEqual(saved.json["invoice_total"], 102000)
        exam = db.session.get(PhieuKham, saved.json["exam_id"])
        self.assertEqual(exam.duDoanLoaiBenh, "Viêm đường hô hấp trên")
        self.assertEqual(medicine.soLuongTon, 8)
        history = self.client.get(
            f"/doctor/api/patients/{patient_code}/history"
        ).json
        self.assertEqual(len(history["exams"]), 2)
        self.assertEqual(history["exams"][0]["id"], saved.json["exam_id"])
        self.assertEqual(history["exams"][0]["prescriptions"], [{
            "code": "MED-1",
            "name": "Thuốc kiểm thử",
            "unit": "Viên",
            "quantity": 2,
            "instructions": "Cách dùng kiểm thử",
        }])

    def test_doctor_history_api_paginates_five_exams_and_returns_prescriptions(self):
        doctor = dao.taoTaiKhoan(self.data("history_page_doctor", Role.DOCTOR))
        patient = dao.taoTaiKhoan(self.data("history_page_patient", Role.PATIENT))
        unit = DonViThuoc(maDonVi="HISTORY-UNIT", tenDonVi="Viên")
        medicine = Thuoc(
            maThuoc="HISTORY-MED", tenThuoc="Thuốc lịch sử", donGia=1000,
            soLuongTon=100, donVi=unit,
        )
        db.session.add_all([unit, medicine])
        for index in range(6):
            exam = PhieuKham(
                maPhieuKham=f"HISTORY-{index}",
                ngayKham=date(2026, 1, 1) + timedelta(days=index),
                trieuChung=f"Triệu chứng {index}",
                benhNhan=patient.benhNhan,
                bacSi=doctor.nhanVien.bacSi,
            )
            exam.chiTietDonThuocs.append(ChiTietDonThuoc(
                thuoc=medicine,
                soLuong=index + 1,
                cachDung=f"Cách dùng {index}",
            ))
            db.session.add(exam)
        db.session.commit()
        self.sign_in("history_page_doctor")

        patient_code = patient.benhNhan.maHienThi
        first_page = self.client.get(
            f"/doctor/api/patients/{patient_code}/history?page=1"
        )
        second_page = self.client.get(
            f"/doctor/api/patients/{patient_code}/history?page=2"
        )
        invalid_page = self.client.get(
            f"/doctor/api/patients/{patient_code}/history?page=0"
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.json["total"], 6)
        self.assertEqual(first_page.json["pages"], 2)
        self.assertEqual(first_page.json["page_size"], 5)
        self.assertEqual(len(first_page.json["exams"]), 5)
        self.assertEqual(first_page.json["exams"][0]["id"], "HISTORY-5")
        self.assertEqual(first_page.json["exams"][0]["prescriptions"][0], {
            "code": "HISTORY-MED",
            "name": "Thuốc lịch sử",
            "unit": "Viên",
            "quantity": 6,
            "instructions": "Cách dùng 5",
        })
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(second_page.json["page"], 2)
        self.assertEqual([exam["id"] for exam in second_page.json["exams"]], ["HISTORY-0"])
        self.assertEqual(invalid_page.status_code, 400)

    def test_doctor_medicine_catalog_paginates_and_filters_with_contains(self):
        dao.taoTaiKhoan(self.data("medicine_page_doctor", Role.DOCTOR))
        unit = DonViThuoc(maDonVi="PAGE-UNIT", tenDonVi="Viên")
        medicines = [
            Thuoc(
                maThuoc=f"PAGE-{index:02d}",
                tenThuoc=f"Thuốc phân trang {index:02d}",
                donGia=1000 + index,
                soLuongTon=0 if index == 11 else 5,
                donVi=unit,
            )
            for index in range(12)
        ]
        db.session.add_all([unit, *medicines])
        db.session.commit()
        self.sign_in("medicine_page_doctor")

        first_page = self.client.get("/doctor/api/medicines")
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.json["total"], 11)
        self.assertEqual(first_page.json["page"], 1)
        self.assertEqual(first_page.json["pages"], 2)
        self.assertEqual(len(first_page.json["medicines"]), 10)

        second_page = self.client.get("/doctor/api/medicines?page=2")
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(
            [row["code"] for row in second_page.json["medicines"]], ["PAGE-10"]
        )

        filtered = self.client.get("/doctor/api/medicines?q=trang&page=2")
        self.assertEqual(filtered.json["total"], 11)
        self.assertEqual(
            [row["code"] for row in filtered.json["medicines"]], ["PAGE-10"]
        )

    def test_doctor_can_save_resume_update_and_finalize_only_own_draft(self):
        doctor = dao.taoTaiKhoan(self.data("draft_doctor", Role.DOCTOR))
        other_doctor = dao.taoTaiKhoan(self.data("other_draft_doctor", Role.DOCTOR))
        patient = dao.taoTaiKhoan(self.data("draft_patient", Role.PATIENT))
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
        self.assertEqual(medicines[0].soLuongTon, 10)
        self.assertIsNone(db.session.scalar(
            db.select(HoaDon).where(HoaDon.maPhieuKham == draft_id)
        ))

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
        self.assertEqual(medicines[1].soLuongTon, 8)
        self.assertIsNone(db.session.scalar(
            db.select(HoaDon).where(HoaDon.maPhieuKham == draft_id)
        ))

        finalized = save(self.client, csrf_for(self.client), {
            "patient_code": patient_code,
            "symptoms": "Phiếu đã hoàn chỉnh",
            "diagnosis": "Viêm đường hô hấp trên",
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
        invoice = db.session.scalar(
            db.select(HoaDon).where(HoaDon.maPhieuKham == draft_id)
        )
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.tienKham, 100000)
        self.assertEqual(invoice.tienThuoc, 6000)
        self.assertEqual(invoice.tongTien, 106000)
        self.assertEqual(finalized.json["invoice_id"], invoice.maHoaDon)
        self.assertEqual(medicines[0].soLuongTon, 10)
        self.assertEqual(medicines[1].soLuongTon, 5)

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
        account = dao.taoTaiKhoan(self.data())
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
        second = dao.taoTaiKhoan(self.data("second", Role.ADMIN))
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
        self.assertIsNone(dao.xacThucTaiKhoan("second", self.password))

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
        account = dao.taoTaiKhoan(self.data())
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
        self.assertIsNone(dao.xacThucTaiKhoan("patient", self.password))
        self.assertIsNotNone(dao.xacThucTaiKhoan("patient", "Replacement-123!"))
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
            dao.taoTaiKhoan(self.data(f"patient{i}"))
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
                dao.taoTaiKhoan(self.data())
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(TaiKhoan)), 1)

    def test_database_failure_returns_explicit_error_page(self):
        with self.assertLogs(app.logger, level="ERROR"), patch.object(
            dao, "xacThucTaiKhoan", side_effect=OperationalError("select", {}, Exception("test"))
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
                "HoaDon", "QuyDinh", "DanhSachKham", "ChiTietDanhSachKham",
            },
        )
        self.assertEqual(BacSi.__table__.primary_key.columns.keys(), ["MaNV"])

    def test_patient_registration_table_command_is_idempotent(self):
        ChiTietDanhSachKham.__table__.drop(db.engine, checkfirst=True)
        DanhSachKham.__table__.drop(db.engine, checkfirst=True)
        runner = app.test_cli_runner()

        first = runner.invoke(args=["create-patient-registration-table"])
        second = runner.invoke(args=["create-patient-registration-table"])

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("DanhSachKham", inspect(db.engine).get_table_names())
        self.assertIn("ChiTietDanhSachKham", inspect(db.engine).get_table_names())

    def test_modal_edit_validates_confirmation_and_preserves_password(self):
        account = dao.taoTaiKhoan(self.data())
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
        account = dao.taoTaiKhoan(self.data())
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
        dao.taoTaiKhoan(self.data())
        self.sign_in()
        response = self.client.get("/admin/accounts", query_string={"q": "Người dùng"})
        self.assertIn("patient", response.get_data(as_text=True))

    def test_numeric_ids_and_profile_codes_expand_without_reuse(self):
        first = dao.taoTaiKhoan(self.data())
        self.assertIsInstance(first.maTK, int)
        self.assertIsInstance(first.benhNhan.maBN, int)
        self.assertEqual(first.benhNhan.maHienThi, "BN-0001")
        first.benhNhan.maBN = 9999
        db.session.commit()
        second = dao.taoTaiKhoan(self.data("next_patient"))
        self.assertEqual(second.maHoSo, "BN-10000")
        self.assertNotEqual(first.maTK, second.maTK)
        deleted_id = second.benhNhan.maBN
        db.session.delete(second.benhNhan)
        db.session.delete(second)
        db.session.commit()
        third = dao.taoTaiKhoan(self.data("third_patient"))
        self.assertGreater(third.benhNhan.maBN, deleted_id)
        self.assertEqual(self.admin.maHoSo, "QT-0001")

    def test_employee_role_prefix_changes_but_id_stays(self):
        account = dao.taoTaiKhoan(self.data("cashier", Role.CASHIER))
        employee_id = account.nhanVien.maNV
        self.assertEqual(account.maHoSo, f"TN-{employee_id:04d}")
        for role, prefix in ((Role.DOCTOR, "BS"), (Role.NURSE, "YT"), (Role.ADMIN, "QT")):
            dao.capNhatTaiKhoan(self.admin.maTK, account.maTK, self.data("cashier", role))
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
