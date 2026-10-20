#ifndef NEXUS_COMMAND_REGISTRY_H
#define NEXUS_COMMAND_REGISTRY_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Canonical Verb Codes */
#define NEXUS_VERB_NOP          0x00U
#define NEXUS_VERB_INITIALIZE   0x01U
#define NEXUS_VERB_START        0x02U
#define NEXUS_VERB_STOP         0x03U
#define NEXUS_VERB_RESET        0x04U
#define NEXUS_VERB_SET          0x05U
#define NEXUS_VERB_GET          0x06U
#define NEXUS_VERB_DISPLAY      0x10U /* 16 */
#define NEXUS_VERB_HISTORY      0x11U /* 17 */
#define NEXUS_VERB_DIAGNOSTICS  0x18U /* 24 */
#define NEXUS_VERB_OPEN         0x1EU /* 30 */
#define NEXUS_VERB_ASK          0x1FU /* 31 */
#define NEXUS_VERB_EXPORT       0x20U /* 32 */
#define NEXUS_VERB_RUN          0x21U /* 33 */

/* Canonical Noun Codes */
#define NEXUS_NOUN_NONE             0x00U

/* Generic nouns */
#define NEXUS_NOUN_SYSTEM           0x01U
#define NEXUS_NOUN_SENSORS          0x02U
#define NEXUS_NOUN_TRANSPORTS       0x03U
#define NEXUS_NOUN_TELEMETRY        0x03U
#define NEXUS_NOUN_SELF_TEST        0x04U

/* RESET nouns */
#define NEXUS_NOUN_RESET_FAULTS     0x01U
#define NEXUS_NOUN_RESET_STATISTICS 0x02U

/* SET nouns */
#define NEXUS_NOUN_PRIORITY         0x01U
#define NEXUS_NOUN_SAMPLE_INTERVAL  0x02U
#define NEXUS_NOUN_THRESHOLD        0x03U

/* GET nouns */
#define NEXUS_NOUN_STATUS           0x01U
#define NEXUS_NOUN_CONFIGURATION    0x02U
#define NEXUS_NOUN_SENSOR_LIST      0x03U
#define NEXUS_NOUN_TIME             0x04U

/* DISPLAY nouns */
#define NEXUS_NOUN_DISP_STATUS      0x01U
#define NEXUS_NOUN_DISP_EXECUTIVE   0x02U
#define NEXUS_NOUN_DISP_QUEUES      0x03U
#define NEXUS_NOUN_DISP_FAULTS      0x04U
#define NEXUS_NOUN_DISP_ENVIRONMENT 0x41U /* 65 */
#define NEXUS_NOUN_DISP_LIGHT       0x42U /* 66 */
#define NEXUS_NOUN_DISP_DISTANCE    0x43U /* 67 */
#define NEXUS_NOUN_DISP_ANALOG      0x44U /* 68 */
#define NEXUS_NOUN_DISP_MOTION      0x45U /* 69 */
#define NEXUS_NOUN_DISP_EVENTS      0x46U /* 70 */

/* HISTORY nouns */
#define NEXUS_NOUN_HIST_EVENTS      0x01U
#define NEXUS_NOUN_HIST_FAULTS      0x02U
#define NEXUS_NOUN_HIST_EXECUTIVE   0x03U
#define NEXUS_NOUN_HIST_ENVIRONMENT 0x41U
#define NEXUS_NOUN_HIST_SENSORS     0x42U

/* DIAGNOSTICS nouns */
#define NEXUS_NOUN_DIAG_SYSTEM      0x01U
#define NEXUS_NOUN_DIAG_SENSORS     0x02U
#define NEXUS_NOUN_DIAG_QUEUES      0x03U
#define NEXUS_NOUN_DIAG_TIMING      0x04U
#define NEXUS_NOUN_DIAG_MEMORY      0x05U
#define NEXUS_NOUN_DIAG_TRANSPORTS  0x06U

/* OPEN nouns */
#define NEXUS_NOUN_DASHBOARD        0x01U
#define NEXUS_NOUN_LOGS             0x02U
#define NEXUS_NOUN_AI               0x03U
#define NEXUS_NOUN_GROUND           0x04U

/* ASK nouns */
#define NEXUS_NOUN_ASK_SYSTEM       0x01U
#define NEXUS_NOUN_ASK_ENVIRONMENT  0x41U
#define NEXUS_NOUN_ASK_SENSOR       0x42U

/* EXPORT nouns */
#define NEXUS_NOUN_EXP_TELEMETRY    0x01U
#define NEXUS_NOUN_EXP_DIAGNOSTICS  0x02U

/* RUN nouns */
#define NEXUS_NOUN_RUN_SELF_TEST    0x01U
#define NEXUS_NOUN_RUN_SENSOR_TEST  0x02U
#define NEXUS_NOUN_RUN_STRESS_TEST  0x03U

/* Canonical Command ID Macro: (verb << 8) | noun */
#define NEXUS_CMD_ID(verb, noun) (((uint16_t)(verb) << 8) | (uint16_t)(noun))

/* Canonical Command IDs */
#define NEXUS_CMD_NOP_NONE                  NEXUS_CMD_ID(NEXUS_VERB_NOP, NEXUS_NOUN_NONE)                     /* 0x0000 = 0 */
#define NEXUS_CMD_INITIALIZE_SYSTEM         NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, NEXUS_NOUN_SYSTEM)            /* 0x0101 = 257 */
#define NEXUS_CMD_INITIALIZE_SENSORS        NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, NEXUS_NOUN_SENSORS)           /* 0x0102 = 258 */
#define NEXUS_CMD_INITIALIZE_TRANSPORTS     NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, NEXUS_NOUN_TRANSPORTS)        /* 0x0103 = 259 */
#define NEXUS_CMD_START_SYSTEM              NEXUS_CMD_ID(NEXUS_VERB_START, NEXUS_NOUN_SYSTEM)                 /* 0x0201 = 513 */
#define NEXUS_CMD_START_SENSORS             NEXUS_CMD_ID(NEXUS_VERB_START, NEXUS_NOUN_SENSORS)                /* 0x0202 = 514 */
#define NEXUS_CMD_START_TELEMETRY           NEXUS_CMD_ID(NEXUS_VERB_START, NEXUS_NOUN_TELEMETRY)              /* 0x0203 = 515 */
#define NEXUS_CMD_START_SELF_TEST           NEXUS_CMD_ID(NEXUS_VERB_START, NEXUS_NOUN_SELF_TEST)              /* 0x0204 = 516 */
#define NEXUS_CMD_STOP_SENSORS              NEXUS_CMD_ID(NEXUS_VERB_STOP, NEXUS_NOUN_SENSORS)                 /* 0x0302 = 770 */
#define NEXUS_CMD_STOP_TELEMETRY            NEXUS_CMD_ID(NEXUS_VERB_STOP, NEXUS_NOUN_TELEMETRY)               /* 0x0303 = 771 */
#define NEXUS_CMD_RESET_FAULTS              NEXUS_CMD_ID(NEXUS_VERB_RESET, NEXUS_NOUN_RESET_FAULTS)           /* 0x0401 = 1025 */
#define NEXUS_CMD_RESET_STATISTICS          NEXUS_CMD_ID(NEXUS_VERB_RESET, NEXUS_NOUN_RESET_STATISTICS)       /* 0x0402 = 1026 */
#define NEXUS_CMD_SET_PRIORITY              NEXUS_CMD_ID(NEXUS_VERB_SET, NEXUS_NOUN_PRIORITY)                 /* 0x0501 = 1281 */
#define NEXUS_CMD_SET_SAMPLE_INTERVAL       NEXUS_CMD_ID(NEXUS_VERB_SET, NEXUS_NOUN_SAMPLE_INTERVAL)          /* 0x0502 = 1282 */
#define NEXUS_CMD_SET_THRESHOLD            NEXUS_CMD_ID(NEXUS_VERB_SET, NEXUS_NOUN_THRESHOLD)                /* 0x0503 = 1283 */
#define NEXUS_CMD_GET_STATUS                NEXUS_CMD_ID(NEXUS_VERB_GET, NEXUS_NOUN_STATUS)                   /* 0x0601 = 1537 */
#define NEXUS_CMD_GET_CONFIGURATION         NEXUS_CMD_ID(NEXUS_VERB_GET, NEXUS_NOUN_CONFIGURATION)            /* 0x0602 = 1538 */
#define NEXUS_CMD_GET_SENSOR_LIST           NEXUS_CMD_ID(NEXUS_VERB_GET, NEXUS_NOUN_SENSOR_LIST)              /* 0x0603 = 1539 */
#define NEXUS_CMD_GET_TIME                  NEXUS_CMD_ID(NEXUS_VERB_GET, NEXUS_NOUN_TIME)                     /* 0x0604 = 1540 */
#define NEXUS_CMD_DISPLAY_STATUS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_STATUS)          /* 0x1001 = 4097 */
#define NEXUS_CMD_DISPLAY_EXECUTIVE         NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_EXECUTIVE)       /* 0x1002 = 4098 */
#define NEXUS_CMD_DISPLAY_QUEUES            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_QUEUES)          /* 0x1003 = 4099 */
#define NEXUS_CMD_DISPLAY_FAULTS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_FAULTS)          /* 0x1004 = 4100 */
#define NEXUS_CMD_DISPLAY_ENVIRONMENT       NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_ENVIRONMENT)     /* 0x1041 = 4161 */
#define NEXUS_CMD_DISPLAY_LIGHT             NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_LIGHT)           /* 0x1042 = 4162 */
#define NEXUS_CMD_DISPLAY_DISTANCE          NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_DISTANCE)        /* 0x1043 = 4163 */
#define NEXUS_CMD_DISPLAY_ANALOG            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_ANALOG)          /* 0x1044 = 4164 */
#define NEXUS_CMD_DISPLAY_MOTION            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_MOTION)          /* 0x1045 = 4165 */
#define NEXUS_CMD_DISPLAY_EVENTS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, NEXUS_NOUN_DISP_EVENTS)          /* 0x1046 = 4166 */
#define NEXUS_CMD_HISTORY_EVENTS            NEXUS_CMD_ID(NEXUS_VERB_HISTORY, NEXUS_NOUN_HIST_EVENTS)          /* 0x1101 = 4353 */
#define NEXUS_CMD_HISTORY_FAULTS            NEXUS_CMD_ID(NEXUS_VERB_HISTORY, NEXUS_NOUN_HIST_FAULTS)          /* 0x1102 = 4354 */
#define NEXUS_CMD_HISTORY_EXECUTIVE         NEXUS_CMD_ID(NEXUS_VERB_HISTORY, NEXUS_NOUN_HIST_EXECUTIVE)       /* 0x1103 = 4355 */
#define NEXUS_CMD_HISTORY_ENVIRONMENT       NEXUS_CMD_ID(NEXUS_VERB_HISTORY, NEXUS_NOUN_HIST_ENVIRONMENT)     /* 0x1141 = 4417 */
#define NEXUS_CMD_HISTORY_SENSORS           NEXUS_CMD_ID(NEXUS_VERB_HISTORY, NEXUS_NOUN_HIST_SENSORS)         /* 0x1142 = 4418 */
#define NEXUS_CMD_DIAGNOSTICS_SYSTEM        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_SYSTEM)      /* 0x1801 = 6145 */
#define NEXUS_CMD_DIAGNOSTICS_SENSORS       NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_SENSORS)     /* 0x1802 = 6146 */
#define NEXUS_CMD_DIAGNOSTICS_QUEUES        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_QUEUES)      /* 0x1803 = 6147 */
#define NEXUS_CMD_DIAGNOSTICS_TIMING        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_TIMING)      /* 0x1804 = 6148 */
#define NEXUS_CMD_DIAGNOSTICS_MEMORY        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_MEMORY)      /* 0x1805 = 6149 */
#define NEXUS_CMD_DIAGNOSTICS_TRANSPORTS    NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, NEXUS_NOUN_DIAG_TRANSPORTS)  /* 0x1806 = 6150 */
#define NEXUS_CMD_OPEN_DASHBOARD            NEXUS_CMD_ID(NEXUS_VERB_OPEN, NEXUS_NOUN_DASHBOARD)               /* 0x1E01 = 7681 */
#define NEXUS_CMD_OPEN_LOGS                 NEXUS_CMD_ID(NEXUS_VERB_OPEN, NEXUS_NOUN_LOGS)                    /* 0x1E02 = 7682 */
#define NEXUS_CMD_OPEN_AI                   NEXUS_CMD_ID(NEXUS_VERB_OPEN, NEXUS_NOUN_AI)                      /* 0x1E03 = 7683 */
#define NEXUS_CMD_OPEN_GROUND               NEXUS_CMD_ID(NEXUS_VERB_OPEN, NEXUS_NOUN_GROUND)                  /* 0x1E04 = 7684 */
#define NEXUS_CMD_ASK_SYSTEM                NEXUS_CMD_ID(NEXUS_VERB_ASK, NEXUS_NOUN_ASK_SYSTEM)               /* 0x1F01 = 7937 */
#define NEXUS_CMD_ASK_ENVIRONMENT           NEXUS_CMD_ID(NEXUS_VERB_ASK, NEXUS_NOUN_ASK_ENVIRONMENT)          /* 0x1F41 = 8001 */
#define NEXUS_CMD_ASK_SENSOR                NEXUS_CMD_ID(NEXUS_VERB_ASK, NEXUS_NOUN_ASK_SENSOR)               /* 0x1F42 = 8002 */
#define NEXUS_CMD_EXPORT_TELEMETRY          NEXUS_CMD_ID(NEXUS_VERB_EXPORT, NEXUS_NOUN_EXP_TELEMETRY)         /* 0x2001 = 8193 */
#define NEXUS_CMD_EXPORT_DIAGNOSTICS        NEXUS_CMD_ID(NEXUS_VERB_EXPORT, NEXUS_NOUN_EXP_DIAGNOSTICS)       /* 0x2002 = 8194 */
#define NEXUS_CMD_RUN_SELF_TEST             NEXUS_CMD_ID(NEXUS_VERB_RUN, NEXUS_NOUN_RUN_SELF_TEST)            /* 0x2101 = 8449 */
#define NEXUS_CMD_RUN_SENSOR_TEST           NEXUS_CMD_ID(NEXUS_VERB_RUN, NEXUS_NOUN_RUN_SENSOR_TEST)          /* 0x2102 = 8450 */
#define NEXUS_CMD_RUN_STRESS_TEST           NEXUS_CMD_ID(NEXUS_VERB_RUN, NEXUS_NOUN_RUN_STRESS_TEST)          /* 0x2103 = 8451 */

/* Milestone Disposition Enum */
typedef enum {
    NEXUS_CMD_DISP_REQUIRED_M8 = 0,
    NEXUS_CMD_DISP_EXISTING_CAPABILITY = 1,
    NEXUS_CMD_DISP_DEFERRED_M9_M10 = 2,
    NEXUS_CMD_DISP_UNSUPPORTED = 3,
    NEXUS_CMD_DISP_NOT_REQUIRED = 4
} nexus_cmd_disposition_t;

/* Target Destination Enum */
typedef enum {
    NEXUS_CMD_DEST_FIRMWARE = 0,
    NEXUS_CMD_DEST_GROUND_STATION = 1,
    NEXUS_CMD_DEST_TEST_HARNESS = 2
} nexus_cmd_destination_t;

/* Response Status Code */
typedef enum {
    NEXUS_CMD_STATUS_OK = 0,
    NEXUS_CMD_STATUS_REJECTED = 1,
    NEXUS_CMD_STATUS_UNKNOWN_CMD = 2,
    NEXUS_CMD_STATUS_UNSUPPORTED = 3,
    NEXUS_CMD_STATUS_FAILED = 4,
    NEXUS_CMD_STATUS_DUPLICATE = 5
} nexus_cmd_status_code_t;

/* Registry Entry Structure */
typedef struct {
    uint16_t cmd_id;
    uint8_t verb_code;
    uint8_t noun_code;
    const char *verb_name;
    const char *noun_name;
    nexus_cmd_disposition_t disposition;
    nexus_cmd_destination_t destination;
    bool is_supported_m8;
    const char *description;
} nexus_cmd_registry_entry_t;

/* Total candidate commands count */
#define NEXUS_CANDIDATE_COMMANDS_COUNT 52U

/* Lookup and validation APIs */
const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_id(uint16_t cmd_id);
const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_name(const char *verb, const char *noun);
bool nexus_cmd_registry_is_supported_m8(uint16_t cmd_id);
const nexus_cmd_registry_entry_t *nexus_cmd_registry_get_all(size_t *out_count);

const char *nexus_cmd_disposition_str(nexus_cmd_disposition_t disp);
const char *nexus_cmd_status_code_str(nexus_cmd_status_code_t code);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_COMMAND_REGISTRY_H */
