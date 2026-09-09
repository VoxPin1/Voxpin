(() => {
  const BT_STORAGE_KEY = "voxpin_bt_device";
  const BT_SESSION_KEY = "voxpin_bt_modal_session";
  // Reserved service UUID for future VoxPin BLE firmware
  const VOXPIN_SERVICE = "a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e6";
  const VOXPIN_PROFILE_CHAR = "a1a2a3a4-b1b2-c1c2-d1d2-e1e2e3e4e5e7";
  const PROFILE_KEY = "voxpin_profile";
  const GOOGLE_CLIENT_KEY = "voxpin_google_client_id";
  const GOOGLE_USER_KEY = "voxpin_google_user";
  const GOOGLE_CAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly";
  const FALLBACK_LANGUAGES = [
    { code: "en", name: "English", native: "English" },
    { code: "te", name: "Telugu", native: "తెలుగు" },
    { code: "es", name: "Spanish", native: "Español" },
    { code: "fr", name: "French", native: "Français" },
    { code: "de", name: "German", native: "Deutsch" },
    { code: "it", name: "Italian", native: "Italiano" },
    { code: "pt", name: "Portuguese", native: "Português" },
    { code: "ja", name: "Japanese", native: "日本語" },
    { code: "ko", name: "Korean", native: "한국어" },
    { code: "zh-CN", name: "Chinese (Simplified)", native: "简体中文" },
    { code: "zh-TW", name: "Chinese (Traditional)", native: "繁體中文" },
    { code: "hi", name: "Hindi", native: "हिन्दी" },
    { code: "ar", name: "Arabic", native: "العربية" },
    { code: "ru", name: "Russian", native: "Русский" },
    { code: "nl", name: "Dutch", native: "Nederlands" },
    { code: "pl", name: "Polish", native: "Polski" },
    { code: "sv", name: "Swedish", native: "Svenska" },
    { code: "tr", name: "Turkish", native: "Türkçe" },
    { code: "vi", name: "Vietnamese", native: "Tiếng Việt" },
    { code: "th", name: "Thai", native: "ไทย" },
  ];
  const STATIC_HOST_NOTE =
    "Voice recordings from the pin still need the local backend (backend/voice_notes ./run.sh), or a hosted server, because GitHub Pages cannot receive uploads.";

  function isPublicStaticHost() {
    return /\.github\.io$/i.test(location.hostname);
  }

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
      profileChar: null,
    },
    profile: {},
    google: {
      clientId: "",
      user: null,
      accessToken: "",
      tokenClient: null,
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
    googleClientId: document.getElementById("googleClientId"),
    saveGoogleClientId: document.getElementById("saveGoogleClientId"),
    googleSignInButton: document.getElementById("googleSignInButton"),
    googleSignInHint: document.getElementById("googleSignInHint"),
    googleSignOut: document.getElementById("googleSignOut"),
    googleConnectCalendar: document.getElementById("googleConnectCalendar"),
    accountStatus: document.getElementById("accountStatus"),
    accountStatusText: document.getElementById("accountStatusText"),
    accountAvatar: document.getElementById("accountAvatar"),
    appsScriptUrl: document.getElementById("appsScriptUrl"),
    appsScriptSecret: document.getElementById("appsScriptSecret"),
    saveAppsScript: document.getElementById("saveAppsScript"),
    testAppsScript: document.getElementById("testAppsScript"),
    appsScriptHint: document.getElementById("appsScriptHint"),
    footerMeta: document.getElementById("footerMeta"),
    btModal: document.getElementById("btModal"),
    btModalConnect: document.getElementById("btModalConnect"),
    btModalGoogle: document.getElementById("btModalGoogle"),
    btModalLater: document.getElementById("btModalLater"),
    btModalNote: document.getElementById("btModalNote"),
    btnConnectBt: document.getElementById("btnConnectBt"),
    btnForgetBt: document.getElementById("btnForgetBt"),
    profileCard: document.getElementById("profileCard"),
    profileName: document.getElementById("profileName"),
    profileHint: document.getElementById("profileHint"),
    profileLanguageMeta: document.getElementById("profileLanguageMeta"),
    saveProfile: document.getElementById("saveProfile"),
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

  function readProfileStore() {
    try {
      return JSON.parse(localStorage.getItem(PROFILE_KEY)) || {};
    } catch {
      return {};
    }
  }

  function languageName(code) {
    const list = state.languages.length ? state.languages : FALLBACK_LANGUAGES;
    return list.find((lang) => lang.code === code)?.name || code || "";
  }

  function mergeProfile(patch) {
    state.profile = {
      name: "VoxPin",
      language: "es",
      languageName: "Spanish",
      ...readProfileStore(),
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    if (state.bt.id) state.profile.deviceId = state.bt.id;
    localStorage.setItem(PROFILE_KEY, JSON.stringify(state.profile));
    if (state.profile.language) state.selectedLang = state.profile.language;
    if (state.profile.name) state.bt.name = state.profile.name;
    updateProfileUi();
    return state.profile;
  }

  function decodeJwtPayload(token) {
    const part = String(token || "").split(".")[1];
    if (!part) throw new Error("Invalid Google sign-in token.");
    const padded = part.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((part.length + 3) % 4);
    return JSON.parse(atob(padded));
  }

  function readGoogleUser() {
    try {
      return JSON.parse(localStorage.getItem(GOOGLE_USER_KEY) || "null");
    } catch {
      return null;
    }
  }

  function waitForGoogleIdentity(timeoutMs = 8000) {
    if (window.google?.accounts?.id) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        if (window.google?.accounts?.id) {
          clearInterval(timer);
          resolve();
        } else if (Date.now() - started > timeoutMs) {
          clearInterval(timer);
          reject(new Error("Google sign-in script did not load."));
        }
      }, 80);
    });
  }

  function updateAccountUi() {
    const user = state.google.user;
    if (els.accountStatusText) {
      els.accountStatusText.textContent = user ? user.name || user.email || "Signed in" : "Sign in";
    }
    if (els.accountAvatar) {
      if (user?.picture) {
        els.accountAvatar.src = user.picture;
        els.accountAvatar.hidden = false;
      } else {
        els.accountAvatar.hidden = true;
        els.accountAvatar.removeAttribute("src");
      }
    }
    els.accountStatus?.classList.toggle("is-live", !!user);
    if (els.googleSignOut) els.googleSignOut.hidden = !user;
    if (els.googleClientId && document.activeElement !== els.googleClientId) {
      els.googleClientId.value = state.google.clientId || "";
    }
  }

  function persistGoogleUser(user) {
    state.google.user = user;
    if (user) localStorage.setItem(GOOGLE_USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(GOOGLE_USER_KEY);
    updateAccountUi();
  }

  function onGoogleCredential(response) {
    try {
      const payload = decodeJwtPayload(response.credential);
      const user = {
        sub: payload.sub,
        email: payload.email || "",
        name: payload.name || payload.email || "Google user",
        picture: payload.picture || "",
      };
      persistGoogleUser(user);
      mergeProfile({
        name: state.profile.name && state.profile.name !== "VoxPin" ? state.profile.name : user.name,
        googleEmail: user.email,
        googleSub: user.sub,
      });
      if (els.googleSignInHint) {
        els.googleSignInHint.textContent = `Signed in as ${user.email || user.name}.`;
      }
      loadGoogleStatus();
      hideBtModal({ forSession: true });
    } catch (err) {
      if (els.googleSignInHint) els.googleSignInHint.textContent = err.message;
    }
  }

  function setupGoogleSignIn() {
    const clientId = state.google.clientId;
    if (!clientId || !window.google?.accounts?.id) {
      if (els.googleSignInButton) els.googleSignInButton.innerHTML = "";
      return;
    }
    google.accounts.id.initialize({
      client_id: clientId,
      callback: onGoogleCredential,
      auto_select: false,
      ux_mode: "popup",
    });
    if (els.googleSignInButton) {
      els.googleSignInButton.innerHTML = "";
      google.accounts.id.renderButton(els.googleSignInButton, {
        theme: "filled_black",
        size: "large",
        text: "signin_with",
        shape: "pill",
        width: 280,
      });
    }
    if (window.google.accounts.oauth2) {
      state.google.tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: GOOGLE_CAL_SCOPE,
        callback: (resp) => {
          if (resp.error) {
            if (els.googleSignInHint) els.googleSignInHint.textContent = resp.error;
            return;
          }
          state.google.accessToken = resp.access_token || "";
          if (els.googleSignInHint) {
            els.googleSignInHint.textContent = "Calendar connected in this browser.";
          }
          loadCalendar();
          loadGoogleStatus();
        },
      });
    }
  }

  async function initGoogleSignIn() {
    state.google.clientId = localStorage.getItem(GOOGLE_CLIENT_KEY) || "";
    persistGoogleUser(readGoogleUser());
    try {
      await waitForGoogleIdentity();
      setupGoogleSignIn();
      if (els.googleSignInHint && !state.google.clientId) {
        els.googleSignInHint.textContent = "Paste a Web client ID to show the Google button.";
      }
    } catch (err) {
      if (els.googleSignInHint) els.googleSignInHint.textContent = err.message;
    }
  }

  function signOutGoogle() {
    state.google.accessToken = "";
    state.google.tokenClient = null;
    persistGoogleUser(null);
    try {
      google.accounts.id.disableAutoSelect();
    } catch {
      /* ignore */
    }
    setupGoogleSignIn();
    if (els.googleSignInHint) els.googleSignInHint.textContent = "Signed out of this browser.";
    loadGoogleStatus();
    loadCalendar();
  }

  function requestGoogleCalendar() {
    if (!state.google.clientId) {
      if (els.googleSignInHint) {
        els.googleSignInHint.textContent = "Save a Web client ID first.";
      }
      return;
    }
    if (!state.google.tokenClient) {
      setupGoogleSignIn();
    }
    if (!state.google.tokenClient) {
      if (els.googleSignInHint) {
        els.googleSignInHint.textContent = "Google sign-in is still loading. Try again in a moment.";
      }
      return;
    }
    state.google.tokenClient.requestAccessToken({ prompt: state.google.accessToken ? "" : "consent" });
  }

  function mapGoogleEvent(item) {
    const start = item.start?.dateTime || item.start?.date || "";
    const allDay = Boolean(item.start?.date && !item.start?.dateTime);
    return {
      title: item.summary || "(no title)",
      start,
      all_day: allDay,
      when_label: allDay
        ? "All day"
        : start
          ? new Date(start).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
          : "",
    };
  }

  async function loadCalendarFromGoogle() {
    if (!state.google.accessToken) {
      state.calendarConnected = false;
      state.events = [];
      if (!state.selectedDate) state.selectedDate = dayKey(new Date());
      renderCalendar();
      els.calNote.textContent = state.google.user
        ? "Signed in. Click Connect Calendar on the Account tab to load events here — no VoxPin server needed."
        : "Sign in with Google on the Account tab to load calendar events here. No VoxPin server required.";
      return true;
    }
    const start = new Date(state.viewYear, state.viewMonth, 1);
    const end = new Date(state.viewYear, state.viewMonth + 1, 1);
    const params = new URLSearchParams({
      timeMin: start.toISOString(),
      timeMax: end.toISOString(),
      singleEvents: "true",
      orderBy: "startTime",
      maxResults: "100",
    });
    const res = await fetch(
      `https://www.googleapis.com/calendar/v3/calendars/primary/events?${params}`,
      { headers: { Authorization: `Bearer ${state.google.accessToken}` } }
    );
    if (res.status === 401) {
      state.google.accessToken = "";
      state.calendarConnected = false;
      els.calNote.textContent = "Calendar access expired. Click Connect Calendar again.";
      renderCalendar();
      return true;
    }
    if (!res.ok) {
      throw new Error(`Google Calendar request failed (${res.status})`);
    }
    const data = await res.json();
    state.calendarConnected = true;
    state.events = (data.items || []).map(mapGoogleEvent);
    if (!state.selectedDate) state.selectedDate = dayKey(new Date());
    renderCalendar();
    return true;
  }

  function updateProfileUi() {
    if (els.profileCard) els.profileCard.hidden = !state.bt.paired;
    if (els.profileName && document.activeElement !== els.profileName) {
      els.profileName.value = state.profile.name || state.bt.name || "";
    }
    if (els.profileLanguageMeta) {
      const lang = state.profile.languageName || languageName(state.profile.language);
      els.profileLanguageMeta.textContent = lang
        ? `Pin speaks ${lang} for translations.`
        : "Pick a language in the Language tab.";
    }
  }

  async function bindProfileCharacteristic(server) {
    if (!server) return null;
    const service = await server.getPrimaryService(VOXPIN_SERVICE);
    const characteristic = await service.getCharacteristic(VOXPIN_PROFILE_CHAR);
    state.bt.profileChar = characteristic;
    return characteristic;
  }

  async function pullProfileFromDevice() {
    if (!state.bt.profileChar) return;
    const value = await state.bt.profileChar.readValue();
    const text = new TextDecoder().decode(value).replace(/\0/g, "").trim();
    if (!text) return;
    const remote = JSON.parse(text);
    mergeProfile({
      name: remote.name || state.profile.name,
      language: remote.language || state.profile.language,
      languageName: languageName(remote.language || state.selectedLang),
    });
    renderLanguages();
  }

  async function pushProfileToDevice() {
    if (!state.bt.profileChar) return;
    const payload = JSON.stringify({
      name: String(state.profile.name || "VoxPin").slice(0, 32),
      language: state.selectedLang || state.profile.language || "es",
    });
    const bytes = new TextEncoder().encode(payload);
    if (state.bt.profileChar.writeValueWithResponse) {
      await state.bt.profileChar.writeValueWithResponse(bytes);
    } else {
      await state.bt.profileChar.writeValue(bytes);
    }
  }

  async function syncProfileOverBle(server) {
    try {
      await bindProfileCharacteristic(server);
      await pullProfileFromDevice();
    } catch {
      // Older firmware can pair without the VoxPin profile service.
    }
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
    updateProfileUi();
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
      state.bt.profileChar = null;
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
    mergeProfile({ name: state.profile.name || state.bt.name });

    if (live) {
      await syncProfileOverBle(state.bt.server);
    }

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
            state.bt.profileChar = null;
            updateDeviceUi();
            loadStatus();
          });
          if (match.gatt?.connected) {
            state.bt.live = true;
            state.bt.server = match.gatt;
            await syncProfileOverBle(match.gatt);
          } else if (match.gatt) {
            try {
              const server = await match.gatt.connect();
              state.bt.server = server;
              state.bt.live = !!server.connected;
              if (state.bt.live) await syncProfileOverBle(server);
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
      profileChar: null,
    };
    clearBtMemory();
    localStorage.removeItem(PROFILE_KEY);
    state.profile = {};
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
    updateAccountUi();
    const user = state.google.user;
    const web = user
      ? `Signed in as ${user.email || user.name}`
      : state.google.clientId
        ? "Web client ID saved — click Sign in with Google"
        : "Paste a Web client ID, then sign in";
    const cal = state.google.accessToken ? "Connected in this browser" : "Not connected yet";

    if (isPublicStaticHost()) {
      els.googleStatus.innerHTML = `
        <ul class="google-flags">
          <li><strong>Website account:</strong> ${escapeHtml(web)}</li>
          <li><strong>Calendar (this browser):</strong> ${escapeHtml(cal)}</li>
        </ul>`;
      return;
    }

    try {
      const data = await api("/api/google/status");
      const docs = data.docs ? "Connected" : "Not connected";
      const flaskCal = data.calendar ? "Connected" : "Not connected";
      const oauth = data.has_credentials
        ? data.has_token
          ? "OAuth client + token saved"
          : "OAuth client saved (sign-in still needed)"
        : "Missing — paste Desktop OAuth JSON below";
      const apps = data.has_apps_script ? "Webhook saved" : "Not set";
      els.googleStatus.innerHTML = `
        <ul class="google-flags">
          <li><strong>Website account:</strong> ${escapeHtml(web)}</li>
          <li><strong>Calendar (this browser):</strong> ${escapeHtml(cal)}</li>
          <li><strong>Docs (Apps Script):</strong> ${escapeHtml(apps)} · ${escapeHtml(docs)}</li>
          <li><strong>Pin backend Calendar:</strong> ${escapeHtml(oauth)} · ${escapeHtml(flaskCal)}</li>
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
      els.googleStatus.innerHTML = `
        <ul class="google-flags">
          <li><strong>Website account:</strong> ${escapeHtml(web)}</li>
          <li><strong>Calendar (this browser):</strong> ${escapeHtml(cal)}</li>
          <li>${escapeHtml(err.message)}</li>
        </ul>`;
    }
  }

  async function api(path, options) {
    if (isPublicStaticHost()) {
      throw new Error(STATIC_HOST_NOTE);
    }
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
    updateProfileUi();
  }

  async function loadLanguages() {
    try {
      if (!isPublicStaticHost()) {
        const data = await api("/api/languages");
        state.languages = data.languages || FALLBACK_LANGUAGES;
        state.selectedLang = data.target_language || data.selected || state.selectedLang || "es";
        renderLanguages();
        return;
      }
    } catch (err) {
      if (!isPublicStaticHost()) {
        els.languageGrid.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
        return;
      }
    }
    state.languages = FALLBACK_LANGUAGES;
    state.selectedLang = state.profile.language || state.selectedLang || "es";
    renderLanguages();
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
    const lang = (state.languages.length ? state.languages : FALLBACK_LANGUAGES).find(
      (item) => item.code === code
    );
    if (!isPublicStaticHost()) {
      const data = await api("/api/settings/language", {
        method: "PUT",
        body: JSON.stringify({ code, role: "target" }),
      });
      state.selectedLang = data.target_language;
      mergeProfile({
        language: code,
        languageName: lang?.name || data.target_language_name,
      });
      await pushProfileToDevice().catch(() => {});
      renderLanguages();
      loadStatus();
      await speakGreeting(code);
      return;
    }
    state.selectedLang = code;
    mergeProfile({ language: code, languageName: lang?.name || code });
    await pushProfileToDevice().catch(() => {});
    renderLanguages();
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
      if (!els.calNote.textContent) {
        els.calNote.textContent =
          "Google Calendar is not connected. Sign in on the Account tab, or run ./run.sh --login.";
      }
    } else if (!els.calNote.textContent) {
      els.calNote.textContent = "Synced with Google Calendar.";
    }
  }

  async function loadCalendar() {
    if (!isPublicStaticHost()) {
      try {
        const data = await api("/api/calendar");
        state.calendarConnected = !!data.connected;
        state.events = data.events || [];
        if (!state.selectedDate) state.selectedDate = dayKey(new Date());
        els.calNote.textContent = state.calendarConnected
          ? "Synced with the same calendar your VoxPin writes reminders to."
          : "";
        renderCalendar();
        if (state.calendarConnected) return;
      } catch {
        /* fall through to browser Google sign-in */
      }
    }
    try {
      await loadCalendarFromGoogle();
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
      loadCalendar();
    });

    document.getElementById("calNext")?.addEventListener("click", () => {
      state.viewMonth += 1;
      if (state.viewMonth > 11) {
        state.viewMonth = 0;
        state.viewYear += 1;
      }
      loadCalendar();
    });

    document.getElementById("calToday")?.addEventListener("click", () => {
      const now = new Date();
      state.viewYear = now.getFullYear();
      state.viewMonth = now.getMonth();
      state.selectedDate = dayKey(now);
      loadCalendar();
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
    els.accountStatus?.addEventListener("click", () => {
      activateTab("google", { scroll: true });
    });
    els.saveGoogleClientId?.addEventListener("click", async () => {
      const clientId = (els.googleClientId?.value || "").trim();
      if (!clientId || !clientId.includes("apps.googleusercontent.com")) {
        if (els.googleSignInHint) {
          els.googleSignInHint.textContent =
            "That doesn’t look like a Web client ID (.apps.googleusercontent.com).";
        }
        return;
      }
      localStorage.setItem(GOOGLE_CLIENT_KEY, clientId);
      state.google.clientId = clientId;
      try {
        await waitForGoogleIdentity();
        setupGoogleSignIn();
        if (els.googleSignInHint) {
          els.googleSignInHint.textContent = "Client ID saved. Click Sign in with Google.";
        }
      } catch (err) {
        if (els.googleSignInHint) els.googleSignInHint.textContent = err.message;
      }
      loadGoogleStatus();
    });
    els.googleSignOut?.addEventListener("click", () => signOutGoogle());
    els.googleConnectCalendar?.addEventListener("click", () => requestGoogleCalendar());
    els.btModalGoogle?.addEventListener("click", () => {
      hideBtModal({ forSession: true });
      activateTab("google", { scroll: true });
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
    els.saveProfile?.addEventListener("click", async () => {
      const name = (els.profileName?.value || "").trim() || "VoxPin";
      mergeProfile({ name });
      try {
        await pushProfileToDevice();
        if (els.profileHint) {
          els.profileHint.textContent = state.bt.live
            ? "Saved on this browser and on the pin."
            : "Saved on this browser. Reconnect Bluetooth to write it to the pin.";
        }
      } catch (err) {
        if (els.profileHint) {
          els.profileHint.textContent = err.message || "Could not write to the pin.";
        }
      }
      updateDeviceUi();
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
    const stored = readProfileStore();
    if (Object.keys(stored).length) {
      state.profile = stored;
      if (stored.language) state.selectedLang = stored.language;
      if (stored.name) state.bt.name = stored.name;
    }
    bindEvents();
    animateWaves();
    await initGoogleSignIn();
    const params = new URLSearchParams(location.search);
    if (params.get("google") === "connected") {
      activateTab("google");
      history.replaceState({}, "", location.pathname);
    } else {
      activateTab("recordings");
    }
    await restoreBluetooth();
    await Promise.all([loadStatus(), loadRecordings(), loadLanguages(), loadCalendar(), loadGoogleStatus()]);
    if (isPublicStaticHost() && els.footerMeta) {
      els.footerMeta.textContent = state.google.user
        ? `Signed in as ${state.google.user.email || state.google.user.name}`
        : "Sign in with Google on the Account tab — no VoxPin server required";
    }
    if (shouldShowFirstVisitModal()) {
      showBtModal(
        bluetoothSupported()
          ? ""
          : "Tip: use Chrome or Edge on desktop for Bluetooth pairing."
      );
    }
    if (isPublicStaticHost()) return;
    setInterval(() => {
      loadStatus();
      loadRecordings();
      loadCalendar();
      loadGoogleStatus();
    }, 20000);
  }

  boot();
})();
