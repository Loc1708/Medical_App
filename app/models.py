from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class Role(str, Enum):
    PATIENT = "PATIENT"
    NURSE = "NURSE"
    CASHIER = "CASHIER"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"

    @property
    def label(self) -> str:
        return {
            "PATIENT": "Bệnh nhân", "NURSE": "Y tá", "CASHIER": "Thu ngân",
            "DOCTOR": "Bác sĩ", "ADMIN": "Quản trị",
        }[self.value]


class TaiKhoan(db.Model):
    __tablename__ = "TaiKhoan"
    __table_args__ = {"sqlite_autoincrement": True}

    maTK: Mapped[int] = mapped_column("MaTK", db.Integer, primary_key=True, autoincrement=True)
    tenDangNhap: Mapped[str] = mapped_column(db.String(80), nullable=False, unique=True)
    matKhau: Mapped[str] = mapped_column(db.String(255), nullable=False)
    role: Mapped[Role] = mapped_column(db.Enum(Role, native_enum=False, create_constraint=True), nullable=False)
    trangThai: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)
    nhanVien: Mapped[NhanVien | None] = relationship(back_populates="taiKhoan", uselist=False)
    benhNhan: Mapped[BenhNhan | None] = relationship(back_populates="taiKhoan", uselist=False)

    def get_id(self) -> str:
        return str(self.maTK)

    @property
    def maHoSo(self) -> str:
        profile = self.benhNhan if self.role == Role.PATIENT else self.nhanVien
        return profile.maHienThi if profile else ""

    @property
    def is_active(self) -> bool:
        return self.trangThai

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def hoTen(self) -> str:
        profile = self.benhNhan if self.role == Role.PATIENT else self.nhanVien
        return profile.hoTen if profile else self.tenDangNhap

    def set_password(self, password: str) -> None:
        self.matKhau = generate_password_hash(password)

    def dangNhap(self, tenDangNhap: str, matKhau: str) -> bool:
        return (
            self.trangThai and self.tenDangNhap == tenDangNhap.strip().lower()
            and check_password_hash(self.matKhau, matKhau)
        )

    def dangXuat(self) -> bool:
        from flask_login import current_user, logout_user

        if not current_user.is_authenticated or current_user.get_id() != self.get_id():
            return False
        logout_user()
        return True

    def doiMatKhau(self, tenDangNhap: str, matKhau: str) -> bool:
        # Authorization and password policy are enforced by the calling DAO.
        if self.tenDangNhap != tenDangNhap.strip().lower():
            raise ValueError("Tên đăng nhập không khớp tài khoản.")
        self.set_password(matKhau)
        return True


class NhanVien(db.Model):
    __tablename__ = "NhanVien"
    __table_args__ = {"sqlite_autoincrement": True}

    maNV: Mapped[int] = mapped_column("MaNV", db.Integer, primary_key=True, autoincrement=True)
    hoTen: Mapped[str] = mapped_column(db.String(100), nullable=False)
    soDienThoai: Mapped[str] = mapped_column(db.String(20), nullable=False)
    maTK: Mapped[int] = mapped_column("MaTK", db.ForeignKey("TaiKhoan.MaTK"), unique=True, nullable=False)
    taiKhoan: Mapped[TaiKhoan] = relationship(back_populates="nhanVien")
    bacSi: Mapped[BacSi | None] = relationship(back_populates="nhanVien", uselist=False)

    @property
    def maHienThi(self) -> str:
        prefix = {
            Role.NURSE: "YT", Role.CASHIER: "TN", Role.DOCTOR: "BS", Role.ADMIN: "QT",
        }.get(self.taiKhoan.role, "NV")
        return f"{prefix}-{self.maNV:04d}"


class BacSi(db.Model):
    __tablename__ = "BacSi"

    maNV: Mapped[int] = mapped_column("MaNV", db.ForeignKey("NhanVien.MaNV"), primary_key=True, autoincrement=False)
    chuyenKhoa: Mapped[str] = mapped_column(db.String(100), nullable=False)
    nhanVien: Mapped[NhanVien] = relationship(back_populates="bacSi")
    phieuKhams: Mapped[list[PhieuKham]] = relationship(back_populates="bacSi")


class BenhNhan(db.Model):
    __tablename__ = "BenhNhan"
    __table_args__ = {"sqlite_autoincrement": True}

    maBN: Mapped[int] = mapped_column("MaBN", db.Integer, primary_key=True, autoincrement=True)
    hoTen: Mapped[str] = mapped_column(db.String(100), nullable=False)
    gioiTinh: Mapped[str] = mapped_column(db.String(10), nullable=False)
    namSinh: Mapped[int] = mapped_column(db.Integer, nullable=False)
    diaChi: Mapped[str] = mapped_column(db.String(255), nullable=False)
    soDienThoai: Mapped[str] = mapped_column(db.String(20), nullable=False)
    maTK: Mapped[int] = mapped_column("MaTK", db.ForeignKey("TaiKhoan.MaTK"), unique=True, nullable=False)
    taiKhoan: Mapped[TaiKhoan] = relationship(back_populates="benhNhan")

    @property
    def maHienThi(self) -> str:
        return f"BN-{self.maBN:04d}"

    phieuKhams: Mapped[list[PhieuKham]] = relationship(back_populates="benhNhan")
    dangKyKhams: Mapped[list[DanhSachKham]] = relationship(back_populates="benhNhan")


class DanhSachKham(db.Model):
    __tablename__ = "DanhSachKham"
    __table_args__ = {"sqlite_autoincrement": True}

    maDSKham: Mapped[int] = mapped_column("MaDSKham", db.Integer, primary_key=True, autoincrement=True)
    maBN: Mapped[int] = mapped_column("MaBN", db.ForeignKey("BenhNhan.MaBN"), nullable=False)
    hoTen: Mapped[str] = mapped_column("HoTen", db.String(100), nullable=False)
    gioiTinh: Mapped[str] = mapped_column("GioiTinh", db.String(10), nullable=False)
    namSinh: Mapped[int] = mapped_column("NamSinh", db.Integer, nullable=False)
    diaChi: Mapped[str] = mapped_column("DiaChi", db.String(255), nullable=False)
    ngayDangKy: Mapped[datetime] = mapped_column("NgayDangKy", db.DateTime, nullable=False)
    trangThai: Mapped[str] = mapped_column(
        "TrangThai", db.String(20), nullable=False, default="CHO_KHAM",
    )
    benhNhan: Mapped[BenhNhan] = relationship(back_populates="dangKyKhams")


class DonViThuoc(db.Model):
    __tablename__ = "DonViThuoc"

    maDonVi: Mapped[str] = mapped_column("MaDonVi", db.String(20), primary_key=True)
    tenDonVi: Mapped[str] = mapped_column(db.String(50), nullable=False)
    thuocs: Mapped[list[Thuoc]] = relationship(back_populates="donVi")


class Thuoc(db.Model):
    __tablename__ = "Thuoc"

    maThuoc: Mapped[str] = mapped_column("MaThuoc", db.String(20), primary_key=True)
    tenThuoc: Mapped[str] = mapped_column(db.String(100), nullable=False)
    donGia: Mapped[float] = mapped_column(db.Float, nullable=False)
    soLuongTon: Mapped[int] = mapped_column(db.Integer, nullable=False)
    maDonVi: Mapped[str] = mapped_column(
        "MaDonVi", db.ForeignKey("DonViThuoc.MaDonVi"), nullable=False,
    )
    donVi: Mapped[DonViThuoc] = relationship(back_populates="thuocs")
    chiTietDonThuocs: Mapped[list[ChiTietDonThuoc]] = relationship(back_populates="thuoc")


class PhieuKham(db.Model):
    __tablename__ = "PhieuKham"

    maPhieuKham: Mapped[str] = mapped_column("MaPhieuKham", db.String(36), primary_key=True)
    ngayKham: Mapped[date] = mapped_column(db.Date, nullable=False)
    trieuChung: Mapped[str] = mapped_column(db.Text, nullable=False)
    trangThai: Mapped[str] = mapped_column(
        db.String(20), nullable=False, default="DA_LAP", server_default="DA_LAP",
    )
    maBN: Mapped[int] = mapped_column(
        "MaBN", db.ForeignKey("BenhNhan.MaBN"), nullable=False,
    )
    maNV: Mapped[int] = mapped_column(
        "MaNV", db.ForeignKey("BacSi.MaNV"), nullable=False,
    )
    benhNhan: Mapped[BenhNhan] = relationship(back_populates="phieuKhams")
    bacSi: Mapped[BacSi] = relationship(back_populates="phieuKhams")
    chiTietDonThuocs: Mapped[list[ChiTietDonThuoc]] = relationship(back_populates="phieuKham")


class ChiTietDonThuoc(db.Model):
    __tablename__ = "ChiTietDonThuoc"

    maThuoc: Mapped[str] = mapped_column(
        "MaThuoc", db.ForeignKey("Thuoc.MaThuoc"), primary_key=True,
    )
    maPhieuKham: Mapped[str] = mapped_column(
        "MaPhieuKham", db.ForeignKey("PhieuKham.MaPhieuKham"), primary_key=True,
    )
    soLuong: Mapped[int] = mapped_column(db.Integer, nullable=False)
    cachDung: Mapped[str] = mapped_column(db.String(255), nullable=False)
    thuoc: Mapped[Thuoc] = relationship(back_populates="chiTietDonThuocs")
    phieuKham: Mapped[PhieuKham] = relationship(back_populates="chiTietDonThuocs")
