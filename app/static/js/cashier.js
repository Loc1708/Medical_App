function searchPatientByCode() {
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
                            onclick="selectPatient('${p.code}', '${p.name}')">
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

function selectPatient(patientCode, patientName) {
    document.getElementById('kw').value = patientName;
    let list = document.getElementById('list');
    list.innerHTML = '';
    list.classList.add('d-none');

    getUnpaidReceiptsList(patientCode);
}

let currentReceipt = [];

function getUnpaidReceiptsList(patientCode) {
    let dropdown = document.getElementById('receipts_list');
    

    fetch(`/cashier/api/receipts?ma_bn=${encodeURIComponent(patientCode)}`)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || 'Lỗi tải dữ liệu');
                });
            }
            return response.json();
        })
        .then(data => {
            currentReceipt = data.receipts || [];
            let html = '<option value="">-- Chọn hóa đơn cần thanh toán --</option>';

            currentReceipt.forEach(r => {
                html += `<option value="${r.id}">
                            HĐ #${r.id} - Ngày khám: ${r.date} - Tổng: ${r.total.toLocaleString('vi-VN')} VNĐ
                         </option>`;
            });

            dropdown.innerHTML = html;
            updateReceiptForm(null);
        })
        .catch(err => {
            dropdown.innerHTML = `<option value="">${err.message}</option>`;
        });
}


function selectReceipt() {
    let id = document.getElementById('receipts_list').value;
    let receipt = currentReceipt.find(r => String(r.id) === id);
    updateReceiptForm(receipt || null);
}

function updateReceiptForm(r) {
    document.getElementById('hoTenBN').innerText = r ? document.getElementById('kw').value : '---';
    document.getElementById('ngayKham').innerText = r ? r.date : '---';
    document.getElementById('tienKham').innerText = (r ? r.medical_fee : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('tienThuoc').innerText = (r ? r.medicine_fee : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('tongTien').innerText = (r ? r.total : 0).toLocaleString('vi-VN') + ' VNĐ';
    document.getElementById('btnThanhToan').disabled = !r;
}

function resetCashierForm() {
    document.getElementById('kw').value = '';

    let list = document.getElementById('list');
    list.innerHTML = '';
    list.classList.add('d-none');

    document.getElementById('receipts_list').innerHTML =
        '<option value="" selected disabled hidden> --Danh sách hóa đơn chưa thanh toán-- </option>';

    currentReceipt = [];
    updateReceiptForm(null);
}