import hashlib

from flask import abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import Role
from app.utils import account_data, csrf_token, protect_csrf


app.before_request(protect_csrf)
app.jinja_env.globals.update(csrf_token=csrf_token, Role=Role)


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login_view():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        account = dao.authenticate(
            request.form.get("tenDangNhap", ""), request.form.get("matKhau", "")
        )
        if account:
            session.clear()
            login_user(account)
            session["auth_hash"] = hashlib.sha256(account.matKhau.encode()).hexdigest()
            return redirect(url_for("dashboard"))
        flash("Tên đăng nhập, mật khẩu không đúng hoặc tài khoản đã bị khóa.", "danger")
    return render_template("auth/login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            data = account_data(request.form, registration=True)
            if data["password"] != request.form.get("xacNhanMatKhau"):
                raise ValueError("Mật khẩu xác nhận không khớp.")
            dao.create_account(data)
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash("Đăng ký thành công. Bạn có thể đăng nhập bằng tài khoản bệnh nhân.", "success")
            return redirect(url_for("login_view"))
    return render_template("auth/register.html")


@app.post("/logout")
@login_required
def logout():
    current_user.dangXuat()
    session.clear()
    return redirect(url_for("login_view"))


@app.get("/dashboard")
@login_required
def dashboard():
    if current_user.role == Role.ADMIN:
        return redirect(url_for("admin_accounts"))
    template = {
        Role.PATIENT: "patient/dashboard.html",
        Role.NURSE: "nurse/dashboard.html",
        Role.CASHIER: "cashier/dashboard.html",
        Role.DOCTOR: "doctor/dashboard.html",
    }.get(current_user.role)
    if template is None:
        abort(403)
    return render_template(template)


@app.errorhandler(SQLAlchemyError)
def database_error(_error):
    db.session.rollback()
    app.logger.exception("Database request failed.")
    return render_template(
        "error.html", code=503, database_unavailable=True,
        message="Không thể xử lý dữ liệu lúc này. Vui lòng thử lại hoặc liên hệ quản trị.",
    ), 503


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def http_error(error):
    messages = {
        400: error.description,
        403: "Bạn không có quyền truy cập chức năng này.",
        404: "Không tìm thấy trang hoặc tài khoản.",
    }
    return render_template("error.html", code=error.code, message=messages[error.code]), error.code


from app import admin


if __name__ == "__main__":
    app.run(debug=True)
