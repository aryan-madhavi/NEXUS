# NEXUS Mission Control — Full-Site UX/UI, Functional, Responsive & Accessibility Audit & Remediation Report

- **Date:** 2026-10-25
- **Target Application:** NEXUS Mission Control (`http://127.0.0.1:8000`)
- **Platform:** EDU_ROBO V14 • ESP32 Apollo Executive Architecture
- **Viewports Audited:**
  - Desktop: `1440 × 900`
  - Laptop: `1280 × 800`
  - Compact: `1024 × 768`
  - Mobile Stress Test: `390 × 844`
- **Verification Artifacts:**
  - Before Screenshots & Metrics: `docs/validation/ux_audit_screenshots/before/` (`audit_report_before.json`, 72 screenshots)
  - After Screenshots & Metrics: `docs/validation/ux_audit_screenshots/after/` (`audit_report_after.json`, 72 screenshots)

---

## 1. Complete Discovered Page, Route & Component Inventory

Derived from both the static source code (`ground_station/server.py`, `ground_station/static/index.html`, `ground_station/static/styles.css`, `ground_station/static/app.js`, `ground_station/command_router/command_registry.py`) and the live rendered DOM at `http://127.0.0.1:8000`.

### 1.1 HTTP Routes & Entry Points (`ground_station/server.py`)
| Route / Endpoint | Method | Type | Purpose |
| :--- | :--- | :--- | :--- |
| `/` or `/index.html` | `GET` | HTML View | Primary Mission Control single-page console (`ground_station/static/index.html`). |
| `/overview` | `GET` | HTTP 302 Redirect | Redirects to `/#tab-dashboard` (mapped to `Telemetry & Sensors` tab). |
| `/diagnostics` | `GET` | HTTP 302 Redirect | Redirects to `/#tab-services` (`Mission Services` tab). |
| `/styles.css` | `GET` | Static Asset | Apollo-inspired Mission Control design system stylesheet. |
| `/app.js` | `GET` | Static Asset | Mission Control frontend logic, polling, command builder, and reference manual renderers. |
| `/favicon.ico` | `GET` | Static Asset | Favicon handler (`204 No Content` + inline SVG data URI in `index.html`). |
| `/api/status` | `GET` | JSON API | Connection status, active transport, ingestion queue, hardware capability profile, and auxiliary service states. |
| `/api/telemetry/latest` | `GET` | JSON API | Latest environmental sensor sample (`temp`, `hum`, `dht_valid`, `ldr`, `x0`, `x1`, `slot`, `dist`, `uptime_ms`, `free_heap_kb`). |
| `/api/telemetry/history` | `GET` | JSON API | Bounded ring-buffer telemetry history (`?limit=N`). |
| `/api/registry` | `GET` | JSON API | Authoritative 115-command schema catalog grouped across 23 verbs. |
| `/api/commands` | `GET` | JSON API | Chronological command dispatch and response audit trail. |
| `/api/sensors` | `GET` | JSON API | Mounted (5) and unmounted (5) sensor metadata with current readings. |
| `/api/services` | `GET` | JSON API | Auxiliary service registry (Grafana `:3000`, InfluxDB `:8086`, Open WebUI `:8080`, REST Diagnostics `:8000`). |
| `/api/diagnostics` | `GET` | JSON API | Host manager transport metrics, ingestion stats, and command router counters. |
| `/api/incidents` | `GET` | JSON API | Firmware event types (`1..11`), ground station monitoring rules, and active incident records. |
| `/api/export` | `GET` | JSON / CSV | Telemetry history export (`?format=json\|csv&limit=100`). |
| `/api/command` | `POST` | JSON API | Canonical command validation, safety gating, and serial/MQTT/host-local dispatch. |

### 1.2 Global Chrome & Persistent Layout Components
| Component | Selector / ID | Interactive / Dynamic States |
| :--- | :--- | :--- |
| **Mission Header** | `header.mission-header` | Sticky top bar (`z-index: 50`) containing brand insignia, status pills, global transport selector, UTC clock, and refresh button. |
| **Connection Badge** | `#connection-badge`, `#connection-text` | `CONNECTING` / `STANDBY` (`badge-offline`) vs. `CONNECTED` (`badge-online`). |
| **Route Badge** | `#transport-badge`, `#transport-text` | `SCANNING` / `NONE` (`badge-neutral`) vs. `DUAL` / `SERIAL` / `MQTT` (`badge-online`). |
| **Global Transport Selector** | `#select-global-transport` | `auto`, `serial`, `mqtt` (bidirectional sync with `#select-transport-route` in Tab 2). |
| **Node Badge** | `#device-id-text` | Displays active device identifier (`nexus_esp32`). |
| **UTC Clock & Refresh** | `#utc-clock`, `#refresh-all-btn` | Live 1 Hz UTC clock; manual telemetry/status/history refresh trigger with toast feedback. |
| **Quick Telemetry Strip** | `section.quick-telemetry-strip` | 5 live metric chips: `#chip-uptime`, `#chip-heap`, `#chip-queue`, `#chip-cmds`, `#chip-age`. |
| **Primary Tab Bar** | `nav.console-tabs` (`role="tablist"`) | 6 top-level tab buttons (`#btn-tab-telemetry`, `#btn-tab-command`, `#btn-tab-hardware`, `#btn-tab-history`, `#btn-tab-services`, `#btn-tab-reference`). |
| **Hazardous Confirmation Modal** | `#confirmation-modal` (`role="dialog"`) | Hidden vs. active overlay; `#modal-warning-text`, `#modal-command-summary`, `#modal-confirm-check` checkbox gating `#modal-btn-confirm` (`Authorize & Transmit`), `#modal-btn-cancel`, Escape key & backdrop click dismissal. |
| **Toast Notification Container** | `#nexus-toast-container` | Dynamically injected bottom-right toast stack (`info`, `success`, `warn`, `error`) with 3.5s auto-dismiss. |
| **Mission Footer** | `footer.mission-footer` | Platform metadata and protocol version summary. |

### 1.3 Top-Level Tabs, Subtabs & Nested Interactive Components
1. **Tab 1 — Telemetry & Sensors (`#tab-telemetry`):**
   - 7 Sensor Cards (`#card-temp`, `#card-hum`, `#card-ldr`, `#card-x0`, `#card-x1` unmounted Hall IC2, `#card-slot`, `#card-dist`) with live values, units, validity badges (`VALID`/`STALE`, `BEAM CLEAR`/`BEAM INTERRUPTED`, `IN RANGE`/`OUT OF RANGE`, `NOT INSTALLED`), and nominal range labels.
   - 1 Mounted Actuators Quick Card (`.actuation-quick-card`) with 11 quick-actuation buttons (`Buzzer 200ms/500ms/Off`, `LED 1..4 ON/OFF`).
2. **Tab 2 — Command Console (`#tab-command`):**
   - Command Specification Card (`.command-builder-card`): `#select-verb` (23 verbs), `#select-noun` (enabled on verb selection), `#command-meta-bar` (`#meta-cmd-id`, `#meta-destination`, `#meta-disposition`, `#meta-supported`), `#command-description`, `#parameters-container` / `#dynamic-fields-area` (dynamically generated `<select>` for enums/booleans, `<input type="number">` for int/float, `<input type="text">` for strings, plus `.param-helper-text`), `#select-transport-route`, `#btn-dispatch-cmd`, and Exhaustive 115-Command Matrix Audit runner (`#btn-run-serial-audit`, `#btn-run-mqtt-audit`, `#audit-progress-status`).
   - Preview & Response Card (`.command-preview-card`): `#wire-preview` (`FIRMWARE_DEVICE_DISPATCH` vs. `HOST_LOCAL_OPERATION`), `#response-status-banner` (`banner-idle`, `banner-running`, `banner-success`, `banner-warn`, `banner-info`, `banner-error`), and `#response-preview`.
3. **Tab 3 — Hardware Inventory (`#tab-hardware`):**
   - Split 2-column grid (`.hardware-split-grid`): Mounted & Verified Modules table (`#table-mounted-hw` / `#tbody-mounted-hw`, 11 rows) and Unmounted Modules table (`#table-unmounted-hw` / `#tbody-unmounted-hw`, 7 rows with truthful rejection notice).
4. **Tab 4 — Audit & Logs (`#tab-history`):**
   - Header actions (`#btn-export-json`, `#btn-export-csv`) and chronological audit table (`#table-audit-history` / `#tbody-audit-history`, 9 columns: Timestamp, Seq, Route, Type, VERB, NOUN, Status, Code, Details).
5. **Tab 5 — Mission Services (`#tab-services`):**
   - 4 Service Cards (`#services-cards-container`): Grafana Dashboard (`:3000`), InfluxDB 2.x Engine (`:8086`), Open WebUI AI Assistant (`:8080`), and Ground Station REST Diagnostics (`:8000` `/api/diagnostics`).
6. **Tab 6 — Command & Data Reference (`#tab-reference`):**
   - Reference Sub-Navigation (`.ref-subnav` with 7 subtabs):
     - **Subtab 1 (`#ref-panel-catalog`):** Search input (`#ref-search-input`), 4 target filter buttons (`#ref-filter-all`, `#ref-filter-firmware`, `#ref-filter-ground`, `#ref-filter-harness`), count badge (`#ref-count-badge`), and 115-row interactive table (`#table-cmd-reference` / `#tbody-cmd-reference`). Clicking any row expands its detail drawer (`#detail-<VERB>_<NOUN>`) containing a 7-column `Parameters & Schema Constraints` table (with nested expandable `View Value Mappings` sub-tables and `jumpToParameter` links), `Execution Semantics & Verification`, `Error Handling & Status Codes`, `Request Payload (JSON)`, and `Expected Response Envelope (JSON)`.
     - **Subtab 2 (`#ref-panel-parameters`):** Search input (`#param-search-input`), count badge (`#param-count-badge`), and 27-parameter dictionary table (`#table-param-dictionary` / `#tbody-param-dictionary`) with expandable `Value Definitions` drawers (`#dict-drawer-<param>`) and `jumpToCommand` cross-navigation buttons.
     - **Subtab 3 (`#ref-panel-sensors`):** 9-row Sensor & Telemetry Dictionary `.data-table`.
     - **Subtab 4 (`#ref-panel-events`):** 11-row Firmware Event Types `.data-table` and 4-row Ground Station Monitoring Incident Rules `.data-table`.
     - **Subtab 5 (`#ref-panel-actuators`):** 9-row Actuators & Peripherals `.data-table`.
     - **Subtab 6 (`#ref-panel-workflows`):** 3 Runtime ID Discovery Workflow cards (`ACKNOWLEDGE EVENT`, `ACKNOWLEDGE FAULT`, `ACKNOWLEDGE WARNING`) + Operational Distinctions card.
     - **Subtab 7 (`#ref-panel-protocol`):** CBOR & JSON Envelope Format card, Execution Targets card, and 10-row Status Code Enumeration `.data-table`.

---

## 2. Pages, States & Viewport Sizes Inspected

Every view and interactive state listed below was programmatically exercised and visually inspected via headless Chromium (Playwright) across all **4 required viewports**:
- `1440 × 900` (Desktop)
- `1280 × 800` (Laptop)
- `1024 × 768` (Compact viewport)
- `390 × 844` (Mobile-width stress test)

In each viewport, **18 distinct application states** (72 total viewport-state captures before remediation + 72 captures after remediation = **144 full-page screenshots**) were captured and analyzed:
1. `tab-telemetry`: Live Environmental Telemetry & Mounted Actuators grid.
2. `tab-command`: Command Console idle state.
3. `tab-command_set-threshold`: Command Console with `SET` -> `THRESHOLD` selected (enum + float + enum parameters, range/unit helper text, firmware wire preview).
4. `tab-command_ask-system`: Command Console with `ASK` -> `SYSTEM` selected (string parameter, host-local operation preview).
5. `tab-command_hazard-modal`: Command Console with hazardous command `CLEAR` -> `FAULTS` selected and Confirmation Modal open (`#confirmation-modal`).
6. `tab-hardware`: Hardware Inventory split tables (11 mounted, 7 unmounted).
7. `tab-history`: Command & Response Audit Trail table populated with live session entries.
8. `tab-services`: Mission Auxiliary Services cards (`ONLINE` / `OFFLINE` states).
9. `tab-reference`: Command & Data Reference default view.
10. `ref_ref-panel-catalog`: Subpanel 1 (115-command catalog table, search, and target filter buttons).
11. `ref_catalog_drawer_expanded`: Subpanel 1 with `ACKNOWLEDGE EVENT` detail drawer expanded AND nested `View Value Mappings (11)` sub-table expanded.
12. `ref_ref-panel-parameters`: Subpanel 2 (27-parameter dictionary table and search).
13. `ref_param_drawer_expanded`: Subpanel 2 with `event_id` `Value Definitions (11)` drawer expanded.
14. `ref_ref-panel-sensors`: Subpanel 3 (Sensor & Telemetry Dictionary table).
15. `ref_ref-panel-events`: Subpanel 4 (Firmware Event Types & Ground Station Monitoring Rules tables).
16. `ref_ref-panel-actuators`: Subpanel 5 (Actuators & Peripherals table).
17. `ref_ref-panel-workflows`: Subpanel 6 (Runtime ID Discovery & Acknowledgement Workflows).
18. `ref_ref-panel-protocol`: Subpanel 7 (Protocol Envelope Specification & Status Code Enumeration).

Additionally, redirect routes (`/overview`, `/diagnostics`), cross-links (`jumpToParameter`, `jumpToCommand`), filter combinations (`All`, `Firmware`, `Ground Station`, `Test Harness`), modal Escape/backdrop dismissal, and `/favicon.ico` were functionally tested.

---

## 3. Defects Found (Prioritized with Reproduction Steps & Evidence)

### DEF-01 [P0 — Critical Functional]: Command Console Dynamic Parameters Populate `"undefined"` for Strings and `null` (`NaN`) for Numeric Fields
- **Affected Component:** `ground_station/static/app.js` -> `renderDynamicParameters()` (Tab 2: Command Console).
- **Reproduction Steps:**
  1. Open Tab 2 (`Command Console`).
  2. Select `VERB = ASK`, `NOUN = SYSTEM`. Inspect the `question (string)` input and Outbound Wire Envelope Preview: the input is pre-filled with the literal text `"undefined"`.
  3. Select `VERB = CALIBRATE`, `NOUN = SENSOR` (or `SET` -> `THRESHOLD`). Inspect the `offset (int)` / `threshold (float)` input: the input is blank and the JSON preview shows `"offset": null` / `"threshold": null`. Clicking `TRANSMIT COMMAND` without manually re-typing the number causes `POST /api/command` to reject with `Code 1: Parameter 'threshold' must be a float, got: None`.
  4. Inspect `.param-helper-text`: parameter units are missing even when defined in the schema.
- **Root Cause:** `/api/registry` serializes `ParameterSpec` with keys `default` and `units`, whereas `renderDynamicParameters()` read `param.default_value` and `param.unit`. Because `undefined !== null` evaluates to `true` in JavaScript, `inputEl.value` was assigned `undefined` (`"undefined"` for text inputs, `NaN` -> `null` for numeric inputs).
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/tab-command_ask-system.png`, `docs/validation/ux_audit_screenshots/before/desktop_1440x900/tab-command_set-threshold.png`, `audit_report_before.json`.

### DEF-02 [P1 — Major Functional]: Outbound Wire Envelope Preview Misclassifies All 97 ESP32 Firmware Commands as `HOST_LOCAL_OPERATION`
- **Affected Component:** `ground_station/static/app.js` -> `updateWirePreview()` and `displayCommandDetails()` (Tab 2: Command Console).
- **Reproduction Steps:**
  1. Open Tab 2 (`Command Console`).
  2. Select any ESP32 firmware command (e.g., `GET` -> `STATUS` or `SET` -> `THRESHOLD`).
  3. Observe `2. Outbound Wire Envelope Preview`: it displays `"_execution_path": "HOST_LOCAL_OPERATION"` and `"device_wire_envelope": "NOT_APPLICABLE"` instead of `"_execution_path": "FIRMWARE_DEVICE_DISPATCH"` and the CBOR/JSON wire packet (`ver`, `dev`, `seq`, `type`, `cmd_id`).
- **Root Cause:** `/api/registry` returns lowercase `"destination": "firmware"`, while `updateWirePreview()` checked `if (destination !== 'FIRMWARE')` case-sensitively.
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/tab-command_set-threshold.png`.

### DEF-03 [P1 — Major Functional]: Reference Manual Target Filter Buttons Return `0 / 115 Commands` & Mislabel Ground Station Commands as ESP32 Firmware
- **Affected Component:** `ground_station/static/app.js` -> `renderCommandReference()` (Tab 6, Subtab 1: Command Catalog).
- **Reproduction Steps:**
  1. Open Tab 6 (`Command & Data Reference` -> `1. Command Catalog (115)`).
  2. Click `Firmware (ESP32)`, `Ground Station`, or `Test Harness`: every filter button empties the table (`No commands matching query ""`) and sets `#ref-count-badge` to `0 / 115 Commands`.
  3. Click `All Commands` and inspect any Ground Station command (e.g., `ASK SENSOR`, `ASK SYSTEM`): its Target badge is green (`tag-ok`), Transports says `USB Serial & MQTT`, and its expanded drawer says `Dispatched to ESP32 Apollo Executive over Serial/MQTT`.
- **Root Cause:** Filter buttons pass uppercase `FIRMWARE`, `GROUND_STATION`, `TEST_HARNESS`, whereas `cmd.destination` from `/api/registry` is lowercase (`firmware`, `ground_station`), and test harness commands (`TEST *`, `RUN *`) have `destination: "firmware"`.
- **Before Evidence:** `audit_report_before.json` (`reference_catalog_filters`).

### DEF-04 [P1 — Major Visual/Layout]: Severe Column Overlap & Text Collision Inside Expanded Command Catalog Detail Drawers
- **Affected Component:** `ground_station/static/styles.css` (`.cmd-detail-box`) & `ground_station/static/app.js` (`renderCommandReference`).
- **Reproduction Steps:**
  1. Open Tab 6 (`Command & Data Reference` -> `1. Command Catalog (115)`).
  2. Click `ACKNOWLEDGE EVENT` to expand its detail drawer (`#detail-ACKNOWLEDGE_EVENT`), and click `View Value Mappings (11)`.
  3. Observe across `1440×900`, `1280×800`, and `1024×768`: the 7-column `Parameters & Schema Constraints` table overflows its 50%-wide left grid column and collides directly into the right-hand `Request Payload (JSON)` column (`DESCRIPTION & DISCOVERY WORKFLOW` text renders on top of `Validated against canonical schema...`). Additionally, expanding `View Value Mappings (11)` pushes the `event_id`, `int`, `OPTIONAL`, `EVENT_IDENTIFIER`, and `1` cells in other columns vertically down to the middle of the tall row.
- **Root Cause:** `.cmd-detail-box` used `grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))` without `min-width: 0` or `overflow-x: auto`, placing a wide 7-column table into a narrow half-width column, and `.data-table td` lacked `vertical-align: top`.
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/ref_catalog_drawer_expanded.png`.

### DEF-05 [P1 — Major Visual/Styling]: Missing `.data-table`, `.tag-warn`, `.tag-error`, `.tag-info`, `.banner-warn`, and `.banner-info` Styles in `styles.css`
- **Affected Component:** `ground_station/static/styles.css` (affects all 6 tables in Tab 6, sensor cards in Tab 1, command status banners in Tab 2, and audit trail tags in Tab 4).
- **Reproduction Steps:**
  1. Inspect any table in Tab 6 (`Command Catalog`, `Parameter Dictionary`, `Sensor Dictionary`, `Event/Fault/Warning Dictionaries`, `Actuators`, `Status Codes`): table cells have `0px` padding, text runs into adjacent columns, headers (`<th>`) are browser-default center-aligned while data cells (`<td>`) are left-aligned, and there are no row borders.
  2. Inspect `NOT INSTALLED` on the Hall sensor card in Tab 1, or `WARN`, `WARNING`, `ERROR`, `CRITICAL`, `INFO`, `REQUIRED`, `REJECTED` badges in Tab 4 and Tab 6: they have no background or border because only `.tag-ok` and `.tag-neutral` were defined in `styles.css`.
- **Root Cause:** `styles.css` defined `.nexus-table` (used in Tabs 3 & 4) but omitted `.data-table` (used in all 6 subpanels of Tab 6), and omitted `.tag-warn`, `.tag-warning`, `.tag-error`, `.tag-info`, `.banner-warn`, `.banner-warning`, `.banner-info`.
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/ref_ref-panel-events.png`, `docs/validation/ux_audit_screenshots/before/desktop_1440x900/ref_ref-panel-protocol.png`.

### DEF-06 [P1 — Major Responsive Layout]: `+459px` Horizontal Page Overflow at `390×844` and Clipped Header & Navigation Tabs at `1024×768`
- **Affected Component:** `ground_station/static/styles.css` (`.mission-header`, `.status-pill-group`, `.console-tabs`, `.transport-select`, `@media` queries) and `ground_station/static/index.html`.
- **Reproduction Steps:**
  1. View the site at `1024×768`: `#select-global-transport` truncates `"AUTO (Pre"`, and the 6th navigation tab (`Command & Data Reference`) is clipped at the right edge (`"Command & D"`) with hidden scrollbars.
  2. View the site at `390×844`: `.mission-header` and `.status-pill-group` do not wrap, forcing `document.documentElement.scrollWidth = 849px` (`+459px` horizontal overflow across every tab) and crushing `#select-global-transport` to `15px` wide.
- **Root Cause:** Missing `flex-wrap: wrap` on `.mission-header`, `.status-pill-group`, and `.console-tabs`; `.form-control { width: 100% }` shrinking `#select-global-transport` inside a flex item; and missing compact/mobile responsive breakpoints.
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/compact_1024x768/tab-telemetry.png`, `docs/validation/ux_audit_screenshots/before/mobile_390x844/tab-telemetry.png`.

### DEF-07 [P2 — Functional/Navigation]: Parameter Link Click Bubbling & `/overview` -> `#tab-dashboard` Tab Mismatch
- **Affected Component:** `ground_station/static/app.js` (`initTabs`, `jumpToParameter`, `jumpToCommand`, `renderCommandReference`).
- **Reproduction Steps:**
  1. In Tab 6 (`Command Catalog`), click a blue parameter link (e.g., `event_id`) inside a command row: because `jumpToParameter()` did not call `event.stopPropagation()`, the click also triggered the parent `<tr onclick="toggleCommandDetail(...)">`.
  2. Navigate to `/overview` (which redirects to `/#tab-dashboard`) or change the URL hash to `#tab-dashboard` from another tab: `initTabs()` looked for `data-tab="tab-dashboard"`, which did not match `data-tab="tab-telemetry"`, and did not listen to `hashchange`.
- **Before Evidence:** `audit_report_before.json`.

### DEF-08 [P2 — Visual/UX]: Audit & Logs Table Displays Duplicate Raw `inbound_response` Rows with `-` Verb/Noun and Unstyled `COMPLETED` Status
- **Affected Component:** `ground_station/static/app.js` -> `pollCommandHistory()` (Tab 4: Audit & Logs).
- **Reproduction Steps:**
  1. Open Tab 4 (`Audit & Logs`) after commands have been executed.
  2. Observe rows with `Type = inbound_response`: `VERB` is `-`, `NOUN` is `-`, `Status` defaults to `DISPATCHED`, and `Details` is `{}` (duplicating the correlated `cmd_response` row for the same `seq`). Furthermore, `cmd_response` rows have `status: "completed"`, which was not mapped to `tag-ok` (rendered gray instead of green).
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/tab-history.png`.

### DEF-09 [P2 — Visual/UX]: Literal `\n` in `<pre>` Placeholders, Mid-Word Line Breaks in Code Blocks, Unstyled Service Card Metadata & Typo, Sensor Card Empty Chasm, and Unstyled Disabled Hazard Button
- **Affected Component:** `ground_station/static/index.html`, `ground_station/static/styles.css`, `ground_station/static/app.js`.
- **Reproduction Steps:**
  1. Open Tab 2 (`Command Console`): `#wire-preview` and `#response-preview` display literal `\n` characters on a single line (`{\n /* Select a command to preview wire envelope */\n}`).
  2. Inspect `.code-view` and `.ref-code-block`: `word-break: break-all` splits words mid-word (`"acknowle\ndged"`), and `max-height: 220px` clips the 14-line CBOR/JSON envelope in Tab 6 Subtab 7.
  3. Open Tab 5 (`Mission Services`): `Port: 3000` and `http://127.0.0.1:3000` run together with no spacing because `.service-meta`, `.service-card-body`, and `.service-action-row` were unstyled, and Grafana's description contains duplicate word `"Interactive telemetry telemetry charts"`.
  4. Open Tab 1 (`Telemetry & Sensors`): row 2 sensor cards (`INFRARED SENSOR`, `OPTICAL SLOT BEAM`, `ULTRASONIC DISTANCE`) are stretched vertically by `MOUNTED ACTUATORS`, leaving a large empty gap between `.card-head` and `.card-body`.
  5. Open the Hazardous Confirmation Modal (`CLEAR` -> `FAULTS` -> `TRANSMIT COMMAND`): the disabled `Authorize & Transmit` button (`.btn-danger:disabled`) has full opacity and looks active even before the confirmation checkbox is checked.
- **Before Evidence:** `docs/validation/ux_audit_screenshots/before/desktop_1440x900/tab-command.png`, `tab-services.png`, `tab-telemetry.png`, `tab-command_hazard-modal.png`.

### DEF-10 [P2 — Accessibility, Keyboard Navigation & Console 404]: Viewport Zoom Disabled, Missing ARIA Attributes & Input Labels, Modal Escape/Backdrop Dismissal Missing, Small Touch Targets, and `/favicon.ico` 404
- **Affected Component:** `ground_station/static/index.html`, `ground_station/static/app.js`, `ground_station/static/styles.css`, `ground_station/server.py`.
- **Reproduction Steps:**
  1. Inspect `<meta name="viewport">`: `maximum-scale=1.0, user-scalable=no` blocks pinch-to-zoom (WCAG 1.4.4 violation).
  2. Inspect `#select-global-transport`, `#ref-search-input`, and `#param-search-input`: missing accessible labels (`aria-label` / `<label for>`).
  3. Inspect `.tab-btn`, `.tab-panel`, `.ref-subtab-btn`, `.ref-subpanel`, and `#confirmation-modal`: missing `aria-selected`, `aria-controls`, `role="tabpanel"`, and `role="dialog" aria-modal="true"`.
  4. Open `#confirmation-modal` and press `Escape` or click the backdrop overlay: modal does not close.
  5. Inspect browser console on initial load: `Failed to load resource: the server responded with a status of 404 (Not Found)` for `http://127.0.0.1:8000/favicon.ico`.
- **Before Evidence:** `audit_report_before.json` (`console_errors`, `a11yIssues`, `modal_escape_closes`).

---

## 4. Files Changed & Rationale

| File | Summary of Changes & Engineering Rationale |
| :--- | :--- |
| `ground_station/static/index.html` | • Enabled viewport zoom (`content="width=device-width, initial-scale=1.0"`).<br>• Added inline SVG `<link rel="icon">` to eliminate `/favicon.ico` 404 requests.<br>• Added `<label for="select-global-transport">` and `aria-label` on `#select-global-transport`, `#refresh-all-btn`, `#ref-search-input`, and `#param-search-input`.<br>• Added `aria-selected`, `aria-controls`, `role="tabpanel"`, ` aria-labelledby`, and `role="dialog" aria-modal="true"` across all tabs, subtabs, panels, and the confirmation modal.<br>• Replaced literal `\n` sequences in `#wire-preview` and `#response-preview` with real newlines.<br>• Structured Tab 4 `.panel-header` with `.panel-header-row` and `.panel-header-titles` for clean alignment of export actions.<br>• Preserved all 23 element IDs and headings validated by `scripts/validate_reference_manual.py`. |
| `ground_station/static/styles.css` | • Defined complete `.data-table` and `.table-container` rules (`padding: 0.65rem 0.85rem`, left-aligned `<th>`, `vertical-align: top`, sticky `<thead>`, row hover states).<br>• Added `.tag-warn`, `.tag-warning`, `.tag-error`, `.tag-info`, `.banner-warn`, `.banner-warning`, `.banner-info`.<br>• Fixed `.cmd-detail-box` layout by placing the wide 7-column parameter schema table in a full-width `.table-responsive` section above a 2-column `.cmd-detail-bottom-grid` with `min-width: 0`.<br>• Added `.card-body { display: flex; flex-direction: column; justify-content: space-between; flex: 1; }` on sensor cards to eliminate the vertical gap.<br>• Styled `.service-name`, `.service-card-body`, `.service-meta`, `.service-action-row`, `.param-helper-text`, `.param-jump-link`, and `.btn:disabled` (`opacity: 0.42; cursor: not-allowed`).<br>• Changed `word-break: break-all` to `overflow-wrap: anywhere; word-break: break-word` on `.code-view` and `.ref-code-block`, and increased `.ref-code-block` `max-height` to `320px`.<br>• Added responsive `@media (max-width: 1180px)` and `@media (max-width: 768px)` rules so all 4 viewports (`1440`, `1280`, `1024`, `390`) have `0px` horizontal overflow and zero clipped tabs or controls. |
| `ground_station/static/app.js` | • Fixed `renderDynamicParameters()` to read `param.default` (fallback `param.default_value`) and `param.units` (fallback `param.unit`), initializing string inputs to `''` and numeric inputs to `param.min_value ?? 0` when no default is present.<br>• Fixed `updateWirePreview()`, `displayCommandDetails()`, and `renderCommandReference()` to normalize `cmd.destination` case-insensitively (`toUpperCase()`) and match `TEST_HARNESS` filter to `TEST`/`RUN` diagnostic commands.<br>• Updated `jumpToParameter(paramName, event)` and `jumpToCommand(verb, noun, event)` to call `event.stopPropagation()`.<br>• Updated `initTabs()` to map `tab-dashboard` to `tab-telemetry`, maintain `aria-selected`, and handle `hashchange`.<br>• Updated `pollCommandHistory()` to deduplicate raw `inbound_response` entries when correlated `cmd_response` entries exist and map `completed` to `tag-ok` and `dispatched` to `tag-info`.<br>• Fixed duplicate word typo in `renderServicesGrid()` and added Escape key, backdrop click, and focus restoration to `#confirmation-modal`. |
| `ground_station/server.py` | • Added `/favicon.ico` route handling returning `204 No Content`. |
| `ground_station/tests/test_server.py` | • Added `test_favicon_returns_no_content` and `test_frontend_ux_ui_regression_invariants` to lock in HTML, CSS, and JS regression invariants. |

---

## 5. Before-and-After Visual & Programmatic Evidence

| Defect / Area | Before Remediation | After Remediation | Screenshot Evidence (`before/` vs. `after/`) |
| :--- | :--- | :--- | :--- |
| **DEF-01 & DEF-02: Command Console Parameters & Wire Preview** | `ASK SYSTEM` initialized `question` to `"undefined"`; `SET THRESHOLD` / `CALIBRATE SENSOR` initialized numeric inputs to `null` and misclassified `FIRMWARE` commands as `HOST_LOCAL_OPERATION`; units missing. | `ASK SYSTEM` initializes `question` to `"Provide complete health status of the ESP32"`; `SET THRESHOLD` initializes `threshold` to `45` with `Unit: °C/%/counts/cm` and `"_execution_path": "FIRMWARE_DEVICE_DISPATCH"`. | `desktop_1440x900/tab-command_set-threshold.png`, `desktop_1440x900/tab-command_ask-system.png` |
| **DEF-03: Reference Manual Target Filters** | `Firmware (ESP32)`, `Ground Station`, and `Test Harness` filters all returned `0 / 115 Commands`. | `All`: `115 / 115`, `Firmware (ESP32)`: `97 / 115`, `Ground Station`: `18 / 115`, `Test Harness`: `9 / 115`. | `audit_report_before.json` vs. `audit_report_after.json` |
| **DEF-04: Expanded Command Drawer Layout** | 7-column parameter table overflowed left column and collided with right-hand `Request Payload (JSON)` column. | Parameter schema table spans full drawer width inside `.table-responsive`; execution semantics and JSON examples sit in a clean 2-column grid below with zero overlap. | `desktop_1440x900/ref_catalog_drawer_expanded.png` |
| **DEF-05: `.data-table` & Semantic Badges** | `0px` cell padding, centered `<th>` vs. left `<td>`, unstyled `WARN`/`ERROR`/`INFO` tags. | `10.4px × 13.6px` cell padding, left-aligned sticky `<thead>`, top-aligned cells, and color-coded `.tag-warn`, `.tag-error`, `.tag-info` badges. | `desktop_1440x900/ref_ref-panel-events.png`, `desktop_1440x900/ref_ref-panel-protocol.png` |
| **DEF-06: Responsive Layout (`1024×768` & `390×844`)** | At `1024×768`, 6th tab clipped (`"Command & D"`) and transport select truncated (`"AUTO (Pre"`). At `390×844`, `+459px` horizontal page overflow (`scrollWidth = 849px`). | `0px` horizontal overflow across all 72 states (`scrollWidth == clientWidth` at `1440`, `1280`, `1024`, and `390`). All 6 tabs and transport selector 100% visible. | `compact_1024x768/tab-telemetry.png`, `mobile_390x844/tab-telemetry.png`, `mobile_390x844/tab-reference.png` |
| **DEF-08: Audit Trail Table (`#tab-history`)** | Duplicate `inbound_response` rows with `-` verb/noun and unstyled `COMPLETED` status. | Correlated rows deduplicated; every row shows verb, noun, and color-coded `COMPLETED` (`tag-ok`), `DISPATCHED` (`tag-info`), or `REJECTED` (`tag-error`). | `desktop_1440x900/tab-history.png` |
| **DEF-09: Sensor Cards, Service Cards, Code Blocks & Modal** | Literal `\n` in `<pre>`, empty vertical gap in sensor cards, unstyled `.service-meta`, duplicate word typo, unstyled disabled confirm button. | Multi-line `<pre>` placeholders, balanced sensor cards, bordered `.service-meta` pills, clean word wrapping, dimmed disabled confirm button. | `desktop_1440x900/tab-telemetry.png`, `tab-command.png`, `tab-services.png`, `tab-command_hazard-modal.png` |
| **DEF-10: Console Errors & Accessibility** | `/favicon.ico` 404 error, `user-scalable=no`, 3 unlabeled inputs, Escape key ignored on modal. | `0` console errors, `0` failed requests, `0` accessibility label/ARIA issues, Escape key & backdrop click close modal and restore focus. | `audit_report_after.json` |

---

## 6. Automated Tests Executed & Results

1. **Ground Station Unit & Integration Test Suite (`pytest`):**
   - Command: `.venv/bin/pytest ground_station/tests/ -q`
   - Result: **244 passed in 58.6s** (242 existing tests + 2 new regression tests in `ground_station/tests/test_server.py`: `test_favicon_returns_no_content` and `test_frontend_ux_ui_regression_invariants`).
2. **Reference Manual Mechanical Completeness & Parity Suite:**
   - Command: `.venv/bin/python scripts/validate_reference_manual.py`
   - Result: **ALL 7 MECHANICAL VALIDATION SUITES PASSED (100% PARITY WITH SOURCE OF TRUTH)** (115/115 commands, 27/27 parameter definitions, 23/23 required DOM IDs, 100% example payload validation).
3. **Playwright Multi-Viewport Layout, Functional & Accessibility Audit:**
   - Command: `.venv/bin/python browser_audit.py after docs/validation/ux_audit_screenshots/after`
   - Result: **72 / 72 viewport states passed** with `0` console errors, `0` page errors, `0` failed network requests, `0px` horizontal overflow across all 4 viewports, `0` overflowing elements, `0` undefined CSS classes, and `0` accessibility label/ARIA violations.

---

## 7. Known Issues, Untested States, Blocked Checks & Environmental Limitations

- **Physical Actuation Safety Boundary:** Per mission safety rules ("Do not execute physical actuation commands merely to test UI controls"), live hardware actuation buttons (`Buzzer 200ms/500ms`, `LED 1..4 ON/OFF`) and the `Audit USB Serial (115)` / `Audit MQTT (115)` batch runners were inspected for DOM wiring, handler binding, and existing audit trail records without triggering new physical actuation cycles during the UI audit.
- **External Auxiliary Services Ports (`:3000`, `:8086`, `:8080`):** The Mission Services tab (`#tab-services`) links to external local services (Grafana on `:3000`, InfluxDB on `:8086`, Open WebUI on `:8080`). Their card rendering, status badges, and outbound link targets (`target="_blank" rel="noopener noreferrer"`) were verified in Mission Control; auditing the third-party Grafana/InfluxDB/Open WebUI web UIs themselves is outside the scope of the Mission Control web application.

---

## 8. Coverage Matrix

| Page / Component / Workflow | Inspected | Tested | Fixed | Independently Reverified (`1440`, `1280`, `1024`, `390`) |
| :--- | :---: | :---: | :---: | :---: |
| **Global Header, Status Badges & Transport Selector** | ✔ | ✔ | ✔ (`DEF-06`, `DEF-10`) | ✔ (All 4 viewports) |
| **Quick Telemetry Strip (5 Metric Chips)** | ✔ | ✔ | ✔ (`DEF-06`) | ✔ (All 4 viewports) |
| **Primary Navigation Tabs (6 Tabs) & URL Hash / Redirect Routing** | ✔ | ✔ | ✔ (`DEF-06`, `DEF-07`, `DEF-10`) | ✔ (All 4 viewports + `/overview`, `/diagnostics`) |
| **Tab 1: Live Environmental Telemetry Cards (7 Sensor Cards)** | ✔ | ✔ | ✔ (`DEF-05`, `DEF-09`) | ✔ (All 4 viewports) |
| **Tab 1: Mounted Actuators Quick Card (11 Controls)** | ✔ | ✔ (Read-only) | ✔ (`DEF-09`) | ✔ (All 4 viewports) |
| **Tab 2: Command Specification Builder (23 Verbs, 115 Commands)** | ✔ | ✔ | ✔ (`DEF-01`, `DEF-02`) | ✔ (All 4 viewports) |
| **Tab 2: Dynamic Parameter Inputs (Enum, Bool, Int, Float, String)** | ✔ | ✔ | ✔ (`DEF-01`) | ✔ (All 4 viewports) |
| **Tab 2: Outbound Wire Preview & Response Telemetry** | ✔ | ✔ | ✔ (`DEF-02`, `DEF-05`, `DEF-09`) | ✔ (All 4 viewports) |
| **Tab 2: Hazardous Operation Confirmation Modal** | ✔ | ✔ | ✔ (`DEF-09`, `DEF-10`) | ✔ (All 4 viewports + Escape/Backdrop) |
| **Tab 3: Hardware Inventory Split Tables (Mounted & Unmounted)** | ✔ | ✔ | ✔ (`DEF-10`) | ✔ (All 4 viewports) |
| **Tab 4: Command & Response Audit Trail & JSON/CSV Export** | ✔ | ✔ | ✔ (`DEF-05`, `DEF-08`) | ✔ (All 4 viewports) |
| **Tab 5: Mission Auxiliary Services Grid (4 Cards)** | ✔ | ✔ | ✔ (`DEF-09`) | ✔ (All 4 viewports) |
| **Tab 6.1: Command Catalog (115 Rows, Search, 4 Filters, Detail Drawers)** | ✔ | ✔ | ✔ (`DEF-03`, `DEF-04`, `DEF-05`, `DEF-07`) | ✔ (All 4 viewports) |
| **Tab 6.2: Parameter Dictionary (27 Params, Value Drawers, Cross-Links)** | ✔ | ✔ | ✔ (`DEF-05`, `DEF-07`, `DEF-10`) | ✔ (All 4 viewports) |
| **Tab 6.3: Sensor & Telemetry Dictionary Table** | ✔ | ✔ | ✔ (`DEF-05`) | ✔ (All 4 viewports) |
| **Tab 6.4: Event, Fault & Warning Dictionaries (2 Tables)** | ✔ | ✔ | ✔ (`DEF-05`) | ✔ (All 4 viewports) |
| **Tab 6.5: Actuators & Peripherals Table** | ✔ | ✔ | ✔ (`DEF-05`) | ✔ (All 4 viewports) |
| **Tab 6.6: Runtime ID Discovery & Acknowledgement Workflows** | ✔ | ✔ | ✔ (`DEF-09`) | ✔ (All 4 viewports) |
| **Tab 6.7: Protocol Envelope Specification & Status Codes** | ✔ | ✔ | ✔ (`DEF-05`, `DEF-09`) | ✔ (All 4 viewports) |

---

## 9. Final List of Outstanding P0, P1, P2 & P3 Issues

- **Outstanding P0 Issues:** None (`0`).
- **Outstanding P1 Issues:** None (`0`).
- **Outstanding P2 Issues:** None (`0`).
- **Outstanding P3 Issues:** None (`0`).

All 10 discovered defects (`DEF-01` through `DEF-10`) have been remediated in the codebase and independently reverified across all 4 required viewports.
