from __future__ import annotations

import re
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import or_, cast, String
from sqlalchemy.orm import joinedload, selectinload
from app import app, db
from app.models import (
    BacSi, BenhNhan, ChiTietDanhSachKham, ChiTietDonThuoc, DanhSachKham,
    DonViThuoc, HoaDon, NhanVien, PhieuKham, QuyDinh, Role, TaiKhoan, Thuoc,
)
from app.utils import kiemTraMatKhau


ACTIVE_EXAM_STATUSES = ("CHO_KHAM", "DA_MO_LAI", "DA_XAC_NHAN")
NURSE_VISIBLE_STATUSES = (*ACTIVE_EXAM_STATUSES, "CHO_DUYET")


class DailyCapacityReached(ValueError):
    pass


class ConfirmedExamDay(ValueError):
    pass


class PastExamDate(ValueError):
    pass


def xacThucTaiKhoan(username: str, password: str):
    if len(username) > 80 or not 1 <= len(password) <= 128:
        return None
    account = db.session.scalar(
        db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == username.strip().lower())
    )
    return account if account and account.dangNhap(username, password) else None


def timKiemBenhNhanTheoId(code: str) -> BenhNhan | None:
    match = re.fullmatch(r"(?:BN-)?(\d{1,10})", code.strip(), re.IGNORECASE)
    if not match:
        return None
    return db.session.get(BenhNhan, int(match.group(1)))


def layThongTinBenhNhan(code: str) -> BenhNhan | None:
    return timKiemBenhNhanTheoId(code)


def timBenhNhanTheoMa(keyword: str, *, limit: int = 10) -> list[BenhNhan]:
    query = keyword.strip().upper()
    if query in {"B", "BN", "BN-"}:
        digits = ""
    elif query.startswith("BN-"):
        digits = query[3:]
    else:
        digits = query
    if digits and (not digits.isdigit() or len(digits) > 10):
        return []

    statement = db.select(BenhNhan).order_by(BenhNhan.maBN)
    if digits:
        conditions = []
        # Match substrings in the zero-padded display code without DB-specific string functions.
        for width in range(4, 11):
            if len(digits) > width:
                continue
            minimum = 1 if width == 4 else 10 ** (width - 1)
            maximum = 10 ** width - 1
            for start in range(width - len(digits) + 1):
                prefix = digits[:start]
                base = int(prefix + digits) if prefix + digits else 0
                scale = 10 ** (width - start - len(digits))
                lower = max(base * scale, minimum)
                upper = min(base * scale + scale - 1, maximum)
                if lower <= upper:
                    conditions.append(BenhNhan.maBN.between(lower, upper))
        if not conditions:
            return []
        statement = statement.where(or_(*conditions))
    return list(db.session.scalars(statement.limit(limit)))

#Cashier
def layHoaDonChuaThanhToan(ma_bn=None):
    res = (db.session.query(HoaDon)
           .join(PhieuKham, HoaDon.maPhieuKham == PhieuKham.maPhieuKham)
           .join(BenhNhan, PhieuKham.maBN == BenhNhan.maBN)
           .filter(HoaDon.trangThai == 'CHUA_THANH_TOAN'))

    if ma_bn:
        res = res.filter(BenhNhan.maBN == ma_bn)
    return res.all()
    

def thuNganTimBenhNhan(kw=None):
    if not kw or not kw.strip():
        return []

    kw = kw.strip()
    clean_kw = kw.upper().replace("BN-", "")

    dieu_kien = [BenhNhan.hoTen.contains(kw)]
    if clean_kw.isdigit():
        dieu_kien.append(cast(BenhNhan.maBN, String).contains(clean_kw))

    return BenhNhan.query.filter(or_(*dieu_kien)).limit(10).all()

def thanhToan(ma_hd):
    hd = HoaDon.query.get(ma_hd)
    if hd is None or hd.trangThai != 'CHUA_THANH_TOAN':
        return None

    hd.trangThai = 'DA_THANH_TOAN'   
    db.session.commit()              
    return hd

def timKiemThuoc(
    keyword: str = "",
    *,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Thuoc], int]:
    keyword = keyword.strip()[:100]
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("Số trang hoặc số dòng mỗi trang không hợp lệ.")
    conditions = [Thuoc.soLuongTon > 0]
    if keyword:
        search_term = keyword.lower()
        conditions.append(or_(
            db.func.lower(Thuoc.tenThuoc).contains(search_term, autoescape=True),
            db.func.lower(Thuoc.maThuoc).contains(search_term, autoescape=True),
        ))
    total = db.session.scalar(
        db.select(db.func.count()).select_from(Thuoc).where(*conditions)
    ) or 0
    return list(db.session.scalars(
        db.select(Thuoc)
        .where(*conditions)
        .order_by(Thuoc.tenThuoc, Thuoc.maThuoc)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )), total


def layThongTinThuoc(
    keyword: str = "",
    *,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Thuoc], int]:
    return timKiemThuoc(keyword, page=page, page_size=page_size)


def layLichSuKham(
    patient_id: int,
    *,
    page: int = 1,
    page_size: int = 5,
) -> tuple[list[PhieuKham], int]:
    total = db.session.scalar(
        db.select(db.func.count())
        .select_from(PhieuKham)
        .where(PhieuKham.maBN == patient_id)
    ) or 0
    exams = list(db.session.scalars(
        db.select(PhieuKham)
        .options(
            joinedload(PhieuKham.bacSi).joinedload(BacSi.nhanVien),
            selectinload(PhieuKham.chiTietDonThuocs)
            .joinedload(ChiTietDonThuoc.thuoc)
            .joinedload(Thuoc.donVi),
        )
        .where(PhieuKham.maBN == patient_id)
        .order_by(PhieuKham.ngayKham.desc(), PhieuKham.maPhieuKham.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ))
    return exams, total


def layLichSuBenhNhan(
    patient_id: int,
    *,
    page: int = 1,
    page_size: int = 5,
) -> tuple[list[PhieuKham], int]:
    return layLichSuKham(patient_id, page=page, page_size=page_size)


def layDanhSachLichSu(
    patient_id: int,
    *,
    page: int = 1,
    page_size: int = 5,
) -> tuple[list[PhieuKham], int]:
    return layLichSuBenhNhan(patient_id, page=page, page_size=page_size)


def layDangKyKhamCuaBenhNhan(patient_id: int) -> list[ChiTietDanhSachKham]:
    return list(db.session.scalars(
        db.select(ChiTietDanhSachKham)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .options(
            joinedload(ChiTietDanhSachKham.benhNhan),
            joinedload(ChiTietDanhSachKham.danhSachKham),
        )
        .where(ChiTietDanhSachKham.maBN == patient_id)
        .order_by(
            DanhSachKham.ngayKham.desc(),
            ChiTietDanhSachKham.ngayDangKy.desc(),
        )
    ))


def layGioiHanBenhNhanNgay(*, lock: bool = False) -> int:
    statement = db.select(QuyDinh).where(QuyDinh.maQD == "SO_BENH_NHAN_TOI_DA")
    if lock:
        statement = statement.with_for_update()
    rule = db.session.scalar(statement)
    if rule is None:
        raise ValueError("Chưa có quy định số bệnh nhân tối đa; hãy cập nhật quy định trước.")
    return rule.laySoBenhNhanToiDa()


def ngayHienTaiPhongKham() -> date:
    return datetime.now(timezone(timedelta(hours=7))).date()


def kiemTraSoLuongToiDa(exam_date: date) -> int | None:
    limit = layGioiHanBenhNhanNgay(lock=True)
    used_slots = set(db.session.scalars(
        db.select(ChiTietDanhSachKham.soThuTu)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai.in_(ACTIVE_EXAM_STATUSES),
            ChiTietDanhSachKham.soThuTu.is_not(None),
        ).with_for_update()
    ))
    if len(used_slots) >= limit:
        return None
    return next((slot for slot in range(1, limit + 1) if slot not in used_slots), None)


def _kiemTraNgayKhamChuaChot(exam_date: date) -> None:
    confirmed_registration = db.session.scalar(
        db.select(ChiTietDanhSachKham.maDSKham)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai == "DA_XAC_NHAN",
        )
        .limit(1)
        .with_for_update()
    )
    if confirmed_registration is not None:
        raise ConfirmedExamDay(
            f"Danh sách khám ngày {exam_date.strftime('%d/%m/%Y')} "
            "đã được xác nhận và chốt; không thể thêm bệnh nhân mới."
        )


def layDanhSachKham(
    exam_date: date,
) -> tuple[list[ChiTietDanhSachKham], list[ChiTietDanhSachKham]]:
    active = list(db.session.scalars(
        db.select(ChiTietDanhSachKham)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai.in_(ACTIVE_EXAM_STATUSES),
        ).options(joinedload(ChiTietDanhSachKham.benhNhan)).order_by(
            ChiTietDanhSachKham.soThuTu,
            ChiTietDanhSachKham.ngayDangKy,
            ChiTietDanhSachKham.maBN,
        )
    ))
    waiting = list(db.session.scalars(
        db.select(ChiTietDanhSachKham).where(
            ChiTietDanhSachKham.trangThai == "CHO_DUYET",
        ).options(
            joinedload(ChiTietDanhSachKham.benhNhan),
            joinedload(ChiTietDanhSachKham.danhSachKham),
        ).join(
            DanhSachKham,
            DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham,
        ).order_by(
            DanhSachKham.ngayKham,
            ChiTietDanhSachKham.ngayDangKy,
            ChiTietDanhSachKham.maBN,
        )
    ))
    return active, waiting


def layLichSuDanhSachDaChot() -> list[dict]:
    rows = db.session.execute(
        db.select(
            ChiTietDanhSachKham,
            BenhNhan.hoTen.label("name"),
            BenhNhan.soDienThoai.label("phone"),
            BenhNhan.gioiTinh.label("gender"),
            BenhNhan.namSinh.label("birth_year"),
        )
        .join(BenhNhan, BenhNhan.maBN == ChiTietDanhSachKham.maBN)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(ChiTietDanhSachKham.trangThai == "DA_XAC_NHAN")
        .order_by(
            DanhSachKham.ngayKham.desc(),
            ChiTietDanhSachKham.soThuTu,
            ChiTietDanhSachKham.maBN,
        )
    )
    history: dict[date, dict] = {}
    for registration, name, phone, gender, birth_year in rows:
        exam_date = registration.danhSachKham.ngayKham
        day = history.setdefault(exam_date, {
            "date": exam_date,
            "registrations": [],
        })
        day["registrations"].append({
            "slot": registration.soThuTu,
            "name": name,
            "phone": phone,
            "gender": gender,
            "birth_year": birth_year,
        })
    return list(history.values())


def capNhatHoSoBenhNhan(
    patient_id: int,
    *,
    name: str,
    phone: str,
    address: str,
) -> None:
    patient = db.session.scalar(
        db.select(BenhNhan).where(BenhNhan.maBN == patient_id).with_for_update()
    )
    if patient is None:
        raise LookupError("Không tìm thấy hồ sơ bệnh nhân.")
    patient.hoTen = name
    patient.soDienThoai = phone
    patient.diaChi = address
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        app.logger.warning("Patient profile update rejected by database constraints.")
        raise ValueError("Không thể cập nhật hồ sơ bệnh nhân. Vui lòng tải lại trang.") from None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Patient profile update failed.")
        raise


def _luuThayDoiDanhSachKham() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        app.logger.exception("Exam list change conflicted with a database constraint.")
        raise ValueError("Danh sách vừa được thay đổi; hãy tải lại và thử lại.") from None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Exam list persistence failed.")
        raise


def _layHoacTaoDanhSachNgay(exam_date: date, nurse_id: int | None = None) -> DanhSachKham:
    exam_day = db.session.scalar(
        db.select(DanhSachKham)
        .where(DanhSachKham.ngayKham == exam_date)
        .with_for_update()
    )
    if exam_day is None:
        exam_day = DanhSachKham(ngayKham=exam_date, maNV=nurse_id)
        db.session.add(exam_day)
    elif exam_day.maNV is None and nurse_id is not None:
        exam_day.maNV = nurse_id
    return exam_day


def _timNgayKhamConChoGanNhat(exam_date: date) -> tuple[date, int]:
    while True:
        try:
            _kiemTraNgayKhamChuaChot(exam_date)
        except ConfirmedExamDay:
            pass
        else:
            slot = kiemTraSoLuongToiDa(exam_date)
            if slot is not None:
                return exam_date, slot
        if exam_date == date.max:
            raise ValueError("Không tìm được ngày khám còn chỗ.")
        exam_date += timedelta(days=1)


def dangKyKham(
    patient: BenhNhan,
    exam_date: date | None = None,
) -> ChiTietDanhSachKham:
    exam_date = exam_date or ngayHienTaiPhongKham()
    layGioiHanBenhNhanNgay(lock=True)
    duplicate = db.session.scalar(
        db.select(ChiTietDanhSachKham.maBN)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            ChiTietDanhSachKham.maBN == patient.maBN,
            DanhSachKham.ngayKham >= exam_date,
            ChiTietDanhSachKham.trangThai.in_(NURSE_VISIBLE_STATUSES),
        ).with_for_update()
    )
    if duplicate is not None:
        raise ValueError("Bạn đã có lượt đăng ký khám từ hôm nay trở đi.")

    exam_date, slot = _timNgayKhamConChoGanNhat(exam_date)
    exam_day = _layHoacTaoDanhSachNgay(exam_date)
    db.session.flush()
    registration = db.session.get(
        ChiTietDanhSachKham, (exam_day.maDSKham, patient.maBN)
    )
    if registration is None:
        registration = ChiTietDanhSachKham(
            danhSachKham=exam_day,
            benhNhan=patient,
            soThuTu=slot,
            ngayDangKy=datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None),
            trangThai="CHO_KHAM",
        )
        db.session.add(registration)
    else:
        registration.soThuTu = slot
        registration.ngayDangKy = datetime.now(
            timezone(timedelta(hours=7))
        ).replace(tzinfo=None)
        registration.trangThai = "CHO_KHAM"
    _luuThayDoiDanhSachKham()
    return registration


def chuyenDangKyChoCu() -> int:
    layGioiHanBenhNhanNgay(lock=True)
    waiting = list(db.session.scalars(
        db.select(ChiTietDanhSachKham)
        .where(ChiTietDanhSachKham.trangThai == "CHO_DUYET")
        .order_by(ChiTietDanhSachKham.ngayDangKy, ChiTietDanhSachKham.maBN)
        .with_for_update()
    ))
    for registration in waiting:
        candidate = max(ngayHienTaiPhongKham(), registration.ngayKham)
        while True:
            candidate, slot = _timNgayKhamConChoGanNhat(candidate)
            duplicate = db.session.scalar(
                db.select(ChiTietDanhSachKham.maBN)
                .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
                .where(
                    ChiTietDanhSachKham.maBN == registration.maBN,
                    DanhSachKham.ngayKham == candidate,
                    ChiTietDanhSachKham.trangThai.in_(ACTIVE_EXAM_STATUSES),
                ).with_for_update()
            )
            if duplicate is None:
                break
            if candidate == date.max:
                raise ValueError("Không tìm được ngày khám còn chỗ.")
            candidate += timedelta(days=1)
        exam_day = _layHoacTaoDanhSachNgay(candidate)
        db.session.flush()
        existing = db.session.get(
            ChiTietDanhSachKham, (exam_day.maDSKham, registration.maBN)
        )
        if existing is not None and existing is not registration:
            existing.soThuTu = slot
            existing.ngayDangKy = registration.ngayDangKy
            existing.trangThai = "CHO_KHAM"
            db.session.delete(registration)
        else:
            registration.danhSachKham = exam_day
            registration.soThuTu = slot
            registration.trangThai = "CHO_KHAM"
        db.session.flush()
    _luuThayDoiDanhSachKham()
    return len(waiting)


def themBenhNhan(
    *,
    exam_date: date,
    patient: BenhNhan,
    nurse_id: int | None = None,
) -> ChiTietDanhSachKham:
    layGioiHanBenhNhanNgay(lock=True)
    _kiemTraNgayKhamChuaChot(exam_date)
    slot = kiemTraSoLuongToiDa(exam_date)
    if slot is None:
        raise DailyCapacityReached(
            f"Danh sách ngày {exam_date.strftime('%d/%m/%Y')} đã đủ chỗ. "
            "Vui lòng chọn ngày khác."
        )
    duplicate = db.session.scalar(
        db.select(ChiTietDanhSachKham.maBN)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            ChiTietDanhSachKham.maBN == patient.maBN,
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai.in_(NURSE_VISIBLE_STATUSES),
        )
    )
    if duplicate is not None:
        raise ValueError("Bệnh nhân này đã có trong danh sách ngày đang chọn.")

    exam_day = _layHoacTaoDanhSachNgay(exam_date, nurse_id)
    db.session.flush()
    registration = db.session.get(
        ChiTietDanhSachKham, (exam_day.maDSKham, patient.maBN)
    )
    if registration is None:
        registration = ChiTietDanhSachKham(
            danhSachKham=exam_day,
            benhNhan=patient,
            soThuTu=slot,
            ngayDangKy=datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None),
            trangThai="CHO_KHAM",
        )
        db.session.add(registration)
    else:
        registration.soThuTu = slot
        registration.ngayDangKy = datetime.now(
            timezone(timedelta(hours=7))
        ).replace(tzinfo=None)
        registration.trangThai = "CHO_KHAM"
    _luuThayDoiDanhSachKham()
    return registration


def huyLuotKham(maDSKham: int, maBN: int) -> None:
    layGioiHanBenhNhanNgay(lock=True)
    registration = db.session.scalar(
        db.select(ChiTietDanhSachKham).where(
            ChiTietDanhSachKham.maDSKham == maDSKham,
            ChiTietDanhSachKham.maBN == maBN,
            ChiTietDanhSachKham.trangThai.in_(NURSE_VISIBLE_STATUSES),
        ).with_for_update()
    )
    if registration is None:
        raise LookupError("Không tìm thấy lượt khám đang hoạt động.")
    registration.trangThai = "DA_HUY"
    registration.soThuTu = None
    _luuThayDoiDanhSachKham()


def xacNhanDanhSach(
    exam_date: date, nurse_id: int | None = None,
) -> list[ChiTietDanhSachKham]:
    layGioiHanBenhNhanNgay(lock=True)
    registrations = list(db.session.scalars(
        db.select(ChiTietDanhSachKham)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai.in_(("CHO_KHAM", "DA_MO_LAI")),
        ).with_for_update()
    ))
    if not registrations:
        if db.session.scalar(
            db.select(ChiTietDanhSachKham.maDSKham)
            .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
            .where(
                DanhSachKham.ngayKham == exam_date,
                ChiTietDanhSachKham.trangThai == "DA_XAC_NHAN",
            )
        ) is not None:
            return []
        raise ValueError("Không có bệnh nhân nào trong danh sách để xác nhận.")
    _layHoacTaoDanhSachNgay(exam_date, nurse_id)
    for registration in registrations:
        registration.trangThai = "DA_XAC_NHAN"
    _luuThayDoiDanhSachKham()

    return registrations


def moLaiDanhSachKham(exam_date: date) -> int:
    if exam_date < ngayHienTaiPhongKham():
        raise ValueError("Không thể mở lại danh sách của ngày đã qua.")

    layGioiHanBenhNhanNgay(lock=True)
    registrations = list(db.session.scalars(
        db.select(ChiTietDanhSachKham)
        .join(DanhSachKham, DanhSachKham.maDSKham == ChiTietDanhSachKham.maDSKham)
        .where(
            DanhSachKham.ngayKham == exam_date,
            ChiTietDanhSachKham.trangThai == "DA_XAC_NHAN",
        ).with_for_update()
    ))
    if not registrations:
        raise ValueError("Ngày này chưa có danh sách đã chốt.")

    for registration in registrations:
        registration.trangThai = "DA_MO_LAI"
    _luuThayDoiDanhSachKham()
    return len(registrations)


def timBanNhapCuaBacSi(exam_id: str, doctor_id: int) -> PhieuKham | None:
    return db.session.scalar(
        db.select(PhieuKham).where(
            PhieuKham.maPhieuKham == exam_id,
            PhieuKham.maNV == doctor_id,
            PhieuKham.trangThai == "NHAP",
        )
    )


def layBanNhapCuaBacSi(doctor_id: int) -> list[PhieuKham]:
    return list(db.session.scalars(
        db.select(PhieuKham)
        .where(
            PhieuKham.maNV == doctor_id,
            PhieuKham.trangThai == "NHAP",
        )
        .order_by(PhieuKham.ngayKham.desc(), PhieuKham.maPhieuKham.desc())
    ))


def xoaBanNhapCuaBacSi(exam_id: str, doctor_id: int) -> bool:
    draft = timBanNhapCuaBacSi(exam_id, doctor_id)
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


def _taoHoaDonPhieuKham(
    exam: PhieuKham,
    doctor: BacSi,
    prescriptions: list[dict],
) -> HoaDon:
    fee_rule = db.session.get(QuyDinh, "TIEN_KHAM")
    if fee_rule is None:
        raise ValueError("Chưa có quy định tiền khám. Hãy cập nhật quy định trước.")

    medicine_fee = Decimal("0.00")
    for prescription in prescriptions:
        medicine_fee += (
            Decimal(str(prescription["medicine"].donGia))
            * prescription["quantity"]
        )
    medicine_fee = medicine_fee.quantize(Decimal("0.01"))
    exam_fee = fee_rule.giaTri
    invoice = HoaDon(
        ngayLap=datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None),
        tienKham=float(exam_fee),
        tienThuoc=float(medicine_fee),
        tongTien=float(exam_fee + medicine_fee),
        maPhieuKham=exam.maPhieuKham,
        maNV=doctor.maNV,
    )
    db.session.add(invoice)
    return invoice


def taoHoaDon(
    exam: PhieuKham,
    doctor: BacSi,
    prescriptions: list[dict],
) -> HoaDon:
    return _taoHoaDonPhieuKham(exam, doctor, prescriptions)


def capNhatLuongThuoc(
    medicines_by_code: dict[str, Thuoc],
    quantities_by_code: dict[str, int],
) -> None:
    for code, quantity in quantities_by_code.items():
        medicines_by_code[code].soLuongTon -= quantity


def capNhatSoLuongThuoc(
    medicines_by_code: dict[str, Thuoc],
    quantities_by_code: dict[str, int],
) -> None:
    capNhatLuongThuoc(medicines_by_code, quantities_by_code)


def taoPhieuKham(
    *,
    patient: BenhNhan,
    doctor: BacSi,
    exam_date: date,
    symptoms: str,
    diagnosis: str,
    status: str,
    exam: PhieuKham | None,
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
    exam.duDoanLoaiBenh = diagnosis or None
    exam.trangThai = status
    exam.benhNhan = patient
    exam.bacSi = doctor
    return exam


def taoChiTietDonThuoc(
    exam: PhieuKham,
    prescription: dict,
) -> ChiTietDonThuoc:
    detail = ChiTietDonThuoc(
        thuoc=prescription["medicine"],
        soLuong=prescription["quantity"],
        cachDung=prescription["instructions"],
    )
    exam.chiTietDonThuocs.append(detail)
    return detail


def lapPhieuKham(
    patient: BenhNhan,
    doctor: BacSi,
    symptoms: str,
    diagnosis: str,
    prescriptions: list[dict],
    exam_date: date,
    status: str = "DA_LAP",
    exam: PhieuKham | None = None,
) -> tuple[PhieuKham, HoaDon | None]:
    invoice = None
    if exam is not None:
        exam = db.session.scalar(
            db.select(PhieuKham).where(
                PhieuKham.maPhieuKham == exam.maPhieuKham,
                PhieuKham.maNV == doctor.maNV,
                PhieuKham.trangThai == "NHAP",
            ).with_for_update().execution_options(populate_existing=True)
        )
        if exam is None:
            raise ValueError("Bản nháp không còn khả dụng để cập nhật.")

    if status == "DA_LAP":
        medicine_codes = sorted({
            prescription["medicine"].maThuoc
            for prescription in prescriptions
        })
        locked_medicines = list(db.session.scalars(
            db.select(Thuoc)
            .where(Thuoc.maThuoc.in_(medicine_codes))
            .order_by(Thuoc.maThuoc)
            .with_for_update()
            .execution_options(populate_existing=True)
        ))
        medicines_by_code = {
            medicine.maThuoc: medicine for medicine in locked_medicines
        }
        missing_codes = set(medicine_codes) - medicines_by_code.keys()
        if missing_codes:
            raise ValueError(f"Không tìm thấy thuốc {min(missing_codes)}.")

        locked_prescriptions = []
        quantities_by_code = {}
        for prescription in prescriptions:
            code = prescription["medicine"].maThuoc
            quantity = prescription["quantity"]
            if (
                not isinstance(quantity, int) or isinstance(quantity, bool)
                or quantity < 1
            ):
                raise ValueError("Số lượng thuốc không hợp lệ.")
            if code in quantities_by_code:
                raise ValueError("Mỗi loại thuốc chỉ được xuất hiện một lần trong đơn.")
            quantities_by_code[code] = quantity
            locked_prescriptions.append({
                **prescription,
                "medicine": medicines_by_code[code],
            })

        for code, quantity in quantities_by_code.items():
            medicine = medicines_by_code[code]
            if quantity > medicine.soLuongTon:
                raise ValueError(
                    f"Số lượng thuốc {medicine.tenThuoc} vượt quá tồn kho."
                )
        capNhatSoLuongThuoc(medicines_by_code, quantities_by_code)
        prescriptions = locked_prescriptions

    exam = taoPhieuKham(
        patient=patient,
        doctor=doctor,
        exam_date=exam_date,
        symptoms=symptoms,
        diagnosis=diagnosis,
        status=status,
        exam=exam,
    )
    for prescription in prescriptions:
        taoChiTietDonThuoc(exam, prescription)
    if status == "DA_LAP":
        invoice = taoHoaDon(exam, doctor, prescriptions)
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
    return exam, invoice


def _capNhatHoSoTaiKhoan(account: TaiKhoan, data: dict) -> None:
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


def taoTaiKhoan(data: dict) -> TaiKhoan:
    kiemTraMatKhau(data["password"])
    account = TaiKhoan()
    account.tenDangNhap = data["tenDangNhap"]
    account.role = data["role"]
    account.trangThai = data["trangThai"]
    account.datMatKhau(data["password"])
    _capNhatHoSoTaiKhoan(account, data)
    db.session.add(account)
    _luuThayDoi()
    return account


def _khoaTaiKhoanDangQuanLy(actor_id: int, target_id: int) -> TaiKhoan:
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


def capNhatTaiKhoan(actor_id: int, target_id: int, data: dict) -> TaiKhoan:
    target = _khoaTaiKhoanDangQuanLy(actor_id, target_id)
    if actor_id == target_id and (data["role"] != Role.ADMIN or not data["trangThai"]):
        db.session.rollback()
        raise ValueError("Không được tự khóa hoặc tự bỏ quyền quản trị của mình.")
    if data["password"]:
        kiemTraMatKhau(data["password"])
        target.doiMatKhau(target.tenDangNhap, data["password"])
    target.tenDangNhap = data["tenDangNhap"]
    target.role = data["role"]
    target.trangThai = data["trangThai"]
    _capNhatHoSoTaiKhoan(target, data)
    _luuThayDoi()
    return target


def capNhatTrangThaiTaiKhoan(actor_id: int, target_id: int, active: bool) -> None:
    target = _khoaTaiKhoanDangQuanLy(actor_id, target_id)
    if actor_id == target_id and not active:
        db.session.rollback()
        raise ValueError("Không được tự khóa tài khoản quản trị của mình.")
    target.trangThai = active
    _luuThayDoi()


def _luuThayDoi() -> None:
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


def _khoaQuanTriVien(actor_id: int) -> None:
    actor = db.session.scalar(db.select(TaiKhoan).where(
        TaiKhoan.maTK == actor_id,
    ).with_for_update().execution_options(populate_existing=True))
    if actor is None or actor.role != Role.ADMIN or not actor.trangThai:
        raise ValueError("Bạn không còn quyền quản trị.")


def _luuDanhMuc() -> None:
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


def chuyenSoTien(value: str, *, positive: bool = False) -> Decimal:
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


def _kiemTraMaDanhMuc(value: str) -> str:
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{1,20}", code):
        raise ValueError("Mã gồm 1–20 chữ không dấu, số, gạch ngang hoặc gạch dưới.")
    return code


def _luuThuoc(actor_id: int, form, code: str | None = None) -> Thuoc:
    _khoaQuanTriVien(actor_id)
    name = form.get("tenThuoc", "").strip()
    if not name or len(name) > 100:
        raise ValueError("Tên thuốc bắt buộc, tối đa 100 ký tự.")
    amount = chuyenSoTien(form.get("donGia", ""))
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
        medicine.maThuoc = _kiemTraMaDanhMuc(form.get("maThuoc", ""))
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
    _luuDanhMuc()
    return medicine


def themThuoc(actor_id: int, form) -> Thuoc:
    return _luuThuoc(actor_id, form)


def suaThuoc(actor_id: int, form, code: str) -> Thuoc:
    return _luuThuoc(actor_id, form, code)


def _luuDonViThuoc(actor_id: int, form, code: str | None = None) -> DonViThuoc:
    _khoaQuanTriVien(actor_id)
    name = form.get("tenDonVi", "").strip()
    if not name or len(name) > 50:
        raise ValueError("Tên đơn vị bắt buộc, tối đa 50 ký tự.")
    if code is None:
        unit = DonViThuoc()
        unit.maDonVi = _kiemTraMaDanhMuc(form.get("maDonVi", ""))
        db.session.add(unit)
    else:
        unit = db.session.scalar(db.select(DonViThuoc).where(
            DonViThuoc.maDonVi == code,
        ).with_for_update().execution_options(populate_existing=True))
        if unit is None:
            raise ValueError("Đơn vị thuốc không còn tồn tại.")
    unit.tenDonVi = name
    _luuDanhMuc()
    return unit


def themDonViThuoc(actor_id: int, form) -> DonViThuoc:
    return _luuDonViThuoc(actor_id, form)


def suaDonViThuoc(actor_id: int, form, code: str) -> DonViThuoc:
    return _luuDonViThuoc(actor_id, form, code)


def xoaDonViThuoc(actor_id: int, code: str) -> None:
    _khoaQuanTriVien(actor_id)
    unit = db.session.scalar(db.select(DonViThuoc).where(
        DonViThuoc.maDonVi == code,
    ).with_for_update())
    if unit is None:
        raise ValueError("Đơn vị thuốc không còn tồn tại.")
    if db.session.scalar(db.select(Thuoc.maThuoc).where(
        Thuoc.maDonVi == code,
    ).limit(1)) is not None:
        raise ValueError("Không thể xóa đơn vị thuốc đang được sử dụng.")
    db.session.delete(unit)
    _luuDanhMuc()


def _xoaMucDanhMuc(actor_id: int, code: str) -> None:
    _khoaQuanTriVien(actor_id)
    item = db.session.scalar(
        db.select(Thuoc).where(Thuoc.maThuoc == code).with_for_update()
    )
    if item is None:
        raise ValueError("Dữ liệu không còn tồn tại.")
    references = db.select(ChiTietDonThuoc.maThuoc).where(
        ChiTietDonThuoc.maThuoc == code
    )
    if db.session.scalar(references.limit(1)) is not None:
        raise ValueError("Không thể xóa: dữ liệu đang được sử dụng trong thuốc hoặc đơn thuốc.")
    db.session.delete(item)
    _luuDanhMuc()


def xoaThuoc(actor_id: int, code: str) -> None:
    _xoaMucDanhMuc(actor_id, code)
def capNhatQuyDinh(actor_id: int, fee: str, maximum: str) -> None:
    _khoaQuanTriVien(actor_id)
    amount = chuyenSoTien(fee, positive=True)
    if not re.fullmatch(r"[0-9]{1,6}", maximum.strip()):
        raise ValueError("Số bệnh nhân tối đa phải là số nguyên từ 1 đến 100000.")
    rules = {rule.maQD: rule for rule in db.session.scalars(
        db.select(QuyDinh).order_by(QuyDinh.maQD).with_for_update()
    )}
    if not {"TIEN_KHAM", "SO_BENH_NHAN_TOI_DA"}.issubset(rules):
        raise ValueError("Chưa khởi tạo quy định. Hãy chạy seed-admin-demo trước.")
    rules["TIEN_KHAM"].capNhatTienKham(amount)
    rules["SO_BENH_NHAN_TOI_DA"].capNhatQuyDinhKham(int(maximum))
    _luuDanhMuc()


def thongKeHangThang(year: int, month: int) -> dict:
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
