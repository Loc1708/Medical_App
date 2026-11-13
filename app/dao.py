from __future__ import annotations

import re
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import app, db
from app.models import (
    BacSi, BenhNhan, ChiTietDonThuoc, DanhSachKham, DonViThuoc, HoaDon,
    NhanVien, PhieuKham, QuyDinh, Role, TaiKhoan, Thuoc,
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


def patient_exam_registrations(patient_id: int) -> list[DanhSachKham]:
    return list(db.session.scalars(
        db.select(DanhSachKham)
        .where(DanhSachKham.maBN == patient_id)
        .order_by(DanhSachKham.ngayDangKy.desc(), DanhSachKham.maDSKham.desc())
    ))


def register_patient_exam(
    patient: BenhNhan,
    *,
    name: str,
    gender: str,
    birth_year: int,
    address: str,
) -> DanhSachKham:
    registration = DanhSachKham(
        benhNhan=patient,
        hoTen=name,
        gioiTinh=gender,
        namSinh=birth_year,
        diaChi=address,
        ngayDangKy=datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None),
        trangThai="CHO_KHAM",
    )
    db.session.add(registration)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Patient exam registration failed.")
        raise
    return registration


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


def _lock_admin(actor_id: int) -> None:
    actor = db.session.scalar(db.select(TaiKhoan).where(
        TaiKhoan.maTK == actor_id,
    ).with_for_update().execution_options(populate_existing=True))
    if actor is None or actor.role != Role.ADMIN or not actor.trangThai:
        raise ValueError("Bạn không còn quyền quản trị.")


def _catalog_commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        app.logger.warning("Catalog update rejected by database constraints.")
        raise ValueError("Mã đã tồn tại hoặc dữ liệu đang được sử dụng. Vui lòng tải lại trang.") from None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Catalog persistence failed.")
        raise


def parse_amount(value: str, *, positive: bool = False) -> Decimal:
    try:
        amount = Decimal(value.strip())
    except InvalidOperation:
        raise ValueError("Số tiền không hợp lệ.") from None
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999999.99"):
        raise ValueError("Số tiền phải từ 0 đến 9999999999999.99.")
    if positive and amount == 0:
        raise ValueError("Số tiền phải lớn hơn 0.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Số tiền chỉ được có tối đa 2 chữ số thập phân.")
    return amount


def _catalog_code(value: str) -> str:
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{1,20}", code):
        raise ValueError("Mã gồm 1–20 chữ không dấu, số, gạch ngang hoặc gạch dưới.")
    return code


def save_medicine(actor_id: int, form, code: str | None = None) -> Thuoc:
    _lock_admin(actor_id)
    name = form.get("tenThuoc", "").strip()
    if not name or len(name) > 100:
        raise ValueError("Tên thuốc bắt buộc, tối đa 100 ký tự.")
    amount = parse_amount(form.get("donGia", ""))
    stock = form.get("soLuongTon", "").strip()
    if not re.fullmatch(r"[0-9]{1,9}", stock):
        raise ValueError("Số lượng phải là số nguyên từ 0 đến 999999999.")
    unit = db.session.scalar(db.select(DonViThuoc).where(
        DonViThuoc.maDonVi == form.get("maDonVi", ""),
    ).with_for_update())
    if unit is None:
        raise ValueError("Đơn vị thuốc không tồn tại. Hãy chọn lại.")
    if code is None:
        medicine = Thuoc()
        medicine.maThuoc = _catalog_code(form.get("maThuoc", ""))
        db.session.add(medicine)
    else:
        medicine = db.session.scalar(db.select(Thuoc).where(
            Thuoc.maThuoc == code,
        ).with_for_update().execution_options(populate_existing=True))
        if medicine is None:
            raise ValueError("Thuốc không còn tồn tại.")
    medicine.tenThuoc = name
    medicine.donGia = float(amount)
    medicine.soLuongTon = int(stock)
    medicine.donVi = unit
    _catalog_commit()
    return medicine


def save_unit(actor_id: int, form, code: str | None = None) -> DonViThuoc:
    _lock_admin(actor_id)
    name = form.get("tenDonVi", "").strip()
    if not name or len(name) > 50:
        raise ValueError("Tên đơn vị bắt buộc, tối đa 50 ký tự.")
    if code is None:
        unit = DonViThuoc()
        unit.maDonVi = _catalog_code(form.get("maDonVi", ""))
        db.session.add(unit)
    else:
        unit = db.session.scalar(db.select(DonViThuoc).where(
            DonViThuoc.maDonVi == code,
        ).with_for_update().execution_options(populate_existing=True))
        if unit is None:
            raise ValueError("Đơn vị không còn tồn tại.")
    unit.tenDonVi = name
    _catalog_commit()
    return unit


def delete_catalog_item(actor_id: int, code: str, *, unit: bool = False) -> None:
    _lock_admin(actor_id)
    model = DonViThuoc if unit else Thuoc
    key = DonViThuoc.maDonVi if unit else Thuoc.maThuoc
    item = db.session.scalar(db.select(model).where(key == code).with_for_update())
    if item is None:
        raise ValueError("Dữ liệu không còn tồn tại.")
    references = db.select(Thuoc.maThuoc).where(Thuoc.maDonVi == code) if unit else (
        db.select(ChiTietDonThuoc.maThuoc).where(ChiTietDonThuoc.maThuoc == code)
    )
    if db.session.scalar(references.limit(1)) is not None:
        raise ValueError("Không thể xóa: dữ liệu đang được sử dụng trong thuốc hoặc đơn thuốc.")
    db.session.delete(item)
    _catalog_commit()


def update_regulations(actor_id: int, fee: str, maximum: str) -> None:
    _lock_admin(actor_id)
    amount = parse_amount(fee, positive=True)
    if not re.fullmatch(r"[0-9]{1,6}", maximum.strip()):
        raise ValueError("Số bệnh nhân tối đa phải là số nguyên từ 1 đến 100000.")
    rules = {rule.maQD: rule for rule in db.session.scalars(
        db.select(QuyDinh).order_by(QuyDinh.maQD).with_for_update()
    )}
    if not {"TIEN_KHAM", "SO_BENH_NHAN_TOI_DA"}.issubset(rules):
        raise ValueError("Chưa khởi tạo quy định. Hãy chạy seed-admin-demo trước.")
    rules["TIEN_KHAM"].capNhatTienKham(amount)
    rules["SO_BENH_NHAN_TOI_DA"].capNhatQuyDinhKham(int(maximum))
    _catalog_commit()


def monthly_reports(year: int, month: int) -> dict:
    start = date(year, month, 1)
    days = calendar.monthrange(year, month)[1]
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    invoice_day = db.func.date(HoaDon.ngayLap)
    revenue_by_day = {
        date.fromisoformat(row["day"]) if isinstance(row["day"], str) else row["day"]:
        Decimal(str(row["amount"])).quantize(Decimal("0.01"))
        for row in db.session.execute(
            db.select(invoice_day.label("day"),
                      db.func.sum(HoaDon.tienKham + HoaDon.tienThuoc).label("amount"))
            .where(HoaDon.ngayLap >= start, HoaDon.ngayLap < end,
                   HoaDon.trangThai == "DA_THANH_TOAN")
            .group_by(invoice_day)
        ).mappings()
    }
    patients_by_day = {row["day"]: int(row["patients"]) for row in db.session.execute(
        db.select(PhieuKham.ngayKham.label("day"),
                  db.func.count(db.distinct(PhieuKham.maBN)).label("patients"))
        .where(PhieuKham.ngayKham >= start, PhieuKham.ngayKham < end,
               PhieuKham.trangThai == "DA_LAP")
        .group_by(PhieuKham.ngayKham)
    ).mappings()}
    total = sum(revenue_by_day.values(), Decimal("0"))
    revenue = []
    for day in range(1, days + 1):
        current = date(year, month, day)
        amount = revenue_by_day.get(current, Decimal("0"))
        revenue.append(dict(day=current, patients=patients_by_day.get(current, 0),
                            amount=amount, ratio=amount * 100 / total if total else Decimal("0")))
    medicines = [dict(row) for row in db.session.execute(
        db.select(Thuoc.maThuoc.label("code"), Thuoc.tenThuoc.label("name"),
                  DonViThuoc.tenDonVi.label("unit"),
                  db.func.sum(ChiTietDonThuoc.soLuong).label("quantity"),
                  db.func.count(db.distinct(ChiTietDonThuoc.maPhieuKham)).label("uses"))
        .join(ChiTietDonThuoc, ChiTietDonThuoc.maThuoc == Thuoc.maThuoc)
        .join(PhieuKham, PhieuKham.maPhieuKham == ChiTietDonThuoc.maPhieuKham)
        .join(DonViThuoc, DonViThuoc.maDonVi == Thuoc.maDonVi)
        .where(PhieuKham.ngayKham >= start, PhieuKham.ngayKham < end,
               PhieuKham.trangThai == "DA_LAP")
        .group_by(Thuoc.maThuoc, Thuoc.tenThuoc, DonViThuoc.tenDonVi)
        .order_by(db.func.sum(ChiTietDonThuoc.soLuong).desc(), Thuoc.maThuoc)
    ).mappings()]
    return dict(revenue=revenue, medicines=medicines, total=total,
                patient_visits=sum(row["patients"] for row in revenue))
