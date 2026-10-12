/**
 * Edge Device Simulator - Web UI
 * Polls FastAPI REST endpoints to display live Modbus TCP register states.
 * Supports dynamic addition and removal of simulated devices.
 * Formats stream telemetry as: {"path1": [[value1], [value2]], ..., "url": "", "key": ""}
 */

// Global State
let pollInterval = null;
let syncInterval = null;
let isSyncing = false;
let activeDevices = []; // List of all device objects returned from API
let streamBuffer = {}; // path -> array of [value]
let userCustomPaths = {}; // slave_id -> custom path edited by user

// DOM Elements
const wasmStatusDot = document.getElementById("wasm-status-dot");
const wasmStatusText = document.getElementById("wasm-status-text");
const devicesContainer = document.getElementById("devices-container");

// Gateway DOM
const elGatewayId = document.getElementById("gateway-id");
const elEndpoint = document.getElementById("endpoint-url");
const elPlatformKey = document.getElementById("platform-key");
const elSyncIntervalSec = document.getElementById("sync-interval-sec");
const elSyncPresetSelect = document.getElementById("sync-preset-select");
const btnSyncToggle = document.getElementById("btn-sync-toggle");
const elJsonDisplay = document.getElementById("json-display");
const elTimestamp = document.getElementById("payload-timestamp");

// Modal DOM
const btnOpenAddDevice = document.getElementById("btn-open-add-device");
const modalAddDevice = document.getElementById("add-device-modal");
const btnCloseModal = document.getElementById("btn-close-modal");
const btnCancelAddDevice = document.getElementById("btn-cancel-add-device");
const formAddDevice = document.getElementById("form-add-device");
const selectNewType = document.getElementById("new-device-type");
const inputNewSlave = document.getElementById("new-device-slave");
const inputNewPath = document.getElementById("new-device-path");

/**
 * Helper: Clean and format base path
 */
function formatBasePath(rawInput, fallback) {
  let path = (rawInput || "").trim();
  if (!path) path = fallback;
  if (!path.startsWith("/")) path = "/" + path;
  return path.replace(/\/+$/, "");
}

function getSyncPeriodSeconds() {
  const val = parseInt(elSyncIntervalSec ? elSyncIntervalSec.value : "5", 10);
  return isNaN(val) || val < 1 ? 5 : val;
}

/**
 * Step 1: Poll live telemetry from FastAPI backend (/api/devices)
 */
async function pollTelemetry() {
  try {
    const res = await fetch("/api/devices");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    // Mark connection status as active
    wasmStatusDot.classList.add("ready");
    wasmStatusDot.style.backgroundColor = "";
    wasmStatusText.innerText = "Connected to Modbus TCP Server (127.0.0.1:5020)";

    activeDevices = data.devices || [];

    // Sync device cards in UI
    syncDeviceCards(activeDevices);

    // Buffer sample points and update JSON stream preview
    recordAllTelemetrySamples(activeDevices);
    updateJsonPreview();

  } catch (err) {
    wasmStatusDot.classList.remove("ready");
    wasmStatusDot.style.backgroundColor = "#ef4444";
    wasmStatusText.innerText = "Simulator Offline (Retrying...)";
  }
}

/**
 * Manage Dynamic Device Cards
 */
function syncDeviceCards(devices) {
  const currentSlaveIds = new Set(devices.map((d) => d.slave_id));

  // Remove cards for deleted devices
  const existingCards = devicesContainer.querySelectorAll(".device-card[data-slave]");
  existingCards.forEach((card) => {
    const sid = parseInt(card.dataset.slave, 10);
    if (!currentSlaveIds.has(sid)) {
      card.remove();
    }
  });

  // Ensure card exists and update values for each device
  devices.forEach((dev) => {
    let card = document.getElementById(`card-dev-${dev.slave_id}`);
    if (!card) {
      if (dev.device_type === "energy_meter") {
        card = createMeterCard(dev);
      } else {
        card = createHvacCard(dev);
      }
      devicesContainer.appendChild(card);
    }
    // Update live metrics on card
    if (dev.device_type === "energy_meter") {
      updateMeterCard(dev);
    } else {
      updateHvacCard(dev);
    }
  });
}

function createMeterCard(dev) {
  const sid = dev.slave_id;
  const initialPath = userCustomPaths[sid] || dev.stream_path || `/gateway-01/device-${String(sid).padStart(2, "0")}`;

  const card = document.createElement("section");
  card.className = "device-card";
  card.id = `card-dev-${sid}`;
  card.dataset.slave = sid;
  card.innerHTML = `
    <div class="card-header">
      <div class="title-with-led">
        <span class="led led-green"></span>
        <h2>⚡ Energy Meter #${sid}</h2>
      </div>
      <div class="header-badges">
        <span class="device-id-badge">Slave ID: ${sid}</span>
        <button class="btn-delete-device" data-slave="${sid}" title="Delete Device">✕</button>
      </div>
    </div>
    <div class="device-path-bar">
      <label>Point Path:</label>
      <div class="path-input-wrap">
        <span class="path-icon">📡</span>
        <input type="text" class="device-path-input" data-slave="${sid}" value="${initialPath}">
      </div>
    </div>
    <div class="meter-faceplate">
      <div class="lcd-screen">
        <div class="lcd-row primary-metric">
          <span class="lcd-label">ACTIVE POWER</span>
          <span class="lcd-value" id="val-power-${sid}">--.--</span>
          <span class="lcd-unit">kW</span>
        </div>
        <div class="lcd-subgrid">
          <div class="lcd-subitem">
            <span class="lcd-label">VOLTAGE</span>
            <span class="lcd-value-small" id="val-voltage-${sid}">---.-</span>
            <span class="lcd-unit-small">V</span>
          </div>
          <div class="lcd-subitem">
            <span class="lcd-label">CURRENT</span>
            <span class="lcd-value-small" id="val-current-${sid}">--.--</span>
            <span class="lcd-unit-small">A</span>
          </div>
          <div class="lcd-subitem">
            <span class="lcd-label">FREQUENCY</span>
            <span class="lcd-value-small" id="val-freq-${sid}">--.--</span>
            <span class="lcd-unit-small">Hz</span>
          </div>
        </div>
        <div class="odometer-container">
          <span class="lcd-label">TOTAL ACCUMULATED ENERGY</span>
          <div class="odometer-display" id="val-kwh-${sid}">00000.000</div>
          <span class="lcd-unit">kWh</span>
        </div>
      </div>
      <div class="alert-box" id="meter-alert-${sid}" style="display: none;">
        ⚠️ Overvoltage Threshold Exceeded (> 231.5 V)
      </div>
    </div>
  `;
  attachCommonCardListeners(card, sid);
  return card;
}

function createHvacCard(dev) {
  const sid = dev.slave_id;
  const initialPath = userCustomPaths[sid] || dev.stream_path || `/gateway-01/device-${String(sid).padStart(2, "0")}`;

  const card = document.createElement("section");
  card.className = "device-card";
  card.id = `card-dev-${sid}`;
  card.dataset.slave = sid;
  card.innerHTML = `
    <div class="card-header">
      <div class="title-with-led">
        <span class="led led-blue"></span>
        <h2>❄️ HVAC Thermostat #${sid}</h2>
      </div>
      <div class="header-badges">
        <span class="device-id-badge">Slave ID: ${sid}</span>
        <button class="btn-delete-device" data-slave="${sid}" title="Delete Device">✕</button>
      </div>
    </div>
    <div class="device-path-bar">
      <label>Point Path:</label>
      <div class="path-input-wrap">
        <span class="path-icon">📡</span>
        <input type="text" class="device-path-input" data-slave="${sid}" value="${initialPath}">
      </div>
    </div>
    <div class="hvac-faceplate">
      <div class="thermostat-dial">
        <div class="dial-inner">
          <span class="thermostat-label">ROOM TEMPERATURE</span>
          <div class="temperature-display">
            <span id="val-temp-${sid}">--.-</span><span class="deg-sym">°C</span>
          </div>
          <div class="setpoint-tag">
            Target: <span id="val-target-${sid}">22.0</span> °C
          </div>
          <div class="hvac-state-badge" id="hvac-status-badge-${sid}">
            <span class="fan-icon" id="fan-icon-${sid}">🌀</span>
            <span id="hvac-mode-text-${sid}">HEATING</span>
          </div>
        </div>
      </div>
      <div class="hvac-controls">
        <div class="control-row">
          <span class="control-label">Fan Relay (Coil 0):</span>
          <label class="toggle-switch">
            <input type="checkbox" id="fan-toggle-${sid}" data-slave="${sid}">
            <span class="slider"></span>
          </label>
          <span class="toggle-status" id="fan-toggle-label-${sid}">OFF</span>
        </div>
        <div class="control-row setpoint-adjuster">
          <span class="control-label">Target Setpoint:</span>
          <div class="btn-group">
            <button class="btn btn-secondary btn-temp-down" data-slave="${sid}">▼ -1°C</button>
            <button class="btn btn-secondary btn-temp-up" data-slave="${sid}">▲ +1°C</button>
          </div>
        </div>
      </div>
      <div class="alert-box" id="hvac-alert-${sid}" style="display: none;">
        🔥 Temperature High Alert (> 32°C)!
      </div>
    </div>
  `;
  attachCommonCardListeners(card, sid);
  attachHvacCardListeners(card, sid);
  return card;
}

function attachCommonCardListeners(card, sid) {
  // Delete button
  const btnDelete = card.querySelector(".btn-delete-device");
  if (btnDelete) {
    btnDelete.addEventListener("click", () => deleteDevice(sid));
  }

  // Point path input
  const inputPath = card.querySelector(".device-path-input");
  if (inputPath) {
    inputPath.addEventListener("input", (e) => {
      userCustomPaths[sid] = e.target.value;
      streamBuffer = {}; // reset buffer keys on path edit
      updateJsonPreview();
    });
    inputPath.addEventListener("change", (e) => {
      const cleaned = formatBasePath(e.target.value, `/gateway-01/device-${sid}`);
      e.target.value = cleaned;
      userCustomPaths[sid] = cleaned;
      saveDevicePath(sid, cleaned);
    });
  }
}

function attachHvacCardListeners(card, sid) {
  // Fan toggle
  const fanToggle = card.querySelector(`#fan-toggle-${sid}`);
  const fanLabel = card.querySelector(`#fan-toggle-label-${sid}`);
  if (fanToggle) {
    fanToggle.addEventListener("change", async (e) => {
      const isChecked = e.target.checked;
      fanLabel.innerText = isChecked ? "ON" : "OFF";
      fanLabel.style.color = isChecked ? "#22c55e" : "#8b949e";
      try {
        await fetch("/api/hvac/fan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slave_id: sid, fan_on: isChecked }),
        });
        pollTelemetry();
      } catch (err) {
        console.error("Failed to set fan coil:", err);
      }
    });
  }

  // Setpoint buttons
  const btnUp = card.querySelector(".btn-temp-up");
  const btnDown = card.querySelector(".btn-temp-down");
  const elTarget = card.querySelector(`#val-target-${sid}`);

  if (btnUp) {
    btnUp.addEventListener("click", async () => {
      const current = parseFloat(elTarget.innerText) || 22.0;
      const target = current + 1.0;
      try {
        await fetch("/api/hvac/setpoint", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slave_id: sid, target_setpoint: target }),
        });
        elTarget.innerText = target.toFixed(1);
        pollTelemetry();
      } catch (err) {
        console.error("Failed to set target setpoint:", err);
      }
    });
  }

  if (btnDown) {
    btnDown.addEventListener("click", async () => {
      const current = parseFloat(elTarget.innerText) || 22.0;
      const target = Math.max(16.0, current - 1.0);
      try {
        await fetch("/api/hvac/setpoint", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slave_id: sid, target_setpoint: target }),
        });
        elTarget.innerText = target.toFixed(1);
        pollTelemetry();
      } catch (err) {
        console.error("Failed to set target setpoint:", err);
      }
    });
  }
}

function updateMeterCard(dev) {
  const sid = dev.slave_id;
  const m = dev.readings || {};

  const elPower = document.getElementById(`val-power-${sid}`);
  const elVoltage = document.getElementById(`val-voltage-${sid}`);
  const elCurrent = document.getElementById(`val-current-${sid}`);
  const elFreq = document.getElementById(`val-freq-${sid}`);
  const elKwh = document.getElementById(`val-kwh-${sid}`);
  const meterAlert = document.getElementById(`meter-alert-${sid}`);

  if (elPower) elPower.innerText = Number(m.power_kw || 0).toFixed(2);
  if (elVoltage) elVoltage.innerText = Number(m.voltage || 0).toFixed(1);
  if (elCurrent) elCurrent.innerText = Number(m.current_a || 0).toFixed(2);
  if (elFreq) elFreq.innerText = Number(m.freq_hz || 0).toFixed(2);
  if (elKwh) elKwh.innerText = Number(m.total_kwh || 0).toFixed(3).padStart(9, "0");

  if (meterAlert) {
    meterAlert.style.display = m.voltage > 231.5 ? "block" : "none";
  }
}

function updateHvacCard(dev) {
  const sid = dev.slave_id;
  const h = dev.readings || {};

  const elTemp = document.getElementById(`val-temp-${sid}`);
  const elTarget = document.getElementById(`val-target-${sid}`);
  const fanIcon = document.getElementById(`fan-icon-${sid}`);
  const statusBadge = document.getElementById(`hvac-status-badge-${sid}`);
  const modeText = document.getElementById(`hvac-mode-text-${sid}`);
  const fanToggle = document.getElementById(`fan-toggle-${sid}`);
  const fanLabel = document.getElementById(`fan-toggle-label-${sid}`);
  const hvacAlert = document.getElementById(`hvac-alert-${sid}`);

  const isFanOn = Boolean(h.fan_relay);
  const temp = Number(h.temperature || 28.0);
  const target = Number(h.target_setpoint || 22.0);

  if (elTemp) elTemp.innerText = temp.toFixed(1);
  if (elTarget) elTarget.innerText = target.toFixed(1);

  if (fanToggle && document.activeElement !== fanToggle) {
    fanToggle.checked = isFanOn;
    if (fanLabel) {
      fanLabel.innerText = isFanOn ? "ON" : "OFF";
      fanLabel.style.color = isFanOn ? "#22c55e" : "#8b949e";
    }
  }

  if (fanIcon && statusBadge && modeText) {
    if (isFanOn) {
      fanIcon.classList.add("spinning");
      statusBadge.classList.remove("heating");
      modeText.innerText = "COOLING";
    } else {
      fanIcon.classList.remove("spinning");
      statusBadge.classList.add("heating");
      modeText.innerText = "HEATING";
    }
  }

  if (hvacAlert) {
    hvacAlert.style.display = temp > 32.0 ? "block" : "none";
  }
}

/**
 * Helper: Extract stream points dictionary for a device
 */
function getDeviceStreamPoints(dev) {
  const sid = dev.slave_id;
  const pathInput = document.querySelector(`.device-path-input[data-slave="${sid}"]`);
  const basePath = formatBasePath(
    pathInput ? pathInput.value : (userCustomPaths[sid] || dev.stream_path),
    `/gateway-01/device-${sid}`
  );

  const r = dev.readings || {};
  if (dev.device_type === "energy_meter") {
    return {
      [`${basePath}/Voltage`]: Number(r.voltage || 0),
      [`${basePath}/ActivePower`]: Number(r.power_kw || 0),
      [`${basePath}/Current`]: Number(r.current_a || 0),
      [`${basePath}/Frequency`]: Number(r.freq_hz || 0),
      [`${basePath}/TotalEnergy`]: Number(r.total_kwh || 0),
    };
  } else {
    return {
      [`${basePath}/Temperature`]: Number(r.temperature || 0),
      [`${basePath}/TargetSetpoint`]: Number(r.target_setpoint || 0),
      [`${basePath}/FanRelay`]: Boolean(r.fan_relay),
      [`${basePath}/Mode`]: r.mode || (r.fan_relay ? "COOLING" : "HEATING"),
    };
  }
}

/**
 * Buffer latest readings into stream sequences: {"path1": [[val1], [val2], ...]}
 */
function recordAllTelemetrySamples(devices) {
  const syncSec = getSyncPeriodSeconds();
  const maxBufferSize = Math.max(120, syncSec * 2);

  devices.forEach((dev) => {
    const points = getDeviceStreamPoints(dev);
    for (const [p, val] of Object.entries(points)) {
      if (!streamBuffer[p]) {
        streamBuffer[p] = [];
      }
      streamBuffer[p].push([val]);
      if (streamBuffer[p].length > maxBufferSize) {
        streamBuffer[p].shift();
      }
    }
  });
}

/**
 * Build the single-second packet for live preview:
 * {"path1": [[current_value]], ..., "url": "", "key": ""}
 */
function buildCurrentSecondPacket() {
  const payload = {};
  activeDevices.forEach((dev) => {
    const points = getDeviceStreamPoints(dev);
    for (const [p, val] of Object.entries(points)) {
      payload[p] = [[val]];
    }
  });
  payload["url"] = elEndpoint ? elEndpoint.value.trim() : "";
  payload["key"] = elPlatformKey ? elPlatformKey.value.trim() : "";
  return payload;
}

/**
 * Build batch payload across sync period:
 * {"path1": [[value1], [value2], ...], ..., "url": "", "key": ""}
 */
function buildBatchSyncPayload() {
  const payload = {};
  const hasBuffered = Object.keys(streamBuffer).length > 0;
  if (hasBuffered) {
    for (const [path, values] of Object.entries(streamBuffer)) {
      payload[path] = values;
    }
  } else {
    return buildCurrentSecondPacket();
  }
  payload["url"] = elEndpoint ? elEndpoint.value.trim() : "";
  payload["key"] = elPlatformKey ? elPlatformKey.value.trim() : "";
  return payload;
}

// Backward compatibility alias
function buildPayload() {
  return buildCurrentSecondPacket();
}

/**
 * Display only the current second packet in the live preview box.
 */
function updateJsonPreview() {
  const now = new Date();
  if (elTimestamp) elTimestamp.innerText = now.toTimeString().split(" ")[0];
  const payload = buildCurrentSecondPacket();
  if (elJsonDisplay) elJsonDisplay.innerText = JSON.stringify(payload, null, 2);
  return payload;
}

/**
 * Device Path and Management API
 */
async function saveDevicePath(slaveId, path) {
  try {
    await fetch("/api/devices/path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slave_id: slaveId, stream_path: path }),
    });
  } catch (err) {
    console.warn(`Failed to update path for slave ${slaveId}:`, err);
  }
}

async function deleteDevice(slaveId) {
  if (activeDevices.length <= 1) {
    alert("At least one simulated device must remain active.");
    return;
  }
  if (!confirm(`Are you sure you want to remove Device Slave ID ${slaveId}?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/devices/${slaveId}`, { method: "DELETE" });
    if (res.ok) {
      streamBuffer = {}; // clear buffer
      pollTelemetry();
    } else {
      const err = await res.json();
      alert(`Error deleting device: ${err.detail || err.message}`);
    }
  } catch (err) {
    alert(`Failed to delete device: ${err.message}`);
  }
}

/**
 * Add Device Modal Controls
 */
function getNextSlaveId() {
  const existing = new Set(activeDevices.map((d) => d.slave_id));
  for (let sid = 1; sid <= 247; sid++) {
    if (!existing.has(sid)) return sid;
  }
  return 3;
}

function updateSuggestedModalFields() {
  const nextId = getNextSlaveId();
  inputNewSlave.value = nextId;
  const type = selectNewType.value;
  const prefix = type === "energy_meter" ? "meter" : "hvac";
  inputNewPath.value = `/gateway-01/${prefix}-${String(nextId).padStart(2, "0")}`;
}

btnOpenAddDevice.addEventListener("click", () => {
  updateSuggestedModalFields();
  modalAddDevice.style.display = "flex";
});

btnCloseModal.addEventListener("click", () => {
  modalAddDevice.style.display = "none";
});

btnCancelAddDevice.addEventListener("click", () => {
  modalAddDevice.style.display = "none";
});

selectNewType.addEventListener("change", () => {
  updateSuggestedModalFields();
});

formAddDevice.addEventListener("submit", async (e) => {
  e.preventDefault();
  const type = selectNewType.value;
  const sid = parseInt(inputNewSlave.value, 10);
  const path = inputNewPath.value.trim();

  try {
    const res = await fetch("/api/devices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_type: type,
        slave_id: sid,
        stream_path: path,
      }),
    });

    if (res.ok) {
      modalAddDevice.style.display = "none";
      streamBuffer = {}; // reset buffer
      pollTelemetry();
    } else {
      const err = await res.json();
      alert(`Error adding device: ${err.detail || err.message}`);
    }
  } catch (err) {
    alert(`Failed to add device: ${err.message}`);
  }
});

// Sync preset selector listener
if (elSyncPresetSelect) {
  elSyncPresetSelect.addEventListener("change", (e) => {
    if (e.target.value) {
      elSyncIntervalSec.value = e.target.value;
      elSyncPresetSelect.selectedIndex = 0; // Reset placeholder
    }
  });
}

// URL & Key input listeners
if (elEndpoint) {
  elEndpoint.addEventListener("input", updateJsonPreview);
}
if (elPlatformKey) {
  elPlatformKey.addEventListener("input", updateJsonPreview);
}

/**
 * HTTPS Cloud Platform Sync
 */
btnSyncToggle.addEventListener("click", () => {
  if (!isSyncing) {
    const endpoint = elEndpoint.value.trim();
    if (!endpoint) {
      alert("Please enter your platform's HTTPS target URL first.");
      elEndpoint.focus();
      return;
    }

    const intervalSec = getSyncPeriodSeconds();
    const intervalMs = intervalSec * 1000;

    isSyncing = true;
    btnSyncToggle.innerText = `Stop Sync (${intervalSec}s)`;
    btnSyncToggle.classList.add("active");

    syncInterval = setInterval(() => {
      sendTelemetryToPlatform(endpoint);
    }, intervalMs);

  } else {
    isSyncing = false;
    btnSyncToggle.innerText = "Start Platform Sync";
    btnSyncToggle.classList.remove("active");
    clearInterval(syncInterval);
    syncInterval = null;
  }
});

async function sendTelemetryToPlatform(endpoint) {
  try {
    const payload = buildBatchSyncPayload();
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.log(`[Platform Sync] Status ${res.status}:`, await res.text());
    streamBuffer = {}; // Flush buffer after batch sync
  } catch (err) {
    console.warn("[Platform Sync] Failed to send payload (CORS or network error):", err.message);
  }
}

// Start polling on page load
window.addEventListener("DOMContentLoaded", () => {
  pollTelemetry();
  pollInterval = setInterval(pollTelemetry, 1000);
});
