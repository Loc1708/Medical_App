from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import app, dao, db
from app.models import BenhNhan, NhanVien, Role, TaiKhoan
from app.utils import account_data, roles_required


@app.get("/admin/accounts")
@roles_required(Role.ADMIN)
def admin_accounts():
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
            return redirect(url_for("admin_accounts"))
        statement = statement.where(TaiKhoan.role == selected_role)
    page = db.paginate(statement.order_by(TaiKhoan.tenDangNhap), per_page=10, max_per_page=10)
    return render_template(
        "admin/accounts.html", page=page, keyword=keyword, role_filter=role_filter
    )


@app.route("/admin/accounts/new", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def admin_account_create():
    error_message = None
    if request.method == "POST":
        try:
            dao.create_account(_validated_form())
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã tạo tài khoản và hồ sơ liên quan.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("admin_accounts"))
    return _render_account_form(None, request.form, error_message)


@app.route("/admin/accounts/<int:account_id>/edit", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def admin_account_edit(account_id: int):
    account = db.get_or_404(TaiKhoan, account_id)
    error_message = None
    if request.method == "POST":
        try:
            dao.update_account(current_user.maTK, account_id, _validated_form())
        except ValueError as error:
            db.session.rollback()
            error_message = str(error)
        else:
            flash("Đã cập nhật tài khoản. Quyền mới được áp dụng từ yêu cầu tiếp theo.", "success")
            if request.args.get("modal") == "1":
                return "", 204
            return redirect(url_for("admin_accounts"))
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
    return _render_account_form(account, values, error_message)


def _validated_form() -> dict:
    data = account_data(request.form)
    if data["password"] != request.form.get("xacNhanMatKhau", ""):
        raise ValueError("Mật khẩu xác nhận không khớp.")
    return data


def _render_account_form(account, values, error_message):
    modal = request.args.get("modal") == "1"
    template = "components/account_dialog.html" if modal else "admin/account_form.html"
    return render_template(
        template, account=account, values=values, error_message=error_message, modal=modal
    ), 422 if modal and error_message else 200


@app.post("/admin/accounts/<int:account_id>/status")
@roles_required(Role.ADMIN)
def admin_account_status(account_id: int):
    active = request.form.get("active")
    if active not in {"0", "1"}:
        abort(400, description="Trạng thái tài khoản không hợp lệ.")
    try:
        dao.set_account_status(current_user.maTK, account_id, active == "1")
    except ValueError as error:
        flash(str(error), "danger")
    else:
        flash("Đã cập nhật trạng thái tài khoản.", "success")
    return redirect(url_for(
        "admin_accounts", q=request.form.get("q", ""), role=request.form.get("filter_role", ""),
        page=request.form.get("page", "1"),
    ))
