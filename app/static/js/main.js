function updateRoleFields(root = document) {
    const selector = root.querySelector("[data-role-select]");
    const selected = selector ? selector.value : "PATIENT";
    const phone = root.querySelector("#phone");
    if (phone) phone.required = selected === "PATIENT";
    root.querySelectorAll("[data-role-fields]").forEach(section => {
        const enabled = section.dataset.roleFields === selected;
        section.hidden = !enabled;
        section.querySelectorAll("input, select").forEach(field => {
            field.disabled = !enabled;
            field.required = enabled;
        });
    });
}

document.addEventListener("change", event => {
    if (event.target.matches("[data-role-select]")) {
        updateRoleFields(event.target.closest("form"));
    }
});
updateRoleFields();
document.addEventListener("click", event => {
    const button = event.target.closest("[data-password-toggle]");
    if (!button) return;
    const input = document.getElementById(button.dataset.passwordToggle);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Ẩn" : "Hiện";
    button.setAttribute("aria-label", show ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    button.setAttribute("aria-pressed", String(show));
});

const modalElement = document.querySelector("#account-modal");
if (modalElement) {
    const content = modalElement.querySelector(".modal-content");
    const errorBox = document.querySelector("#modal-error");
    let loading = false;
    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({block: "nearest"});
    }
    document.addEventListener("click", async event => {
        const link = event.target.closest("[data-account-modal]");
        if (!link || !window.bootstrap || event.ctrlKey || event.metaKey || event.shiftKey) return;
        event.preventDefault();
        if (loading) return;
        loading = true;
        errorBox.hidden = true;
        const url = new URL(link.href);
        url.searchParams.set("modal", "1");
        try {
            const response = await fetch(url);
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error("Không tải được biểu mẫu. Vui lòng tải lại trang hoặc thử lại.");
            content.innerHTML = await response.text();
            updateRoleFields(content);
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
        } catch (error) {
            showError(error.message);
        } finally {
            loading = false;
        }
    });
    document.addEventListener("submit", async event => {
        const form = event.target;
        if (!form.matches("[data-modal-form]")) return;
        event.preventDefault();
        if (form.dataset.saving) return;
        form.dataset.saving = "true";
        const button = form.querySelector('button:not([type="button"])');
        button.disabled = true;
        errorBox.hidden = true;
        try {
            const response = await fetch(form.action, {method: "POST", body: new FormData(form)});
            if (response.redirected) {
                window.location.assign(response.url);
            } else if (response.status === 204) {
                window.location.reload();
            } else if (response.status === 422) {
                content.innerHTML = await response.text();
                updateRoleFields(content);
                content.querySelector("[role='alert']")?.scrollIntoView({block: "nearest"});
            } else {
                throw new Error("Không lưu được tài khoản. Vui lòng kiểm tra kết quả trước khi thử lại.");
            }
        } catch (error) {
            showError(error.message);
            bootstrap.Modal.getInstance(modalElement)?.hide();
        } finally {
            button.disabled = false;
            delete form.dataset.saving;
        }
    });
}
