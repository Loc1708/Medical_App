import hashlib
from datetime import datetime, timedelta, timezone

from flask import abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import Role
from app.utils import layDuLieuTaiKhoan, taoMaCsrf, baoVeCsrf


app.before_request(baoVeCsrf)
app.jinja_env.globals.update(csrf_token=taoMaCsrf, Role=Role)


@app.route("/", endpoint="index")
def trangChu():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"], endpoint="login_view")
def giaoDienDangNhap():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        account = dao.xacThucTaiKhoan(
            request.form.get("tenDangNhap", ""), request.form.get("matKhau", "")
        )
        if account:
            session.clear()
            login_user(account)
            session["auth_hash"] = hashlib.sha256(account.matKhau.encode()).hexdigest()
            return redirect(url_for("dashboard"))
        flash("Tên đăng nhập, mật khẩu không đúng hoặc tài khoản đã bị khóa.", "danger")
    return render_template("auth/login.html")


@app.route("/register", methods=["GET", "POST"], endpoint="register")
def dangKyTaiKhoan():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            data = layDuLieuTaiKhoan(request.form, registration=True)
            if data["password"] != request.form.get("xacNhanMatKhau"):
                raise ValueError("Mật khẩu xác nhận không khớp.")
            dao.taoTaiKhoan(data)
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash("Đăng ký thành công. Bạn có thể đăng nhập bằng tài khoản bệnh nhân.", "success")
            return redirect(url_for("login_view"))
    return render_template("auth/register.html")


@app.post("/logout", endpoint="logout")
@login_required
def dangXuat():
    current_user.dangXuat()
    session.clear()
    return redirect(url_for("login_view"))


@app.get("/dashboard", endpoint="dashboard")
@login_required
def trangDieuKhien():
    if current_user.role == Role.ADMIN:
        return redirect(url_for("admin_accounts"))
    if current_user.role == Role.DOCTOR:
        clinic_timezone = timezone(timedelta(hours=7))
        exam_date = datetime.now(clinic_timezone).date()
        return render_template("doctor/dashboard.html", exam_date=exam_date)
    if current_user.role == Role.NURSE:
        ngayHienTaiPhongKham = dao.ngayHienTaiPhongKham()
        return render_template(
            "nurse/dashboard.html",
            exam_date=ngayHienTaiPhongKham.isoformat(),
        )
    if current_user.role == Role.PATIENT:
        return patient_api.hienThiTrangBenhNhan()
    template = {
        Role.NURSE: "nurse/dashboard.html",
        Role.CASHIER: "cashier/dashboard.html",
    }.get(current_user.role)
    if template is None:
        abort(403)
    return render_template(template)


@app.errorhandler(SQLAlchemyError)
def xuLyLoiCoSoDuLieu(_error):
    db.session.rollback()
    app.logger.exception("Database request failed.")
    return render_template(
        "error.html", code=503, database_unavailable=True,
        message="Không thể xử lý dữ liệu lúc này. Vui lòng thử lại hoặc liên hệ quản trị.",
    ), 503


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def xuLyLoiHttp(error):
    messages = {
        400: error.description,
        403: "Bạn không có quyền truy cập chức năng này.",
        404: "Không tìm thấy trang hoặc tài khoản.",
    }
    return render_template("error.html", code=error.code, message=messages[error.code]), error.code


from app.routes import admin, cashier, doctor, nurse, patient as patient_api


if __name__ == "__main__":
    app.run(debug=True)
