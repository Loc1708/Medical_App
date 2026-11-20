import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app, dao, db
from app.models import Role
from app.utils import roles_required


def _render_patient_profile(patient, form_values=None, status: int = 200):
    return render_template(
        "patient/profile.html",
        patient=patient,
        form_values=form_values or {},
    ), status


@app.route("/patient/profile", methods=["GET", "POST"])
@roles_required(Role.PATIENT)
def patient_profile():
    patient = current_user.benhNhan
    if patient is None:
        abort(400, description="Tài khoản bệnh nhân chưa có hồ sơ.")
    if request.method == "POST":
        name = request.form.get("hoTen", "").strip()
        phone = request.form.get("soDienThoai", "").strip()
        address = request.form.get("diaChi", "").strip()
        error = None
        if not name or len(name) > 100:
            error = "Họ tên bắt buộc và tối đa 100 ký tự."
        elif not re.fullmatch(r"\+?[0-9]{9,15}", phone):
            error = "Số điện thoại phải có 9–15 chữ số, có thể bắt đầu bằng +."
        elif not address or len(address) > 255:
            error = "Địa chỉ bắt buộc và tối đa 255 ký tự."

        if error:
            flash(error, "danger")
            return _render_patient_profile(patient, request.form, status=400)
        try:
            dao.update_patient_profile(
                patient.maBN,
                name=name,
                phone=phone,
                address=address,
            )
        except LookupError:
            abort(404, description="Không tìm thấy hồ sơ bệnh nhân.")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
            return _render_patient_profile(patient, request.form, status=409)

        flash("Thông tin bệnh nhân đã được cập nhật.", "success")
        return redirect(url_for("patient_profile"))
    return _render_patient_profile(patient)


def render_patient_dashboard(status: int = 200):
    patient = current_user.benhNhan
    if patient is None:
        abort(400, description="Tài khoản bệnh nhân chưa có hồ sơ.")
    return render_template(
        "patient/dashboard.html",
        patient=patient,
        registrations=dao.patient_exam_registrations(patient.maBN),
    ), status


@app.post("/patient/exam-registrations")
@login_required
@roles_required(Role.PATIENT)
def patient_register_exam():
    patient = current_user.benhNhan
    if patient is None:
        abort(400, description="Tài khoản bệnh nhân chưa có hồ sơ.")

    try:
        registration = dao.register_patient_exam(patient)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return render_patient_dashboard(status=409)
    if registration.ngayKham > dao.clinic_today():
        flash(
            "Danh sách hôm nay đã đầy hoặc đã chốt. Hồ sơ được chuyển sang ngày gần nhất còn chỗ; ngày khám sẽ hiển thị sau khi y tá xác nhận.",
            "success",
        )
    else:
        flash("Đăng ký khám thành công. Hồ sơ đã được thêm vào danh sách khám.", "success")
    return redirect(url_for("dashboard"))
