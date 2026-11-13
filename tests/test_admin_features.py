import unittest
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from flask import g
from flask.testing import FlaskClient
from sqlalchemy.exc import OperationalError

from app.index import app
from app import dao, db
from app.models import (
    ChiTietDonThuoc, DonViThuoc, HoaDon, PhieuKham, QuyDinh, Role, TaiKhoan, Thuoc,
)


class FeatureClient(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


class AdminFeatureTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        if db.engine.url.drivername != "sqlite" or db.engine.url.database != ":memory:":
            self.context.pop()
            raise RuntimeError("Admin feature tests require in-memory SQLite.")
        db.create_all()
        self.previous_client = app.test_client_class
        app.test_client_class = FeatureClient
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.password = "Admin-feature-test-123!"
        self.admin = self.account("admin", Role.ADMIN)
        self.doctor = self.account("doctor", Role.DOCTOR)
        self.patient = self.account("patient", Role.PATIENT)
        result = app.test_cli_runner().invoke(args=["seed-admin-demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.login("admin")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        app.test_client_class = self.previous_client
        self.context.pop()

    def account(self, username, role):
        return dao.create_account(dict(
            tenDangNhap=username, role=role, password=self.password, trangThai=True,
            hoTen="Kiểm thử", soDienThoai="0900000000", gioiTinh="Khác", namSinh=2000,
            diaChi="Địa chỉ kiểm thử", chuyenKhoa="Kiểm thử",
        ))

    def post(self, url, data=None, client=None):
        client = client or self.client
        client.get("/login", follow_redirects=True)
        with client.session_transaction() as session:
            csrf = session["csrf_token"]
        return client.post(url, data={**(data or {}), "csrf_token": csrf})

    def login(self, username, client=None):
        return self.post("/login", dict(tenDangNhap=username, matKhau=self.password), client)

    def medicine_form(self, **changes):
        return dict(maThuoc="T001", tenThuoc="Thuốc kiểm thử", donGia="1234.50",
                    soLuongTon="10", maDonVi="SAMPLE-VIEN", **changes)

    def exam(self, code, day, *, status="DA_LAP", medicines=(), invoice=None):
        exam = PhieuKham(maPhieuKham=code, ngayKham=day, trieuChung="Kiểm thử",
                         benhNhan=self.patient.benhNhan, bacSi=self.doctor.nhanVien.bacSi,
                         trangThai=status)
        for medicine, quantity in medicines:
            exam.chiTietDonThuocs.append(ChiTietDonThuoc(
                maThuoc=medicine, soLuong=quantity, cachDung="Dữ liệu kiểm thử",
            ))
        db.session.add(exam)
        if invoice:
            fee, amount, paid, invoice_day = invoice
            db.session.add(HoaDon(ngayLap=datetime.combine(invoice_day, time(12, 30)),
                                  tienKham=float(fee), tienThuoc=float(amount),
                                  tongTien=float(fee) + float(amount),
                                  trangThai="DA_THANH_TOAN" if paid else "CHUA_THANH_TOAN",
                                  phieuKham=exam, maNV=self.admin.nhanVien.maNV))
        db.session.commit()
        return exam

    def test_monthly_totals_distinct_patients_and_no_invoice_fanout(self):
        self.exam("1", date(2026, 11, 1), medicines=(("SAMPLE-T001", 2), ("SAMPLE-T002", 3)),
                  invoice=("100000", "25000", True, date(2026, 11, 1)))
        self.exam("2", date(2026, 11, 1), medicines=(("SAMPLE-T001", 4),),
                  invoice=("100000", "50000", True, date(2026, 11, 2)))
        self.exam("unpaid", date(2026, 11, 2), medicines=(("SAMPLE-T001", 1),),
                  invoice=("100000", "25000", False, date(2026, 11, 2)))
        self.exam("draft", date(2026, 11, 2), status="NHAP", medicines=(("SAMPLE-T001", 100),))
        self.exam("outside", date(2026, 12, 1), medicines=(("SAMPLE-T001", 100),),
                  invoice=("100000", "25000", True, date(2026, 12, 1)))
        report = dao.monthly_reports(2026, 11)
        self.assertEqual(report["total"], Decimal("275000.00"))
        self.assertEqual(len(report["revenue"]), 30)
        self.assertEqual(report["revenue"][0]["amount"], Decimal("125000.00"))
        self.assertEqual(report["revenue"][0]["patients"], 1)
        self.assertEqual(report["patient_visits"], 2)
        self.assertAlmostEqual(sum(row["ratio"] for row in report["revenue"]), Decimal("100"))
        by_code = {row["code"]: row for row in report["medicines"]}
        self.assertEqual(by_code["SAMPLE-T001"]["quantity"], 7)
        self.assertEqual(by_code["SAMPLE-T001"]["uses"], 3)
        self.assertEqual(by_code["SAMPLE-T002"]["quantity"], 3)
        response = self.client.get("/admin/reports?month=2026-11")
        self.assertEqual(response.status_code, 200)
        self.assertIn("275,000.00", response.get_data(as_text=True))
        self.assertIn("js/admin/reports.js", response.get_data(as_text=True))

    def test_empty_month_leap_year_and_december_boundary(self):
        report = dao.monthly_reports(2024, 2)
        self.assertEqual(len(report["revenue"]), 29)
        self.assertEqual(report["total"], 0)
        self.assertTrue(all(row["ratio"] == 0 for row in report["revenue"]))
        self.assertEqual(report["medicines"], [])
        self.assertEqual(len(dao.monthly_reports(2026, 12)["revenue"]), 31)
        for month in ("oops", "2026-13", "0000-01", "9999-12"):
            self.assertEqual(self.client.get("/admin/reports", query_string={"month": month}).status_code, 400)

    def test_medicine_crud_search_pagination_and_modal_errors(self):
        self.assertEqual(self.post("/admin/medicines/new?modal=1", self.medicine_form()).status_code, 204)
        medicine = db.session.get(Thuoc, "T001")
        self.assertEqual(medicine.donGia, 1234.5)
        self.assertEqual(medicine.donVi.maDonVi, "SAMPLE-VIEN")
        for changes in ({"donGia": "NaN"}, {"donGia": "-1"}, {"donGia": "1.234"},
                        {"soLuongTon": "1.5"}, {"maDonVi": "missing"}, {"tenThuoc": " "}):
            response = self.post("/admin/medicines/T001/edit?modal=1",
                                 {**self.medicine_form(), **changes})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(medicine.donGia, 1234.5)
        self.assertEqual(self.post("/admin/medicines/T001/edit", {
            **self.medicine_form(), "tenThuoc": "Tên mới", "maThuoc": "CHANGED", "soLuongTon": "0",
        }).status_code, 302)
        self.assertEqual(medicine.maThuoc, "T001")
        self.assertEqual(medicine.soLuongTon, 0)
        for index in range(11):
            self.post("/admin/medicines/new", {
                **self.medicine_form(), "maThuoc": f"T{index + 10}", "tenThuoc": f"Search {index}",
            })
        filtered = self.client.get("/admin/medicines?q=Search").get_data(as_text=True)
        self.assertIn("11 kết quả", filtered)
        self.assertIn("page=2", filtered)
        self.assertIn("js/admin/catalog.js", filtered)
        self.assertEqual(self.client.get("/admin/medicines?q=Search&page=2").status_code, 200)
        self.assertEqual(self.post("/admin/medicines/T001/delete").status_code, 302)
        self.assertIsNone(db.session.get(Thuoc, "T001"))

    def test_unit_crud_and_referenced_records_cannot_be_deleted(self):
        self.assertEqual(self.post("/admin/units/new", {
            "maDonVi": "NEW", "tenDonVi": "Đơn vị mới",
        }).status_code, 302)
        self.post("/admin/units/NEW/edit", {"tenDonVi": "Đã sửa"})
        self.assertEqual(db.session.get(DonViThuoc, "NEW").tenDonVi, "Đã sửa")
        self.assertIn("Đã sửa", self.client.get("/admin/units?q=Đã").get_data(as_text=True))
        self.post("/admin/units/NEW/delete")
        self.assertIsNone(db.session.get(DonViThuoc, "NEW"))
        self.post("/admin/units/SAMPLE-VIEN/delete")
        self.assertIsNotNone(db.session.get(DonViThuoc, "SAMPLE-VIEN"))
        self.exam("used", date(2026, 11, 1), medicines=(("SAMPLE-T001", 1),))
        self.post("/admin/medicines/SAMPLE-T001/delete")
        self.assertIsNotNone(db.session.get(Thuoc, "SAMPLE-T001"))
        self.assertIn("Không thể xóa", self.client.get("/admin/medicines").get_data(as_text=True))

    def test_regulations_validate_atomically_and_preserve_invoice_amounts(self):
        self.exam("fee", date(2026, 11, 1), invoice=("100000", "0", True, date(2026, 11, 1)))
        self.post("/admin/regulations", {"fee": "150000.50", "maximum": "50"})
        self.assertEqual(db.session.get(QuyDinh, "TIEN_KHAM").giaTri, Decimal("150000.50"))
        self.assertEqual(db.session.get(QuyDinh, "SO_BENH_NHAN_TOI_DA").laySoBenhNhanToiDa(), 50)
        self.assertEqual(db.session.scalar(db.select(HoaDon)).tienKham, 100000)
        for maximum in ("0", "1.5", "100001", "bad"):
            response = self.post("/admin/regulations", {"fee": "200000", "maximum": maximum})
            self.assertIn('role="alert"', response.get_data(as_text=True))
            self.assertEqual(db.session.get(QuyDinh, "TIEN_KHAM").giaTri, Decimal("150000.50"))
        self.post("/admin/regulations", {"fee": "NaN", "maximum": "40"})
        self.assertEqual(db.session.get(QuyDinh, "SO_BENH_NHAN_TOI_DA").laySoBenhNhanToiDa(), 50)

    def test_non_admin_authorization_csrf_and_database_failures(self):
        other = app.test_client()
        self.login("doctor", other)
        for path in ("/admin/reports", "/admin/medicines", "/admin/units",
                     "/admin/regulations", "/admin/medicines/new", "/admin/units/new"):
            self.assertEqual(other.get(path).status_code, 403)
        for path in ("/admin/medicines/new", "/admin/units/new",
                     "/admin/medicines/SAMPLE-T001/delete", "/admin/regulations"):
            self.assertEqual(self.post(path, {}, other).status_code, 403)
            self.assertEqual(self.client.post(path, data={}).status_code, 400)
        with self.assertLogs(app.logger, level="ERROR"), patch.object(
            dao, "monthly_reports", side_effect=OperationalError("select", {}, Exception("test")),
        ):
            self.assertEqual(self.client.get("/admin/reports").status_code, 503)

    def test_sample_initialization_is_repeatable_and_preserves_edits(self):
        medicine = db.session.get(Thuoc, "SAMPLE-T001")
        medicine.soLuongTon = 5
        db.session.get(QuyDinh, "TIEN_KHAM").giaTri = Decimal("200000")
        db.session.commit()
        result = app.test_cli_runner().invoke(args=["seed-admin-demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Thuoc)), 3)
        self.assertEqual(medicine.soLuongTon, 5)
        self.assertEqual(db.session.get(QuyDinh, "TIEN_KHAM").giaTri, Decimal("200000"))
