from datetime import date

from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import Role
from app.utils import yeuCauVaiTro, guiTinNhanSms


@app.get("/nurse/history", endpoint="nurse_exam_history")
@yeuCauVaiTro(Role.NURSE)
def lichSuDanhSachKham():
    return render_template(
        "nurse/history.html",
        history=dao.layLichSuDanhSachDaChot(),
    )


def _layNgayKham(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Ngày khám không hợp lệ.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Ngày khám không hợp lệ.") from None


def _chuyenLuotKhamThanhJson(registration) -> dict:
    patient = registration.benhNhan
    return {
        "listId": registration.maDSKham,
        "patientId": registration.maBN,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birthYear": patient.namSinh,
        "phone": patient.soDienThoai,
        "address": patient.diaChi,
        "status": registration.trangThai,
        "slot": registration.soThuTu,
        "examDate": registration.ngayKham.isoformat(),
    }


@app.get("/nurse/api/lists", endpoint="nurse_exam_lists")
@yeuCauVaiTro(Role.NURSE)
def layDanhSachKhamYTa():
    try:
        exam_date = _layNgayKham(request.args.get("date"))
        limit = dao.layGioiHanBenhNhanNgay()
        active, waiting = dao.layDanhSachKham(exam_date)
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
        active=[_chuyenLuotKhamThanhJson(entry) for entry in active],
        waiting=[_chuyenLuotKhamThanhJson(entry) for entry in waiting],
        confirmed=confirmed,
        locked=locked,
        today=dao.ngayHienTaiPhongKham().isoformat(),
    )


@app.get("/nurse/api/patients", endpoint="nurse_find_patient")
@yeuCauVaiTro(Role.NURSE)
def yTaTimBenhNhan():
    query = request.args.get("q", "").strip()
    patients = dao.timBenhNhanTheoMa(query) if query else []
    return jsonify(patients=[{
        "code": patient.maHienThi,
        "name": patient.hoTen,
        "gender": patient.gioiTinh,
        "birth_year": patient.namSinh,
        "phone": patient.soDienThoai,
    } for patient in patients])


@app.post("/nurse/api/lists", endpoint="nurse_create_exam")
@yeuCauVaiTro(Role.NURSE)
def yTaThemLuotKham():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Dữ liệu yêu cầu không hợp lệ."), 400
        patient_code = payload.get("patient_code")
        if not isinstance(patient_code, str) or not patient_code.strip():
            return jsonify(error="Vui lòng nhập mã bệnh nhân."), 400
        patient = dao.timKiemBenhNhanTheoId(patient_code)
        if patient is None:
            return jsonify(error="Không tìm thấy bệnh nhân với mã này."), 404
        exam_date = _layNgayKham(payload.get("date"))
        nurse = current_user.nhanVien
        registration = dao.themBenhNhan(
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
    return jsonify(patient=_chuyenLuotKhamThanhJson(registration),
                   message="Đã lưu bệnh nhân vào danh sách khám."), 201


@app.delete(
    "/nurse/api/lists/<int:maDSKham>/<int:maBN>",
    endpoint="nurse_cancel_exam",
)
@yeuCauVaiTro(Role.NURSE)
def yTaHuyLuotKham(maDSKham: int, maBN: int):
    try:
        dao.huyLuotKham(maDSKham, maBN)
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam cancellation failed.")
        return jsonify(error="Không thể hủy lượt khám trong cơ sở dữ liệu."), 500
    return jsonify(message="Đã hủy lượt khám.")


@app.post("/nurse/api/lists/confirm", endpoint="nurse_confirm_exam_day")
@yeuCauVaiTro(Role.NURSE)
def yTaXacNhanDanhSach():
    try:
        payload = request.get_json(silent=True)
        exam_date = _layNgayKham(payload.get("date") if isinstance(payload, dict) else None)
        nurse = current_user.nhanVien
        sms_entries = dao.xacNhanDanhSach(
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

    if not sms_entries:
        return jsonify(message="Danh sách đã được xác nhận trước đó.")
    sent = failed = 0
    for entry in sms_entries:
        patient = entry.benhNhan
        code = f"{entry.soThuTu or 0:02d}"   # phần biến, tối đa 20 ký tự
        content = f"{code} la ma xac minh dang ky Baotrixemay cua ban"
        #f"Lich kham: {exam_date.strftime('%d/%m/%Y')}, STT: {entry.soThuTu}."
        ok, data = guiTinNhanSms(patient.soDienThoai.lstrip("+"), content)
        if ok:
            sent += 1
        else:
            failed += 1
            app.logger.warning("SMS that bai cho benh nhan %s: %s", patient.maBN, data)

    return jsonify(message=f"Danh sách đã được xác nhận. Đã gửi {sent} SMS, lỗi {failed}.")


@app.post("/nurse/api/lists/reopen", endpoint="nurse_reopen_exam_day")
@yeuCauVaiTro(Role.NURSE)
def yTaMoLaiDanhSach():
    try:
        payload = request.get_json(silent=True)
        exam_date = _layNgayKham(
            payload.get("date") if isinstance(payload, dict) else None
        )
        reopened_count = dao.moLaiDanhSachKham(exam_date)
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Nurse exam-list reopen failed.")
        return jsonify(error="Không thể mở lại danh sách trong cơ sở dữ liệu."), 500
    return jsonify(
        message=(
            "Đã mở lại danh sách khám để bổ sung bệnh nhân. "
            f"Có {reopened_count} bệnh nhân cần xác nhận lại."
        ),
        reopened_count=reopened_count,
    )
