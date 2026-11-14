import hashlib
import re
from datetime import date, datetime, timedelta, timezone

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import BacSi, Role, Thuoc
from app.utils import account_data, csrf_token, protect_csrf, roles_required


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
    if current_user.role == Role.DOCTOR:
        clinic_timezone = timezone(timedelta(hours=7))
        exam_date = datetime.now(clinic_timezone).date()
        return render_template("doctor/dashboard.html", exam_date=exam_date)
    if current_user.role == Role.NURSE:
        return render_template("nurse/dashboard.html", current_year=date.today().year)
    if current_user.role == Role.PATIENT:
        return _render_patient_dashboard()
    template = {
        Role.NURSE: "nurse/dashboard.html",
        Role.CASHIER: "cashier/dashboard.html",
    }.get(current_user.role)
    if template is None:
        abort(403)
    return render_template(template)


def _render_patient_dashboard(registration_values=None, status: int = 200):
    patient = current_user.benhNhan
    if patient is None:
        abort(400, description="Tài khoản bệnh nhân chưa có hồ sơ.")
    return render_template(
        "patient/dashboard.html",
        registrations=dao.patient_exam_registrations(patient.maBN),
        registration_values=registration_values or {},
    ), status


@app.post("/patient/exam-registrations")
@login_required
@roles_required(Role.PATIENT)
def patient_register_exam():
    patient = current_user.benhNhan
    if patient is None:
        abort(400, description="Tài khoản bệnh nhân chưa có hồ sơ.")

    name = request.form.get("hoTen", "").strip()
    gender = request.form.get("gioiTinh", "")
    address = request.form.get("diaChi", "").strip()
    try:
        birth_year = int(request.form.get("namSinh", ""))
    except ValueError:
        birth_year = 0

    if not name or len(name) > 100:
        flash("Họ tên bắt buộc và tối đa 100 ký tự.", "danger")
    elif gender not in {"Nam", "Nữ", "Khác"}:
        flash("Vui lòng chọn giới tính hợp lệ.", "danger")
    elif not 1900 <= birth_year <= date.today().year:
        flash("Năm sinh phải từ 1900 đến năm hiện tại.", "danger")
    elif not address or len(address) > 255:
        flash("Địa chỉ bắt buộc và tối đa 255 ký tự.", "danger")
    else:
        try:
            registration = dao.register_patient_exam(
                patient,
                name=name,
                gender=gender,
                birth_year=birth_year,
                address=address,
            )
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
            return _render_patient_dashboard(request.form, status=400)
        if registration.trangThai == "CHO_DUYET":
            flash(
                "Đã nhận đăng ký. Danh sách đủ chỗ; hồ sơ đang chờ y tá duyệt.",
                "success",
            )
        else:
            flash("Đăng ký khám thành công. Hồ sơ đã được thêm vào danh sách khám.", "success")
        return redirect(url_for("dashboard"))

    return _render_patient_dashboard(request.form, status=400)


def _nurse_exam_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Ngày khám không hợp lệ.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Ngày khám không hợp lệ.") from None


def _nurse_exam_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dữ liệu bệnh nhân không hợp lệ.")
    name = payload.get("name", "")
    gender = payload.get("gender", "")
    phone = payload.get("phone", "")
    address = payload.get("address", "")
    try:
        birth_year = int(payload.get("birthYear", ""))
    except (TypeError, ValueError):
        birth_year = 0
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("Họ tên bắt buộc và tối đa 100 ký tự.")
    if not isinstance(gender, str) or gender not in {"Nam", "Nữ", "Khác"}:
        raise ValueError("Giới tính không hợp lệ.")
    if not 1900 <= birth_year <= date.today().year:
        raise ValueError("Năm sinh phải từ 1900 đến năm hiện tại.")
    if not isinstance(phone, str) or not re.fullmatch(r"\+?[0-9]{9,15}", phone.strip()):
        raise ValueError("Số điện thoại phải có 9–15 chữ số, có thể bắt đầu bằng +.")
    if not isinstance(address, str) or not address.strip() or len(address.strip()) > 255:
        raise ValueError("Địa chỉ bắt buộc và tối đa 255 ký tự.")
    return {
        "name": name.strip(),
        "gender": gender,
        "birth_year": birth_year,
        "phone": phone.strip(),
        "address": address.strip(),
    }


def _nurse_exam_json(registration) -> dict:
    return {
        "id": registration.maDSKham,
        "name": registration.hoTen,
        "gender": registration.gioiTinh,
        "birthYear": registration.namSinh,
        "phone": registration.benhNhan.soDienThoai,
        "address": registration.diaChi,
        "status": registration.trangThai,
        "slot": registration.soThuTu,
    }


@app.get("/nurse/api/lists")
@roles_required(Role.NURSE)
def nurse_exam_lists():
    try:
        exam_date = _nurse_exam_date(request.args.get("date"))
        limit = dao.daily_patient_limit()
        active, waiting = dao.nurse_exam_list(exam_date)
        history = dao.nurse_exam_history()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam list read failed.")
        return jsonify(error="Không thể tải danh sách khám từ cơ sở dữ liệu."), 500
    confirmed = bool(active) and all(
        entry.trangThai == "DA_XAC_NHAN" for entry in active
    )
    return jsonify(
        date=exam_date.isoformat(),
        limit=limit,
        active=[_nurse_exam_json(entry) for entry in active],
        waiting=[_nurse_exam_json(entry) for entry in waiting],
        history=history,
        confirmed=confirmed,
    )


@app.post("/nurse/api/lists")
@roles_required(Role.NURSE)
def nurse_create_exam():
    try:
        payload = request.get_json(silent=True)
        data = _nurse_exam_payload(payload)
        exam_date = _nurse_exam_date(payload.get("date") if isinstance(payload, dict) else None)
        registration = dao.create_nurse_exam(exam_date=exam_date, **data)
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409 if isinstance(error, dao.DailyCapacityReached) else 400
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse patient registration failed.")
        return jsonify(error="Không thể lưu lượt khám vào cơ sở dữ liệu."), 500
    message = (
        "Danh sách đã đủ chỗ; bệnh nhân được lưu vào hàng chờ để y tá duyệt."
        if registration.trangThai == "CHO_DUYET"
        else "Đã lưu bệnh nhân vào danh sách khám."
    )
    return jsonify(patient=_nurse_exam_json(registration), message=message), 201


@app.put("/nurse/api/lists/<int:registration_id>")
@roles_required(Role.NURSE)
def nurse_update_exam(registration_id: int):
    try:
        data = _nurse_exam_payload(request.get_json(silent=True))
        registration = dao.update_nurse_exam(registration_id, **data)
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse patient update failed.")
        return jsonify(error="Không thể cập nhật lượt khám trong cơ sở dữ liệu."), 500
    return jsonify(patient=_nurse_exam_json(registration), message="Đã cập nhật bệnh nhân.")


@app.delete("/nurse/api/lists/<int:registration_id>")
@roles_required(Role.NURSE)
def nurse_cancel_exam(registration_id: int):
    try:
        dao.cancel_nurse_exam(registration_id)
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam cancellation failed.")
        return jsonify(error="Không thể hủy lượt khám trong cơ sở dữ liệu."), 500
    return jsonify(message="Đã hủy lượt khám.")


@app.post("/nurse/api/lists/<int:registration_id>/approve")
@roles_required(Role.NURSE)
def nurse_approve_exam(registration_id: int):
    try:
        registration = dao.approve_waiting_nurse_exam(registration_id)
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except dao.DailyCapacityReached as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 400
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse waiting-list approval failed.")
        return jsonify(error="Không thể duyệt bệnh nhân trong cơ sở dữ liệu."), 500
    return jsonify(patient=_nurse_exam_json(registration), message="Đã duyệt bệnh nhân vào danh sách khám.")


@app.post("/nurse/api/lists/confirm")
@roles_required(Role.NURSE)
def nurse_confirm_exam_day():
    try:
        payload = request.get_json(silent=True)
        exam_date = _nurse_exam_date(payload.get("date") if isinstance(payload, dict) else None)
        confirmed_count = dao.confirm_nurse_exam_day(exam_date)
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam-list confirmation failed.")
        return jsonify(error="Không thể xác nhận danh sách trong cơ sở dữ liệu."), 500
    message = "Danh sách đã được xác nhận." if confirmed_count else "Danh sách đã được xác nhận trước đó."
    return jsonify(message=message)


@app.get("/doctor/api/patients")
@roles_required(Role.DOCTOR)
def doctor_find_patient():
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify(error="Vui lòng nhập mã bệnh nhân."), 400
    patient = dao.find_patient_by_code(code)
    if patient is None:
        return jsonify(error="Không tìm thấy bệnh nhân với mã này."), 404
    return jsonify(patient={
        "code": patient.maHienThi,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birth_year": patient.namSinh,
        "phone": patient.soDienThoai,
        "address": patient.diaChi,
    })


@app.get("/doctor/api/patients/<code>/history")
@roles_required(Role.DOCTOR)
def doctor_patient_history(code: str):
    patient = dao.find_patient_by_code(code)
    if patient is None:
        return jsonify(error="Không tìm thấy bệnh nhân với mã này."), 404
    history = dao.patient_exam_history(patient.maBN)
    return jsonify(exams=[{
        "id": exam.maPhieuKham,
        "date": exam.ngayKham.strftime("%d/%m/%Y"),
        "symptoms": exam.trieuChung,
        "doctor": exam.bacSi.nhanVien.hoTen,
        "prescription_count": len(exam.chiTietDonThuocs),
        "status": exam.trangThai,
        "can_resume": (
            exam.trangThai == "NHAP"
            and current_user.nhanVien is not None
            and exam.maNV == current_user.nhanVien.maNV
        ),
    } for exam in history])


@app.get("/doctor/api/exams/<exam_id>")
@roles_required(Role.DOCTOR)
def doctor_get_draft(exam_id: str):
    doctor_id = current_user.nhanVien.maNV if current_user.nhanVien else None
    draft = dao.find_doctor_draft(exam_id, doctor_id) if doctor_id is not None else None
    if draft is None:
        return jsonify(error="Không tìm thấy bản nháp của bác sĩ này."), 404
    return jsonify(exam={
        "id": draft.maPhieuKham,
        "patient_code": draft.benhNhan.maHienThi,
        "symptoms": draft.trieuChung,
        "prescriptions": [{
            "medicine_code": detail.maThuoc,
            "name": detail.thuoc.tenThuoc,
            "unit": detail.thuoc.donVi.tenDonVi,
            "stock": detail.thuoc.soLuongTon,
            "quantity": detail.soLuong,
            "instructions": detail.cachDung,
        } for detail in draft.chiTietDonThuocs],
    })


@app.get("/doctor/api/drafts")
@roles_required(Role.DOCTOR)
def doctor_list_drafts():
    doctor_id = current_user.nhanVien.maNV if current_user.nhanVien else None
    if doctor_id is None:
        return jsonify(error="Tài khoản bác sĩ chưa có hồ sơ chuyên môn."), 409
    drafts = dao.doctor_drafts(doctor_id)
    return jsonify(drafts=[{
        "id": draft.maPhieuKham,
        "patient_code": draft.benhNhan.maHienThi,
        "patient_name": draft.benhNhan.hoTen,
        "date": draft.ngayKham.strftime("%d/%m/%Y"),
        "symptoms": draft.trieuChung,
        "prescription_count": len(draft.chiTietDonThuocs),
    } for draft in drafts])


@app.delete("/doctor/api/drafts/<exam_id>")
@roles_required(Role.DOCTOR)
def doctor_delete_draft(exam_id: str):
    doctor_id = current_user.nhanVien.maNV if current_user.nhanVien else None
    if doctor_id is None:
        return jsonify(error="Tài khoản bác sĩ chưa có hồ sơ chuyên môn."), 409
    if not dao.delete_doctor_draft(exam_id, doctor_id):
        return jsonify(error="Không tìm thấy bản nháp của bác sĩ này."), 404
    return jsonify(message="Đã xóa bản nháp.")


@app.get("/doctor/api/medicines")
@roles_required(Role.DOCTOR)
def doctor_search_medicines():
    keyword = request.args.get("q", "").strip()
    if len(keyword) < 2:
        return jsonify(medicines=[])
    medicines = dao.search_medicines(keyword)
    return jsonify(medicines=[{
        "code": medicine.maThuoc,
        "name": medicine.tenThuoc,
        "unit": medicine.donVi.tenDonVi,
        "stock": medicine.soLuongTon,
        "price": medicine.donGia,
    } for medicine in medicines])


@app.post("/doctor/api/exams")
@roles_required(Role.DOCTOR)
def doctor_create_exam():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Dữ liệu phiếu khám không hợp lệ."), 400

    patient = dao.find_patient_by_code(str(payload.get("patient_code", "")))
    if patient is None:
        return jsonify(error="Vui lòng tìm bệnh nhân hợp lệ trước khi lập phiếu."), 400
    symptoms = payload.get("symptoms")
    if not isinstance(symptoms, str) or len(symptoms.strip()) > 2000:
        return jsonify(error="Triệu chứng tối đa 2.000 ký tự."), 400
    status = payload.get("status", "DA_LAP")
    if not isinstance(status, str) or status not in {"NHAP", "DA_LAP"}:
        return jsonify(error="Trạng thái phiếu khám không hợp lệ."), 400
    if status == "DA_LAP" and not symptoms.strip():
        return jsonify(error="Triệu chứng bắt buộc khi lập phiếu khám."), 400
    rows = payload.get("prescriptions", [])
    if not isinstance(rows, list) or len(rows) > 30:
        return jsonify(error="Danh sách thuốc không hợp lệ."), 400

    doctor = db.session.get(BacSi, current_user.nhanVien.maNV) if current_user.nhanVien else None
    if doctor is None:
        return jsonify(error="Tài khoản bác sĩ chưa có hồ sơ chuyên môn."), 409

    draft = None
    draft_id = payload.get("draft_id")
    if draft_id is not None:
        if not isinstance(draft_id, str):
            return jsonify(error="Mã bản nháp không hợp lệ."), 400
        draft = dao.find_doctor_draft(draft_id, doctor.maNV)
        if draft is None:
            return jsonify(error="Không tìm thấy bản nháp của bác sĩ này."), 404
        if draft.maBN != patient.maBN:
            return jsonify(error="Bản nháp đã thuộc về bệnh nhân khác."), 409

    prescription_data = []
    seen_medicine_codes = set()
    for row in rows:
        if not isinstance(row, dict):
            return jsonify(error="Thông tin thuốc trong đơn không hợp lệ."), 400
        medicine_code = row.get("medicine_code")
        instructions = row.get("instructions")
        quantity = row.get("quantity")
        if (
            not isinstance(medicine_code, str) or medicine_code in seen_medicine_codes
            or not isinstance(instructions, str)
            or (status == "DA_LAP" and not instructions.strip())
            or len(instructions.strip()) > 255
            or not isinstance(quantity, int) or isinstance(quantity, bool)
            or not 1 <= quantity <= 500
        ):
            return jsonify(error="Vui lòng kiểm tra mã thuốc, số lượng và cách dùng."), 400
        seen_medicine_codes.add(medicine_code)
        medicine = db.session.get(Thuoc, medicine_code)
        if medicine is None:
            return jsonify(error=f"Không tìm thấy thuốc {medicine_code}."), 400
        if quantity > medicine.soLuongTon:
            return jsonify(error=f"Số lượng thuốc {medicine.tenThuoc} vượt quá tồn kho."), 400
        prescription_data.append({
            "medicine": medicine,
            "quantity": quantity,
            "instructions": instructions.strip(),
        })

    clinic_timezone = timezone(timedelta(hours=7))
    exam_date = datetime.now(clinic_timezone).date()
    try:
        exam = dao.create_exam(
            patient, doctor, symptoms.strip(), prescription_data, exam_date,
            status=status, exam=draft,
        )
    except ValueError:
        return jsonify(error="Phiếu khám bị xung đột dữ liệu; vui lòng kiểm tra và thử lại."), 409
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Chưa lưu được phiếu khám. Vui lòng thử lại."), 503
    return jsonify(
        exam_id=exam.maPhieuKham,
        status=exam.trangThai,
        message="Đã lưu bản nháp." if status == "NHAP" else "Đã lập phiếu khám.",
    ), 201

@app.route('/cashier/api/dashboard', methods=['get'])
@roles_required(Role.CASHIER)
def cashier_search_patient():
    code = request.args.get('kw', None)
    
    patient = dao.find_patient_by_code(code)
    if patient is None:
            return jsonify(error="Không tìm thấy bệnh nhân với mã này."), 404
    return jsonify(patients=[{
        "code": patient.maHienThi,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birth_year": patient.namSinh,
    }])
        
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
