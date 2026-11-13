import unittest
from datetime import date

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app import db
from app.models import (
    BacSi, BenhNhan, ChiTietDonThuoc, DonViThuoc, NhanVien, PhieuKham,
    Role, TaiKhoan, Thuoc,
)


class ClinicalModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        db.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_doctor_workflow_tables_and_relationships(self):
        expected_tables = {
            "DonViThuoc", "Thuoc", "PhieuKham", "ChiTietDonThuoc",
        }
        self.assertTrue(expected_tables.issubset(inspect(self.engine).get_table_names()))

        doctor_account = TaiKhoan(
            tenDangNhap="doctor", matKhau="test-hash", role=Role.DOCTOR, trangThai=True,
        )
        doctor_employee = NhanVien(
            hoTen="Bác sĩ kiểm thử", soDienThoai="0900000000",
            taiKhoan=doctor_account,
        )
        doctor = BacSi(chuyenKhoa="Nội khoa", nhanVien=doctor_employee)
        patient_account = TaiKhoan(
            tenDangNhap="patient", matKhau="test-hash", role=Role.PATIENT, trangThai=True,
        )
        patient = BenhNhan(
            hoTen="Bệnh nhân kiểm thử", gioiTinh="Khác", namSinh=2000,
            diaChi="Địa chỉ kiểm thử", soDienThoai="0900000001",
            taiKhoan=patient_account,
        )
        unit = DonViThuoc(maDonVi="VIEN", tenDonVi="Viên")
        medicine = Thuoc(
            maThuoc="T001", tenThuoc="Thuốc kiểm thử", donGia=1000.0,
            soLuongTon=20, donVi=unit,
        )
        exam = PhieuKham(
            maPhieuKham="PK-0001", ngayKham=date(2026, 11, 13),
            trieuChung="Đau đầu", benhNhan=patient, bacSi=doctor,
        )
        detail = ChiTietDonThuoc(
            thuoc=medicine, phieuKham=exam, soLuong=2, cachDung="Ngày 2 lần",
        )

        self.session.add_all([doctor, patient, unit, medicine, exam, detail])
        self.session.commit()
        self.session.expire_all()

        saved_exam = self.session.get(PhieuKham, "PK-0001")
        self.assertEqual(saved_exam.benhNhan.hoTen, "Bệnh nhân kiểm thử")
        self.assertEqual(saved_exam.bacSi.chuyenKhoa, "Nội khoa")
        self.assertEqual(saved_exam.ngayKham, date(2026, 11, 13))
        self.assertEqual(saved_exam.trangThai, "DA_LAP")
        self.assertEqual(saved_exam.chiTietDonThuocs[0].thuoc.donVi.tenDonVi, "Viên")
        self.assertEqual(saved_exam.chiTietDonThuocs[0].soLuong, 2)


if __name__ == "__main__":
    unittest.main()
