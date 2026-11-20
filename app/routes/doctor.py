import re
from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app import app, dao, db
from app.models import BacSi, Role, Thuoc
from app.utils import roles_required


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
    raw_page = request.args.get("page", "1")
    if not re.fullmatch(r"[0-9]{1,6}", raw_page) or int(raw_page) < 1:
        return jsonify(error="Số trang không hợp lệ."), 400
    page = int(raw_page)
    page_size = 5
    history, total = dao.patient_exam_history(
        patient.maBN,
        page=page,
        page_size=page_size,
    )
    return jsonify(exams=[{
        "id": exam.maPhieuKham,
        "date": exam.ngayKham.strftime("%d/%m/%Y"),
        "symptoms": exam.trieuChung,
        "diagnosis": exam.duDoanLoaiBenh or "",
        "doctor": exam.bacSi.nhanVien.hoTen,
        "prescription_count": len(exam.chiTietDonThuocs),
        "prescriptions": [{
            "code": detail.maThuoc,
            "name": detail.thuoc.tenThuoc,
            "unit": detail.thuoc.donVi.tenDonVi,
            "quantity": detail.soLuong,
            "instructions": detail.cachDung,
        } for detail in exam.chiTietDonThuocs],
        "status": exam.trangThai,
        "can_resume": (
            exam.trangThai == "NHAP"
            and current_user.nhanVien is not None
            and exam.maNV == current_user.nhanVien.maNV
        ),
    } for exam in history], page=page, page_size=page_size, total=total,
        pages=(total + page_size - 1) // page_size)


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
        "diagnosis": draft.duDoanLoaiBenh or "",
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
        "diagnosis": draft.duDoanLoaiBenh or "",
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
    raw_page = request.args.get("page", "1")
    if not re.fullmatch(r"[0-9]{1,6}", raw_page) or int(raw_page) < 1:
        return jsonify(error="Số trang không hợp lệ."), 400
    page = int(raw_page)
    medicines, total = dao.search_medicines(keyword, page=page)
    return jsonify(medicines=[{
        "code": medicine.maThuoc,
        "name": medicine.tenThuoc,
        "unit": medicine.donVi.tenDonVi,
        "stock": medicine.soLuongTon,
        "price": medicine.donGia,
    } for medicine in medicines], page=page, page_size=10, total=total,
        pages=(total + 9) // 10)


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
    diagnosis = payload.get("diagnosis", "")
    if not isinstance(diagnosis, str) or len(diagnosis.strip()) > 2000:
        return jsonify(error="Dự đoán loại bệnh tối đa 2.000 ký tự."), 400
    status = payload.get("status", "DA_LAP")
    if not isinstance(status, str) or status not in {"NHAP", "DA_LAP"}:
        return jsonify(error="Trạng thái phiếu khám không hợp lệ."), 400
    if status == "DA_LAP" and not symptoms.strip():
        return jsonify(error="Triệu chứng bắt buộc khi lập phiếu khám."), 400
    if status == "DA_LAP" and not diagnosis.strip():
        return jsonify(error="Dự đoán loại bệnh bắt buộc khi lập phiếu khám."), 400
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
        exam, invoice = dao.create_exam(
            patient, doctor, symptoms.strip(), diagnosis.strip(), prescription_data, exam_date,
            status=status, exam=draft,
        )
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Chưa lưu được phiếu khám. Vui lòng thử lại."), 503
    return jsonify(
        exam_id=exam.maPhieuKham,
        status=exam.trangThai,
        message=(
            "Đã lưu bản nháp." if status == "NHAP"
            else "Đã lập phiếu khám và hóa đơn."
        ),
        invoice_id=invoice.maHoaDon if invoice else None,
        invoice_total=invoice.tongTien if invoice else None,
    ), 201
