#include "nexus_command_registry.h"
#include <string.h>

static const nexus_cmd_registry_entry_t s_command_registry[] = {
    /* 00 NOP */
    {
        .cmd_id = NEXUS_CMD_NOP_NONE,
        .verb_code = NEXUS_VERB_NOP,
        .noun_code = NEXUS_NOUN_NONE,
        .verb_name = "NOP",
        .noun_name = "NONE",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Parser and protocol loopback test"
    },

    /* 01 INITIALIZE */
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_SYSTEM,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = NEXUS_NOUN_SYSTEM,
        .verb_name = "INITIALIZE",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Re-initialization of running system services is unsupported without reboot"
    },
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_SENSORS,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = NEXUS_NOUN_SENSORS,
        .verb_name = "INITIALIZE",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Dynamic re-initialization of sensor peripherals is unsupported at runtime"
    },
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_TRANSPORTS,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = NEXUS_NOUN_TRANSPORTS,
        .verb_name = "INITIALIZE",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Transport re-initialization without clean teardown is unsupported"
    },

    /* 02 START */
    {
        .cmd_id = NEXUS_CMD_START_SYSTEM,
        .verb_code = NEXUS_VERB_START,
        .noun_code = NEXUS_NOUN_SYSTEM,
        .verb_name = "START",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "System executive is started automatically at boot"
    },
    {
        .cmd_id = NEXUS_CMD_START_SENSORS,
        .verb_code = NEXUS_VERB_START,
        .noun_code = NEXUS_NOUN_SENSORS,
        .verb_name = "START",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Sensor acquisition jobs are started deterministically at boot"
    },
    {
        .cmd_id = NEXUS_CMD_START_TELEMETRY,
        .verb_code = NEXUS_VERB_START,
        .noun_code = NEXUS_NOUN_TELEMETRY,
        .verb_name = "START",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Telemetry broadcast is enabled automatically at boot"
    },
    {
        .cmd_id = NEXUS_CMD_START_SELF_TEST,
        .verb_code = NEXUS_VERB_START,
        .noun_code = NEXUS_NOUN_SELF_TEST,
        .verb_name = "START",
        .noun_name = "SELF_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Run bounded executive and data-structure self-test"
    },

    /* 03 STOP */
    {
        .cmd_id = NEXUS_CMD_STOP_SENSORS,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = NEXUS_NOUN_SENSORS,
        .verb_name = "STOP",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Halting scheduled sensor acquisitions is deferred to M9/M10"
    },
    {
        .cmd_id = NEXUS_CMD_STOP_TELEMETRY,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = NEXUS_NOUN_TELEMETRY,
        .verb_name = "STOP",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Halting core telemetry transmission remotely is deferred to M9/M10"
    },

    /* 04 RESET */
    {
        .cmd_id = NEXUS_CMD_RESET_FAULTS,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = NEXUS_NOUN_RESET_FAULTS,
        .verb_name = "RESET",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Clearing latched hardware faults requires dedicated fault manager (M9/M10)"
    },
    {
        .cmd_id = NEXUS_CMD_RESET_STATISTICS,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = NEXUS_NOUN_RESET_STATISTICS,
        .verb_name = "RESET",
        .noun_name = "STATISTICS",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Resetting diagnostic counters destabilizes host metrics monitoring; unsupported"
    },

    /* 05 SET */
    {
        .cmd_id = NEXUS_CMD_SET_PRIORITY,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = NEXUS_NOUN_PRIORITY,
        .verb_name = "SET",
        .noun_name = "PRIORITY",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Modifying job priorities at runtime alters deterministic scheduling guarantees"
    },
    {
        .cmd_id = NEXUS_CMD_SET_SAMPLE_INTERVAL,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = NEXUS_NOUN_SAMPLE_INTERVAL,
        .verb_name = "SET",
        .noun_name = "SAMPLE_INTERVAL",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Modifying sample intervals at runtime is not supported by current executive"
    },
    {
        .cmd_id = NEXUS_CMD_SET_THRESHOLD,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = NEXUS_NOUN_THRESHOLD,
        .verb_name = "SET",
        .noun_name = "THRESHOLD",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Threshold monitoring is handled host-side in Ground Station monitoring engine"
    },

    /* 06 GET */
    {
        .cmd_id = NEXUS_CMD_GET_STATUS,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = NEXUS_NOUN_STATUS,
        .verb_name = "GET",
        .noun_name = "STATUS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Retrieve system state, uptime, free heap, and connection state"
    },
    {
        .cmd_id = NEXUS_CMD_GET_CONFIGURATION,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = NEXUS_NOUN_CONFIGURATION,
        .verb_name = "GET",
        .noun_name = "CONFIGURATION",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Retrieve protocol version, device identity, and routing defaults"
    },
    {
        .cmd_id = NEXUS_CMD_GET_SENSOR_LIST,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = NEXUS_NOUN_SENSOR_LIST,
        .verb_name = "GET",
        .noun_name = "SENSOR_LIST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Retrieve registered present sensor drivers"
    },
    {
        .cmd_id = NEXUS_CMD_GET_TIME,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = NEXUS_NOUN_TIME,
        .verb_name = "GET",
        .noun_name = "TIME",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Retrieve monotonic uptime in milliseconds and microseconds"
    },

    /* 16 DISPLAY */
    {
        .cmd_id = NEXUS_CMD_DISPLAY_STATUS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_STATUS,
        .verb_name = "DISPLAY",
        .noun_name = "STATUS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display overall device operational status summary"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_EXECUTIVE,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_EXECUTIVE,
        .verb_name = "DISPLAY",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display executive dispatch metrics and latency"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_QUEUES,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_QUEUES,
        .verb_name = "DISPLAY",
        .noun_name = "QUEUES",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display ready queue, event queue, and tx queue depths"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_FAULTS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_FAULTS,
        .verb_name = "DISPLAY",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display active sensor error counts and executive failures"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_ENVIRONMENT,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_ENVIRONMENT,
        .verb_name = "DISPLAY",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display latest DHT11 temperature, humidity, and validity"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_LIGHT,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_LIGHT,
        .verb_name = "DISPLAY",
        .noun_name = "LIGHT",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display latest calibrated LDR light reading"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_DISTANCE,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_DISTANCE,
        .verb_name = "DISPLAY",
        .noun_name = "DISTANCE",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "HC-SR04 distance sensor is not yet connected; deferred to M9"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_ANALOG,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_ANALOG,
        .verb_name = "DISPLAY",
        .noun_name = "ANALOG",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display raw analog readings from CD4051 channel X0"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_MOTION,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_MOTION,
        .verb_name = "DISPLAY",
        .noun_name = "MOTION",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Motion sensor hardware is not installed; deferred to M9"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_EVENTS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = NEXUS_NOUN_DISP_EVENTS,
        .verb_name = "DISPLAY",
        .noun_name = "EVENTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Display recent system and executive event details"
    },

    /* 17 HISTORY */
    {
        .cmd_id = NEXUS_CMD_HISTORY_EVENTS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = NEXUS_NOUN_HIST_EVENTS,
        .verb_name = "HISTORY",
        .noun_name = "EVENTS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Bounded firmware event history query deferred to M9/M10 (use host incidents.db)"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_FAULTS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = NEXUS_NOUN_HIST_FAULTS,
        .verb_name = "HISTORY",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Firmware fault history query deferred to M9/M10 (use host incidents.db)"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_EXECUTIVE,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = NEXUS_NOUN_HIST_EXECUTIVE,
        .verb_name = "HISTORY",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Scheduler history query deferred to M9/M10"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_ENVIRONMENT,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = NEXUS_NOUN_HIST_ENVIRONMENT,
        .verb_name = "HISTORY",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Environmental history is persisted host-side in InfluxDB (query via Ground Station)"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_SENSORS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = NEXUS_NOUN_HIST_SENSORS,
        .verb_name = "HISTORY",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .description = "Per-sensor history is persisted host-side in InfluxDB (query via Ground Station)"
    },

    /* 24 DIAGNOSTICS */
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_SYSTEM,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_SYSTEM,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Detailed system health diagnostics: uptime, heap, reset reason, ticks"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_SENSORS,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_SENSORS,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Sensor driver error counts, read counts, and freshness metrics"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_QUEUES,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_QUEUES,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "QUEUES",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Queue depths, high-water marks, and overflow statistics"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_TIMING,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_TIMING,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "TIMING",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Executive dispatch latency, execution duration, and deadline metrics"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_MEMORY,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_MEMORY,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "MEMORY",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Free heap, minimum free heap watermark, and allocation health"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_TRANSPORTS,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = NEXUS_NOUN_DIAG_TRANSPORTS,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Serial and MQTT transport connection states, packets, and error counts"
    },

    /* 30 OPEN (Laptop actions) */
    {
        .cmd_id = NEXUS_CMD_OPEN_DASHBOARD,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = NEXUS_NOUN_DASHBOARD,
        .verb_name = "OPEN",
        .noun_name = "DASHBOARD",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .description = "Laptop Ground Station opens Grafana dashboard"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_LOGS,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = NEXUS_NOUN_LOGS,
        .verb_name = "OPEN",
        .noun_name = "LOGS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .description = "Laptop Ground Station opens structured log viewer"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_AI,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = NEXUS_NOUN_AI,
        .verb_name = "OPEN",
        .noun_name = "AI",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .description = "Laptop Ground Station opens Open WebUI AI interface"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_GROUND,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = NEXUS_NOUN_GROUND,
        .verb_name = "OPEN",
        .noun_name = "GROUND",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .description = "Laptop Ground Station opens ground-station overview"
    },

    /* 31 ASK */
    {
        .cmd_id = NEXUS_CMD_ASK_SYSTEM,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = NEXUS_NOUN_ASK_SYSTEM,
        .verb_name = "ASK",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .description = "Open AI with system context; deferred to M9/M10"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_ENVIRONMENT,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = NEXUS_NOUN_ASK_ENVIRONMENT,
        .verb_name = "ASK",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .description = "Open AI with environmental context; deferred to M9/M10"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_SENSOR,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = NEXUS_NOUN_ASK_SENSOR,
        .verb_name = "ASK",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .description = "Open AI with selected sensor context; deferred to M9/M10"
    },

    /* 32 EXPORT */
    {
        .cmd_id = NEXUS_CMD_EXPORT_TELEMETRY,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = NEXUS_NOUN_EXP_TELEMETRY,
        .verb_name = "EXPORT",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .description = "Bounded telemetry export job deferred to M9/M10 (supported via host analysis)"
    },
    {
        .cmd_id = NEXUS_CMD_EXPORT_DIAGNOSTICS,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = NEXUS_NOUN_EXP_DIAGNOSTICS,
        .verb_name = "EXPORT",
        .noun_name = "DIAGNOSTICS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .description = "Diagnostic report generation deferred to M9/M10 (supported via host analysis)"
    },

    /* 33 RUN */
    {
        .cmd_id = NEXUS_CMD_RUN_SELF_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = NEXUS_NOUN_RUN_SELF_TEST,
        .verb_name = "RUN",
        .noun_name = "SELF_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Execute bounded executive and bounded data structures self-test"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_SENSOR_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = NEXUS_NOUN_RUN_SENSOR_TEST,
        .verb_name = "RUN",
        .noun_name = "SENSOR_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .description = "Execute physical sensor driver validity and presence self-test"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_STRESS_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = NEXUS_NOUN_RUN_STRESS_TEST,
        .verb_name = "RUN",
        .noun_name = "STRESS_TEST",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_TEST_HARNESS,
        .is_supported_m8 = false,
        .description = "Stress test is restricted to controlled host test harness builds only"
    }
};

static const size_t s_registry_count = sizeof(s_command_registry) / sizeof(s_command_registry[0]);

const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_id(uint16_t cmd_id)
{
    for (size_t i = 0; i < s_registry_count; ++i) {
        if (s_command_registry[i].cmd_id == cmd_id) {
            return &s_command_registry[i];
        }
    }
    return NULL;
}

const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_name(const char *verb, const char *noun)
{
    if (!verb || !noun) {
        return NULL;
    }
    for (size_t i = 0; i < s_registry_count; ++i) {
        if (strcasecmp(s_command_registry[i].verb_name, verb) == 0 &&
            strcasecmp(s_command_registry[i].noun_name, noun) == 0) {
            return &s_command_registry[i];
        }
    }
    return NULL;
}

bool nexus_cmd_registry_is_supported_m8(uint16_t cmd_id)
{
    const nexus_cmd_registry_entry_t *entry = nexus_cmd_registry_lookup_by_id(cmd_id);
    return (entry != NULL && entry->is_supported_m8);
}

const nexus_cmd_registry_entry_t *nexus_cmd_registry_get_all(size_t *out_count)
{
    if (out_count) {
        *out_count = s_registry_count;
    }
    return s_command_registry;
}

const char *nexus_cmd_disposition_str(nexus_cmd_disposition_t disp)
{
    switch (disp) {
    case NEXUS_CMD_DISP_REQUIRED_M8:        return "REQUIRED_M8";
    case NEXUS_CMD_DISP_EXISTING_CAPABILITY: return "EXISTING_CAPABILITY";
    case NEXUS_CMD_DISP_DEFERRED_M9_M10:    return "DEFERRED_M9_M10";
    case NEXUS_CMD_DISP_UNSUPPORTED:        return "UNSUPPORTED";
    case NEXUS_CMD_DISP_NOT_REQUIRED:       return "NOT_REQUIRED";
    default:                                return "UNKNOWN";
    }
}

const char *nexus_cmd_status_code_str(nexus_cmd_status_code_t code)
{
    switch (code) {
    case NEXUS_CMD_STATUS_OK:          return "completed";
    case NEXUS_CMD_STATUS_REJECTED:    return "rejected";
    case NEXUS_CMD_STATUS_UNKNOWN_CMD: return "rejected";
    case NEXUS_CMD_STATUS_UNSUPPORTED: return "unsupported";
    case NEXUS_CMD_STATUS_FAILED:      return "failed";
    case NEXUS_CMD_STATUS_DUPLICATE:   return "rejected";
    default:                           return "failed";
    }
}
