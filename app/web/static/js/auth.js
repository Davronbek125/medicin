/**
 * Umumiy frontend yordamchilari:
 *  - getInitData() — Telegram initData ni ishonchli olish (js kutubxonasi yuklanmasa ham);
 *  - fetch() ga avtomatik Authorization / X-Telegram-Init-Data sarlavhalarini qo'shadi;
 *  - showAdminLoginFallback() — Telegram tashqarisida Super Admin kirishi;
 *  - esc() — HTML belgilarini xavfsiz ekranlash (XSS dan himoya).
 */
(function () {
  "use strict";

  const originalFetch = window.fetch.bind(window);

  // Xodim panellari (shifokor/qabulxona).
  // Brauzerda (Telegram tashqarisida) ularga faqat Super Admin tokeni bilan kirish mumkin.
  const STAFF_ONLY_PAGES = ["/doctor", "/reception"];

  function isStaffPanel() {
    return STAFF_ONLY_PAGES.indexOf(window.location.pathname) !== -1;
  }

  /**
   * Telegram initData ni olish.
   *  1) telegram-web-app.js yuklangan bo'lsa — tg.initData;
   *  2) aks holda (CDN sekin/bloklangan yoki sahifalar orasida o'tishda) —
   *     URL hash'idagi `tgWebAppData` ni o'zimiz o'qiymiz.
   */
  window.getInitData = function () {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg && tg.initData) return tg.initData;
    try {
      const hash = (window.location.hash || "").replace(/^#/, "");
      if (!hash) return "";
      const params = new URLSearchParams(hash);
      return params.get("tgWebAppData") || "";
    } catch (e) {
      return "";
    }
  };

  window.fetch = function (input, init) {
    const opts = Object.assign({}, init);
    const headers = new Headers(opts.headers || {});
    const url = typeof input === "string" ? input : (input && input.url) || "";

    if (url.startsWith("/api/")) {
      const initData = window.getInitData();
      const hasInitData = !!initData;
      if (hasInitData && !headers.has("X-Telegram-Init-Data")) {
        headers.set("X-Telegram-Init-Data", initData);
      }
      // Super Admin tokeni:
      //  - admin panelda har doim;
      //  - xodim panellarida FAQAT brauzerda (Telegram initData yo'q bo'lsa).
      // Telegram ichida xodim sessiyasi faqat initData bilan ishlaydi — umumiy
      // qurilmada qolib ketgan eski admin_token unga aralashmaydi.
      if (!isStaffPanel() || !hasInitData) {
        const token = localStorage.getItem("admin_token");
        if (token && !headers.has("Authorization")) {
          headers.set("Authorization", "Bearer " + token);
        }
      }
    }
    opts.headers = headers;
    return originalFetch(input, opts);
  };

  /**
   * Brauzerda ochilgan xodim paneli uchun Super Admin kirishi.
   * Muvaffaqiyatli kirishdan keyin sahifa qayta yuklanadi va token ishlatiladi.
   */
  window.showAdminLoginFallback = function (reason) {
    document.body.innerHTML = `
      <div class="container" style="max-width: 400px; margin-top: 40px;">
        <div class="card">
          <h2 class="card-title" style="justify-content: center; margin-bottom: 14px;">🔐 Kirish</h2>
          <p style="color: var(--gray-muted); font-size: 0.9rem; margin: 0 0 14px;">${reason}</p>
          <div id="fbError" class="badge badge-danger" style="display: none; width: 100%; margin-bottom: 12px; text-align: center; padding: 8px;"></div>
          <div class="form-group">
            <label class="form-label">Login</label>
            <input type="text" id="fbLogin" class="form-control" placeholder="admin" autocomplete="username">
          </div>
          <div class="form-group">
            <label class="form-label">Parol</label>
            <input type="password" id="fbPass" class="form-control" placeholder="••••••••" autocomplete="current-password">
          </div>
          <button class="btn btn-primary btn-block" id="fbBtn" type="button">Kirish</button>
        </div>
      </div>`;

    const errEl = document.getElementById("fbError");
    const btn = document.getElementById("fbBtn");
    const passEl = document.getElementById("fbPass");

    async function submit() {
      errEl.style.display = "none";
      btn.disabled = true;
      try {
        const res = await originalFetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            login: document.getElementById("fbLogin").value.trim(),
            password: passEl.value,
          }),
        });
        const data = await res.json();
        if (res.ok && data.token) {
          localStorage.setItem("admin_token", data.token);
          localStorage.setItem("admin_login", data.login || "");
          window.location.reload();
          return;
        }
        errEl.innerText = data.detail || "Kirishda xatolik.";
        errEl.style.display = "block";
      } catch (e) {
        errEl.innerText = "Server bilan bog'lanishda xatolik.";
        errEl.style.display = "block";
      }
      btn.disabled = false;
    }

    btn.addEventListener("click", submit);
    passEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submit();
    });
  };

  const ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  window.esc = function (value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (ch) => ESC_MAP[ch]);
  };
})();
