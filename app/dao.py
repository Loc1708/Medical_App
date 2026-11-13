from __future__ import annotations

import re
from datetime import date
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import app, db
from app.models import (
    BacSi, BenhNhan, ChiTietDonThuoc, NhanVien, PhieuKham, Role, TaiKhoan, Thuoc,
)
from app.utils import validate_password


def authenticate(username: str, password: str):
    if len(username) > 80 or not 1 <= len(password) <= 128:
        return None
    account = db.session.scalar(
        db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == username.strip().lower())
    )
    return account if account and account.dangNhap(username, password) else None


def find_patient_by_code(code: str) -> BenhNhan | None:
    match = re.fullmatch(r"(?:BN-)?(\d{1,10})", code.strip(), re.IGNORECASE)
    if not match:
        return None
    return db.session.get(BenhNhan, int(match.group(1)))


def search_medicines(keyword: str, *, limit: int = 30) -> list[Thuoc]:
    keyword = keyword.strip()
    if not keyword:
        return []
    return list(db.session.scalars(
        db.select(Thuoc)
        .where(Thuoc.tenThuoc.contains(keyword, autoescape=True), Thuoc.soLuongTon > 0)
        .order_by(Thuoc.tenThuoc, Thuoc.maThuoc)
        .limit(limit)
    ))


def patient_exam_history(patient_id: int) -> list[PhieuKham]:
    return list(db.session.scalars(
        db.select(PhieuKham)
        .where(PhieuKham.maBN == patient_id)
        .order_by(PhieuKham.ngayKham.desc(), PhieuKham.maPhieuKham.desc())
    ))


def find_doctor_draft(exam_id: str, doctor_id: int) -> PhieuKham | None:
    return db.session.scalar(
        db.select(PhieuKham).where(
            PhieuKham.maPhieuKham == exam_id,
            PhieuKham.maNV == doctor_id,
            PhieuKham.trangThai == "NHAP",
        )
    )


def doctor_drafts(doctor_id: int) -> list[PhieuKham]:
    return list(db.session.scalars(
        db.select(PhieuKham)
        .where(
            PhieuKham.maNV == doctor_id,
            PhieuKham.trangThai == "NHAP",
        )
        .order_by(PhieuKham.ngayKham.desc(), PhieuKham.maPhieuKham.desc())
    ))


def delete_doctor_draft(exam_id: str, doctor_id: int) -> bool:
    draft = find_doctor_draft(exam_id, doctor_id)
    if draft is None:
        return False
    try:
        for detail in list(draft.chiTietDonThuocs):
            db.session.delete(detail)
        db.session.delete(draft)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Doctor draft deletion failed.")
        raise
    return True


def create_exam(
    patient: BenhNhan,
    doctor: BacSi,
    symptoms: str,
    prescriptions: list[dict],
    exam_date: date,
    status: str = "DA_LAP",
    exam: PhieuKham | None = None,
) -> PhieuKham:
    if exam is None:
        exam = PhieuKham(maPhieuKham=str(uuid4()))
        db.session.add(exam)
    else:
        for detail in list(exam.chiTietDonThuocs):
            db.session.delete(detail)
        exam.chiTietDonThuocs.clear()

    exam.ngayKham = exam_date
    exam.trieuChung = symptoms
    exam.trangThai = status
    exam.benhNhan = patient
    exam.bacSi = doctor
    for prescription in prescriptions:
        exam.chiTietDonThuocs.append(ChiTietDonThuoc(
            thuoc=prescription["medicine"],
            soLuong=prescription["quantity"],
            cachDung=prescription["instructions"],
        ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        app.logger.warning("Exam creation rejected by database constraints.")
        raise ValueError("Phiếu khám hoặc chi tiết đơn thuốc không hợp lệ.") from None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Exam creation failed.")
        raise
    return exam


def _update_profile(account: TaiKhoan, data: dict) -> None:
    if data["role"] == Role.PATIENT:
        if account.benhNhan is None:
            account.benhNhan = BenhNhan()
        profile = account.benhNhan
        profile.namSinh = data["namSinh"]
        profile.gioiTinh = data["gioiTinh"]
        profile.diaChi = data["diaChi"]
    else:
        if account.nhanVien is None:
            account.nhanVien = NhanVien()
        profile = account.nhanVien
        if data["role"] == Role.DOCTOR:
            if profile.bacSi is None:
                profile.bacSi = BacSi()
            profile.bacSi.chuyenKhoa = data["chuyenKhoa"]
    profile.hoTen = data["hoTen"]
    profile.soDienThoai = data["soDienThoai"]


def create_account(data: dict) -> TaiKhoan:
    validate_password(data["password"])
    account = TaiKhoan()
    account.tenDangNhap = data["tenDangNhap"]
    account.role = data["role"]
    account.trangThai = data["trangThai"]
    account.set_password(data["password"])
    _update_profile(account, data)
    db.session.add(account)
    _commit()
    return account


def _lock_managed_account(actor_id: int, target_id: int) -> TaiKhoan:
    # Lock both accounts so concurrent admins cannot disable one another's last access.
    locked = list(db.session.scalars(
        db.select(TaiKhoan).where(TaiKhoan.maTK.in_([actor_id, target_id]))
        .order_by(TaiKhoan.maTK).with_for_update().execution_options(populate_existing=True)
    ))
    accounts = {account.maTK: account for account in locked}
    actor = accounts.get(actor_id)
    target = accounts.get(target_id)
    if actor is None or actor.role != Role.ADMIN or not actor.trangThai:
        db.session.rollback()
        raise ValueError("Bạn không còn quyền quản trị.")
    if target is None:
        db.session.rollback()
        raise ValueError("Tài khoản không còn tồn tại.")
    return target


def update_account(actor_id: int, target_id: int, data: dict) -> TaiKhoan:
    target = _lock_managed_account(actor_id, target_id)
    if actor_id == target_id and (data["role"] != Role.ADMIN or not data["trangThai"]):
        db.session.rollback()
        raise ValueError("Không được tự khóa hoặc tự bỏ quyền quản trị của mình.")
    if data["password"]:
        validate_password(data["password"])
        target.doiMatKhau(target.tenDangNhap, data["password"])
    target.tenDangNhap = data["tenDangNhap"]
    target.role = data["role"]
    target.trangThai = data["trangThai"]
    _update_profile(target, data)
    _commit()
    return target


def set_account_status(actor_id: int, target_id: int, active: bool) -> None:
    target = _lock_managed_account(actor_id, target_id)
    if actor_id == target_id and not active:
        db.session.rollback()
        raise ValueError("Không được tự khóa tài khoản quản trị của mình.")
    target.trangThai = active
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        app.logger.warning("Account update rejected by database uniqueness constraints.")
        raise ValueError("Tên đăng nhập đã tồn tại hoặc hồ sơ đã được liên kết.") from None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Account persistence failed.")
        raise
