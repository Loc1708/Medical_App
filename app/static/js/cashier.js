let receiptPaidState = 'DA_THANH_TOAN';
let receiptUnpaidState = 'CHUA_THANH_TOAN';

function timKiemBenhNhan() {
    let kw = document.getElementById('kw').value.trim();
    let list = document.getElementById('list');

    if (!kw) {
        list.innerHTML = '';
        list.classList.add('d-none');
        return;
    }
    fetch(`/cashier/api/patients?kw=${encodeURIComponent(kw)}`)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error);
                });
            }
            return response.json();
        })
        .then(data => {
            let patients = data.patients || [];

            if (patients.length > 0) {
                let html = '';

                patients.forEach(p => {
                    html += `
                        <li class="list-group-item list-group-item-action"
                            style="cursor: pointer;"
                            onclick="chonBenhNhan('${p.code}', '${p.name}')">
                            <strong>${p.name}</strong>
                            <small class="text-muted">(${p.code})</small>
                        </li>`;
                });
                list.innerHTML = html;
                list.classList.remove('d-none');
            }
        })
        .catch(err => {
            list.innerHTML = `<li class="list-group-item text-danger">${err.message}</li>`;
            list.classList.remove('d-none');
        });
}

function chonBenhNhan(patientCode, patientName) {
    document.getElementById('kw').value = patientName;
    let list = document.getElementById('list');
    list.innerHTML = '';
    list.classList.add('d-none');

    layDanhSachHoaDonChuaThanhToan(patientCode);
}

let currentReceipt = [];

function layDanhSachHoaDonChuaThanhToan(patientCode) {
    let dropdown = document.getElementById('receipts_list');
    
    fetch(`/cashier/api/receipts?ma_bn=${encodeURIComponent(patientCode)}`).then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || 'Lỗi tải dữ liệu');
                });
            }
            return response.json();

        }).then(data => {
            currentReceipt = data.receipts || [];
            let html = '<option value="">-- Chọn hóa đơn cần thanh toán --</option>';

            currentReceipt.forEach(r => {
                html += `<option value="${r.id}">
                            HĐ #${r.id} - Ngày khám: ${r.date} - Tổng: ${r.total.toLocaleString('vi-VN')} VNĐ
                         </option>`;
            });
            dropdown.innerHTML = html;
            capNhatHoaDon(null);

        }).catch(err => {
            dropdown.innerHTML = `<option value="">${err.message}</option>`;
        });
}


function chonHoaDon() {
    let id = document.getElementById('receipts_list').value;
    let receipt = currentReceipt.find(r => String(r.id) === id);
    capNhatHoaDon(receipt || null);
}

function capNhatHoaDon(r) {
    document.getElementById('hoTenBN').innerText = r ? document.getElementById('kw').value : '---';
    document.getElementById('ngayKham').innerText = r ? r.date : '---';
    document.getElementById('tienKham').innerText = (r ? r.medical_fee : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('tienThuoc').innerText = (r ? r.medicine_fee : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('tongTien').innerText = (r ? r.total : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('btnThanhToan').disabled = !r;
}

function lamMoiBieuMauThuNgan() {
    document.getElementById('kw').value = '';

    let list = document.getElementById('list');
    list.innerHTML = '';
    list.classList.add('d-none');

    document.getElementById('receipts_list').innerHTML =
        '<option value="" selected disabled hidden> --Danh sách hóa đơn chưa thanh toán-- </option>';

    currentReceipt = [];
    capNhatHoaDon(null);
}

function thanhToan() {
    let id = document.getElementById('receipts_list').value;
    if (!id) return;

    fetch('/cashier/api/receipts/pay', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content          
        },
        body: JSON.stringify({ id: id })
    }).then(response => response.json().then(data => {
            if (!response.ok) {
                throw new Error(data.error || 'Lỗi thanh toán');
            }
            return data;
        })).then(data => {
            alert(data.message);
            lamMoiBieuMauThuNgan();
        }).catch(err => alert(err.message));
}