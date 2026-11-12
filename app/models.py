from __future__ import annotations

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
