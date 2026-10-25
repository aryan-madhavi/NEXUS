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
        .is_supported = true,
        .description = "Parser and protocol loopback test"
    },

    /* 01 INITIALIZE */
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_SYSTEM,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = 0x01U,
        .verb_name = "INITIALIZE",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Re-initialization of running system requires restart"
    },
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_SENSORS,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = 0x02U,
        .verb_name = "INITIALIZE",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Re-initialize sensor registry and sampling states"
    },
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_TRANSPORTS,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = 0x03U,
        .verb_name = "INITIALIZE",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Transport re-initialization at runtime requires controlled teardown"
    },
    {
        .cmd_id = NEXUS_CMD_INITIALIZE_EXECUTIVE,
        .verb_code = NEXUS_VERB_INITIALIZE,
        .noun_code = 0x04U,
        .verb_name = "INITIALIZE",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Executive runs deterministically from boot; live re-init is restricted"
    },

    /* 02 START */
    {
        .cmd_id = NEXUS_CMD_START_SYSTEM,
        .verb_code = NEXUS_VERB_START,
        .noun_code = 0x01U,
        .verb_name = "START",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "System executive is already started and running"
    },
    {
        .cmd_id = NEXUS_CMD_START_SENSORS,
        .verb_code = NEXUS_VERB_START,
        .noun_code = 0x02U,
        .verb_name = "START",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Resume sensor sampling jobs"
    },
    {
        .cmd_id = NEXUS_CMD_START_TELEMETRY,
        .verb_code = NEXUS_VERB_START,
        .noun_code = 0x03U,
        .verb_name = "START",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Resume periodic telemetry streaming"
    },
    {
        .cmd_id = NEXUS_CMD_START_SELF_TEST,
        .verb_code = NEXUS_VERB_START,
        .noun_code = 0x04U,
        .verb_name = "START",
        .noun_name = "SELF_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Run executive and data structure self-tests"
    },
    {
        .cmd_id = NEXUS_CMD_START_EXECUTIVE,
        .verb_code = NEXUS_VERB_START,
        .noun_code = 0x05U,
        .verb_name = "START",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Resume executive scheduler if paused"
    },

    /* 03 STOP */
    {
        .cmd_id = NEXUS_CMD_STOP_SYSTEM,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = 0x01U,
        .verb_name = "STOP",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Stopping core system is prohibited to preserve safety watchdog"
    },
    {
        .cmd_id = NEXUS_CMD_STOP_SENSORS,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = 0x02U,
        .verb_name = "STOP",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Pause sensor sampling jobs"
    },
    {
        .cmd_id = NEXUS_CMD_STOP_TELEMETRY,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = 0x03U,
        .verb_name = "STOP",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Mute periodic telemetry streaming"
    },
    {
        .cmd_id = NEXUS_CMD_STOP_EXECUTIVE,
        .verb_code = NEXUS_VERB_STOP,
        .noun_code = 0x04U,
        .verb_name = "STOP",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Stopping executive scheduler is unsupported"
    },

    /* 04 RESET */
    {
        .cmd_id = NEXUS_CMD_RESET_FAULTS,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = 0x01U,
        .verb_name = "RESET",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Clear registered fault counters without rebooting"
    },
    {
        .cmd_id = NEXUS_CMD_RESET_STATISTICS,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = 0x02U,
        .verb_name = "RESET",
        .noun_name = "STATISTICS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Reset executive and transport statistical counters"
    },
    {
        .cmd_id = NEXUS_CMD_RESET_SENSOR_STATE,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = 0x03U,
        .verb_name = "RESET",
        .noun_name = "SENSOR_STATE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Reset sensor error states and re-arm readings"
    },
    {
        .cmd_id = NEXUS_CMD_RESET_QUEUES,
        .verb_code = NEXUS_VERB_RESET,
        .noun_code = 0x04U,
        .verb_name = "RESET",
        .noun_name = "QUEUES",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Flush non-critical ready and event queue backlogs"
    },

    /* 05 SET */
    {
        .cmd_id = NEXUS_CMD_SET_PRIORITY,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x01U,
        .verb_name = "SET",
        .noun_name = "PRIORITY",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Dynamic priority adjustment unsupported for executive scheduling safety"
    },
    {
        .cmd_id = NEXUS_CMD_SET_SAMPLE_INTERVAL,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x02U,
        .verb_name = "SET",
        .noun_name = "SAMPLE_INTERVAL",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Configure sampling interval for target sensor"
    },
    {
        .cmd_id = NEXUS_CMD_SET_THRESHOLD,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x03U,
        .verb_name = "SET",
        .noun_name = "THRESHOLD",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Set telemetry alert thresholds"
    },
    {
        .cmd_id = NEXUS_CMD_SET_SENSOR_ENABLE,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x04U,
        .verb_name = "SET",
        .noun_name = "SENSOR_ENABLE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Enable or disable sensor sampling"
    },
    {
        .cmd_id = NEXUS_CMD_SET_TRANSPORT_PREF,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x05U,
        .verb_name = "SET",
        .noun_name = "TRANSPORT_PREFERENCE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Set active transport preference (serial, mqtt, or auto)"
    },
    {
        .cmd_id = NEXUS_CMD_SET_CONFIGURATION,
        .verb_code = NEXUS_VERB_SET,
        .noun_code = 0x06U,
        .verb_name = "SET",
        .noun_name = "CONFIGURATION",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Set runtime operational parameter"
    },

    /* 06 GET */
    {
        .cmd_id = NEXUS_CMD_GET_STATUS,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x01U,
        .verb_name = "GET",
        .noun_name = "STATUS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Retrieve current executive, heap, and connection status"
    },
    {
        .cmd_id = NEXUS_CMD_GET_CONFIGURATION,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x02U,
        .verb_name = "GET",
        .noun_name = "CONFIGURATION",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Retrieve protocol version and configuration parameters"
    },
    {
        .cmd_id = NEXUS_CMD_GET_SENSOR_LIST,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x03U,
        .verb_name = "GET",
        .noun_name = "SENSOR_LIST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Enumerate registered sensors on device"
    },
    {
        .cmd_id = NEXUS_CMD_GET_TIME,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x04U,
        .verb_name = "GET",
        .noun_name = "TIME",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Retrieve high-resolution device uptime timestamps"
    },
    {
        .cmd_id = NEXUS_CMD_GET_VERSION,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x05U,
        .verb_name = "GET",
        .noun_name = "VERSION",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Retrieve firmware version and build timestamp"
    },
    {
        .cmd_id = NEXUS_CMD_GET_HEALTH,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x06U,
        .verb_name = "GET",
        .noun_name = "HEALTH",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Retrieve system health score and subsystem flags"
    },
    {
        .cmd_id = NEXUS_CMD_GET_CAPABILITIES,
        .verb_code = NEXUS_VERB_GET,
        .noun_code = 0x07U,
        .verb_name = "GET",
        .noun_name = "CAPABILITIES",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Enumerate actual installed hardware sensors, actuators, and transports"
    },

    /* 07 ENABLE */
    {
        .cmd_id = NEXUS_CMD_ENABLE_SENSOR,
        .verb_code = NEXUS_VERB_ENABLE,
        .noun_code = 0x01U,
        .verb_name = "ENABLE",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Enable acquisition job for specified sensor"
    },
    {
        .cmd_id = NEXUS_CMD_ENABLE_TRANSPORT,
        .verb_code = NEXUS_VERB_ENABLE,
        .noun_code = 0x02U,
        .verb_name = "ENABLE",
        .noun_name = "TRANSPORT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Enable target transport (serial or mqtt)"
    },
    {
        .cmd_id = NEXUS_CMD_ENABLE_TELEMETRY,
        .verb_code = NEXUS_VERB_ENABLE,
        .noun_code = 0x03U,
        .verb_name = "ENABLE",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Enable periodic telemetry transmission"
    },

    /* 08 DISABLE */
    {
        .cmd_id = NEXUS_CMD_DISABLE_SENSOR,
        .verb_code = NEXUS_VERB_DISABLE,
        .noun_code = 0x01U,
        .verb_name = "DISABLE",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Disable acquisition job for specified sensor"
    },
    {
        .cmd_id = NEXUS_CMD_DISABLE_TRANSPORT,
        .verb_code = NEXUS_VERB_DISABLE,
        .noun_code = 0x02U,
        .verb_name = "DISABLE",
        .noun_name = "TRANSPORT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Disable target transport"
    },
    {
        .cmd_id = NEXUS_CMD_DISABLE_TELEMETRY,
        .verb_code = NEXUS_VERB_DISABLE,
        .noun_code = 0x03U,
        .verb_name = "DISABLE",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Disable periodic telemetry transmission"
    },

    /* 09 CALIBRATE */
    {
        .cmd_id = NEXUS_CMD_CALIBRATE_SENSOR,
        .verb_code = NEXUS_VERB_CALIBRATE,
        .noun_code = 0x01U,
        .verb_name = "CALIBRATE",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Set zero/span calibration offset for target sensor"
    },
    {
        .cmd_id = NEXUS_CMD_CALIBRATE_ANALOG,
        .verb_code = NEXUS_VERB_CALIBRATE,
        .noun_code = 0x02U,
        .verb_name = "CALIBRATE",
        .noun_name = "ANALOG",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Sample analog baseline calibration for MUX channel"
    },
    {
        .cmd_id = NEXUS_CMD_CALIBRATE_ENVIRONMENT,
        .verb_code = NEXUS_VERB_CALIBRATE,
        .noun_code = 0x03U,
        .verb_name = "CALIBRATE",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Calibrate temperature and humidity reference baseline"
    },

    /* 10 ACKNOWLEDGE */
    {
        .cmd_id = NEXUS_CMD_ACKNOWLEDGE_FAULT,
        .verb_code = NEXUS_VERB_ACKNOWLEDGE,
        .noun_code = 0x01U,
        .verb_name = "ACKNOWLEDGE",
        .noun_name = "FAULT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Acknowledge active fault alert"
    },
    {
        .cmd_id = NEXUS_CMD_ACKNOWLEDGE_WARNING,
        .verb_code = NEXUS_VERB_ACKNOWLEDGE,
        .noun_code = 0x02U,
        .verb_name = "ACKNOWLEDGE",
        .noun_name = "WARNING",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Acknowledge warning alert"
    },
    {
        .cmd_id = NEXUS_CMD_ACKNOWLEDGE_EVENT,
        .verb_code = NEXUS_VERB_ACKNOWLEDGE,
        .noun_code = 0x03U,
        .verb_name = "ACKNOWLEDGE",
        .noun_name = "EVENT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Acknowledge notification event"
    },

    /* 11 CLEAR */
    {
        .cmd_id = NEXUS_CMD_CLEAR_FAULTS,
        .verb_code = NEXUS_VERB_CLEAR,
        .noun_code = 0x01U,
        .verb_name = "CLEAR",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Clear all active and latched faults without rebooting"
    },
    {
        .cmd_id = NEXUS_CMD_CLEAR_HISTORY,
        .verb_code = NEXUS_VERB_CLEAR,
        .noun_code = 0x02U,
        .verb_name = "CLEAR",
        .noun_name = "HISTORY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Clear stored history ring buffer"
    },
    {
        .cmd_id = NEXUS_CMD_CLEAR_STATISTICS,
        .verb_code = NEXUS_VERB_CLEAR,
        .noun_code = 0x03U,
        .verb_name = "CLEAR",
        .noun_name = "STATISTICS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Clear executive dispatch statistics"
    },

    /* 12 TEST */
    {
        .cmd_id = NEXUS_CMD_TEST_SENSOR,
        .verb_code = NEXUS_VERB_TEST,
        .noun_code = 0x01U,
        .verb_name = "TEST",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Execute single synchronous sensor diagnostic read"
    },
    {
        .cmd_id = NEXUS_CMD_TEST_TRANSPORT,
        .verb_code = NEXUS_VERB_TEST,
        .noun_code = 0x02U,
        .verb_name = "TEST",
        .noun_name = "TRANSPORT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Ping and verify transport round-trip"
    },
    {
        .cmd_id = NEXUS_CMD_TEST_EXECUTIVE,
        .verb_code = NEXUS_VERB_TEST,
        .noun_code = 0x03U,
        .verb_name = "TEST",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Run executive dispatch timing validation"
    },
    {
        .cmd_id = NEXUS_CMD_TEST_PERIPHERAL,
        .verb_code = NEXUS_VERB_TEST,
        .noun_code = 0x04U,
        .verb_name = "TEST",
        .noun_name = "PERIPHERAL",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Test board peripheral lines and shift register"
    },

    /* 13 ACTUATE */
    {
        .cmd_id = NEXUS_CMD_ACTUATE_RELAY,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x01U,
        .verb_name = "ACTUATE",
        .noun_name = "RELAY",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Relay K1 hardware unmounted on this build"
    },
    {
        .cmd_id = NEXUS_CMD_ACTUATE_LED,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x02U,
        .verb_name = "ACTUATE",
        .noun_name = "LED",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Set onboard LED state (LED1..4)"
    },
    {
        .cmd_id = NEXUS_CMD_ACTUATE_MOTOR,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x03U,
        .verb_name = "ACTUATE",
        .noun_name = "MOTOR",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "DC Motors unmounted on this build"
    },
    {
        .cmd_id = NEXUS_CMD_ACTUATE_SERVO,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x04U,
        .verb_name = "ACTUATE",
        .noun_name = "SERVO",
        .disposition = NEXUS_CMD_DISP_UNSUPPORTED,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = false,
        .description = "Servo motor unmounted on GPIO33 on this build"
    },
    {
        .cmd_id = NEXUS_CMD_ACTUATE_BUZZER,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x05U,
        .verb_name = "ACTUATE",
        .noun_name = "BUZZER",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Beep onboard 5V buzzer for bounded duration"
    },
    {
        .cmd_id = NEXUS_CMD_ACTUATE_SHIFT_REGISTER,
        .verb_code = NEXUS_VERB_ACTUATE,
        .noun_code = 0x06U,
        .verb_name = "ACTUATE",
        .noun_name = "SHIFT_REGISTER",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Shift 8-bit output pattern to 74HC595"
    },

    /* 14 CAPTURE */
    {
        .cmd_id = NEXUS_CMD_CAPTURE_TELEMETRY,
        .verb_code = NEXUS_VERB_CAPTURE,
        .noun_code = 0x01U,
        .verb_name = "CAPTURE",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Capture instantaneous telemetry snapshot"
    },
    {
        .cmd_id = NEXUS_CMD_CAPTURE_SENSOR_SNAPSHOT,
        .verb_code = NEXUS_VERB_CAPTURE,
        .noun_code = 0x02U,
        .verb_name = "CAPTURE",
        .noun_name = "SENSOR_SNAPSHOT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Capture snapshot of all active sensor channels"
    },
    {
        .cmd_id = NEXUS_CMD_CAPTURE_EVENT_SNAPSHOT,
        .verb_code = NEXUS_VERB_CAPTURE,
        .noun_code = 0x03U,
        .verb_name = "CAPTURE",
        .noun_name = "EVENT_SNAPSHOT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Capture snapshot of recent event queue entries"
    },

    /* 15 PUBLISH */
    {
        .cmd_id = NEXUS_CMD_PUBLISH_TELEMETRY,
        .verb_code = NEXUS_VERB_PUBLISH,
        .noun_code = 0x01U,
        .verb_name = "PUBLISH",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Immediately transmit current telemetry frame"
    },
    {
        .cmd_id = NEXUS_CMD_PUBLISH_EVENT,
        .verb_code = NEXUS_VERB_PUBLISH,
        .noun_code = 0x02U,
        .verb_name = "PUBLISH",
        .noun_name = "EVENT",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Publish high-priority event notification"
    },
    {
        .cmd_id = NEXUS_CMD_PUBLISH_STATUS,
        .verb_code = NEXUS_VERB_PUBLISH,
        .noun_code = 0x03U,
        .verb_name = "PUBLISH",
        .noun_name = "STATUS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Publish heartbeat status envelope"
    },

    /* 16 DISPLAY */
    {
        .cmd_id = NEXUS_CMD_DISPLAY_STATUS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x01U,
        .verb_name = "DISPLAY",
        .noun_name = "STATUS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format active device and executive status"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_EXECUTIVE,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x02U,
        .verb_name = "DISPLAY",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format executive metrics (dispatch, complete, fail, misses)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_QUEUES,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x03U,
        .verb_name = "DISPLAY",
        .noun_name = "QUEUES",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format ready and event queue depths and watermarks"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_FAULTS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x04U,
        .verb_name = "DISPLAY",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format fault summary"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_SENSORS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x05U,
        .verb_name = "DISPLAY",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format comprehensive summary of all registered sensors"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_TRANSPORTS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x06U,
        .verb_name = "DISPLAY",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format active connection status and transport stats"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_CONFIGURATION,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x07U,
        .verb_name = "DISPLAY",
        .noun_name = "CONFIGURATION",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format current device configuration"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_ENVIRONMENT,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x41U,
        .verb_name = "DISPLAY",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format environmental sensor readings (DHT11 temp and humidity)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_LIGHT,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x42U,
        .verb_name = "DISPLAY",
        .noun_name = "LIGHT",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format light sensor readings (LDR ADC raw)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_DISTANCE,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x43U,
        .verb_name = "DISPLAY",
        .noun_name = "DISTANCE",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format HC-SR04 ultrasonic distance reading"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_ANALOG,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x44U,
        .verb_name = "DISPLAY",
        .noun_name = "ANALOG",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format analog multiplexer readings (CD4051 X0 Gas, X1 Hall)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_MOTION,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x45U,
        .verb_name = "DISPLAY",
        .noun_name = "MOTION",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format optical motion readings (MOC7811 slot opto)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_EVENTS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x46U,
        .verb_name = "DISPLAY",
        .noun_name = "EVENTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format event queue counters"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_ACTUATORS,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x47U,
        .verb_name = "DISPLAY",
        .noun_name = "ACTUATORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format current status of board actuators (LEDs, Buzzer, Shift Register)"
    },
    {
        .cmd_id = NEXUS_CMD_DISPLAY_CONNECTIVITY,
        .verb_code = NEXUS_VERB_DISPLAY,
        .noun_code = 0x48U,
        .verb_name = "DISPLAY",
        .noun_name = "CONNECTIVITY",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format Wi-Fi, IP, and broker connectivity details"
    },

    /* 17 HISTORY */
    {
        .cmd_id = NEXUS_CMD_HISTORY_EVENTS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x01U,
        .verb_name = "HISTORY",
        .noun_name = "EVENTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format recent event logs from memory ring buffer"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_FAULTS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x02U,
        .verb_name = "HISTORY",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format historical fault logs"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_EXECUTIVE,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x03U,
        .verb_name = "HISTORY",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format historical executive latency milestones"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_SENSORS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x04U,
        .verb_name = "HISTORY",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format sensor transition history"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_TRANSPORTS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x05U,
        .verb_name = "HISTORY",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format transport state transition history"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_ENVIRONMENT,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x41U,
        .verb_name = "HISTORY",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format environmental history snapshots"
    },
    {
        .cmd_id = NEXUS_CMD_HISTORY_SENSOR_READINGS,
        .verb_code = NEXUS_VERB_HISTORY,
        .noun_code = 0x42U,
        .verb_name = "HISTORY",
        .noun_name = "SENSOR_READINGS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format recent sensor reading trends"
    },

    /* 24 DIAGNOSTICS */
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_SYSTEM,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x01U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format full system diagnostics (heap, reset reason, uptime)"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_SENSORS,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x02U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "SENSORS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format sensor diagnostics (read counts, error rates, valid flags)"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_QUEUES,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x03U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "QUEUES",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format queue high water marks and overflow tallies"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_TIMING,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x04U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "TIMING",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format execution timing (max dispatch latency, job durations)"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_MEMORY,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x05U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "MEMORY",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format memory heap usage and minimum watermark"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_TRANSPORTS,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x06U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "TRANSPORTS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Format transport throughput and error counters"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_EXECUTIVE,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x07U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format executive priority class stats and scheduling health"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_PERIPHERALS,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x08U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "PERIPHERALS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Format peripheral bus and GPIO diagnostics"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_DATABASE,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x09U,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "DATABASE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Check InfluxDB time-series database health from ground station"
    },
    {
        .cmd_id = NEXUS_CMD_DIAGNOSTICS_AI_SERVICE,
        .verb_code = NEXUS_VERB_DIAGNOSTICS,
        .noun_code = 0x0AU,
        .verb_name = "DIAGNOSTICS",
        .noun_name = "AI_SERVICE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Check Open WebUI and local LLM service reachability"
    },

    /* 30 OPEN */
    {
        .cmd_id = NEXUS_CMD_OPEN_DASHBOARD,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x01U,
        .verb_name = "OPEN",
        .noun_name = "DASHBOARD",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Open Grafana telemetry dashboard on operator workstation"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_LOGS,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x02U,
        .verb_name = "OPEN",
        .noun_name = "LOGS",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Open operational log explorer in browser"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_AI,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x03U,
        .verb_name = "OPEN",
        .noun_name = "AI",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Open Open WebUI AI assistant interface"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_GROUND,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x04U,
        .verb_name = "OPEN",
        .noun_name = "GROUND",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Open NEXUS Ground Station web control panel"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_DATABASE,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x05U,
        .verb_name = "OPEN",
        .noun_name = "DATABASE",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Open InfluxDB web UI"
    },
    {
        .cmd_id = NEXUS_CMD_OPEN_DIAGNOSTICS,
        .verb_code = NEXUS_VERB_OPEN,
        .noun_code = 0x06U,
        .verb_name = "OPEN",
        .noun_name = "DIAGNOSTICS",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Open ground station diagnostics view"
    },

    /* 31 ASK */
    {
        .cmd_id = NEXUS_CMD_ASK_SYSTEM,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = 0x01U,
        .verb_name = "ASK",
        .noun_name = "SYSTEM",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Query AI assistant about system operational status"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_SENSOR,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = 0x02U,
        .verb_name = "ASK",
        .noun_name = "SENSOR",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Query AI assistant about specific sensor trends and anomalies"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_EXECUTIVE,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = 0x03U,
        .verb_name = "ASK",
        .noun_name = "EXECUTIVE",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Query AI assistant about executive scheduling and timing"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_DIAGNOSTICS,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = 0x04U,
        .verb_name = "ASK",
        .noun_name = "DIAGNOSTICS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Query AI assistant for diagnostic health analysis"
    },
    {
        .cmd_id = NEXUS_CMD_ASK_ENVIRONMENT,
        .verb_code = NEXUS_VERB_ASK,
        .noun_code = 0x41U,
        .verb_name = "ASK",
        .noun_name = "ENVIRONMENT",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Query AI assistant regarding environmental conditions"
    },

    /* 32 EXPORT */
    {
        .cmd_id = NEXUS_CMD_EXPORT_TELEMETRY,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = 0x01U,
        .verb_name = "EXPORT",
        .noun_name = "TELEMETRY",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Export telemetry data to JSON or CSV via ground station"
    },
    {
        .cmd_id = NEXUS_CMD_EXPORT_DIAGNOSTICS,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = 0x02U,
        .verb_name = "EXPORT",
        .noun_name = "DIAGNOSTICS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Export diagnostic snapshot from ground station"
    },
    {
        .cmd_id = NEXUS_CMD_EXPORT_EVENTS,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = 0x03U,
        .verb_name = "EXPORT",
        .noun_name = "EVENTS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Export recorded incident events"
    },
    {
        .cmd_id = NEXUS_CMD_EXPORT_FAULTS,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = 0x04U,
        .verb_name = "EXPORT",
        .noun_name = "FAULTS",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Export recorded fault history"
    },
    {
        .cmd_id = NEXUS_CMD_EXPORT_CONFIGURATION,
        .verb_code = NEXUS_VERB_EXPORT,
        .noun_code = 0x05U,
        .verb_name = "EXPORT",
        .noun_name = "CONFIGURATION",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_GROUND_STATION,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Export current configuration manifest"
    },

    /* 33 RUN */
    {
        .cmd_id = NEXUS_CMD_RUN_SELF_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = 0x01U,
        .verb_name = "RUN",
        .noun_name = "SELF_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Run bounded executive and data structure self-test"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_SENSOR_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = 0x02U,
        .verb_name = "RUN",
        .noun_name = "SENSOR_TEST",
        .disposition = NEXUS_CMD_DISP_REQUIRED_M8,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = true,
        .is_supported = true,
        .description = "Run live hardware sensor diagnostics validation"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_STRESS_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = 0x03U,
        .verb_name = "RUN",
        .noun_name = "STRESS_TEST",
        .disposition = NEXUS_CMD_DISP_DEFERRED_M9_M10,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Run bounded executive queue stress test"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_TRANSPORT_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = 0x04U,
        .verb_name = "RUN",
        .noun_name = "TRANSPORT_TEST",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Run end-to-end transport roundtrip latency test"
    },
    {
        .cmd_id = NEXUS_CMD_RUN_QUALIFICATION_TEST,
        .verb_code = NEXUS_VERB_RUN,
        .noun_code = 0x05U,
        .verb_name = "RUN",
        .noun_name = "QUALIFICATION_TEST",
        .disposition = NEXUS_CMD_DISP_EXISTING_CAPABILITY,
        .destination = NEXUS_CMD_DEST_FIRMWARE,
        .is_supported_m8 = false,
        .is_supported = true,
        .description = "Run qualification test verification suite"
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

bool nexus_cmd_registry_is_supported(uint16_t cmd_id)
{
    const nexus_cmd_registry_entry_t *entry = nexus_cmd_registry_lookup_by_id(cmd_id);
    return (entry != NULL && entry->is_supported);
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
