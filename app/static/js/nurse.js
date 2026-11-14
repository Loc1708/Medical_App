const nurseApp = document.querySelector("[data-nurse-app]");

if (nurseApp) {
    const pageSize = 10;
    const dateInput = nurseApp.querySelector("#nurse-exam-date");
    const limitLabel = nurseApp.querySelector("[data-daily-limit]");
    const patientForm = nurseApp.querySelector("[data-patient-form]");
    const nameInput = nurseApp.querySelector("#nurse-patient-name");
    const birthYearInput = nurseApp.querySelector("#nurse-birth-year");
    const phoneInput = nurseApp.querySelector("#nurse-patient-phone");
    const addressInput = nurseApp.querySelector("#nurse-patient-address");
    const submitPatientButton = nurseApp.querySelector("[data-submit-patient]");
    const cancelEditButton = nurseApp.querySelector("[data-cancel-edit]");
    const searchForm = nurseApp.querySelector("[data-search-form]");
    const searchInput = nurseApp.querySelector("#nurse-search");
    const patientRows = nurseApp.querySelector("[data-patient-rows]");
    const waitingRows = nurseApp.querySelector("[data-waiting-rows]");
    const pagination = nurseApp.querySelector("[data-pagination]");
    const waitingPagination = nurseApp.querySelector("[data-waiting-pagination]");
    const listSummary = nurseApp.querySelector("[data-list-summary]");
    const waitingSummary = nurseApp.querySelector("[data-waiting-summary]");
    const patientCount = nurseApp.querySelector("[data-patient-count]");
    const waitingCount = nurseApp.querySelector("[data-waiting-count]");
    const approvalTarget = nurseApp.querySelector("[data-approval-target]");
    const status = nurseApp.querySelector("[data-nurse-status]");
    const historyPanel = nurseApp.querySelector("#nurse-history");
    const historyRows = nurseApp.querySelector("[data-history-rows]");
    const confirmedStatus = nurseApp.querySelector("[data-confirmed-status]");
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    let selectedDate = "";
    let clinicToday = todayValue();
    let currentPage = 1;
    let currentWaitingPage = 1;
    let searchTerm = "";
    let editingPatientId = null;
    let dailyLimit = 0;
    let activePatients = [];
    let waitingPatients = [];
    let history = [];
    let dayConfirmed = false;

    function todayValue() {
        const now = new Date();
        return [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("-");
    }

    function showStatus(message, kind = "info") {
        status.textContent = message;
        status.classList.toggle("is-error", kind === "error");
        status.classList.toggle("is-success", kind === "success");
        status.hidden = !message;
    }

    function normalize(value) {
        return value.toLocaleLowerCase("vi")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d");
    }

    function formatDate(value) {
        const [year, month, day] = value.split("-").map(Number);
        return new Intl.DateTimeFormat("vi-VN").format(new Date(year, month - 1, day));
    }

    async function requestApi(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken,
                ...options.headers,
            },
        });
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error("Máy chủ trả về dữ liệu không hợp lệ.");
        }
        if (!response.ok) {
            throw new Error(data.error || "Không thể hoàn thành thao tác.");
        }
        return data;
    }

    async function refreshDay() {
        const data = await requestApi(
            `/nurse/api/lists?date=${encodeURIComponent(selectedDate)}`
        );
        dailyLimit = data.limit;
        clinicToday = data.today;
        activePatients = data.active;
        waitingPatients = data.waiting;
        history = data.history;
        dayConfirmed = data.confirmed;
        nurseApp.dataset.maxPatients = String(dailyLimit);
        limitLabel.textContent = `Giới hạn: ${dailyLimit} bệnh nhân/ngày`;
        renderAll();
    }

    function makeCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
        return cell;
    }

    function makeButton(label, className, action, id, disabled = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className;
        button.dataset[action] = id;
        button.textContent = label;
        button.disabled = disabled;
        return button;
    }

    function addPagination(container, pageCount, page, action) {
        container.replaceChildren();
        if (pageCount <= 1) return;

        function addPageButton(label, target, disabled = false, current = false) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = current
                ? "btn btn-sm btn-primary"
                : "btn btn-sm btn-outline-primary";
            button.textContent = label;
            button.dataset[action] = String(target);
            button.disabled = disabled;
            if (current) button.setAttribute("aria-current", "page");
            container.append(button);
        }

        addPageButton("< Trước", page - 1, page === 1);
        for (let target = 1; target <= pageCount; target += 1) {
            addPageButton(String(target), target, false, target === page);
        }
        addPageButton("Sau >", page + 1, page === pageCount);
    }

    function filtered(items) {
        const query = normalize(searchTerm.trim());
        return items.filter(patient => (
            !query || normalize(patient.name).includes(query)
        ));
    }

    function renderPatients() {
        const patients = filtered(activePatients);
        const pageCount = Math.ceil(patients.length / pageSize);
        currentPage = Math.min(currentPage, Math.max(pageCount, 1));
        const start = (currentPage - 1) * pageSize;
        const visible = patients.slice(start, start + pageSize);

        patientRows.replaceChildren();
        patientCount.textContent = `${activePatients.length}/${dailyLimit}`;
        confirmedStatus.textContent = dayConfirmed
            ? "Danh sách hiện tại đã được xác nhận."
            : "";

        if (!visible.length) {
            const row = document.createElement("tr");
            const cell = makeCell(
                row,
                searchTerm ? "Không tìm thấy bệnh nhân phù hợp." : "Chưa có bệnh nhân trong ngày này."
            );
            cell.colSpan = 6;
            cell.className = "nurse-table-empty";
            patientRows.append(row);
        } else {
            visible.forEach((patient, index) => {
                const row = document.createElement("tr");
                makeCell(row, String(start + index + 1));
                makeCell(row, patient.name);
                makeCell(row, patient.gender);
                makeCell(row, patient.phone);
                makeCell(row, String(patient.birthYear));
                const actions = document.createElement("td");
                actions.className = "nurse-row-actions";
                actions.append(
                    makeButton(
                        "Sửa", "btn btn-sm btn-outline-primary", "editPatient",
                        patient.id, patient.status === "DA_XAC_NHAN"
                    ),
                    makeButton(
                        "Hủy", "btn btn-sm btn-outline-danger", "cancelPatient", patient.id
                    )
                );
                row.append(actions);
                patientRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        listSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`
            : `0 kết quả · ${activePatients.length}/${dailyLimit} bệnh nhân trong danh sách`;
        addPagination(pagination, pageCount, currentPage, "page");
    }

    function renderWaiting() {
        const patients = filtered(waitingPatients);
        const pageCount = Math.ceil(patients.length / pageSize);
        currentWaitingPage = Math.min(currentWaitingPage, Math.max(pageCount, 1));
        const start = (currentWaitingPage - 1) * pageSize;
        const visible = patients.slice(start, start + pageSize);

        waitingRows.replaceChildren();
        waitingCount.textContent = String(waitingPatients.length);
        const targetIsPast = selectedDate < clinicToday;
        approvalTarget.textContent = targetIsPast
            ? "Không thể duyệt vào ngày đã qua."
            : `Ngày khám đích: ${formatDate(selectedDate)}`;
        if (!visible.length) {
            const row = document.createElement("tr");
            const cell = makeCell(
                row,
                searchTerm ? "Không tìm thấy bệnh nhân phù hợp." : "Chưa có bệnh nhân chờ duyệt."
            );
            cell.colSpan = 6;
            cell.className = "nurse-table-empty";
            waitingRows.append(row);
        } else {
            visible.forEach((patient, index) => {
                const row = document.createElement("tr");
                makeCell(row, String(start + index + 1));
                makeCell(row, patient.name);
                makeCell(row, formatDate(patient.examDate));
                makeCell(row, patient.phone);
                makeCell(row, String(patient.birthYear));
                const actions = document.createElement("td");
                actions.className = "nurse-row-actions";
                actions.append(
                    makeButton("Sửa", "btn btn-sm btn-outline-primary", "editPatient", patient.id),
                    makeButton(
                        "Duyệt vào ngày đã chọn", "btn btn-sm btn-outline-success",
                        "approvePatient", patient.id,
                        targetIsPast || activePatients.length >= dailyLimit
                    ),
                    makeButton(
                        "Hủy", "btn btn-sm btn-outline-danger", "cancelPatient", patient.id
                    )
                );
                row.append(actions);
                waitingRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        waitingSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} bệnh nhân đang chờ`
            : "Chưa có bệnh nhân chờ duyệt.";
        addPagination(waitingPagination, pageCount, currentWaitingPage, "waitingPage");
    }

    function renderHistory() {
        historyRows.replaceChildren();
        if (!history.length) {
            const row = document.createElement("tr");
            const cell = makeCell(row, "Chưa có danh sách khám đã lưu.");
            cell.colSpan = 5;
            cell.className = "nurse-table-empty";
            historyRows.append(row);
            return;
        }

        history.forEach(day => {
            const row = document.createElement("tr");
            makeCell(row, formatDate(day.date));
            makeCell(row, String(day.active));
            makeCell(row, String(day.waiting));
            makeCell(
                row,
                day.active && day.confirmed === day.active ? "Đã xác nhận" : "Đang tiếp nhận"
            );
            const action = document.createElement("td");
            action.append(makeButton(
                "Mở danh sách", "btn btn-sm btn-outline-primary", "openDate", day.date
            ));
            row.append(action);
            historyRows.append(row);
        });
    }

    function renderAll() {
        renderPatients();
        renderWaiting();
        renderHistory();
    }

    function resetPatientForm() {
        patientForm.reset();
        editingPatientId = null;
        submitPatientButton.textContent = "Thêm vào danh sách";
        cancelEditButton.hidden = true;
    }

    function beginEdit(patientId) {
        const patient = [...activePatients, ...waitingPatients]
            .find(item => String(item.id) === String(patientId));
        if (!patient) return;
        if (patient.status === "DA_XAC_NHAN") {
            showStatus("Lượt khám đã xác nhận, không thể chỉnh sửa.", "error");
            return;
        }

        editingPatientId = patient.id;
        nameInput.value = patient.name;
        patientForm.querySelector(`input[name="gender"][value="${patient.gender}"]`).checked = true;
        birthYearInput.value = String(patient.birthYear);
        phoneInput.value = patient.phone;
        addressInput.value = patient.address;
        submitPatientButton.textContent = "Cập nhật bệnh nhân";
        cancelEditButton.hidden = false;
        nameInput.focus();
        showStatus(`Đang chỉnh sửa thông tin của ${patient.name}.`);
    }

    async function savePatient(event) {
        event.preventDefault();
        if (!selectedDate) {
            showStatus("Vui lòng chọn ngày khám trước.", "error");
            dateInput.focus();
            return;
        }
        if (!patientForm.reportValidity()) return;

        const gender = patientForm.querySelector('input[name="gender"]:checked');
        const patient = {
            date: selectedDate,
            name: nameInput.value.trim(),
            gender: gender ? gender.value : "",
            birthYear: Number(birthYearInput.value),
            phone: phoneInput.value.trim(),
            address: addressInput.value.trim(),
        };
        const currentYear = new Date().getFullYear();
        if (!patient.name || !Number.isInteger(patient.birthYear)
            || patient.birthYear < 1900 || patient.birthYear > currentYear
            || !/^\+?[0-9]{9,15}$/.test(patient.phone)
            || !patient.address || patient.address.length > 255) {
            showStatus("Vui lòng kiểm tra lại thông tin bệnh nhân.", "error");
            return;
        }

        submitPatientButton.disabled = true;
        try {
            const endpoint = editingPatientId
                ? `/nurse/api/lists/${editingPatientId}`
                : "/nurse/api/lists";
            const result = await requestApi(endpoint, {
                method: editingPatientId ? "PUT" : "POST",
                body: JSON.stringify(patient),
            });
            resetPatientForm();
            currentPage = 1;
            currentWaitingPage = 1;
            searchTerm = "";
            searchInput.value = "";
            await refreshDay();
            showStatus(result.message, result.patient.status === "CHO_DUYET" ? "info" : "success");
        } catch (error) {
            showStatus(error.message, "error");
        } finally {
            submitPatientButton.disabled = false;
        }
    }

    async function cancelPatient(patientId) {
        const patient = [...activePatients, ...waitingPatients]
            .find(item => String(item.id) === String(patientId));
        if (!patient || !window.confirm(`Hủy lượt khám của ${patient.name}?`)) return;
        try {
            const result = await requestApi(`/nurse/api/lists/${patient.id}`, {
                method: "DELETE",
            });
            if (String(editingPatientId) === String(patient.id)) resetPatientForm();
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    }

    async function approvePatient(patientId) {
        try {
            const result = await requestApi(`/nurse/api/lists/${patientId}/approve`, {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    }

    patientForm.addEventListener("submit", savePatient);
    cancelEditButton.addEventListener("click", () => {
        resetPatientForm();
        showStatus("Đã hủy chỉnh sửa.");
    });

    dateInput.value = dateInput.value || todayValue();
    selectedDate = dateInput.value;
    dateInput.addEventListener("change", async () => {
        if (editingPatientId) resetPatientForm();
        selectedDate = dateInput.value;
        currentPage = 1;
        currentWaitingPage = 1;
        searchTerm = "";
        searchInput.value = "";
        activePatients = [];
        waitingPatients = [];
        dayConfirmed = false;
        renderAll();
        showStatus("");
        try {
            await refreshDay();
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    searchForm.addEventListener("submit", event => {
        event.preventDefault();
        searchTerm = searchInput.value.trim();
        currentPage = 1;
        currentWaitingPage = 1;
        renderAll();
        showStatus("");
    });
    nurseApp.querySelector("[data-clear-search]").addEventListener("click", () => {
        searchInput.value = "";
        searchTerm = "";
        currentPage = 1;
        currentWaitingPage = 1;
        renderAll();
        showStatus("");
        searchInput.focus();
    });

    nurseApp.querySelector("[data-toggle-history]").addEventListener("click", event => {
        const button = event.currentTarget;
        historyPanel.hidden = !historyPanel.hidden;
        button.setAttribute("aria-expanded", String(!historyPanel.hidden));
        if (!historyPanel.hidden) {
            historyPanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    });

    patientRows.addEventListener("click", async event => {
        const editButton = event.target.closest("[data-edit-patient]");
        const cancelButton = event.target.closest("[data-cancel-patient]");
        if (editButton) beginEdit(editButton.dataset.editPatient);
        if (cancelButton) await cancelPatient(cancelButton.dataset.cancelPatient);
    });
    waitingRows.addEventListener("click", async event => {
        const editButton = event.target.closest("[data-edit-patient]");
        const cancelButton = event.target.closest("[data-cancel-patient]");
        const approveButton = event.target.closest("[data-approve-patient]");
        if (editButton) beginEdit(editButton.dataset.editPatient);
        if (cancelButton) await cancelPatient(cancelButton.dataset.cancelPatient);
        if (approveButton && !approveButton.disabled) {
            await approvePatient(approveButton.dataset.approvePatient);
        }
    });

    pagination.addEventListener("click", event => {
        const button = event.target.closest("[data-page]");
        if (!button || button.disabled) return;
        currentPage = Number(button.dataset.page);
        renderPatients();
    });
    waitingPagination.addEventListener("click", event => {
        const button = event.target.closest("[data-waiting-page]");
        if (!button || button.disabled) return;
        currentWaitingPage = Number(button.dataset.waitingPage);
        renderWaiting();
    });

    historyRows.addEventListener("click", async event => {
        const button = event.target.closest("[data-open-date]");
        if (!button) return;
        selectedDate = button.dataset.openDate;
        dateInput.value = selectedDate;
        currentPage = 1;
        currentWaitingPage = 1;
        searchTerm = "";
        searchInput.value = "";
        historyPanel.hidden = true;
        nurseApp.querySelector("[data-toggle-history]").setAttribute("aria-expanded", "false");
        activePatients = [];
        waitingPatients = [];
        dayConfirmed = false;
        renderAll();
        try {
            await refreshDay();
            showStatus(`Đang xem danh sách ngày ${formatDate(selectedDate)}.`);
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    nurseApp.querySelector("[data-confirm-list]").addEventListener("click", async () => {
        if (!activePatients.length) {
            showStatus("Danh sách đang trống; hãy thêm ít nhất một bệnh nhân trước khi xác nhận.", "error");
            return;
        }
        if (dayConfirmed) {
            showStatus("Danh sách ngày này đã được xác nhận.");
            return;
        }
        if (!window.confirm(
            `Xác nhận danh sách ngày ${formatDate(selectedDate)} gồm ${activePatients.length} bệnh nhân?`
        )) return;
        try {
            const result = await requestApi("/nurse/api/lists/confirm", {
                method: "POST",
                body: JSON.stringify({ date: selectedDate }),
            });
            await refreshDay();
            showStatus(result.message, "success");
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    refreshDay().catch(error => showStatus(error.message, "error"));
}
