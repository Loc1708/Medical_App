from flask import jsonify, request

from app import app, dao
from app.models import Role
from app.utils import yeuCauVaiTro


@app.route('/cashier/api/patients', methods=['get'], endpoint="cashier_search_patient")
@yeuCauVaiTro(Role.CASHIER)
def thuNganTimKiemBenhNhan():
    code = request.args.get('kw', '')
    
    patients = dao.thuNganTimBenhNhan(code)
        
    return jsonify(patients=[{
        "code": p.maBN,
        "name": p.hoTen,
    }for p in patients])
        
@app.route('/cashier/api/receipts', methods=['get'], endpoint="get_unpaid_receipts_list")
@yeuCauVaiTro(Role.CASHIER)
def layDanhSachHoaDonChuaThanhToan():
    patient = dao.timKiemBenhNhanTheoId(request.args.get('ma_bn', ''))
    if patient is None:
        return jsonify(error="Không tìm thấy bệnh nhân."), 404

    receipts = dao.layHoaDonChuaThanhToan(ma_bn=patient.maBN)
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

@app.route('/cashier/api/receipts/pay', methods=['post'], endpoint="pay_receipt_api")
@yeuCauVaiTro(Role.CASHIER)
def apiThanhToan():
    data = request.get_json(silent=True) or {}
    hd = dao.thanhToan(data.get('id'))

    if hd is None:
        return jsonify(error="Hóa đơn không tồn tại hoặc đã thanh toán."), 400
    return jsonify(message="Thanh toán thành công.")
