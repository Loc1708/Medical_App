from flask import abort
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user

from app import app, db, login
from app.models import BenhNhan, HoaDon, NhanVien, QuyDinh, Role, TaiKhoan, Thuoc


class QuyenQuanTri:
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == Role.ADMIN

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return login.unauthorized()
        abort(403)


class TrangChuQuanTri(QuyenQuanTri, AdminIndexView):
    pass


class BangChiXem(QuyenQuanTri, ModelView):
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_view_details = False


class BangTaiKhoan(BangChiXem):
    column_list = ("maTK", "tenDangNhap", "role", "trangThai")
    column_searchable_list = ("tenDangNhap",)


class BangBenhNhan(BangChiXem):
    column_list = ("maBN", "hoTen", "gioiTinh", "namSinh", "soDienThoai", "diaChi")
    column_searchable_list = ("hoTen",)


class BangNhanVien(BangChiXem):
    column_list = ("maNV", "hoTen", "soDienThoai", "maTK")
    column_searchable_list = ("hoTen",)


class BangThuoc(BangChiXem):
    column_list = ("maThuoc", "tenThuoc", "maDonVi", "donGia", "soLuongTon")
    column_searchable_list = ("maThuoc", "tenThuoc")


class BangHoaDon(BangChiXem):
    column_list = (
        "maHoaDon", "maPhieuKham", "maNV", "ngayLap", "tienKham",
        "tienThuoc", "tongTien", "phuongThuc", "trangThai",
    )


class BangQuyDinh(BangChiXem):
    column_list = ("maQD", "tenQuyDinh", "giaTri")


quanTri = Admin(
    app,
    name="Quản trị dữ liệu",
    index_view=TrangChuQuanTri(endpoint="flask_admin", url="/admin-console"),
)
for view, model, name, endpoint in (
    (BangTaiKhoan, TaiKhoan, "Tài khoản", "console_accounts"),
    (BangBenhNhan, BenhNhan, "Bệnh nhân", "console_patients"),
    (BangNhanVien, NhanVien, "Nhân viên", "console_employees"),
    (BangThuoc, Thuoc, "Thuốc", "console_medicines"),
    (BangHoaDon, HoaDon, "Hóa đơn", "console_invoices"),
    (BangQuyDinh, QuyDinh, "Quy định", "console_regulations"),
):
    quanTri.add_view(view(model, db.session, name=name, endpoint=endpoint))
