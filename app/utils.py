import re
import secrets
from datetime import date
from functools import wraps
import os
import requests

from flask import abort, request, session
from flask_login import current_user

from app.models import Role

ESMS_URL = "https://rest.esms.vn/MainService.svc/json/SendMultipleMessage_V4_post_json/"

def taoMaCsrf() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def baoVeCsrf() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not secrets.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            abort(400, description="Phiên biểu mẫu không hợp lệ. Hãy tải lại trang và thử lại.")


def yeuCauVaiTro(*roles: Role):
    def trangTriTheoVaiTro(function):
        @wraps(function)
        def kiemTraVaiTro(*args, **kwargs):
            if not current_user.is_authenticated:
                from app import login
                return login.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return function(*args, **kwargs)
        return kiemTraVaiTro
    return trangTriTheoVaiTro


def kiemTraMatKhau(password: str) -> None:
    if not 10 <= len(password) <= 128:
        raise ValueError("Mật khẩu phải có từ 10 đến 128 ký tự.")


def layDuLieuTaiKhoan(form, *, registration: bool = False) -> dict:
    username = form.get("tenDangNhap", "")
    if registration:
        if not re.fullmatch(r"[a-zA-Z0-9]{3,80}", username):
            raise ValueError("Tên đăng nhập phải gồm 3–80 chữ không dấu hoặc chữ số.")
        password = form.get("matKhau", "")
        kiemTraMatKhau(password)
        if not re.fullmatch(r"[a-zA-Z0-9]+", password):
            raise ValueError("Mật khẩu chỉ được gồm chữ không dấu và chữ số.")
    username = username.strip().lower()
    if not registration and not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
        raise ValueError("Tên đăng nhập gồm 3–80 chữ không dấu, số hoặc ký tự _ . -")
    try:
        role = Role.PATIENT if registration else Role(form.get("role", ""))
    except ValueError:
        raise ValueError("Vai trò không hợp lệ.") from None
    name = form.get("hoTen", "").strip()
    phone = form.get("soDienThoai", "")
    if not registration:
        phone = phone.strip()
    if not name or len(name) > 100:
        raise ValueError("Họ tên bắt buộc và tối đa 100 ký tự.")
    if registration and not re.fullmatch(r"[0-9]{9,15}", phone):
        raise ValueError("Số điện thoại phải gồm 9–15 chữ số.")
    if not registration and ((role == Role.PATIENT and not phone) or (
        phone and not re.fullmatch(r"\+?[0-9]{9,15}", phone)
    )):
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

def guiTinNhanSms(phone, content):
    mode = os.getenv("SMS_MODE", "mock")
    if mode == "mock":
        print(f"[MOCK SMS] {phone}: {content}")
        return True, {"mode": "mock"}

    payload = {
        "ApiKey": os.getenv("ESMS_API_KEY"),
        "SecretKey": os.getenv("ESMS_SECRET_KEY"),
        "Phone": phone,
        "Content": content,
        "Brandname": "Baotrixemay",
        "SmsType": "2",
        "IsUnicode": "0",
        "Sandbox": "1" if mode == "sandbox" else "0",
    }
    try:
        res = requests.post(ESMS_URL, json=payload, timeout=10)
        data = res.json()
        print("ESMS:", data, "| phone:", phone, "| mode:", mode)
        return data.get("CodeResult") == "100", data
    except (requests.RequestException, ValueError) as e:
        return False, {"error": str(e)}