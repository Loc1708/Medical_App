from flask import jsonify, request

from app import app, dao
from app.models import Role
from app.utils import roles_required


@app.route('/cashier/api/patients', methods=['get'])
@roles_required(Role.CASHIER)
def cashier_search_patient():
    code = request.args.get('kw', '')
    
    patients = dao.cashier_search_patients(code)
        
    return jsonify(patients=[{
        "code": p.maBN,
        "name": p.hoTen,
    }for p in patients])
        
@app.route('/cashier/api/receipts', methods=['get'])
@roles_required(Role.CASHIER)
def get_unpaid_receipts_list():
    patient = dao.find_patient_by_code(request.args.get('ma_bn', ''))
    if patient is None:
        return jsonify(error="Không tìm thấy bệnh nhân."), 404

    receipts = dao.find_unpaid_receipts(ma_bn=patient.maBN)
    if not receipts:
        return jsonify(error="Không có hóa đơn nào chưa thanh toán."), 404

    result = []
    for hd in receipts:
        result.append({
            "id": hd.maHoaDon,
            "date": hd.phieuKham.ngayKham.strftime('%d/%m/%Y'),
            "medical_fee": hd.tienKham,
            "medicine_fee": hd.tienThuoc,
            "total": hd.tongTien
        })
    return jsonify(receipts=result) 

@app.route('/cashier/api/receipts/pay', methods=['post'])
@roles_required(Role.CASHIER)
def pay_receipt_api():
    data = request.get_json(silent=True) or {}
    hd = dao.pay_receipt(data.get('id'))

    if hd is None:
        return jsonify(error="Hóa đơn không tồn tại hoặc đã thanh toán."), 400
    return jsonify(message="Thanh toán thành công.")
