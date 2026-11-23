from flask import abort, redirect, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_login import current_user

from app import app, login
from app.models import Role
from app.routes import admin as xuLyQuanTri


class QuanTriPhongMach(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == Role.ADMIN

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return login.unauthorized()
        abort(403)

    @expose("/")
    def index(self):
        return redirect(url_for("quan_tri.admin_accounts"))

    @expose("/accounts")
    def admin_accounts(self):
        return xuLyQuanTri.quanLyTaiKhoan()

    @expose("/accounts/new", methods=("GET", "POST"))
    def admin_account_create(self):
        return xuLyQuanTri.quanTriThemTaiKhoan()

    @expose("/accounts/<int:account_id>/edit", methods=("GET", "POST"))
    def admin_account_edit(self, account_id):
        return xuLyQuanTri.quanTriSuaTaiKhoan(account_id)

    @expose("/accounts/<int:account_id>/status", methods=("POST",))
    def admin_account_status(self, account_id):
        return xuLyQuanTri.quanTriDoiTrangThaiTaiKhoan(account_id)

    @expose("/medicines")
    def admin_medicines(self):
        return xuLyQuanTri.quanLyThuoc()

    @expose("/units")
    def admin_units(self):
        return xuLyQuanTri.quanLyDonViThuoc()

    @expose("/medicines/new", methods=("GET", "POST"))
    @expose("/medicines/<code>/edit", methods=("GET", "POST"))
    def admin_medicine_edit(self, code=None):
        return xuLyQuanTri.quanTriChinhSuaThuoc(code)

    @expose("/units/new", methods=("GET", "POST"))
    @expose("/units/<code>/edit", methods=("GET", "POST"))
    def admin_unit_edit(self, code=None):
        return xuLyQuanTri.quanTriChinhSuaDonVi(code)

    @expose("/medicines/<code>/delete", methods=("POST",))
    def admin_medicine_delete(self, code):
        return xuLyQuanTri.quanTriXoaThuoc(code)

    @expose("/units/<code>/delete", methods=("POST",))
    def admin_unit_delete(self, code):
        return xuLyQuanTri.quanTriXoaDonVi(code)

    @expose("/regulations", methods=("GET", "POST"))
    def admin_regulations(self):
        return xuLyQuanTri.quanLyQuyDinh()

    @expose("/reports")
    def admin_reports(self):
        return xuLyQuanTri.xemBaoCao()


quanTri = Admin(app, index_view=QuanTriPhongMach(endpoint="quan_tri", url="/admin"))
