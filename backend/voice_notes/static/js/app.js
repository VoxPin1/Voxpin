(() => {
  const BT_STORAGE_KEY = "voxpin_bt_device";
  const BT_SESSION_KEY = "voxpin_bt_modal_session";
  // Reserved service UUID for future VoxPin BLE firmware
  const VOXPIN_SERVICE = "a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e6";

  const state = {
    filter: "all",
    recordings: [],
    languages: [],
    selectedLang: "en",
    events: [],
    calendarConnected: false,
    viewYear: new Date().getFullYear(),
    viewMonth: new Date().getMonth(),
    selectedDate: null,
    greetingAudio: null,
    bt: {
      paired: false,
      live: false,
      name: "",
      id: "",
      device: null,
      server: null,
    },
  };

  const els = {
    tabs: [...document.querySelectorAll(".tab")],
    panels: {
      recordings: document.getElementById("panel-recordings"),
      language: document.getElementById("panel-language"),
      calendar: document.getElementById("panel-calendar"),
      google: document.getElementById("panel-google"),
      device: document.getElementById("panel-device"),
    },
    deviceStatus: document.getElementById("deviceStatus"),
    deviceStatusText: document.getElementById("deviceStatusText"),
    recordingList: document.getElementById("recordingList"),
    languageGrid: document.getElementById("languageGrid"),
    languageName: document.getElementById("languageName"),
    calendarGrid: document.getElementById("calendarGrid"),
    calMonthLabel: document.getElementById("calMonthLabel"),
    dayTitle: document.getElementById("dayTitle"),
    dayEvents: document.getElementById("dayEvents"),
    calNote: document.getElementById("calNote"),
    googleStatus: document.getElementById("googleStatus"),
    googleCreds: document.getElementById("googleCreds"),
    googleCredsHint: document.getElementById("googleCredsHint"),
    saveGoogleCreds: document.getElementById("saveGoogleCreds"),
    googleDocLink: document.getElementById("googleDocLink"),
    googleConnectHint: document.getElementById("googleConnectHint"),
    appsScriptUrl: document.getElementById("appsScriptUrl"),
    appsScriptSecret: document.getElementById("appsScriptSecret"),
    saveAppsScript: document.getElementById("saveAppsScript"),
    testAppsScript: document.getElementById("testAppsScript"),
    appsScriptHint: document.getElementById("appsScriptHint"),
    footerMeta: document.getElementById("footerMeta"),
    btModal: document.getElementById("btModal"),
    btModalConnect: document.getElementById("btModalConnect"),
    btModalLater: document.getElementById("btModalLater"),
    btModalNote: document.getElementById("btModalNote"),
    btnConnectBt: document.getElementById("btnConnectBt"),
    btnForgetBt: document.getElementById("btnForgetBt"),
    deviceDot: document.getElementById("deviceDot"),
    deviceCardTitle: document.getElementById("deviceCardTitle"),
    deviceCardMeta: document.getElementById("deviceCardMeta"),
    deviceHint: document.getElementById("deviceHint"),
  };

  function bluetoothSupported() {
    return typeof navigator !== "undefined" && !!navigator.bluetooth;
  }

  function loadBtMemory() {
    try {
      const raw = localStorage.getItem(BT_STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function saveBtMemory(payload) {
    localStorage.setItem(BT_STORAGE_KEY, JSON.stringify(payload));
  }

  function clearBtMemory() {
    localStorage.removeItem(BT_STORAGE_KEY);
  }

  function updateDeviceUi() {
    const name = state.bt.name || "VoxPin";
    const paired = state.bt.paired;
    const live = state.bt.live;

    els.deviceDot?.classList.toggle("is-connected", paired);
    if (els.btnForgetBt) els.btnForgetBt.hidden = !paired;
    if (els.btnConnectBt) {
      els.btnConnectBt.textContent = paired ? "Reconnect Bluetooth" : "Connect with Bluetooth";
    }

    if (live) {
      if (els.deviceCardTitle) els.deviceCardTitle.textContent = `${name} connected`;
      if (els.deviceCardMeta) els.deviceCardMeta.textContent = "Linked over Bluetooth and ready.";
      if (els.deviceHint) els.deviceHint.textContent = "This browser will remember your pin.";
    } else if (paired) {
      if (els.deviceCardTitle) els.deviceCardTitle.textContent = `${name} saved`;
      if (els.deviceCardMeta) {
        els.deviceCardMeta.textContent =
          "Paired on this browser. It will show as connected automatically when in range.";
      }
      if (els.deviceHint) {
        els.deviceHint.textContent = bluetoothSupported()
          ? "Click reconnect if the live link dropped."
          : "Use Chrome or Edge on desktop for live Bluetooth.";
      }
    } else {
      if (els.deviceCardTitle) els.deviceCardTitle.textContent = "Not connected";
      if (els.deviceCardMeta) els.deviceCardMeta.textContent = "Pair your pin to sync status here.";
      if (els.deviceHint) {
        els.deviceHint.textContent = bluetoothSupported()
          ? "Turn on your VoxPin, then connect with Bluetooth."
          : "Web Bluetooth needs Chrome or Edge (HTTPS or localhost).";
      }
    }
  }

  function updateStatusChip(backend) {
    const lang =
      backend?.target_language_name ||
      backend?.base_language_name ||
      state.selectedLang ||
      "—";
    els.deviceStatus.classList.toggle("is-live", !!(state.bt.paired || backend));
    els.deviceStatus.classList.toggle("is-warn", state.bt.paired && !state.bt.live);

    if (state.bt.paired) {
      const name = state.bt.name || "VoxPin";
      els.deviceStatusText.textContent = state.bt.live
        ? `${name} · BT on · ${lang}`
        : `${name} paired · ${lang}`;
      return;
    }

    if (backend) {
      const google =
        backend.docs && backend.calendar
          ? "Google on"
          : backend.docs
            ? "Docs on"
            : backend.calendar
              ? "Calendar on"
              : "Google off";
      els.deviceStatusText.textContent = `Backend · ${google} · ${lang}`;
      return;
    }

    els.deviceStatus.classList.remove("is-live");
    els.deviceStatus.classList.add("is-warn");
    els.deviceStatusText.textContent = "Device not connected";
  }

  function showBtModal(note = "") {
    if (!els.btModal) return;
    els.btModal.hidden = false;
    if (els.btModalNote) els.btModalNote.textContent = note;
    document.body.style.overflow = "hidden";
  }

  function hideBtModal({ forSession = false } = {}) {
    if (!els.btModal) return;
    els.btModal.hidden = true;
    document.body.style.overflow = "";
    if (forSession) sessionStorage.setItem(BT_SESSION_KEY, "1");
  }

  function shouldShowFirstVisitModal() {
    if (loadBtMemory()?.paired) return false;
    if (sessionStorage.getItem(BT_SESSION_KEY) === "1") return false;
    return true;
  }

  async function requestVoxPinDevice() {
    const optionalServices = [VOXPIN_SERVICE, "battery_service", "device_information"];
    try {
      return await navigator.bluetooth.requestDevice({
        filters: [
          { namePrefix: "VoxPin" },
          { namePrefix: "Voxpin" },
          { namePrefix: "VOXPIN" },
        ],
        optionalServices,
      });
    } catch (err) {
      const cancelled =
        err?.name === "AbortError" || /cancel/i.test(String(err?.message || ""));
      if (cancelled) throw err;
      // Early firmware may not advertise "VoxPin" yet — let the user pick nearby BLE
      return navigator.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices,
      });
    }
  }

  async function connectBluetooth() {
    if (!bluetoothSupported()) {
      throw new Error("Bluetooth is not supported in this browser. Try Chrome or Edge.");
    }

    const device = await requestVoxPinDevice();

    let live = false;
    try {
      const server = await device.gatt.connect();
      state.bt.server = server;
      live = server.connected;
    } catch {
      // Pairing permission still counts — GATT may wait on firmware BLE services
      live = false;
    }

    device.addEventListener("gattserverdisconnected", () => {
      state.bt.live = false;
      state.bt.server = null;
      updateDeviceUi();
      loadStatus();
    });

    state.bt.device = device;
    state.bt.paired = true;
    state.bt.live = live;
    state.bt.name = device.name || "VoxPin";
    state.bt.id = device.id || "";

    saveBtMemory({
      paired: true,
      id: state.bt.id,
      name: state.bt.name,
      pairedAt: new Date().toISOString(),
    });

    updateDeviceUi();
    hideBtModal();
    await loadStatus();
    return state.bt;
  }

  async function restoreBluetooth() {
    const memory = loadBtMemory();
    if (!memory?.paired) {
      state.bt.paired = false;
      updateDeviceUi();
      return;
    }

    state.bt.paired = true;
    state.bt.name = memory.name || "VoxPin";
    state.bt.id = memory.id || "";
    state.bt.live = false;

    if (bluetoothSupported() && navigator.bluetooth.getDevices) {
      try {
        const devices = await navigator.bluetooth.getDevices();
        const match =
          devices.find((d) => memory.id && d.id === memory.id) ||
          devices.find((d) => (d.name || "").toLowerCase().includes("voxpin")) ||
          devices[0];
        if (match) {
          state.bt.device = match;
          state.bt.name = match.name || state.bt.name;
          match.addEventListener("gattserverdisconnected", () => {
            state.bt.live = false;
            state.bt.server = null;
            updateDeviceUi();
            loadStatus();
          });
          if (match.gatt?.connected) {
            state.bt.live = true;
            state.bt.server = match.gatt;
          } else if (match.gatt) {
            try {
              const server = await match.gatt.connect();
              state.bt.server = server;
              state.bt.live = !!server.connected;
            } catch {
              // Stay paired; live link can wait until pin is nearby
            }
          }
        }
      } catch {
        // Permission / API limits — still treat as paired from memory
      }
    }

    updateDeviceUi();
  }

  function forgetBluetooth() {
    try {
      state.bt.device?.gatt?.disconnect();
    } catch {
      /* ignore */
    }
    state.bt = {
      paired: false,
      live: false,
      name: "",
      id: "",
      device: null,
      server: null,
    };
    clearBtMemory();
    // Allow first-visit popup again only after an explicit forget
    sessionStorage.removeItem(BT_SESSION_KEY);
    updateDeviceUi();
    loadStatus();
  }

  function activateTab(name, { scroll = false } = {}) {
    els.tabs.forEach((tab) => {
      const on = tab.dataset.tab === name;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    Object.entries(els.panels).forEach(([key, panel]) => {
      if (!panel) return;
      const on = key === name;
      panel.classList.toggle("is-active", on);
      panel.hidden = !on;
    });
    if (name === "calendar") renderCalendar();
    if (name === "google") loadGoogleStatus();
    if (name === "device") updateDeviceUi();
    if (scroll) {
      document.getElementById(`panel-${name}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function loadGoogleStatus() {
    if (!els.googleStatus) return;
    try {
      const data = await api("/api/google/status");
      const docs = data.docs ? "Connected" : "Not connected";
      const cal = data.calendar ? "Connected" : "Not connected";
      const oauth = data.has_credentials
        ? data.has_token
          ? "OAuth client + token saved"
          : "OAuth client saved (sign-in still needed)"
        : "Missing — paste Desktop OAuth JSON below";
      const apps = data.has_apps_script ? "Webhook saved" : "Not set";
      els.googleStatus.innerHTML = `
        <ul class="google-flags">
          <li><strong>Docs (Apps Script):</strong> ${escapeHtml(apps)} · ${escapeHtml(docs)}</li>
          <li><strong>Calendar (OAuth):</strong> ${escapeHtml(oauth)} · ${escapeHtml(cal)}</li>
        </ul>`;
      if (els.googleDocLink && data.document_url) {
        els.googleDocLink.href = data.document_url;
      }
      const connectBtn = document.getElementById("connectGoogle");
      if (connectBtn) {
        if (data.calendar) {
          connectBtn.setAttribute("aria-disabled", "true");
          connectBtn.classList.add("is-disabled");
          connectBtn.removeAttribute("href");
        } else if (data.has_credentials) {
          connectBtn.setAttribute("href", "/api/google/connect");
          connectBtn.removeAttribute("aria-disabled");
          connectBtn.classList.remove("is-disabled");
        } else {
          connectBtn.removeAttribute("href");
          connectBtn.setAttribute("aria-disabled", "true");
          connectBtn.classList.add("is-disabled");
        }
      }
      if (els.googleConnectHint) {
        els.googleConnectHint.textContent = data.calendar
          ? "Calendar signed in."
          : data.has_credentials
            ? "OAuth client ready — click Sign in with Google (browser popup)."
            : "Paste a Desktop OAuth client JSON and Save before signing in.";
      }
      if (els.appsScriptHint) {
        els.appsScriptHint.textContent = data.has_apps_script
          ? "Apps Script webhook is saved — Docs notes should work."
          : "Paste the Web app URL (+ secret) from your old deployment.";
      }
    } catch (err) {
      els.googleStatus.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(options?.body ? { "Content-Type": "application/json" } : {}) },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Request failed (${res.status})`);
    }
    return res.json();
  }

  async function loadStatus() {
    try {
      const data = await api("/api/status");
      els.footerMeta.textContent = `${data.recording_count || 0} recordings stored`;
      updateStatusChip(data);
    } catch {
      updateStatusChip(null);
      if (!state.bt.paired) {
        els.footerMeta.textContent = "";
      }
    }
    updateDeviceUi();
  }

  function formatWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function kindLabel(kind) {
    if (kind === "translate") return "Translate";
    if (kind === "task") return "Task";
    return "Note";
  }

  function renderRecordings() {
    const items = state.recordings.filter(
      (r) => state.filter === "all" || r.kind === state.filter
    );
    if (!items.length) {
      els.recordingList.innerHTML =
        '<p class="empty">No recordings yet. Click the pin button to start, click again to send — or hold to talk. Try “take notes…”, “translate this…”, or “remind me…”.</p>';
      return;
    }
    els.recordingList.innerHTML = items
      .map((r) => {
        const extra =
          r.kind === "translate" && r.translation
            ? `<p class="translation">${escapeHtml(r.translation)}${
                r.language ? ` · ${escapeHtml(r.language)}` : ""
              }</p>`
            : r.kind === "task" && r.when
              ? `<p class="meta">Due ${escapeHtml(r.when)}</p>`
              : "";
        return `
          <article class="recording" data-id="${escapeAttr(r.id)}">
            <span class="kind-badge ${escapeAttr(r.kind)}">${kindLabel(r.kind)}</span>
            <div>
              <h3>${escapeHtml(r.text || "(empty)")}</h3>
              ${extra}
            </div>
            <div style="display:grid;justify-items:end;gap:0.4rem">
              <time datetime="${escapeAttr(r.created_at || "")}">${formatWhen(r.created_at)}</time>
              <button class="delete-btn" data-delete="${escapeAttr(r.id)}" aria-label="Delete recording">Delete</button>
            </div>
          </article>`;
      })
      .join("");
  }

  function escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str).replaceAll("'", "&#39;");
  }

  async function loadRecordings() {
    try {
      const data = await api("/api/recordings");
      state.recordings = data.recordings || [];
      renderRecordings();
    } catch (err) {
      els.recordingList.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  function langButtons(selectedCode) {
    return state.languages
      .map((lang) => {
        const selected = lang.code === selectedCode ? "is-selected" : "";
        return `
          <button class="lang-option ${selected}" data-lang="${escapeAttr(lang.code)}">
            <strong>${escapeHtml(lang.name)}</strong>
            <span class="native">${escapeHtml(lang.native)}</span>
          </button>`;
      })
      .join("");
  }

  function renderLanguages() {
    els.languageName.textContent =
      state.languages.find((l) => l.code === state.selectedLang)?.name || "—";
    els.languageGrid.innerHTML = langButtons(state.selectedLang);
  }

  async function loadLanguages() {
    try {
      const data = await api("/api/languages");
      state.languages = data.languages || [];
      state.selectedLang = data.target_language || data.selected || "es";
      renderLanguages();
    } catch (err) {
      els.languageGrid.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function speakGreeting(code) {
    const greetingEl = document.getElementById("languageGreeting");
    try {
      const data = await api(`/api/speak-greeting?code=${encodeURIComponent(code)}`);
      if (greetingEl) {
        greetingEl.textContent = data.text || "";
        greetingEl.classList.remove("is-visible");
        void greetingEl.offsetWidth;
        greetingEl.classList.add("is-visible");
      }
      if (state.greetingAudio) {
        state.greetingAudio.pause();
        state.greetingAudio = null;
      }
      if (data.audio_base64) {
        const audio = new Audio(`data:${data.mime || "audio/mpeg"};base64,${data.audio_base64}`);
        state.greetingAudio = audio;
        await audio.play().catch(() => {});
      }
    } catch {
      if (greetingEl) {
        greetingEl.textContent = "Hello, Are you ready to start your Journey!";
        greetingEl.classList.add("is-visible");
      }
    }
  }

  async function setLanguage(code) {
    const data = await api("/api/settings/language", {
      method: "PUT",
      body: JSON.stringify({ code, role: "target" }),
    });
    state.selectedLang = data.target_language;
    renderLanguages();
    loadStatus();
    await speakGreeting(code);
  }

  function dayKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function eventDay(event) {
    if (!event.start) return null;
    return event.start.slice(0, 10);
  }

  function eventsForDay(key) {
    return state.events.filter((e) => eventDay(e) === key);
  }

  function renderDayDetail(key) {
    if (!key) {
      els.dayTitle.textContent = "Select a day";
      els.dayEvents.innerHTML = '<li class="empty">No day selected.</li>';
      return;
    }
    const [y, m, d] = key.split("-").map(Number);
    const label = new Date(y, m - 1, d).toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
    });
    els.dayTitle.textContent = label;
    const items = eventsForDay(key);
    if (!items.length) {
      els.dayEvents.innerHTML = '<li class="empty">No tasks on this day.</li>';
      return;
    }
    els.dayEvents.innerHTML = items
      .map((e) => {
        const time = e.all_day ? "All day" : e.when_label || formatWhen(e.start);
        return `<li><span class="time">${escapeHtml(time)}</span>${escapeHtml(e.title)}</li>`;
      })
      .join("");
  }

  function renderCalendar() {
    const year = state.viewYear;
    const month = state.viewMonth;
    const first = new Date(year, month, 1);
    const startPad = first.getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevDays = new Date(year, month, 0).getDate();

    els.calMonthLabel.textContent = first.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });

    const labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
      .map((d) => `<div class="dow">${d}</div>`)
      .join("");

    const cells = [];
    for (let i = 0; i < startPad; i++) {
      const day = prevDays - startPad + i + 1;
      cells.push(`<button class="day is-muted" disabled>${day}</button>`);
    }

    const todayKey = dayKey(new Date());
    for (let day = 1; day <= daysInMonth; day++) {
      const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const classes = ["day"];
      if (key === todayKey) classes.push("is-today");
      if (key === state.selectedDate) classes.push("is-selected");
      if (eventsForDay(key).length) classes.push("has-events");
      cells.push(
        `<button class="${classes.join(" ")}" data-day="${key}" aria-label="${key}">${day}</button>`
      );
    }

    while (cells.length % 7 !== 0) {
      const day = cells.length - (startPad + daysInMonth) + 1;
      cells.push(`<button class="day is-muted" disabled>${day}</button>`);
    }

    els.calendarGrid.innerHTML = labels + cells.join("");
    renderDayDetail(state.selectedDate);

    if (!state.calendarConnected) {
      els.calNote.textContent =
        "Google Calendar is not connected. Run ./run.sh --login in backend/voice_notes, then refresh.";
    } else {
      els.calNote.textContent = "Synced with the same calendar your VoxPin writes reminders to.";
    }
  }

  async function loadCalendar() {
    try {
      const data = await api("/api/calendar");
      state.calendarConnected = !!data.connected;
      state.events = data.events || [];
      if (!state.selectedDate) state.selectedDate = dayKey(new Date());
      renderCalendar();
    } catch (err) {
      els.calNote.textContent = err.message;
      state.events = [];
      renderCalendar();
    }
  }

  function animateWaves() {
    const paths = [...document.querySelectorAll(".wave-path")];
    if (!paths.length) return;
    let t = 0;
    function frame() {
      t += 0.035;
      paths.forEach((path, i) => {
        const amp = 18 + i * 8;
        const freq = 0.018 + i * 0.004;
        const phase = t * (0.8 + i * 0.25);
        let d = `M 0 80`;
        for (let x = 0; x <= 400; x += 8) {
          const y = 80 + Math.sin(x * freq + phase) * amp + Math.sin(x * 0.04 + phase * 1.4) * (amp * 0.25);
          d += ` L ${x} ${y}`;
        }
        path.setAttribute("d", d);
      });
      requestAnimationFrame(frame);
    }
    frame();
  }

  function bindEvents() {
    els.tabs.forEach((tab) => {
      tab.addEventListener("click", () => activateTab(tab.dataset.tab, { scroll: true }));
    });

    document.querySelectorAll("[data-jump]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activateTab(btn.dataset.jump, { scroll: true });
      });
    });

    document.querySelectorAll("[data-filter]").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.filter = chip.dataset.filter;
        document.querySelectorAll("[data-filter]").forEach((c) => {
          c.classList.toggle("is-active", c === chip);
        });
        renderRecordings();
      });
    });

    document.getElementById("refreshRecordings")?.addEventListener("click", () => {
      loadRecordings();
      loadStatus();
    });

    els.recordingList.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-delete]");
      if (!btn) return;
      const id = btn.dataset.delete;
      try {
        await api(`/api/recordings/${id}`, { method: "DELETE" });
        state.recordings = state.recordings.filter((r) => r.id !== id);
        renderRecordings();
        loadStatus();
      } catch (err) {
        alert(err.message);
      }
    });

    els.languageGrid.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-lang]");
      if (!btn) return;
      try {
        await setLanguage(btn.dataset.lang);
      } catch (err) {
        alert(err.message);
      }
    });

    document.getElementById("calPrev")?.addEventListener("click", () => {
      state.viewMonth -= 1;
      if (state.viewMonth < 0) {
        state.viewMonth = 11;
        state.viewYear -= 1;
      }
      renderCalendar();
    });

    document.getElementById("calNext")?.addEventListener("click", () => {
      state.viewMonth += 1;
      if (state.viewMonth > 11) {
        state.viewMonth = 0;
        state.viewYear += 1;
      }
      renderCalendar();
    });

    document.getElementById("calToday")?.addEventListener("click", () => {
      const now = new Date();
      state.viewYear = now.getFullYear();
      state.viewMonth = now.getMonth();
      state.selectedDate = dayKey(now);
      renderCalendar();
    });

    els.calendarGrid.addEventListener("click", (e) => {
      const day = e.target.closest("[data-day]");
      if (!day) return;
      state.selectedDate = day.dataset.day;
      renderCalendar();
    });

    els.deviceStatus?.addEventListener("click", () => {
      activateTab("device", { scroll: true });
    });

    async function handleConnectClick(noteEl) {
      if (noteEl) noteEl.textContent = "Choose your VoxPin in the browser prompt…";
      try {
        await connectBluetooth();
        if (noteEl) noteEl.textContent = "Connected.";
      } catch (err) {
        if (err?.name === "NotFoundError") {
          if (noteEl) noteEl.textContent = "No device selected.";
          return;
        }
        if (noteEl) noteEl.textContent = err.message || "Could not connect.";
      }
    }

    els.btModalConnect?.addEventListener("click", () => handleConnectClick(els.btModalNote));
    els.btModalLater?.addEventListener("click", () => hideBtModal({ forSession: true }));
    els.btnConnectBt?.addEventListener("click", () => handleConnectClick(els.deviceHint));
    els.btnForgetBt?.addEventListener("click", () => {
      forgetBluetooth();
    });

    els.saveGoogleCreds?.addEventListener("click", async () => {
      const raw = (els.googleCreds?.value || "").trim();
      if (!raw) {
        if (els.googleCredsHint) els.googleCredsHint.textContent = "Paste the downloaded JSON first.";
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        if (els.googleCredsHint) els.googleCredsHint.textContent = "That doesn’t look like valid JSON.";
        return;
      }
      try {
        await api("/api/google/credentials", { method: "POST", body: JSON.stringify(parsed) });
        if (els.googleCredsHint) els.googleCredsHint.textContent = "Saved. Now click Sign in with Google.";
        if (els.googleCreds) els.googleCreds.value = "";
        loadGoogleStatus();
      } catch (err) {
        if (els.googleCredsHint) els.googleCredsHint.textContent = err.message;
      }
    });

    els.saveAppsScript?.addEventListener("click", async () => {
      const url = (els.appsScriptUrl?.value || "").trim();
      const secret = (els.appsScriptSecret?.value || "").trim();
      if (!url) {
        if (els.appsScriptHint) els.appsScriptHint.textContent = "Paste the Web app URL first.";
        return;
      }
      try {
        await api("/api/google/apps-script", {
          method: "POST",
          body: JSON.stringify({ url, secret }),
        });
        if (els.appsScriptHint) {
          els.appsScriptHint.textContent = "Saved. Click Send test note to verify the Doc.";
        }
        loadGoogleStatus();
        loadStatus();
      } catch (err) {
        if (els.appsScriptHint) els.appsScriptHint.textContent = err.message;
      }
    });

    els.testAppsScript?.addEventListener("click", async () => {
      try {
        const data = await api("/api/google/apps-script/test", {
          method: "POST",
          body: "{}",
        });
        if (els.appsScriptHint) {
          els.appsScriptHint.textContent = data.message || "Test note sent — check the Doc.";
        }
      } catch (err) {
        if (els.appsScriptHint) els.appsScriptHint.textContent = err.message;
      }
    });
  }

  async function boot() {
    bindEvents();
    animateWaves();
    const params = new URLSearchParams(location.search);
    if (params.get("google") === "connected") {
      activateTab("google");
      history.replaceState({}, "", "/");
    } else {
      activateTab("recordings");
    }
    await restoreBluetooth();
    await Promise.all([loadStatus(), loadRecordings(), loadLanguages(), loadCalendar(), loadGoogleStatus()]);
    if (shouldShowFirstVisitModal()) {
      showBtModal(
        bluetoothSupported()
          ? ""
          : "Tip: use Chrome or Edge on desktop for Bluetooth pairing."
      );
    }
    setInterval(() => {
      loadStatus();
      loadRecordings();
      loadCalendar();
      loadGoogleStatus();
    }, 20000);
  }

  boot();
})();
