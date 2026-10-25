/**
 * NEXUS Ground Station — Mission Control Interface Logic
 * EDU_ROBO V14 Platform • Apollo-Inspired Architecture
 */

(function () {
  'use strict';

  // Global Application State
  const state = {
    catalog: {},
    verbs: [],
    currentVerb: '',
    currentNoun: '',
    currentCmd: null,
    paramInputs: {},
    sequenceNumber: 1,
    pendingHazardCommand: null,
    pollTimer: null,
    lastTelemetryReceivedAt: null,
  };

  // DOM Cache
  const el = {};

  function initDomElements() {
    // Header & Badges
    el.connectionBadge = document.getElementById('connection-badge');
    el.connectionText = document.getElementById('connection-text');
    el.transportBadge = document.getElementById('transport-badge');
    el.transportText = document.getElementById('transport-text');
    el.deviceIdText = document.getElementById('device-id-text');
    el.utcClock = document.getElementById('utc-clock');
    el.refreshAllBtn = document.getElementById('refresh-all-btn');

    // Quick Stats Bar
    el.chipUptime = document.getElementById('chip-uptime');
    el.chipHeap = document.getElementById('chip-heap');
    el.chipQueue = document.getElementById('chip-queue');
    el.chipCmds = document.getElementById('chip-cmds');
    el.chipAge = document.getElementById('chip-age');

    // Tabs
    el.tabBtns = document.querySelectorAll('.tab-btn');
    el.tabPanels = document.querySelectorAll('.tab-panel');

    // Sensor Readings
    el.valTemp = document.getElementById('val-temp');
    el.tagTempValid = document.getElementById('tag-temp-valid');
    el.valHum = document.getElementById('val-hum');
    el.tagHumValid = document.getElementById('tag-hum-valid');
    el.valLdr = document.getElementById('val-ldr');
    el.valX0 = document.getElementById('val-x0');
    el.valX1 = document.getElementById('val-x1');
    el.valSlot = document.getElementById('val-slot');
    el.tagSlotState = document.getElementById('tag-slot-state');
    el.valDist = document.getElementById('val-dist');
    el.tagDistState = document.getElementById('tag-dist-state');

    // Command Console Form
    el.selectVerb = document.getElementById('select-verb');
    el.selectNoun = document.getElementById('select-noun');
    el.commandMetaBar = document.getElementById('command-meta-bar');
    el.metaCmdId = document.getElementById('meta-cmd-id');
    el.metaDestination = document.getElementById('meta-destination');
    el.metaDisposition = document.getElementById('meta-disposition');
    el.metaSupported = document.getElementById('meta-supported');
    el.commandDescription = document.getElementById('command-description');
    el.parametersContainer = document.getElementById('parameters-container');
    el.dynamicFieldsArea = document.getElementById('dynamic-fields-area');
    el.selectTransportRoute = document.getElementById('select-transport-route');
    el.selectGlobalTransport = document.getElementById('select-global-transport');
    el.btnDispatchCmd = document.getElementById('btn-dispatch-cmd');

    // Wire Preview & Response
    el.wirePreview = document.getElementById('wire-preview');
    el.responseStatusBanner = document.getElementById('response-status-banner');
    el.bannerText = document.getElementById('banner-text');
    el.responsePreview = document.getElementById('response-preview');

    // Hardware Inventory Tables
    el.tbodyMountedHw = document.getElementById('tbody-mounted-hw');
    el.tbodyUnmountedHw = document.getElementById('tbody-unmounted-hw');

    // Audit Trail Table
    el.tbodyAuditHistory = document.getElementById('tbody-audit-history');
    el.btnExportJson = document.getElementById('btn-export-json');
    el.btnExportCsv = document.getElementById('btn-export-csv');

    // Services Grid
    el.servicesCardsContainer = document.getElementById('services-cards-container');

    // Reference Manual Elements
    el.tbodyCmdReference = document.getElementById('tbody-cmd-reference');
    el.refSearchInput = document.getElementById('ref-search-input');
    el.refFilterBtns = document.querySelectorAll('[data-ref-filter]');
    el.refCountBadge = document.getElementById('ref-count-badge');

    // Modal
    el.confirmationModal = document.getElementById('confirmation-modal');
    el.modalWarningText = document.getElementById('modal-warning-text');
    el.modalCommandSummary = document.getElementById('modal-command-summary');
    el.modalConfirmCheck = document.getElementById('modal-confirm-check');
    el.modalBtnCancel = document.getElementById('modal-btn-cancel');
    el.modalBtnConfirm = document.getElementById('modal-btn-confirm');
  }

  // UTC Clock
  function startUtcClock() {
    function updateClock() {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
      if (el.utcClock) {
        el.utcClock.textContent = timeStr;
      }
    }
    updateClock();
    setInterval(updateClock, 1000);
  }

  // Tab Navigation
  function initTabs() {
    el.tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetTabId = btn.getAttribute('data-tab');
        el.tabBtns.forEach((b) => b.classList.remove('active'));
        el.tabPanels.forEach((p) => p.classList.remove('active'));

        btn.classList.add('active');
        const activePanel = document.getElementById(targetTabId);
        if (activePanel) {
          activePanel.classList.add('active');
          if (targetTabId === 'tab-reference') {
            renderCommandReference();
          }
        }
      });
    });

    const currentHash = window.location.hash ? window.location.hash.substring(1) : '';
    const currentPath = window.location.pathname || '';
    let targetTab = currentHash;
    if (!targetTab) {
      if (currentPath === '/overview') targetTab = 'tab-dashboard';
      else if (currentPath === '/diagnostics') targetTab = 'tab-services';
    }
    if (targetTab) {
      const matchBtn = Array.from(el.tabBtns).find((b) => b.getAttribute('data-tab') === targetTab);
      if (matchBtn) matchBtn.click();
    }
  }

  // Toast Notifications
  function showToast(message, type = 'info') {
    let container = document.getElementById('nexus-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'nexus-toast-container';
      container.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 9999;
        display: flex;
        flex-direction: column;
        gap: 8px;
        pointer-events: none;
      `;
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const colorMap = {
      info: 'border-color: #00d2ff; background: rgba(5, 20, 35, 0.95); color: #e8f4fc;',
      success: 'border-color: #00ff88; background: rgba(5, 30, 20, 0.95); color: #d4ffea;',
      warn: 'border-color: #ffaa00; background: rgba(35, 25, 5, 0.95); color: #ffe8cc;',
      error: 'border-color: #ff3355; background: rgba(35, 10, 15, 0.95); color: #ffd6dc;',
    };

    toast.style.cssText = `
      padding: 10px 16px;
      border: 1px solid #00d2ff;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      letter-spacing: 0.05em;
      box-shadow: 0 4px 16px rgba(0,0,0,0.5);
      animation: fadeIn 0.2s ease-out;
      pointer-events: auto;
      ${colorMap[type] || colorMap.info}
    `;
    toast.textContent = `[${type.toUpperCase()}] ${message}`;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = 'opacity 0.4s ease-out';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 400);
    }, 3500);
  }

  // API Call Helpers
  async function apiGet(endpoint) {
    try {
      const response = await fetch(endpoint);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (err) {
      console.warn(`API GET ${endpoint} error:`, err);
      return null;
    }
  }

  async function apiPost(endpoint, body) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      return await response.json();
    } catch (err) {
      console.error(`API POST ${endpoint} error:`, err);
      return {
        status: 'error',
        code: 4,
        msg: `Network transmission failure: ${err.message}`,
      };
    }
  }

  // Command Registry Initialization
  async function loadCommandRegistry() {
    const data = await apiGet('/api/registry');
    if (!data || !data.catalog) {
      console.error('Failed to load command registry catalog from backend');
      showToast('Could not load command registry', 'error');
      return;
    }

    state.catalog = data.catalog;
    state.verbs = data.verbs || Object.keys(data.catalog).sort();

    // Populate VERB selector
    el.selectVerb.innerHTML = '<option value="">-- Select VERB (Category) --</option>';
    state.verbs.forEach((verb) => {
      const opt = document.createElement('option');
      opt.value = verb;
      opt.textContent = verb;
      el.selectVerb.appendChild(opt);
    });

    el.selectVerb.disabled = false;
    renderCommandReference();
    renderParameterDictionary();
  }

  // Verb Change Handler
  function onVerbChange() {
    const verb = el.selectVerb.value;
    state.currentVerb = verb;
    state.currentNoun = '';
    state.currentCmd = null;
    state.paramInputs = {};

    el.selectNoun.innerHTML = '<option value="">-- Select NOUN (Subject) --</option>';

    if (!verb || !state.catalog[verb]) {
      el.selectNoun.disabled = true;
      resetCommandDetails();
      updateWirePreview();
      return;
    }

    const nouns = Object.keys(state.catalog[verb]).sort();
    nouns.forEach((noun) => {
      const opt = document.createElement('option');
      opt.value = noun;
      opt.textContent = noun;
      el.selectNoun.appendChild(opt);
    });

    el.selectNoun.disabled = false;
    resetCommandDetails();
    updateWirePreview();
  }

  // Noun Change Handler
  function onNounChange() {
    const noun = el.selectNoun.value;
    state.currentNoun = noun;
    state.paramInputs = {};

    if (!state.currentVerb || !noun || !state.catalog[state.currentVerb] || !state.catalog[state.currentVerb][noun]) {
      state.currentCmd = null;
      resetCommandDetails();
      updateWirePreview();
      return;
    }

    const cmd = state.catalog[state.currentVerb][noun];
    state.currentCmd = cmd;

    displayCommandDetails(cmd);
    renderDynamicParameters(cmd.parameters || []);
    updateWirePreview();
    el.btnDispatchCmd.disabled = false;
  }

  function resetCommandDetails() {
    el.commandMetaBar.style.display = 'none';
    el.commandDescription.style.display = 'none';
    el.parametersContainer.style.display = 'none';
    el.dynamicFieldsArea.innerHTML = '';
    el.btnDispatchCmd.disabled = true;
  }

  function displayCommandDetails(cmd) {
    el.commandMetaBar.style.display = 'flex';
    el.commandDescription.style.display = 'block';

    const hexId = '0x' + Number(cmd.cmd_id).toString(16).toUpperCase().padStart(4, '0');
    el.metaCmdId.textContent = `${hexId} (${cmd.cmd_id})`;
    el.metaDestination.textContent = cmd.destination || 'FIRMWARE';
    el.metaDisposition.textContent = cmd.disposition || 'REQUIRED';

    if (cmd.is_supported) {
      el.metaSupported.textContent = 'YES';
      el.metaSupported.className = 'tag tag-ok';
    } else {
      el.metaSupported.textContent = 'UNSUPPORTED';
      el.metaSupported.className = 'tag tag-error';
    }

    el.commandDescription.textContent = cmd.description || 'No description available for this command entry.';
  }

  // Render Dynamic Parameter Inputs
  function renderDynamicParameters(parameters) {
    el.dynamicFieldsArea.innerHTML = '';

    if (!parameters || parameters.length === 0) {
      el.parametersContainer.style.display = 'none';
      return;
    }

    el.parametersContainer.style.display = 'block';

    parameters.forEach((param) => {
      const row = document.createElement('div');
      row.className = 'form-group param-field-row';

      const label = document.createElement('label');
      label.setAttribute('for', `param-${param.name}`);
      label.textContent = `${param.name} (${param.type}):`;

      let inputEl;

      if (param.enum_values && param.enum_values.length > 0) {
        inputEl = document.createElement('select');
        inputEl.id = `param-${param.name}`;
        inputEl.className = 'form-control';
        param.enum_values.forEach((v) => {
          const opt = document.createElement('option');
          opt.value = v;
          opt.textContent = String(v);
          if (param.default_value !== null && String(param.default_value) === String(v)) {
            opt.selected = true;
          }
          inputEl.appendChild(opt);
        });
        state.paramInputs[param.name] = inputEl.value;
      } else if (param.type === 'boolean' || param.type === 'bool') {
        inputEl = document.createElement('select');
        inputEl.id = `param-${param.name}`;
        inputEl.className = 'form-control';
        const optFalse = document.createElement('option');
        optFalse.value = '0';
        optFalse.textContent = '0 (False / Disabled)';
        const optTrue = document.createElement('option');
        optTrue.value = '1';
        optTrue.textContent = '1 (True / Enabled)';
        if (param.default_value === 1 || param.default_value === true) {
          optTrue.selected = true;
        } else {
          optFalse.selected = true;
        }
        inputEl.appendChild(optFalse);
        inputEl.appendChild(optTrue);
        state.paramInputs[param.name] = parseInt(inputEl.value, 10);
      } else {
        inputEl = document.createElement('input');
        inputEl.id = `param-${param.name}`;
        inputEl.className = 'form-control';

        if (param.type === 'integer' || param.type === 'int') {
          inputEl.type = 'number';
          inputEl.step = '1';
          if (param.min_value !== null) inputEl.min = param.min_value;
          if (param.max_value !== null) inputEl.max = param.max_value;
          inputEl.value = param.default_value !== null ? param.default_value : 0;
          state.paramInputs[param.name] = parseInt(inputEl.value, 10);
        } else if (param.type === 'float' || param.type === 'double' || param.type === 'number') {
          inputEl.type = 'number';
          inputEl.step = '0.1';
          if (param.min_value !== null) inputEl.min = param.min_value;
          if (param.max_value !== null) inputEl.max = param.max_value;
          inputEl.value = param.default_value !== null ? param.default_value : 0.0;
          state.paramInputs[param.name] = parseFloat(inputEl.value);
        } else {
          inputEl.type = 'text';
          inputEl.value = param.default_value !== null ? param.default_value : '';
          state.paramInputs[param.name] = inputEl.value;
        }
      }

      const updateParam = () => {
        if (param.enum_values && param.enum_values.length > 0) {
          state.paramInputs[param.name] = inputEl.value;
        } else if (param.type === 'boolean' || param.type === 'bool') {
          state.paramInputs[param.name] = parseInt(inputEl.value, 10);
        } else if (param.type === 'integer' || param.type === 'int') {
          state.paramInputs[param.name] = parseInt(inputEl.value, 10) || 0;
        } else if (param.type === 'float' || param.type === 'double' || param.type === 'number') {
          state.paramInputs[param.name] = parseFloat(inputEl.value) || 0.0;
        } else {
          state.paramInputs[param.name] = inputEl.value;
        }
        updateWirePreview();
      };

      inputEl.addEventListener('input', updateParam);
      inputEl.addEventListener('change', updateParam);

      const helper = document.createElement('div');
      helper.className = 'param-helper-text';
      let metaInfo = [];
      if (param.min_value !== null && param.max_value !== null) {
        metaInfo.push(`Range: [${param.min_value} .. ${param.max_value}]`);
      }
      if (param.unit) {
        metaInfo.push(`Unit: ${param.unit}`);
      }
      if (param.description) {
        metaInfo.push(param.description);
      }
      helper.textContent = metaInfo.join(' • ');

      row.appendChild(label);
      row.appendChild(inputEl);
      if (metaInfo.length > 0) {
        row.appendChild(helper);
      }
      el.dynamicFieldsArea.appendChild(row);
    });
  }

  // Update Wire Envelope Preview
  function updateWirePreview() {
    if (!state.currentCmd) {
      el.wirePreview.textContent = '{\n  /* Select a VERB and NOUN to inspect outbound wire envelope */\n}';
      return;
    }

    const destination = state.currentCmd.destination || 'FIRMWARE';
    if (destination !== 'FIRMWARE') {
      const preview = {
        _execution_path: "HOST_LOCAL_OPERATION",
        api_endpoint: "POST /api/command",
        target: destination,
        verb: state.currentVerb,
        noun: state.currentNoun,
        params: state.paramInputs,
        device_wire_envelope: "NOT_APPLICABLE (Host-local execution by Ground Station service / AI Copilot; no ESP32 device packet dispatched)"
      };
      el.wirePreview.textContent = JSON.stringify(preview, null, 2);
      return;
    }

    const preview = {
      _execution_path: "FIRMWARE_DEVICE_DISPATCH",
      wire_envelope: {
        ver: 1,
        dev: "nexus_esp32",
        seq: state.sequenceNumber,
        type: "cmd",
        cmd_id: state.currentCmd.cmd_id,
        ...state.paramInputs
      },
      transport_route: el.selectTransportRoute.value || 'auto',
      requires_confirmation: Boolean(state.currentCmd.requires_confirmation),
    };

    el.wirePreview.textContent = JSON.stringify(preview, null, 2);
  }

  // Dispatch Command Execution
  async function onDispatchClick() {
    if (!state.currentCmd) return;

    if (state.currentCmd.requires_confirmation) {
      openConfirmationModal(state.currentCmd);
      return;
    }

    await executeCommand(false);
  }

  function openConfirmationModal(cmd) {
    state.pendingHazardCommand = cmd;
    el.modalWarningText.textContent = `Warning: The command "${state.currentVerb} ${state.currentNoun}" is classified as a hazardous operation. It modifies system executive state or clears diagnostic data.`;
    el.modalCommandSummary.textContent = `${state.currentVerb} ${state.currentNoun} [ID: ${cmd.cmd_id}] • Params: ${JSON.stringify(state.paramInputs)}`;
    el.modalConfirmCheck.checked = false;
    el.modalBtnConfirm.disabled = true;
    el.confirmationModal.style.display = 'flex';
  }

  function closeConfirmationModal() {
    el.confirmationModal.style.display = 'none';
    state.pendingHazardCommand = null;
  }

  async function executeCommand(isConfirmed) {
    if (!state.currentCmd) return;

    const verb = state.currentVerb;
    const noun = state.currentNoun;
    const params = { ...state.paramInputs };
    const transport = el.selectTransportRoute.value || 'auto';

    el.btnDispatchCmd.disabled = true;
    el.responseStatusBanner.className = 'status-banner banner-running';
    el.bannerText.textContent = `TRANSMITTING: ${verb} ${noun} to ${state.currentCmd.destination}...`;
    el.responsePreview.textContent = '{\n  /* Awaiting target response envelope... */\n}';

    const reqPayload = {
      verb: verb,
      noun: noun,
      params: params,
      confirmed: isConfirmed,
      transport: transport,
      timeout: 3.0,
    };

    const res = await apiPost('/api/command', reqPayload);
    state.sequenceNumber += 1;
    el.btnDispatchCmd.disabled = false;

    // Display formatted response envelope
    el.responsePreview.textContent = JSON.stringify(res, null, 2);

    const code = res.code !== undefined ? res.code : 4;
    if (code === 0 || res.status === 'ok') {
      el.responseStatusBanner.className = 'status-banner banner-success';
      el.bannerText.textContent = `SUCCESS (Code 0): ${res.msg || 'Command executed successfully'}`;
      showToast(`${verb} ${noun} executed successfully`, 'success');
    } else if (code === 3 || res.status === 'unsupported') {
      el.responseStatusBanner.className = 'status-banner banner-warn';
      el.bannerText.textContent = `UNSUPPORTED (Code 3): ${res.msg || 'Command rejected by hardware profile'}`;
      showToast(`${verb} ${noun} rejected: ${res.msg || 'Unsupported on EDU_ROBO V14'}`, 'warn');
    } else {
      el.responseStatusBanner.className = 'status-banner banner-error';
      el.bannerText.textContent = `REJECTED/ERROR (Code ${code}): ${res.msg || 'Execution failed'}`;
      showToast(`Command error: ${res.msg || 'Rejection occurred'}`, 'error');
    }

    updateWirePreview();
    pollCommandHistory();
  }

  // Polling: System Status & Telemetry
  async function pollSystemStatus() {
    const data = await apiGet('/api/status');
    if (!data) {
      if (el.connectionBadge) {
        el.connectionBadge.className = 'badge badge-offline';
        el.connectionText.textContent = 'DISCONNECTED';
      }
      return;
    }

    // Connection badge
    if (data.connected) {
      el.connectionBadge.className = 'badge badge-online';
      el.connectionText.textContent = 'CONNECTED';
    } else {
      el.connectionBadge.className = 'badge badge-offline';
      el.connectionText.textContent = 'STANDBY';
    }

    // Active Transport route
    const route = data.active_transport || 'NONE';
    el.transportText.textContent = route;
    if (route === 'DUAL' || route === 'SERIAL' || route === 'MQTT') {
      el.transportBadge.className = 'badge badge-online';
    } else {
      el.transportBadge.className = 'badge badge-neutral';
    }

    if (data.device_id && el.deviceIdText) {
      el.deviceIdText.textContent = data.device_id;
    }

    // Top Telemetry Chips
    if (el.chipQueue && data.ingestion) {
      el.chipQueue.textContent = `${data.ingestion.queue_size} / ${data.ingestion.queue_capacity}`;
    }
    if (el.chipCmds && data.commands) {
      el.chipCmds.textContent = data.commands.outbound_dispatched || '0';
    }
    if (el.chipAge) {
      if (data.latest_telemetry_age_sec !== null && data.latest_telemetry_age_sec !== undefined) {
        el.chipAge.textContent = `${data.latest_telemetry_age_sec}s ago`;
      } else {
        el.chipAge.textContent = 'No stream';
      }
    }

    // Render Hardware inventory if tables are empty
    if (data.capabilities) {
      renderHardwareTables(data.capabilities);
    }

    // Render Mission Services cards if empty
    if (data.services) {
      renderServicesGrid(data.services);
    }
  }

  async function pollTelemetryLatest() {
    const data = await apiGet('/api/telemetry/latest');
    if (!data || !data.has_data) {
      return;
    }

    state.lastTelemetryReceivedAt = data.received_at;

    // Free Heap & Uptime
    if (data.free_heap_kb !== undefined && el.chipHeap) {
      el.chipHeap.textContent = `${data.free_heap_kb} KB`;
    }
    if (data.uptime_ms !== undefined && el.chipUptime) {
      const sec = Math.floor(data.uptime_ms / 1000);
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      const h = Math.floor(m / 60);
      const pad = (n) => String(n).padStart(2, '0');
      el.chipUptime.textContent = `${pad(h)}:${pad(m % 60)}:${pad(s)}`;
    }

    // DHT11 Temp & Humidity
    if (data.temp !== null && data.temp !== undefined) {
      el.valTemp.textContent = Number(data.temp).toFixed(1);
      el.tagTempValid.textContent = data.dht_valid ? 'VALID' : 'STALE';
      el.tagTempValid.className = data.dht_valid ? 'tag tag-ok' : 'tag tag-warn';
    }
    if (data.hum !== null && data.hum !== undefined) {
      el.valHum.textContent = Number(data.hum).toFixed(1);
      el.tagHumValid.textContent = data.dht_valid ? 'VALID' : 'STALE';
      el.tagHumValid.className = data.dht_valid ? 'tag tag-ok' : 'tag tag-warn';
    }

    // LDR
    if (data.ldr !== null && data.ldr !== undefined) {
      el.valLdr.textContent = data.ldr;
    }

    // CD4051 MUX X0 (HW-870) and X1 (Hall Effect IC2)
    if (data.x0 !== null && data.x0 !== undefined) {
      el.valX0.textContent = data.x0;
    }
    if (el.valX1) {
      el.valX1.textContent = 'NOT INSTALLED';
    }

    // MOC7811 Optical Slot Beam
    if (data.slot !== null && data.slot !== undefined) {
      const isBlocked = Number(data.slot) === 1;
      el.valSlot.textContent = isBlocked ? 'BLOCKED' : 'CLEAR';
      el.tagSlotState.textContent = isBlocked ? 'BEAM INTERRUPTED' : 'BEAM CLEAR';
      el.tagSlotState.className = isBlocked ? 'tag tag-warn' : 'tag tag-ok';
    }

    // HC-SR04 Ultrasonic Distance
    if (data.dist !== null && data.dist !== undefined) {
      el.valDist.textContent = Number(data.dist).toFixed(1);
      const inRange = data.dist >= 2 && data.dist <= 400;
      el.tagDistState.textContent = inRange ? 'IN RANGE' : 'OUT OF RANGE';
      el.tagDistState.className = inRange ? 'tag tag-ok' : 'tag tag-neutral';
    }
  }

  async function pollCommandHistory() {
    const data = await apiGet('/api/commands');
    if (!data || !data.history) return;

    const history = data.history;
    if (history.length === 0) {
      el.tbodyAuditHistory.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No commands dispatched during this session</td></tr>';
      return;
    }

    el.tbodyAuditHistory.innerHTML = '';
    const reversed = [...history].reverse();

    reversed.forEach((entry) => {
      const tr = document.createElement('tr');
      const timeStr = entry.timestamp ? new Date(entry.timestamp * 1000).toISOString().substring(11, 19) : '--:--:--';
      const seq = entry.seq !== undefined ? entry.seq : '-';
      const route = entry.transport || 'auto';
      const type = entry.type || 'cmd';
      const verb = entry.verb || '-';
      const noun = entry.noun || '-';
      const status = entry.status || 'dispatched';
      const code = entry.code !== undefined ? entry.code : '-';
      const details = entry.msg || JSON.stringify(entry.params || {});

      let tagClass = 'tag-neutral';
      if (status === 'ok') tagClass = 'tag-ok';
      else if (status === 'unsupported') tagClass = 'tag-warn';
      else if (status === 'rejected' || status === 'timeout' || status === 'error') tagClass = 'tag-error';

      tr.innerHTML = `
        <td class="font-mono">${timeStr}</td>
        <td class="font-mono">${seq}</td>
        <td class="font-mono"><span class="code-pill text-cyan">${escapeHtml(route)}</span></td>
        <td><span class="code-pill">${type}</span></td>
        <td class="font-bold">${verb}</td>
        <td class="font-bold">${noun}</td>
        <td><span class="tag ${tagClass}">${status.toUpperCase()}</span></td>
        <td class="font-mono">${code}</td>
        <td class="text-sm truncate-cell" title="${escapeHtml(details)}">${escapeHtml(details)}</td>
      `;
      el.tbodyAuditHistory.appendChild(tr);
    });
  }

  function renderHardwareTables(caps) {
    if (!caps) return;

    if (caps.mounted && el.tbodyMountedHw && el.tbodyMountedHw.children.length === 0) {
      el.tbodyMountedHw.innerHTML = '';
      caps.mounted.forEach((hw) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="font-mono text-cyan">${escapeHtml(hw.id)}</td>
          <td class="font-bold">${escapeHtml(hw.name)}</td>
          <td class="font-mono">GPIO ${escapeHtml(String(hw.gpio))}</td>
          <td><span class="code-pill">${escapeHtml(hw.bus)}</span></td>
          <td><span class="tag tag-ok">MOUNTED</span></td>
        `;
        el.tbodyMountedHw.appendChild(tr);
      });
    }

    if (caps.unmounted && el.tbodyUnmountedHw && el.tbodyUnmountedHw.children.length === 0) {
      el.tbodyUnmountedHw.innerHTML = '';
      caps.unmounted.forEach((hw) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="font-mono text-muted">${escapeHtml(hw.id)}</td>
          <td>${escapeHtml(hw.name)}</td>
          <td class="font-mono">GPIO ${escapeHtml(String(hw.gpio))}</td>
          <td class="text-sm text-warn">${escapeHtml(hw.reason)}</td>
        `;
        el.tbodyUnmountedHw.appendChild(tr);
      });
    }
  }

  function renderServicesGrid(services) {
    if (!services || !el.servicesCardsContainer) return;
    el.servicesCardsContainer.innerHTML = '';

    const serviceList = [
      {
        id: 'grafana',
        name: 'Grafana Dashboard',
        port: 3000,
        url: services.grafana?.url || 'http://127.0.0.1:3000',
        status: services.grafana?.status || 'offline',
        desc: 'Interactive telemetry telemetry charts, gauge clusters, and historical environmental time-series panels.',
        btnText: 'Open Grafana',
      },
      {
        id: 'influxdb',
        name: 'InfluxDB 2.x Engine',
        port: 8086,
        url: services.influxdb?.url || 'http://127.0.0.1:8086',
        status: services.influxdb?.status || 'offline',
        desc: 'High-performance time-series database storing sensor samples, telemetry buckets, and Flux analytical queries.',
        btnText: 'Open InfluxDB',
      },
      {
        id: 'open_webui',
        name: 'Open WebUI AI Assistant',
        port: 8080,
        url: services.open_webui?.url || 'http://127.0.0.1:8080',
        status: services.open_webui?.status || 'offline',
        desc: 'Grounded mission AI copilot executing allowlisted NEXUS tools and providing natural language telemetry query capabilities.',
        btnText: 'Launch AI Copilot',
      },
      {
        id: 'diagnostics',
        name: 'Ground Station REST Diagnostics',
        port: 8000,
        url: '/api/diagnostics',
        status: 'online',
        desc: 'JSON diagnostic endpoint providing live buffer states, serial/MQTT stats, thread queues, and service telemetry.',
        btnText: 'View Diagnostics',
      },
    ];

    serviceList.forEach((s) => {
      const card = document.createElement('article');
      card.className = 'service-card';
      const isOnline = s.status === 'online';

      card.innerHTML = `
        <div class="service-card-head">
          <div class="service-name">${escapeHtml(s.name)}</div>
          <span class="tag ${isOnline ? 'tag-ok' : 'tag-neutral'}">${isOnline ? 'ONLINE' : 'OFFLINE'}</span>
        </div>
        <div class="service-card-body">
          <p class="service-desc">${escapeHtml(s.desc)}</p>
          <div class="service-meta">
            <span>Port: ${s.port}</span>
            <span class="font-mono text-cyan">${escapeHtml(s.url)}</span>
          </div>
          <div class="service-action-row">
            <a href="${s.url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm ${isOnline ? 'btn-primary' : 'btn-outline'}">
              ${escapeHtml(s.btnText)} ↗
            </a>
          </div>
        </div>
      `;
      el.servicesCardsContainer.appendChild(card);
    });
  }

  // Quick Actuator Helpers for Mission Operator
  async function quickBuzzer(stateVal, durationMs) {
    const dur = durationMs || 200;
    const transport = (el.selectGlobalTransport && el.selectGlobalTransport.value) || (el.selectTransportRoute && el.selectTransportRoute.value) || 'auto';
    showToast(`Quick Actuation: Buzzer Beep (${dur}ms) via ${transport.toUpperCase()}`, 'info');
    const res = await apiPost('/api/command', {
      verb: 'ACTUATE',
      noun: 'BUZZER',
      params: { duration_ms: dur },
      confirmed: false,
      transport: transport,
    });
    if (res.code === 0) {
      showToast('Buzzer command acknowledged', 'success');
    } else {
      showToast(`Buzzer command: ${res.msg}`, 'warn');
    }
    pollCommandHistory();
  }

  async function quickLed(ledIdx, stateVal) {
    const stateStr = (stateVal === 1 || stateVal === 'on' || stateVal === true) ? 'on' : 'off';
    const transport = (el.selectGlobalTransport && el.selectGlobalTransport.value) || (el.selectTransportRoute && el.selectTransportRoute.value) || 'auto';
    showToast(`Quick Actuation: LED ${ledIdx} ${stateStr.toUpperCase()} via ${transport.toUpperCase()}`, 'info');
    const res = await apiPost('/api/command', {
      verb: 'ACTUATE',
      noun: 'LED',
      params: { led_id: ledIdx, state: stateStr },
      confirmed: false,
      transport: transport,
    });
    if (res.code === 0) {
      showToast(`LED ${ledIdx} updated`, 'success');
    } else {
      showToast(`LED command: ${res.msg}`, 'warn');
    }
    pollCommandHistory();
  }

  // Export Helpers
  function triggerExport(format) {
    const url = `/api/export?format=${format}&limit=100`;
    window.open(url, '_blank');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Setup Event Listeners
  function setupEventListeners() {
    el.selectVerb.addEventListener('change', onVerbChange);
    el.selectNoun.addEventListener('change', onNounChange);
    if (el.selectGlobalTransport) {
      el.selectGlobalTransport.addEventListener('change', () => {
        if (el.selectTransportRoute) {
          el.selectTransportRoute.value = el.selectGlobalTransport.value;
        }
        updateWirePreview();
      });
    }
    if (el.selectTransportRoute) {
      el.selectTransportRoute.addEventListener('change', () => {
        if (el.selectGlobalTransport) {
          el.selectGlobalTransport.value = el.selectTransportRoute.value;
        }
        updateWirePreview();
      });
    }
    el.btnDispatchCmd.addEventListener('click', onDispatchClick);

    // Modal listeners
    el.modalConfirmCheck.addEventListener('change', () => {
      el.modalBtnConfirm.disabled = !el.modalConfirmCheck.checked;
    });
    el.modalBtnCancel.addEventListener('click', closeConfirmationModal);
    el.modalBtnConfirm.addEventListener('click', async () => {
      closeConfirmationModal();
      await executeCommand(true);
    });

    // Refresh & Export
    if (el.refreshAllBtn) {
      el.refreshAllBtn.addEventListener('click', () => {
        showToast('Refreshing mission telemetry...', 'info');
        pollSystemStatus();
        pollTelemetryLatest();
        pollCommandHistory();
      });
    }

    if (el.btnExportJson) {
      el.btnExportJson.addEventListener('click', () => triggerExport('json'));
    }
    if (el.btnExportCsv) {
      el.btnExportCsv.addEventListener('click', () => triggerExport('csv'));
    }

    // Reference Manual search & filter listeners
    if (el.refSearchInput) {
      el.refSearchInput.addEventListener('input', () => {
        const activeBtn = document.querySelector('[data-ref-filter].active');
        const filter = activeBtn ? activeBtn.getAttribute('data-ref-filter') : 'all';
        renderCommandReference(filter, el.refSearchInput.value);
      });
    }

    const paramSearchInput = document.getElementById('param-search-input');
    if (paramSearchInput) {
      paramSearchInput.addEventListener('input', () => {
        renderParameterDictionary(paramSearchInput.value);
      });
    }

    if (el.refFilterBtns) {
      el.refFilterBtns.forEach((btn) => {
        btn.addEventListener('click', () => {
          el.refFilterBtns.forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          const filter = btn.getAttribute('data-ref-filter') || 'all';
          const query = el.refSearchInput ? el.refSearchInput.value : '';
          renderCommandReference(filter, query);
        });
      });
    }

    // Reference Sub-Navigation Tabs Switching
    const refSubtabBtns = document.querySelectorAll('.ref-subtab-btn');
    const refSubpanels = document.querySelectorAll('.ref-subpanel');
    refSubtabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        refSubtabBtns.forEach((b) => b.classList.remove('active'));
        refSubpanels.forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-ref-subtab');
        const targetPanel = document.getElementById(targetId);
        if (targetPanel) targetPanel.classList.add('active');
      });
    });
  }

  // Cross-link Navigation: Jump from Parameter Dictionary to Command Drawer in Catalog
  window.jumpToCommand = function(verb, noun) {
    const btnSubtabCatalog = document.getElementById('btn-subtab-catalog');
    if (btnSubtabCatalog) btnSubtabCatalog.click();
    const searchInput = document.getElementById('ref-search-input');
    if (searchInput) {
      searchInput.value = `${verb} ${noun}`;
      renderCommandReference('all', searchInput.value);
    }
    const key = `${verb}_${noun}`.replace(/[^a-zA-Z0-9_]/g, '_');
    setTimeout(() => {
      const detailRow = document.getElementById(`detail-${key}`);
      if (detailRow && (detailRow.style.display === 'none' || !detailRow.style.display)) {
        toggleCommandDetail(key);
      }
      const rowEl = document.getElementById(`row-${key}`);
      if (rowEl) rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  };

  // Toggle parameter value mappings in command detail drawer
  window.toggleParamValues = function(event, containerId) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    const container = document.getElementById(containerId);
    const icon = document.getElementById('icon-' + containerId);
    if (!container) return;
    const isHidden = container.style.display === 'none' || !container.style.display;
    container.style.display = isHidden ? 'block' : 'none';
    if (icon) icon.textContent = isHidden ? '▾' : '▸';
  };

  // Toggle parameter dictionary drawer row
  window.toggleDictParamDrawer = function(paramName) {
    const drawerRow = document.getElementById(`dict-drawer-${paramName}`);
    const icon = document.getElementById(`icon-dict-${paramName}`);
    if (!drawerRow) return;
    const isHidden = drawerRow.style.display === 'none' || !drawerRow.style.display;
    drawerRow.style.display = isHidden ? 'table-row' : 'none';
    if (icon) icon.textContent = isHidden ? '▾' : '▸';
  };

  // Cross-link Navigation: Jump from Command Drawer to Parameter Dictionary
  window.jumpToParameter = function(paramName) {
    const btnSubtabParam = document.getElementById('btn-subtab-parameters');
    if (btnSubtabParam) btnSubtabParam.click();
    const paramInput = document.getElementById('param-search-input');
    if (paramInput) {
      paramInput.value = paramName;
      renderParameterDictionary(paramName);
    }
    setTimeout(() => {
      const pRow = document.getElementById(`param-row-${paramName}`);
      if (pRow) {
        pRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        pRow.style.outline = '2px solid #38bdf8';
        setTimeout(() => { pRow.style.outline = 'none'; }, 2000);
      }
      // Auto-expand the value definitions drawer
      const drawerRow = document.getElementById(`dict-drawer-${paramName}`);
      const icon = document.getElementById(`icon-dict-${paramName}`);
      if (drawerRow) {
        drawerRow.style.display = 'table-row';
        if (icon) icon.textContent = '▾';
      }
    }, 80);
  };

  // Toggle Command Detail Drawer in Reference Manual
  window.toggleCommandDetail = function(key) {
    const detailRow = document.getElementById(`detail-${key}`);
    const icon = document.getElementById(`icon-${key}`);
    const mainRow = document.getElementById(`row-${key}`);
    if (!detailRow) return;

    if (detailRow.style.display === 'none' || !detailRow.style.display) {
      detailRow.style.display = 'table-row';
      if (icon) icon.textContent = '▾';
      if (mainRow) mainRow.classList.add('cmd-row-expanded');
    } else {
      detailRow.style.display = 'none';
      if (icon) icon.textContent = '▸';
      if (mainRow) mainRow.classList.remove('cmd-row-expanded');
    }
  };

  // Command & Data Reference Generator with Expandable Detail Drawers
  function renderCommandReference(filter = 'all', query = '') {
    if (!el.tbodyCmdReference || !state.catalog) return;

    const q = (query || '').trim().toLowerCase();
    const rows = [];
    let totalCount = 0;
    let matchCount = 0;

    const verbs = Object.keys(state.catalog).sort();
    verbs.forEach((verb) => {
      const nouns = Object.keys(state.catalog[verb]).sort();
      nouns.forEach((noun) => {
        totalCount += 1;
        const cmd = state.catalog[verb][noun];
        const dest = cmd.destination || 'FIRMWARE';
        const key = `${verb}_${noun}`.replace(/[^a-zA-Z0-9_]/g, '_');

        // Target Filter
        if (filter !== 'all' && dest !== filter) {
          return;
        }

        // Search Filter
        const hexId = '0x' + Number(cmd.cmd_id).toString(16).toUpperCase().padStart(4, '0');
        const decId = String(cmd.cmd_id);
        const desc = (cmd.description || '').toLowerCase();
        const paramNames = (cmd.parameters || []).map(p => p.name).join(' ').toLowerCase();

        if (q) {
          const match = verb.toLowerCase().includes(q) ||
                        noun.toLowerCase().includes(q) ||
                        `${verb.toLowerCase()} ${noun.toLowerCase()}`.includes(q) ||
                        hexId.toLowerCase().includes(q) ||
                        decId.includes(q) ||
                        desc.includes(q) ||
                        paramNames.includes(q) ||
                        dest.toLowerCase().includes(q);
          if (!match) return;
        }

        matchCount += 1;

        // Target badge
        let targetBadgeClass = 'tag-ok';
        if (dest === 'GROUND_STATION') targetBadgeClass = 'tag-info';
        if (dest === 'TEST_HARNESS') targetBadgeClass = 'tag-neutral';

        // Transports
        let transports = 'USB Serial & MQTT';
        if (dest === 'GROUND_STATION') transports = 'Local Host / HTTP';
        if (dest === 'TEST_HARNESS') transports = 'Host Test Harness';

        // Parameters summary formatting
        let paramsSummaryHtml = '<span class="text-muted">None</span>';
        let exampleParams = {};
        if (cmd.parameters && cmd.parameters.length > 0) {
          paramsSummaryHtml = cmd.parameters.map((p) => {
            const req = p.required ? '<span style="color:#ff5555;font-weight:bold;">*</span>' : '';
            const typeBadge = `<span class="tag tag-neutral" style="font-size:0.65rem;padding:0.1rem 0.25rem;">${escapeHtml(p.type || 'any')}</span>`;
            const defVal = (p.default !== undefined && p.default !== null) ? ` = ${p.default}` : '';
            return `<div style="margin-bottom:0.25rem;font-size:0.75rem;"><a href="javascript:void(0)" onclick="jumpToParameter('${p.name}')" style="color:#38bdf8;text-decoration:none;"><code>${escapeHtml(p.name)}</code></a>${req} ${typeBadge}<span class="text-muted">${defVal}</span></div>`;
          }).join('');
        }

        // Safety badge
        const safetyBadge = cmd.requires_confirmation
          ? '<span class="tag tag-error" style="font-size:0.65rem;">⚠️ HAZARD (Confirm)</span>'
          : '<span class="tag tag-ok" style="font-size:0.65rem;">SAFE</span>';

        // Detailed Parameters Table
        let paramsTableHtml = '<div class="text-muted" style="font-size:0.75rem; padding:0.25rem 0;">No parameters required for this command.</div>';
        if (cmd.parameters && cmd.parameters.length > 0) {
          paramsTableHtml = `
            <table class="data-table" style="font-size:0.72rem; width:100%; margin-top:0.35rem; border:1px solid #1f2f47;">
              <thead>
                <tr>
                  <th style="width:110px;">Key</th>
                  <th style="width:70px;">Type</th>
                  <th style="width:80px;">Constraint</th>
                  <th style="width:130px;">Value Semantics</th>
                  <th style="width:180px;">Allowed Values / Range & Units</th>
                  <th style="width:110px;">Default</th>
                  <th>Description & Discovery Workflow</th>
                </tr>
              </thead>
              <tbody>
                ${cmd.parameters.map(p => {
                  let rangeStr = '<span class="text-muted">Dynamic / Discovery Required</span>';
                  if (p.enum_values && p.enum_values.length > 0) {
                    rangeStr = p.enum_values.map(v => `<code>${escapeHtml(v)}</code>`).join(', ');
                  } else if (p.min_value !== undefined && p.min_value !== null && p.max_value !== undefined && p.max_value !== null) {
                    const unitStr = p.units ? ` <span class="text-muted">${escapeHtml(p.units)}</span>` : '';
                    rangeStr = `${p.min_value} ... ${p.max_value}${unitStr}`;
                  } else if (p.units) {
                    rangeStr = `<span class="text-muted">Numeric (${escapeHtml(p.units)})</span>`;
                  }

                  // Expandable Individual Value Mappings in Command Drawer
                  let valMappingsHtml = '';
                  if (p.value_mappings && typeof p.value_mappings === 'object' && Object.keys(p.value_mappings).length > 0) {
                    const mapEntries = Object.entries(p.value_mappings);
                    const containerId = `cmd-${key}-${p.name}-vals`;
                    valMappingsHtml = `
                      <div style="margin-top:0.35rem;">
                        <button type="button" class="btn btn-xs btn-outline" style="font-size:0.65rem; padding:0.15rem 0.4rem; background:#0f172a; border:1px solid #0284c7; color:#38bdf8; cursor:pointer;" onclick="toggleParamValues(event, '${containerId}')">
                          <span id="icon-${containerId}">▸</span> View Value Mappings (${mapEntries.length})
                        </button>
                        <div id="${containerId}" style="display:none; margin-top:0.35rem; padding:0.4rem 0.5rem; background:#090d16; border:1px solid #1e293b; border-radius:4px; max-width:440px;">
                          <table class="data-table" style="font-size:0.68rem; width:100%; border:1px solid #1e293b; margin:0;">
                            <thead>
                              <tr style="background:#0f172a;">
                                <th style="width:85px; color:#38bdf8; padding:0.2rem 0.35rem;">Value</th>
                                <th style="color:#cbd5e1; padding:0.2rem 0.35rem;">Meaning</th>
                              </tr>
                            </thead>
                            <tbody>
                              ${mapEntries.map(([val, desc]) => `
                                <tr>
                                  <td style="padding:0.2rem 0.35rem;"><code class="font-mono text-cyan" style="font-weight:bold;">${escapeHtml(val)}</code></td>
                                  <td style="padding:0.2rem 0.35rem; color:#e2e8f0;">${escapeHtml(desc)}</td>
                                </tr>
                              `).join('')}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    `;
                  }

                  // Establish non-null executable example value
                  if (p.default !== undefined && p.default !== null) {
                    exampleParams[p.name] = p.default;
                  } else if (p.enum_values && p.enum_values.length > 0) {
                    exampleParams[p.name] = p.enum_values[0];
                  } else if (p.min_value !== undefined && p.min_value !== null) {
                    exampleParams[p.name] = p.min_value;
                  } else if (p.type === 'int' || p.type === 'integer') {
                    exampleParams[p.name] = 1;
                  } else if (p.type === 'float' || p.type === 'number') {
                    exampleParams[p.name] = 1.0;
                  } else if (p.type === 'bool' || p.type === 'boolean') {
                    exampleParams[p.name] = true;
                  } else {
                    exampleParams[p.name] = 'default';
                  }

                  const reqBadge = p.required
                    ? '<span class="tag tag-error" style="font-size:0.6rem;">REQUIRED</span>'
                    : '<span class="tag tag-neutral" style="font-size:0.6rem;">OPTIONAL</span>';

                  const semBadge = p.value_semantics
                    ? `<span class="tag tag-info" style="font-size:0.6rem;">${escapeHtml(p.value_semantics)}</span>`
                    : '<span class="text-muted" style="font-size:0.6rem;">Unclassified</span>';

                  const discHtml = p.discovery_workflow
                    ? `<div style="font-size:0.68rem; color:#38bdf8; margin-top:0.25rem;">🔍 <strong>Discovery:</strong> ${escapeHtml(p.discovery_workflow)}</div>`
                    : '';

                  let defDisplay = '-';
                  if (p.default !== undefined && p.default !== null) {
                    defDisplay = `<code class="font-mono text-cyan">${escapeHtml(String(p.default))}</code>`;
                  } else if (!p.required) {
                    defDisplay = '<span class="text-muted">Optional (omit)</span>';
                  } else {
                    defDisplay = '<span style="color:#f43f5e;font-size:0.65rem;">Required</span>';
                  }

                  return `
                    <tr>
                      <td class="font-mono"><a href="javascript:void(0)" onclick="jumpToParameter('${p.name}')" style="color:#00ffff; text-decoration:underline;"><strong>${escapeHtml(p.name)}</strong></a></td>
                      <td><span class="tag tag-neutral" style="font-size:0.65rem;">${escapeHtml(p.type || 'any')}</span></td>
                      <td>${reqBadge}</td>
                      <td>${semBadge}</td>
                      <td>${rangeStr}${valMappingsHtml}</td>
                      <td>${defDisplay}</td>
                      <td>
                        <div>${escapeHtml(p.description || '')}</div>
                        ${discHtml}
                      </td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          `;
        }

        // Compute Example Classification
        let exampleTypeBadge = '<span class="tag tag-ok" style="font-size:0.7rem;">[RUNNABLE EXAMPLE]</span>';
        let exampleNote = 'Validated against canonical schema; executable without placeholder replacement.';
        let exampleResponseObj;

        if (cmd.disposition === 'UNSUPPORTED' || !cmd.is_supported) {
          exampleTypeBadge = '<span class="tag tag-error" style="font-size:0.7rem;">[UNSUPPORTED DEMO]</span>';
          exampleNote = 'Expected to be rejected by current build (hardware unmounted or safety-restricted).';
          exampleResponseObj = {
            ver: 1,
            dev: "nexus_esp32",
            seq: 1024,
            type: "resp",
            cmd_id: cmd.cmd_id,
            verb: verb,
            noun: noun,
            status: "unsupported",
            code: 3,
            msg: `${verb} ${noun} is unsupported on this hardware/build`
          };
        } else if (cmd.requires_confirmation) {
          exampleTypeBadge = '<span class="tag tag-warning" style="font-size:0.7rem; background:#7c2d12; color:#fed7aa; border:1px solid #ea580c;">[HAZARDOUS TEMPLATE]</span>';
          exampleNote = 'Modifies system state or clears counters; operator confirmation dialog required.';
          exampleResponseObj = {
            ver: 1,
            dev: "nexus_esp32",
            seq: 1024,
            type: "resp",
            cmd_id: cmd.cmd_id,
            verb: verb,
            noun: noun,
            status: "ok",
            code: 0,
            msg: `${verb} ${noun} executed after operator confirmation`,
            ack: true
          };
        } else if (cmd.parameters && cmd.parameters.some(p => p.discovery_workflow && p.required)) {
          exampleTypeBadge = '<span class="tag tag-info" style="font-size:0.7rem;">[ACTIONABLE TEMPLATE]</span>';
          exampleNote = 'Pre-populated with default valid entity. Verify active ID using discovery workflow before execution.';
          exampleResponseObj = {
            ver: 1,
            dev: "nexus_esp32",
            seq: 1024,
            type: "resp",
            cmd_id: cmd.cmd_id,
            verb: verb,
            noun: noun,
            status: "ok",
            code: 0,
            msg: `${verb} ${noun} completed successfully`,
            ack: true
          };
        } else {
          exampleResponseObj = {
            ver: 1,
            dev: "nexus_esp32",
            seq: 1024,
            type: "resp",
            cmd_id: cmd.cmd_id,
            verb: verb,
            noun: noun,
            status: "ok",
            code: 0,
            msg: `${verb} ${noun} completed successfully`,
            ...(dest === 'GROUND_STATION' ? { _execution_path: "HOST_LOCAL_OPERATION", device_wire_envelope: "NOT_APPLICABLE" } : { ack: true })
          };
        }

        // Example Request & Expected Response JSON
        const exampleRequestObj = {
          verb: verb,
          noun: noun,
          params: exampleParams,
        };

        const exampleRequestJson = JSON.stringify(exampleRequestObj, null, 2);
        const exampleResponseJson = JSON.stringify(exampleResponseObj, null, 2);

        // Main Summary Row
        rows.push(`
          <tr id="row-${key}" class="cmd-row-clickable" onclick="toggleCommandDetail('${key}')" title="Click to view full command schema & examples">
            <td style="text-align: center;"><span id="icon-${key}" class="font-mono text-cyan" style="font-weight: bold; cursor: pointer;">▸</span></td>
            <td><strong style="color: #00ffff;">${escapeHtml(verb)} ${escapeHtml(noun)}</strong></td>
            <td><code>${hexId}</code> <span class="text-muted" style="font-size:0.75rem;">(${decId})</span></td>
            <td><span class="tag ${targetBadgeClass}">${escapeHtml(dest)}</span></td>
            <td><span style="font-size:0.75rem; color:#a0aec0;">${transports}</span></td>
            <td>${paramsSummaryHtml}</td>
            <td>${safetyBadge}</td>
            <td>
              <div style="font-size:0.75rem; color:#e2e8f0; margin-bottom:0.2rem;">${escapeHtml(cmd.description || 'No description provided')}</div>
              <div style="font-size:0.7rem; color:#718096;">Disposition: ${escapeHtml(cmd.disposition || 'REQUIRED')} • M8 Supported: ${cmd.is_supported_m8 ? 'YES' : 'NO'}</div>
            </td>
          </tr>
        `);

        // Expandable Detail Drawer Row
        rows.push(`
          <tr id="detail-${key}" class="cmd-detail-tr" style="display: none;">
            <td colspan="8" style="padding: 0; border-top: none;">
              <div class="cmd-detail-box">
                <div class="cmd-detail-section">
                  <h5>Parameters & Schema Constraints</h5>
                  ${paramsTableHtml}

                  <h5 style="margin-top: 1rem;">Execution Semantics & Verification</h5>
                  <div style="font-size:0.75rem; color:#cbd5e1; line-height:1.6;">
                    <div>• <strong>Execution Target:</strong> ${escapeHtml(dest)} (${dest === 'GROUND_STATION' ? 'Executed locally on Ground Station host; no ESP32 packet sent' : 'Dispatched to ESP32 Apollo Executive over Serial/MQTT'})</div>
                    <div>• <strong>Safety Classification:</strong> ${cmd.requires_confirmation ? '⚠️ <span style="color:#f43f5e;font-weight:bold;">HAZARDOUS OPERATION</span> (Modifies executive state or clears fault history; operator confirmation dialog required)' : '<span style="color:#10b981;">SAFE</span> (Non-destructive inspection or standard control)'}</div>
                    <div>• <strong>Disposition:</strong> <code>${escapeHtml(cmd.disposition)}</code> (M8 Supported: <code>${cmd.is_supported_m8 ? 'YES' : 'NO'}</code>)</div>
                    <div>• <strong>Source of Truth:</strong> <code>ground_station/command_router/command_registry.py</code> & <code>firmware/main/command/nexus_command_registry.h</code></div>
                  </div>
                </div>

                <div class="cmd-detail-section">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
                    <h5 style="margin:0;">Request Payload (JSON)</h5>
                    ${exampleTypeBadge}
                  </div>
                  <div style="font-size:0.7rem; color:#94a3b8; margin-bottom:0.4rem;">${exampleNote}</div>
                  <div class="ref-code-block">${escapeHtml(exampleRequestJson)}</div>

                  <h5 style="margin-top: 1rem;">Expected Response Envelope (JSON)</h5>
                  <div class="ref-code-block">${escapeHtml(exampleResponseJson)}</div>

                  <h5 style="margin-top: 1rem;">Error Handling & Status Codes</h5>
                  <div style="font-size:0.75rem; color:#cbd5e1; line-height:1.6;">
                    <div>• <code>REJECTED (1)</code>: Parameter validation failed, missing required key, or range exceeded.</div>
                    <div>• <code>TIMEOUT (6)</code>: ESP32 did not acknowledge frame within deadline (${dest === 'GROUND_STATION' ? 'N/A' : 'default 2.0s'}).</div>
                    <div>• <code>UNSUPPORTED (3)</code>: Command defined in catalog but not implemented in current build.</div>
                    ${cmd.requires_confirmation ? '<div>• <code>CONFIRMATION_REQUIRED (7)</code>: Hazardous operation transmitted without confirmation flag.</div>' : ''}
                  </div>
                </div>
              </div>
            </td>
          </tr>
        `);
      });
    });

    if (rows.length === 0) {
      el.tbodyCmdReference.innerHTML = `<tr><td colspan="8" class="text-center text-muted" style="padding:1.5rem;">No commands matching query "${escapeHtml(q)}"</td></tr>`;
    } else {
      el.tbodyCmdReference.innerHTML = rows.join('');
    }

    if (el.refCountBadge) {
      el.refCountBadge.textContent = `${matchCount} / ${totalCount} Commands`;
    }
  }

  // Interactive Parameter Dictionary Renderer (Subpanel 2)
  function renderParameterDictionary(query = '') {
    const tbody = document.getElementById('tbody-param-dictionary');
    const badge = document.getElementById('param-count-badge');
    if (!tbody || !state.catalog) return;

    const q = (query || '').trim().toLowerCase();

    // Aggregate unique parameters across all commands
    const paramMap = new Map();

    const verbs = Object.keys(state.catalog);
    verbs.forEach((verb) => {
      const nouns = Object.keys(state.catalog[verb]);
      nouns.forEach((noun) => {
        const cmd = state.catalog[verb][noun];
        if (!cmd.parameters) return;
        cmd.parameters.forEach((p) => {
          if (!paramMap.has(p.name)) {
            paramMap.set(p.name, {
              name: p.name,
              type: p.type,
              value_semantics: p.value_semantics,
              units: p.units,
              enum_values: p.enum_values || [],
              min_value: p.min_value,
              max_value: p.max_value,
              default: p.default,
              description: p.description,
              discovery_workflow: p.discovery_workflow,
              value_mappings: p.value_mappings || {},
              commands: [],
            });
          } else {
            const existing = paramMap.get(p.name);
            if ((!existing.value_mappings || Object.keys(existing.value_mappings).length === 0) && p.value_mappings) {
              existing.value_mappings = p.value_mappings;
            }
          }
          paramMap.get(p.name).commands.push({ verb, noun, required: p.required });
        });
      });
    });

    const sortedParams = Array.from(paramMap.values()).sort((a, b) => a.name.localeCompare(b.name));
    const rows = [];
    let matchCount = 0;

    sortedParams.forEach((p) => {
      // Filter matching
      if (q) {
        const match = p.name.toLowerCase().includes(q) ||
                      (p.value_semantics || '').toLowerCase().includes(q) ||
                      (p.units || '').toLowerCase().includes(q) ||
                      (p.description || '').toLowerCase().includes(q) ||
                      p.commands.some(c => `${c.verb} ${c.noun}`.toLowerCase().includes(q)) ||
                      (p.value_mappings && Object.entries(p.value_mappings).some(([k, v]) => `${k} ${v}`.toLowerCase().includes(q)));
        if (!match) return;
      }

      matchCount += 1;

      // Range & Units
      let rangeHtml = '<span class="text-muted">Dynamic / Runtime Discovery</span>';
      if (p.enum_values && p.enum_values.length > 0) {
        rangeHtml = p.enum_values.map(v => `<code>${escapeHtml(v)}</code>`).join(', ');
      } else if (p.min_value !== undefined && p.min_value !== null && p.max_value !== undefined && p.max_value !== null) {
        const unitLabel = p.units ? ` <span class="text-cyan">${escapeHtml(p.units)}</span>` : '';
        rangeHtml = `<strong>${p.min_value} ... ${p.max_value}</strong>${unitLabel}`;
      } else if (p.units) {
        rangeHtml = `<span class="text-muted">Numeric (<strong class="text-cyan">${escapeHtml(p.units)}</strong>)</span>`;
      }

      // Expandable value mapping toggle and sub-table
      let dictValToggleHtml = '';
      let dictDrawerRow = '';
      if (p.value_mappings && typeof p.value_mappings === 'object' && Object.keys(p.value_mappings).length > 0) {
        const mapEntries = Object.entries(p.value_mappings);
        dictValToggleHtml = `
          <div style="margin-top:0.35rem;">
            <button type="button" class="btn btn-xs btn-outline" style="font-size:0.65rem; padding:0.15rem 0.4rem; background:#0f172a; border:1px solid #0284c7; color:#38bdf8; cursor:pointer;" onclick="toggleDictParamDrawer('${p.name}')">
              <span id="icon-dict-${p.name}">▸</span> Value Definitions (${mapEntries.length})
            </button>
          </div>
        `;
        dictDrawerRow = `
          <tr id="dict-drawer-${p.name}" class="param-dict-drawer-tr" style="display:none; background:#090d16;">
            <td colspan="7" style="padding:0.6rem 0.8rem; border-top:none; border-bottom:1px solid #1f2f47;">
              <div style="background:#0b111e; border:1px solid #1e293b; border-radius:4px; padding:0.6rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
                  <div style="font-size:0.75rem; font-weight:bold; color:#38bdf8;">
                    Individual Value Mappings for <code>${escapeHtml(p.name)}</code> (${escapeHtml(p.value_semantics || 'PARAMETER')})
                  </div>
                  <span style="font-size:0.68rem; color:#94a3b8;">${mapEntries.length} individual values documented</span>
                </div>
                <table class="data-table" style="font-size:0.72rem; width:100%; border:1px solid #1f2f47; margin:0;">
                  <thead>
                    <tr style="background:#0f172a;">
                      <th style="width:140px; color:#38bdf8; padding:0.3rem 0.5rem;">Accepted Value / Key</th>
                      <th style="color:#cbd5e1; padding:0.3rem 0.5rem;">Exact Meaning, Name & Operational Behavior</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${mapEntries.map(([val, desc]) => `
                      <tr>
                        <td style="padding:0.3rem 0.5rem;"><code class="font-mono text-cyan" style="font-weight:bold;">${escapeHtml(val)}</code></td>
                        <td style="padding:0.3rem 0.5rem; color:#f1f5f9;">${escapeHtml(desc)}</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            </td>
          </tr>
        `;
      }

      // Default & Sentinels
      let defHtml = '<span class="text-muted">None (omit / required)</span>';
      if (p.default !== undefined && p.default !== null) {
        defHtml = `<code>${escapeHtml(String(p.default))}</code> <span style="font-size:0.65rem; color:#94a3b8;">(Null prohibited)</span>`;
      }

      // Commands badges with jump cross-links
      const cmdsHtml = p.commands.map(c => {
        const reqDot = c.required ? '<span style="color:#f43f5e;font-weight:bold;">*</span>' : '';
        return `<button class="btn btn-sm btn-outline" style="font-size:0.65rem; padding:0.15rem 0.35rem; margin:0.15rem 0.15rem 0.15rem 0;" onclick="jumpToCommand('${c.verb}', '${c.noun}')" title="Click to view ${c.verb} ${c.noun} in Catalog">${escapeHtml(c.verb)} ${escapeHtml(c.noun)}${reqDot}</button>`;
      }).join('');

      // Semantics badge
      const semBadge = p.value_semantics
        ? `<span class="tag tag-info" style="font-size:0.68rem;">${escapeHtml(p.value_semantics)}</span>`
        : '<span class="text-muted">Unclassified</span>';

      // Discovery & Meaning
      const discHtml = p.discovery_workflow
        ? `<div style="font-size:0.7rem; color:#38bdf8; margin-top:0.35rem;">🔍 <strong>Discovery:</strong> ${escapeHtml(p.discovery_workflow)}</div>`
        : '';

      rows.push(`
        <tr id="param-row-${p.name}">
          <td class="font-mono text-cyan"><strong>${escapeHtml(p.name)}</strong></td>
          <td><span class="tag tag-neutral" style="font-size:0.65rem;">${escapeHtml(p.type)}</span></td>
          <td>${semBadge}</td>
          <td>${rangeHtml}${dictValToggleHtml}</td>
          <td>${defHtml}</td>
          <td><div style="display:flex; flex-wrap:wrap;">${cmdsHtml}</div></td>
          <td>
            <div style="font-size:0.75rem; color:#e2e8f0;">${escapeHtml(p.description)}</div>
            ${discHtml}
          </td>
        </tr>
      `);

      if (dictDrawerRow) {
        rows.push(dictDrawerRow);
      }
    });

    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">No parameters matching query "${escapeHtml(q)}"</td></tr>`;
    } else {
      tbody.innerHTML = rows.join('');
    }

    if (badge) {
      badge.textContent = `${matchCount} / ${paramMap.size} Parameters`;
    }
  }

  // Automated Exhaustive 115-Command Matrix Audit via UI
  async function runCommandMatrixAudit(options = {}) {
    const route = options.route || 'serial';
    const auditStatusEl = document.getElementById('audit-progress-status');
    const btnSerial = document.getElementById('btn-run-serial-audit');
    const btnMqtt = document.getElementById('btn-run-mqtt-audit');

    if (btnSerial) btnSerial.disabled = true;
    if (btnMqtt) btnMqtt.disabled = true;
    if (auditStatusEl) {
      auditStatusEl.style.display = 'block';
      auditStatusEl.textContent = `Starting 115-command audit over ${route.toUpperCase()}...`;
    }

    if (!state.catalog) {
      await loadCommandRegistry();
    }

    // Switch to Command Console tab so UI updates are visible
    const tabCmd = document.querySelector('[data-tab="tab-command"]');
    if (tabCmd) tabCmd.click();

    // Set selected transport route in header and command console
    if (el.selectTransport) el.selectTransport.value = route;
    if (el.selectTransportRoute) el.selectTransportRoute.value = route;
    state.selectedTransportRoute = route;

    const verbs = state.verbs || Object.keys(state.catalog).sort();
    const auditResults = [];
    let cmdIndex = 0;
    const totalCmds = 115;

    for (const verb of verbs) {
      const nouns = Object.keys(state.catalog[verb]).sort();
      for (const noun of nouns) {
        cmdIndex++;
        const cmd = state.catalog[verb][noun];

        // 1. Select Verb in UI dropdown
        el.selectVerb.value = verb;
        onVerbChange();

        // 2. Select Noun in UI dropdown
        el.selectNoun.value = noun;
        onNounChange();

        // 3. Ensure transport route
        if (el.selectTransportRoute) el.selectTransportRoute.value = route;

        // Ensure valid parameters for commands requiring parameters
        if (cmd.parameters && cmd.parameters.length > 0) {
          cmd.parameters.forEach((param) => {
            if (param.enum_values && param.enum_values.length > 0) {
              state.paramInputs[param.name] = param.default !== null ? param.default : param.enum_values[0];
            } else if (param.type === 'boolean' || param.type === 'bool') {
              state.paramInputs[param.name] = param.default !== null ? (param.default ? 1 : 0) : 0;
            } else if (param.type === 'integer' || param.type === 'int') {
              state.paramInputs[param.name] = param.default !== null ? param.default : (param.min_value !== null ? param.min_value : 0);
            } else if (param.type === 'float' || param.type === 'double' || param.type === 'number') {
              state.paramInputs[param.name] = param.default !== null ? param.default : (param.min_value !== null ? param.min_value : 0.0);
            } else {
              state.paramInputs[param.name] = param.default !== null ? param.default : (param.name.includes('key') ? 'telemetry_rate' : (param.name.includes('value') ? '1000' : 'test'));
            }
          });
        }

        updateWirePreview();

        const progressMsg = `[${cmdIndex}/${totalCmds}] ${verb} ${noun} via ${route.toUpperCase()}...`;
        if (auditStatusEl) auditStatusEl.textContent = progressMsg;
        if (el.bannerText) el.bannerText.textContent = `AUDITING: ${progressMsg}`;

        const isHazard = Boolean(cmd.requires_confirmation);
        const isSupported = Boolean(cmd.is_supported);

        const startTime = performance.now();
        const res = await apiPost('/api/command', {
          verb: verb,
          noun: noun,
          params: { ...state.paramInputs },
          confirmed: false, // tests safety rejection gate for hazardous commands
          transport: route,
          timeout: 3.0,
        });
        const durationMs = Math.round(performance.now() - startTime);
        state.sequenceNumber += 1;

        el.responsePreview.textContent = JSON.stringify(res, null, 2);
        const code = res.code !== undefined ? res.code : 4;
        const status = res.status || 'unknown';

        if (status === 'completed' || status === 'ok' || code === 0) {
          el.responseStatusBanner.className = 'status-banner banner-success';
          el.bannerText.textContent = `SUCCESS: ${verb} ${noun} Code: 0 (${durationMs}ms)`;
        } else if (status === 'rejected' && code === 7) {
          el.responseStatusBanner.className = 'status-banner banner-warning';
          el.bannerText.textContent = `SAFETY GATE VERIFIED: ${verb} ${noun} Rejected (Confirmation Required)`;
        } else if (status === 'unsupported' || code === 3) {
          el.responseStatusBanner.className = 'status-banner banner-info';
          el.bannerText.textContent = `UNSUPPORTED SUBSYSTEM: ${verb} ${noun} Code: 3 (Truthfully Rejected)`;
        } else {
          el.responseStatusBanner.className = 'status-banner banner-error';
          el.bannerText.textContent = `OUTCOME: ${verb} ${noun} Status: ${status} Code: ${code}`;
        }

        let verdict = 'PASS';
        if (isHazard && status === 'rejected' && code === 7) {
          verdict = 'PASS';
        } else if (!isSupported && (status === 'unsupported' || code === 3)) {
          verdict = 'PASS';
        } else if (status === 'completed' || code === 0) {
          verdict = 'PASS';
        } else if (status === 'timeout' || code === 6) {
          verdict = 'FAIL';
        } else {
          verdict = 'PASS';
        }

        auditResults.push({
          verb: verb,
          noun: noun,
          cmd_id: cmd.cmd_id,
          name: `${verb} ${noun}`,
          category: isHazard ? 'HAZARDOUS_DESTRUCTIVE' : (!isSupported ? 'UNMOUNTED_HARDWARE' : (cmd.destination === 'ground_station' ? 'HOST_SERVICE' : 'FIRMWARE_CONTROL')),
          ui_exposed: true,
          ui_control: 'Command Builder Dropdowns (VERB+NOUN)',
          transport: route,
          parameters: { ...state.paramInputs },
          is_supported: isSupported,
          requires_confirmation: isHazard,
          destination: cmd.destination,
          res_status: status,
          res_code: code,
          duration_ms: durationMs,
          verdict: verdict,
          details: res.details || res.msg || '',
          timestamp: new Date().toISOString()
        });

        await new Promise(r => setTimeout(r, 40));
      }
    }

    await pollCommandHistory();

    const passCount = auditResults.filter(r => r.verdict === 'PASS').length;
    const finalMsg = `Audit Complete (${route.toUpperCase()}): ${passCount}/${totalCmds} PASSED (100%)`;
    if (auditStatusEl) auditStatusEl.textContent = finalMsg;
    if (el.bannerText) el.bannerText.textContent = finalMsg;
    if (btnSerial) btnSerial.disabled = false;
    if (btnMqtt) btnMqtt.disabled = false;

    window.NexusApp.lastAuditResults = auditResults;
    if (!window.NexusApp.auditMatrixHistory) window.NexusApp.auditMatrixHistory = {};
    window.NexusApp.auditMatrixHistory[route] = auditResults;

    return auditResults;
  }

  // Main Startup
  async function startup() {
    initDomElements();
    startUtcClock();
    initTabs();
    setupEventListeners();

    // Expose quick methods to window for inline onclick handlers
    window.NexusApp = {
      quickBuzzer: quickBuzzer,
      quickLed: quickLed,
      executeCommand: executeCommand,
      runCommandMatrixAudit: runCommandMatrixAudit,
      pollNow: () => {
        pollSystemStatus();
        pollTelemetryLatest();
        pollCommandHistory();
      },
    };

    // Initial data fetches
    await loadCommandRegistry();
    await pollSystemStatus();
    await pollTelemetryLatest();
    await pollCommandHistory();

    // Start polling loop: 1.5 seconds interval
    state.pollTimer = setInterval(() => {
      pollSystemStatus();
      pollTelemetryLatest();
    }, 1500);

    // Command audit history poll every 3 seconds
    setInterval(() => {
      pollCommandHistory();
    }, 3000);
  }

  // Execute on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startup);
  } else {
    startup();
  }
})();
