import re
from datetime import date

from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import Role
from app.utils import roles_required, send_sms


@app.get("/nurse/history")
@roles_required(Role.NURSE)
def nurse_exam_history():
    return render_template(
        "nurse/history.html",
        history=dao.nurse_confirmed_exam_history(),
    )


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
    patient = registration.benhNhan
    return {
        "id": registration.maCTDSKham,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birthYear": patient.namSinh,
        "phone": patient.soDienThoai,
        "address": patient.diaChi,
        "status": registration.trangThai,
        "slot": registration.soThuTu,
        "examDate": registration.ngayKham.isoformat(),
    }


@app.get("/nurse/api/lists")
@roles_required(Role.NURSE)
def nurse_exam_lists():
    try:
        exam_date = _nurse_exam_date(request.args.get("date"))
        limit = dao.daily_patient_limit()
        active, waiting = dao.nurse_exam_list(exam_date)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam list read failed.")
        return jsonify(error="Không thể tải danh sách khám từ cơ sở dữ liệu."), 500
    confirmed = bool(active) and all(
        entry.trangThai == "DA_XAC_NHAN" for entry in active
    )
    locked = any(entry.trangThai == "DA_XAC_NHAN" for entry in active)
    return jsonify(
        date=exam_date.isoformat(),
        limit=limit,
        active=[_nurse_exam_json(entry) for entry in active],
        waiting=[_nurse_exam_json(entry) for entry in waiting],
        confirmed=confirmed,
        locked=locked,
        today=dao.clinic_today().isoformat(),
    )


@app.get("/nurse/api/patients")
@roles_required(Role.NURSE)
def nurse_find_patient():
    query = request.args.get("q", "").strip()
    patients = dao.search_patients_by_code(query) if query else []
    return jsonify(patients=[{
        "code": patient.maHienThi,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birth_year": patient.namSinh,
        "phone": patient.soDienThoai,
    } for patient in patients])


@app.post("/nurse/api/lists")
@roles_required(Role.NURSE)
def nurse_create_exam():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Dữ liệu yêu cầu không hợp lệ."), 400
        patient_code = payload.get("patient_code")
        if not isinstance(patient_code, str) or not patient_code.strip():
            return jsonify(error="Vui lòng nhập mã bệnh nhân."), 400
        patient = dao.find_patient_by_code(patient_code)
        if patient is None:
            return jsonify(error="Không tìm thấy bệnh nhân với mã này."), 404
        exam_date = _nurse_exam_date(payload.get("date"))
        nurse = current_user.nhanVien
        registration = dao.create_nurse_exam(
            exam_date=exam_date,
            patient=patient,
            nurse_id=nurse.maNV if nurse else None,
        )
    except ValueError as error:
        db.session.rollback()
        status_code = (
            409
            if isinstance(error, (dao.DailyCapacityReached, dao.ConfirmedExamDay))
            else 400
        )
        return jsonify(error=str(error)), status_code
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
        payload = request.get_json(silent=True)
        target_date = _nurse_exam_date(
            payload.get("date") if isinstance(payload, dict) else None
        )
        nurse = current_user.nhanVien
        registration = dao.approve_waiting_nurse_exam(
            registration_id,
            target_date,
            nurse_id=nurse.maNV if nurse else None,
        )
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except dao.ConfirmedExamDay as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
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
    return jsonify(
        patient=_nurse_exam_json(registration),
        message=(
            "Đã duyệt bệnh nhân vào danh sách khám ngày "
            f"{registration.ngayKham.strftime('%d/%m/%Y')}."
        ),
    )


@app.post("/nurse/api/lists/confirm")
@roles_required(Role.NURSE)
def nurse_confirm_exam_day():
    try:
        payload = request.get_json(silent=True)
        exam_date = _nurse_exam_date(payload.get("date") if isinstance(payload, dict) else None)
        nurse = current_user.nhanVien
        confirmed_count = dao.confirm_nurse_exam_day(
            exam_date,
            nurse_id=nurse.maNV if nurse else None,
        )
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam-list confirmation failed.")
        return jsonify(error="Không thể xác nhận danh sách trong cơ sở dữ liệu."), 500
    
    if not confirmed_count:
        return jsonify(message="Danh sách đã được xác nhận trước đó.")
    sent = failed = 0
    active, _waiting = dao.nurse_exam_list(exam_date)
    for entry in active:
        patient = entry.benhNhan
        content = f"Code: {entry.soThuTu or 0:02d}"
        #f"Lich kham: {exam_date.strftime('%d/%m/%Y')}, STT: {entry.soThuTu}."
        ok, data = send_sms(patient.soDienThoai.lstrip("+"), content)
        if ok:
            sent += 1
        else:
            failed += 1
            app.logger.warning("SMS that bai cho benh nhan %s: %s", patient.maBN, data)

    return jsonify(message=f"Danh sách đã được xác nhận. Đã gửi {sent} SMS, lỗi {failed}.")
