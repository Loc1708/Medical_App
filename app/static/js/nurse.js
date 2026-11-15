const nurseApp = document.querySelector("[data-nurse-app]");

if (nurseApp) {
    const pageSize = 10;
    const dateInput = nurseApp.querySelector("#nurse-exam-date");
    const limitLabel = nurseApp.querySelector("[data-daily-limit]");
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
    const confirmedStatus = nurseApp.querySelector("[data-confirmed-status]");
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    let selectedDate = "";
    let clinicToday = todayValue();
    let currentPage = 1;
    let currentWaitingPage = 1;
    let searchTerm = "";
    let dailyLimit = 0;
    let activePatients = [];
    let waitingPatients = [];
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

    function makeIconButton(label, action, id) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "catalog-icon";
        button.dataset[action] = id;
        button.setAttribute("aria-label", label);
        button.title = label;

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7");
        svg.append(path);
        button.append(svg);
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
                const actionsCell = document.createElement("td");
                const actions = document.createElement("div");
                actions.className = "nurse-row-actions";
                actions.append(makeIconButton("Hủy lượt khám", "cancelPatient", patient.id));
                actionsCell.append(actions);
                row.append(actionsCell);
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
                const actionsCell = document.createElement("td");
                const actions = document.createElement("div");
                actions.className = "nurse-row-actions";
                actions.append(
                    makeButton(
                        "Duyệt vào ngày đã chọn", "btn btn-sm btn-outline-success",
                        "approvePatient", patient.id,
                        targetIsPast || activePatients.length >= dailyLimit
                    ),
                    makeIconButton("Hủy lượt khám", "cancelPatient", patient.id)
                );
                actionsCell.append(actions);
                row.append(actionsCell);
                waitingRows.append(row);
            });
        }

        const end = Math.min(start + pageSize, patients.length);
        waitingSummary.textContent = patients.length
            ? `Hiển thị ${start + 1}–${end} trên ${patients.length} bệnh nhân đang chờ`
            : "Chưa có bệnh nhân chờ duyệt.";
        addPagination(waitingPagination, pageCount, currentWaitingPage, "waitingPage");
    }

    function renderAll() {
        renderPatients();
        renderWaiting();
    }

    async function cancelPatient(patientId) {
        const patient = [...activePatients, ...waitingPatients]
            .find(item => String(item.id) === String(patientId));
        if (!patient || !window.confirm(`Hủy lượt khám của ${patient.name}?`)) return;
        try {
            const result = await requestApi(`/nurse/api/lists/${patient.id}`, {
                method: "DELETE",
            });
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

    dateInput.value = dateInput.value || todayValue();
    selectedDate = dateInput.value;
    dateInput.addEventListener("change", async () => {
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

    patientRows.addEventListener("click", async event => {
        const cancelButton = event.target.closest("[data-cancel-patient]");
        if (cancelButton) await cancelPatient(cancelButton.dataset.cancelPatient);
    });
    waitingRows.addEventListener("click", async event => {
        const cancelButton = event.target.closest("[data-cancel-patient]");
        const approveButton = event.target.closest("[data-approve-patient]");
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
