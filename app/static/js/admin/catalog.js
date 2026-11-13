(() => {
    const searchForm = document.querySelector("[data-catalog-search]");
    const errorBox = document.querySelector("#catalog-error");
    const modalElement = document.querySelector("#catalog-modal");
    const content = modalElement.querySelector(".modal-content");
    let timer;
    let sequence = 0;
    let loading = false;
    const showError = message => {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({block: "nearest"});
    };
    searchForm.querySelector("input").addEventListener("input", () => {
        clearTimeout(timer);
        const requestId = ++sequence;
        timer = setTimeout(async () => {
            const url = new URL(searchForm.action);
            url.searchParams.set("q", searchForm.querySelector("input").value);
            try {
                const response = await fetch(url);
                if (requestId !== sequence) return;
                if (response.redirected) {
                    window.location.assign(response.url);
                    return;
                }
                if (!response.ok) throw new Error("Không tải được danh mục. Vui lòng thử lại.");
                const documentResult = new DOMParser().parseFromString(await response.text(), "text/html");
                if (requestId !== sequence) return;
                const results = documentResult.querySelector("[data-catalog-results]");
                if (!results) throw new Error("Dữ liệu danh mục không hợp lệ. Vui lòng tải lại trang.");
                document.querySelector("[data-catalog-results]").replaceWith(results);
                history.replaceState(null, "", url);
                errorBox.hidden = true;
            } catch (error) {
                if (requestId === sequence) showError(error.message);
            }
        }, 300);
    });
    document.addEventListener("click", async event => {
        const link = event.target.closest("[data-catalog-modal]");
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
            if (!response.ok) throw new Error("Không tải được biểu mẫu. Vui lòng thử lại.");
            content.innerHTML = await response.text();
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
        } catch (error) {
            showError(error.message);
        } finally {
            loading = false;
        }
    });
    document.addEventListener("submit", async event => {
        const form = event.target;
        if (form.matches("[data-catalog-delete]")) {
            if (!window.confirm("Xóa " + form.dataset.code + "? Thao tác này không thể hoàn tác.")) event.preventDefault();
            return;
        }
        if (!form.matches("[data-catalog-form]")) return;
        event.preventDefault();
        if (form.dataset.saving) return;
        form.dataset.saving = "true";
        const button = form.querySelector('button:not([type="button"])');
        button.disabled = true;
        try {
            const response = await fetch(form.action, {method: "POST", body: new FormData(form)});
            if (response.redirected) window.location.assign(response.url);
            else if (response.status === 204) window.location.reload();
            else if (response.status === 422) content.innerHTML = await response.text();
            else throw new Error("Không lưu được dữ liệu. Kiểm tra kết quả trước khi thử lại.");
        } catch (error) {
            bootstrap.Modal.getInstance(modalElement)?.hide();
            showError(error.message);
        } finally {
            button.disabled = false;
            delete form.dataset.saving;
        }
    });
})();
