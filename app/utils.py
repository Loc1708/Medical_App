import re
import secrets
from datetime import date
from functools import wraps

from flask import abort, request, session
from flask_login import current_user

from app.models import Role


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def protect_csrf() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not secrets.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            abort(400, description="Phiên biểu mẫu không hợp lệ. Hãy tải lại trang và thử lại.")


def roles_required(*roles: Role):
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            if not current_user.is_authenticated:
                from app import login
                return login.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return function(*args, **kwargs)
        return guarded
    return decorate


def validate_password(password: str) -> None:
    if not 10 <= len(password) <= 128:
        raise ValueError("Mật khẩu phải có từ 10 đến 128 ký tự.")


def account_data(form, *, registration: bool = False) -> dict:
    username = form.get("tenDangNhap", "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
        raise ValueError("Tên đăng nhập gồm 3–80 chữ không dấu, số hoặc ký tự _ . -")
    try:
        role = Role.PATIENT if registration else Role(form.get("role", ""))
    except ValueError:
        raise ValueError("Vai trò không hợp lệ.") from None
    name = form.get("hoTen", "").strip()
    phone = form.get("soDienThoai", "").strip()
    if not name or len(name) > 100:
        raise ValueError("Họ tên bắt buộc và tối đa 100 ký tự.")
    if (role == Role.PATIENT and not phone) or (
        phone and not re.fullmatch(r"\+?[0-9]{9,15}", phone)
    ):
        raise ValueError("Số điện thoại phải có 9–15 chữ số, có thể bắt đầu bằng +.")
    data = {
        "tenDangNhap": username, "role": role, "hoTen": name,
        "soDienThoai": phone, "password": form.get("matKhau", ""),
        "trangThai": True if registration else form.get("trangThai") == "on",
    }
    if role == Role.PATIENT:
        try:
            year = int(form.get("namSinh", ""))
        except ValueError:
            raise ValueError("Năm sinh không hợp lệ.") from None
        gender = form.get("gioiTinh", "")
        address = form.get("diaChi", "").strip()
        if not 1900 <= year <= date.today().year:
            raise ValueError("Năm sinh phải từ 1900 đến năm hiện tại.")
        if gender not in {"Nam", "Nữ", "Khác"} or not address or len(address) > 255:
            raise ValueError("Vui lòng chọn giới tính và nhập địa chỉ tối đa 255 ký tự.")
        data.update(namSinh=year, gioiTinh=gender, diaChi=address)
    if role == Role.DOCTOR:
        specialty = form.get("chuyenKhoa", "").strip()
        if not specialty or len(specialty) > 100:
            raise ValueError("Chuyên khoa bắt buộc và tối đa 100 ký tự.")
        data["chuyenKhoa"] = specialty
    return data
