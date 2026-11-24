from datetime import datetime, timedelta, timezone
import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import dao, db
from app.models import (
    BenhNhan, DonViThuoc, NhanVien, QuyDinh, Role, TaiKhoan, Thuoc,
)
from app.utils import layDuLieuTaiKhoan, yeuCauVaiTro


@yeuCauVaiTro(Role.ADMIN)
def quanLyTaiKhoan():
    keyword = request.args.get("q", "").strip()[:80]
    role_filter = request.args.get("role", "")
    statement = db.select(TaiKhoan)
    if keyword:
        statement = statement.where(
            TaiKhoan.tenDangNhap.contains(keyword, autoescape=True)
            | TaiKhoan.benhNhan.has(BenhNhan.hoTen.contains(keyword, autoescape=True))
            | TaiKhoan.nhanVien.has(NhanVien.hoTen.contains(keyword, autoescape=True))
        )
    if role_filter:
        try:
            selected_role = Role(role_filter)
        except ValueError:
            flash("Bộ lọc vai trò không hợp lệ.", "danger")
            return redirect(url_for("quan_tri.admin_accounts"))
        statement = statement.where(TaiKhoan.role == selected_role)
    page = db.paginate(statement.order_by(TaiKhoan.tenDangNhap), per_page=10, max_per_page=10)
    return render_template(
        "admin/accounts.html", page=page, keyword=keyword, role_filter=role_filter
    )


@yeuCauVaiTro(Role.ADMIN)
def quanTriThemTaiKhoan():
    error_message = None
    if request.method == "POST":
        try:
            dao.taoTaiKhoan(_kiemTraBieuMauTaiKhoan())
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã tạo tài khoản và hồ sơ liên quan.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("quan_tri.admin_accounts"))
    return _hienThiBieuMauTaiKhoan(None, request.form, error_message)


@yeuCauVaiTro(Role.ADMIN)
def quanTriSuaTaiKhoan(account_id: int):
    account = db.get_or_404(TaiKhoan, account_id)
    error_message = None
    if request.method == "POST":
        try:
            dao.capNhatTaiKhoan(current_user.maTK, account_id, _kiemTraBieuMauTaiKhoan())
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã cập nhật tài khoản. Quyền mới được áp dụng từ yêu cầu tiếp theo.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("quan_tri.admin_accounts"))
        values = request.form
    else:
        patient, employee = account.benhNhan, account.nhanVien
        profile = patient if account.role == Role.PATIENT else employee
        values = {
            "tenDangNhap": account.tenDangNhap,
            "role": account.role.value,
            "hoTen": profile.hoTen if profile else "",
            "soDienThoai": profile.soDienThoai if profile else "",
            "trangThai": "on" if account.trangThai else "",
            "namSinh": patient.namSinh if patient else "",
            "gioiTinh": patient.gioiTinh if patient else "",
            "diaChi": patient.diaChi if patient else "",
            "chuyenKhoa": employee.bacSi.chuyenKhoa if employee and employee.bacSi else "",
        }
    return _hienThiBieuMauTaiKhoan(account, values, error_message)


def _kiemTraBieuMauTaiKhoan() -> dict:
    data = layDuLieuTaiKhoan(request.form)
    if data["password"] != request.form.get("xacNhanMatKhau", ""):
        raise ValueError("Mật khẩu xác nhận không khớp.")
    return data


def _hienThiBieuMauTaiKhoan(account, values, error_message):
    modal = request.args.get("modal") == "1"
    template = "components/account_dialog.html" if modal else "admin/account_form.html"
    return render_template(
        template, account=account, values=values, error_message=error_message, modal=modal
    ), 422 if modal and error_message else 200


@yeuCauVaiTro(Role.ADMIN)
def quanTriDoiTrangThaiTaiKhoan(account_id: int):
    active = request.form.get("active")
    if active not in {"0", "1"}:
        abort(400, description="Trạng thái tài khoản không hợp lệ.")
    try:
        dao.capNhatTrangThaiTaiKhoan(current_user.maTK, account_id, active == "1")
    except ValueError as error:
        flash(str(error), "danger")
    else:
        flash("Đã cập nhật trạng thái tài khoản.", "success")
    return redirect(url_for(
        "quan_tri.admin_accounts", q=request.form.get("q", ""), role=request.form.get("filter_role", ""),
        page=request.form.get("page", "1"),
    ))


@yeuCauVaiTro(Role.ADMIN)
def layThongTinThuoc():
    keyword = request.args.get("q", "").strip()[:100]
    statement = db.select(Thuoc)
    if keyword:
        statement = statement.where(Thuoc.tenThuoc.contains(keyword, autoescape=True))
    page = db.paginate(statement.order_by(Thuoc.maThuoc), per_page=10, max_per_page=10)
    return render_template("admin/catalog.html", page=page, keyword=keyword, unit_mode=False)


@yeuCauVaiTro(Role.ADMIN)
def quanLyDonViThuoc():
    keyword = request.args.get("q", "").strip()[:50]
    statement = db.select(DonViThuoc)
    if keyword:
        statement = statement.where(DonViThuoc.tenDonVi.contains(keyword, autoescape=True))
    page = db.paginate(statement.order_by(DonViThuoc.maDonVi), per_page=10, max_per_page=10)
    return render_template("admin/catalog.html", page=page, keyword=keyword, unit_mode=True)


def _chinhSuaThuoc(code: str | None):
    item = db.get_or_404(Thuoc, code) if code else None
    error_message = None
    if request.method == "POST":
        try:
            if code is None:
                dao.themThuoc(current_user.maTK, request.form)
            else:
                dao.suaThuoc(current_user.maTK, request.form, code)
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã lưu thuốc.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("quan_tri.admin_medicines"))
    if request.method == "POST":
        values = request.form
    elif isinstance(item, Thuoc):
        values = {
            "maThuoc": item.maThuoc, "tenThuoc": item.tenThuoc, "maDonVi": item.maDonVi,
            "donGia": f"{item.donGia:.2f}", "soLuongTon": item.soLuongTon,
        }
    else:
        values = {}
    units = list(db.session.scalars(
        db.select(DonViThuoc).order_by(DonViThuoc.tenDonVi)
    ))
    modal = request.args.get("modal") == "1"
    return render_template(
        "components/catalog_dialog.html" if modal else "admin/catalog_form.html",
        values=values, item=item, unit_mode=False, units=units,
        error_message=error_message, modal=modal,
    ), 422 if modal and error_message else 200


@yeuCauVaiTro(Role.ADMIN)
def quanTriChinhSuaThuoc(code: str | None = None):
    return _chinhSuaThuoc(code)


@yeuCauVaiTro(Role.ADMIN)
def quanTriChinhSuaDonVi(code: str | None = None):
    item = db.get_or_404(DonViThuoc, code) if code else None
    error_message = None
    if request.method == "POST":
        try:
            if code is None:
                dao.themDonViThuoc(current_user.maTK, request.form)
            else:
                dao.suaDonViThuoc(current_user.maTK, request.form, code)
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã lưu đơn vị thuốc.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("quan_tri.admin_units"))
    if request.method == "POST":
        values = request.form
    elif item:
        values = {"maDonVi": item.maDonVi, "tenDonVi": item.tenDonVi}
    else:
        values = {}
    modal = request.args.get("modal") == "1"
    return render_template(
        "components/catalog_dialog.html" if modal else "admin/catalog_form.html",
        values=values, item=item, unit_mode=True,
        error_message=error_message, modal=modal,
    ), 422 if modal and error_message else 200


@yeuCauVaiTro(Role.ADMIN)
def quanTriXoaThuoc(code: str):
    try:
        dao.xoaThuoc(current_user.maTK, code)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash("Đã xóa thuốc.", "success")
    return redirect(url_for("quan_tri.admin_medicines", q=request.form.get("q", "")))


@yeuCauVaiTro(Role.ADMIN)
def quanTriXoaDonVi(code: str):
    try:
        dao.xoaDonViThuoc(current_user.maTK, code)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash("Đã xóa đơn vị thuốc.", "success")
    return redirect(url_for("quan_tri.admin_units", q=request.form.get("q", "")))


@yeuCauVaiTro(Role.ADMIN)
def quanLyQuyDinh():
    error_message = None
    if request.method == "POST":
        try:
            dao.capNhatQuyDinh(current_user.maTK, request.form.get("fee", ""),
                                   request.form.get("maximum", ""))
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã cập nhật quy định. Không thay đổi số tiền trên hóa đơn cũ.", "success")
            return redirect(url_for("quan_tri.admin_regulations"))
    rules = {rule.maQD: rule for rule in db.session.scalars(db.select(QuyDinh))}
    ready = {"TIEN_KHAM", "SO_BENH_NHAN_TOI_DA"}.issubset(rules)
    if request.method == "GET" and not ready:
        error_message = "Chưa khởi tạo quy định. Hãy chạy seed-admin-demo."
    values = request.form if request.method == "POST" else {
        "fee": rules["TIEN_KHAM"].giaTri if ready else "",
        "maximum": rules["SO_BENH_NHAN_TOI_DA"].laySoBenhNhanToiDa() if ready else "",
    }
    return render_template("admin/regulations.html", values=values, error_message=error_message,
                           ready=ready)


@yeuCauVaiTro(Role.ADMIN)
def xemBaoCao():
    current = datetime.now(timezone(timedelta(hours=7)))
    selected_month = request.args.get("month", current.strftime("%Y-%m"))
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", selected_month):
        abort(400, description="Tháng báo cáo không hợp lệ.")
    year, month = map(int, selected_month.split("-"))
    if not 1900 <= year <= 9998:
        abort(400, description="Năm báo cáo phải từ 1900 đến 9998.")
    report = dao.thongKeHangThang(year, month)
    chart_data = dict(
        days=[row["day"].strftime("%d/%m") for row in report["revenue"]],
        revenue=[float(row["amount"]) for row in report["revenue"]],
        patients=[row["patients"] for row in report["revenue"]],
        medicines=[row["name"] for row in report["medicines"]],
        quantities=[row["quantity"] for row in report["medicines"]],
        uses=[row["uses"] for row in report["medicines"]],
    )
    return render_template("admin/reports.html", report=report,
                           selected_month=selected_month, chart_data=chart_data)
