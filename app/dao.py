from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import app, db
from app.models import BacSi, BenhNhan, NhanVien, Role, TaiKhoan
from app.utils import validate_password


def authenticate(username: str, password: str):
    if len(username) > 80 or not 1 <= len(password) <= 128:
        return None
    account = db.session.scalar(
        db.select(TaiKhoan).where(TaiKhoan.tenDangNhap == username.strip().lower())
    )
    return account if account and account.dangNhap(username, password) else None


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
