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
#define NEXUS_VERB_ENABLE       0x07U
#define NEXUS_VERB_DISABLE      0x08U
#define NEXUS_VERB_CALIBRATE    0x09U
#define NEXUS_VERB_ACKNOWLEDGE  0x0AU
#define NEXUS_VERB_CLEAR        0x0BU
#define NEXUS_VERB_TEST         0x0CU
#define NEXUS_VERB_ACTUATE      0x0DU
#define NEXUS_VERB_CAPTURE      0x0EU
#define NEXUS_VERB_PUBLISH      0x0FU
#define NEXUS_VERB_DISPLAY      0x10U /* 16 */
#define NEXUS_VERB_HISTORY      0x11U /* 17 */
#define NEXUS_VERB_DIAGNOSTICS  0x18U /* 24 */
#define NEXUS_VERB_OPEN         0x1EU /* 30 */
#define NEXUS_VERB_ASK          0x1FU /* 31 */
#define NEXUS_VERB_EXPORT       0x20U /* 32 */
#define NEXUS_VERB_RUN          0x21U /* 33 */

/* Canonical Noun Codes */
#define NEXUS_NOUN_NONE                 0x00U

/* Generic nouns */
#define NEXUS_NOUN_SYSTEM               0x01U
#define NEXUS_NOUN_SENSORS              0x02U
#define NEXUS_NOUN_TRANSPORTS           0x03U
#define NEXUS_NOUN_TELEMETRY            0x03U
#define NEXUS_NOUN_SELF_TEST            0x04U
#define NEXUS_NOUN_EXECUTIVE            0x04U

/* RESET nouns */
#define NEXUS_NOUN_RESET_FAULTS         0x01U
#define NEXUS_NOUN_RESET_STATISTICS     0x02U
#define NEXUS_NOUN_RESET_SENSOR_STATE   0x03U
#define NEXUS_NOUN_RESET_QUEUES         0x04U

/* SET nouns */
#define NEXUS_NOUN_PRIORITY             0x01U
#define NEXUS_NOUN_SAMPLE_INTERVAL      0x02U
#define NEXUS_NOUN_THRESHOLD            0x03U
#define NEXUS_NOUN_SENSOR_ENABLE        0x04U
#define NEXUS_NOUN_TRANSPORT_PREF       0x05U
#define NEXUS_NOUN_CONFIGURATION        0x06U

/* GET nouns */
#define NEXUS_NOUN_STATUS               0x01U
#define NEXUS_NOUN_GET_CONFIGURATION    0x02U
#define NEXUS_NOUN_SENSOR_LIST          0x03U
#define NEXUS_NOUN_TIME                 0x04U
#define NEXUS_NOUN_VERSION              0x05U
#define NEXUS_NOUN_HEALTH               0x06U
#define NEXUS_NOUN_CAPABILITIES         0x07U

/* ENABLE / DISABLE nouns */
#define NEXUS_NOUN_EN_SENSOR            0x01U
#define NEXUS_NOUN_EN_TRANSPORT         0x02U
#define NEXUS_NOUN_EN_TELEMETRY         0x03U

/* CALIBRATE nouns */
#define NEXUS_NOUN_CAL_SENSOR           0x01U
#define NEXUS_NOUN_CAL_ANALOG           0x02U
#define NEXUS_NOUN_CAL_ENVIRONMENT      0x03U

/* ACKNOWLEDGE nouns */
#define NEXUS_NOUN_ACK_FAULT            0x01U
#define NEXUS_NOUN_ACK_WARNING          0x02U
#define NEXUS_NOUN_ACK_EVENT            0x03U

/* CLEAR nouns */
#define NEXUS_NOUN_CLR_FAULTS           0x01U
#define NEXUS_NOUN_CLR_HISTORY          0x02U
#define NEXUS_NOUN_CLR_STATISTICS       0x03U

/* TEST nouns */
#define NEXUS_NOUN_TEST_SENSOR          0x01U
#define NEXUS_NOUN_TEST_TRANSPORT       0x02U
#define NEXUS_NOUN_TEST_EXECUTIVE       0x03U
#define NEXUS_NOUN_TEST_PERIPHERAL      0x04U

/* ACTUATE nouns */
#define NEXUS_NOUN_ACT_RELAY            0x01U
#define NEXUS_NOUN_ACT_LED              0x02U
#define NEXUS_NOUN_ACT_MOTOR            0x03U
#define NEXUS_NOUN_ACT_SERVO            0x04U
#define NEXUS_NOUN_ACT_BUZZER           0x05U
#define NEXUS_NOUN_ACT_SHIFT_REG        0x06U

/* CAPTURE nouns */
#define NEXUS_NOUN_CAP_TELEMETRY        0x01U
#define NEXUS_NOUN_CAP_SENSOR_SNAP      0x02U
#define NEXUS_NOUN_CAP_EVENT_SNAP       0x03U

/* PUBLISH nouns */
#define NEXUS_NOUN_PUB_TELEMETRY        0x01U
#define NEXUS_NOUN_PUB_EVENT            0x02U
#define NEXUS_NOUN_PUB_STATUS           0x03U

/* DISPLAY nouns */
#define NEXUS_NOUN_DISP_STATUS          0x01U
#define NEXUS_NOUN_DISP_EXECUTIVE       0x02U
#define NEXUS_NOUN_DISP_QUEUES          0x03U
#define NEXUS_NOUN_DISP_FAULTS          0x04U
#define NEXUS_NOUN_DISP_SENSORS         0x05U
#define NEXUS_NOUN_DISP_TRANSPORTS      0x06U
#define NEXUS_NOUN_DISP_CONFIGURATION   0x07U
#define NEXUS_NOUN_DISP_ENVIRONMENT     0x41U /* 65 */
#define NEXUS_NOUN_DISP_LIGHT           0x42U /* 66 */
#define NEXUS_NOUN_DISP_DISTANCE        0x43U /* 67 */
#define NEXUS_NOUN_DISP_ANALOG          0x44U /* 68 */
#define NEXUS_NOUN_DISP_MOTION          0x45U /* 69 */
#define NEXUS_NOUN_DISP_EVENTS          0x46U /* 70 */
#define NEXUS_NOUN_DISP_ACTUATORS       0x47U /* 71 */
#define NEXUS_NOUN_DISP_CONNECTIVITY    0x48U /* 72 */

/* HISTORY nouns */
#define NEXUS_NOUN_HIST_EVENTS          0x01U
#define NEXUS_NOUN_HIST_FAULTS          0x02U
#define NEXUS_NOUN_HIST_EXECUTIVE       0x03U
#define NEXUS_NOUN_HIST_SENSORS         0x04U
#define NEXUS_NOUN_HIST_TRANSPORTS      0x05U
#define NEXUS_NOUN_HIST_ENVIRONMENT     0x41U /* 65 */
#define NEXUS_NOUN_HIST_SENSOR_READINGS 0x42U /* 66 */

/* DIAGNOSTICS nouns */
#define NEXUS_NOUN_DIAG_SYSTEM          0x01U
#define NEXUS_NOUN_DIAG_SENSORS         0x02U
#define NEXUS_NOUN_DIAG_QUEUES          0x03U
#define NEXUS_NOUN_DIAG_TIMING          0x04U
#define NEXUS_NOUN_DIAG_MEMORY          0x05U
#define NEXUS_NOUN_DIAG_TRANSPORTS      0x06U
#define NEXUS_NOUN_DIAG_EXECUTIVE       0x07U
#define NEXUS_NOUN_DIAG_PERIPHERALS     0x08U
#define NEXUS_NOUN_DIAG_DATABASE        0x09U
#define NEXUS_NOUN_DIAG_AI_SERVICE      0x0AU

/* OPEN nouns */
#define NEXUS_NOUN_DASHBOARD            0x01U
#define NEXUS_NOUN_LOGS                 0x02U
#define NEXUS_NOUN_AI                   0x03U
#define NEXUS_NOUN_GROUND               0x04U
#define NEXUS_NOUN_DATABASE             0x05U
#define NEXUS_NOUN_DIAGNOSTICS          0x06U

/* ASK nouns */
#define NEXUS_NOUN_ASK_SYSTEM           0x01U
#define NEXUS_NOUN_ASK_SENSOR           0x02U
#define NEXUS_NOUN_ASK_EXECUTIVE        0x03U
#define NEXUS_NOUN_ASK_DIAGNOSTICS      0x04U
#define NEXUS_NOUN_ASK_ENVIRONMENT      0x41U /* 65 */

/* EXPORT nouns */
#define NEXUS_NOUN_EXP_TELEMETRY        0x01U
#define NEXUS_NOUN_EXP_DIAGNOSTICS      0x02U
#define NEXUS_NOUN_EXP_EVENTS           0x03U
#define NEXUS_NOUN_EXP_FAULTS           0x04U
#define NEXUS_NOUN_EXP_CONFIGURATION    0x05U

/* RUN nouns */
#define NEXUS_NOUN_RUN_SELF_TEST        0x01U
#define NEXUS_NOUN_RUN_SENSOR_TEST      0x02U
#define NEXUS_NOUN_RUN_STRESS_TEST      0x03U
#define NEXUS_NOUN_RUN_TRANSPORT_TEST   0x04U
#define NEXUS_NOUN_RUN_QUAL_TEST        0x05U

/* Canonical Command ID Macro: (verb << 8) | noun */
#define NEXUS_CMD_ID(verb, noun) (((uint16_t)(verb) << 8) | (uint16_t)(noun))

/* Canonical Command IDs */
/* 00 NOP */
#define NEXUS_CMD_NOP_NONE                  NEXUS_CMD_ID(NEXUS_VERB_NOP, NEXUS_NOUN_NONE)                     /* 0x0000 = 0 */

/* 01 INITIALIZE */
#define NEXUS_CMD_INITIALIZE_SYSTEM         NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, 0x01U)                        /* 0x0101 = 257 */
#define NEXUS_CMD_INITIALIZE_SENSORS        NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, 0x02U)                        /* 0x0102 = 258 */
#define NEXUS_CMD_INITIALIZE_TRANSPORTS     NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, 0x03U)                        /* 0x0103 = 259 */
#define NEXUS_CMD_INITIALIZE_EXECUTIVE      NEXUS_CMD_ID(NEXUS_VERB_INITIALIZE, 0x04U)                        /* 0x0104 = 260 */

/* 02 START */
#define NEXUS_CMD_START_SYSTEM              NEXUS_CMD_ID(NEXUS_VERB_START, 0x01U)                             /* 0x0201 = 513 */
#define NEXUS_CMD_START_SENSORS             NEXUS_CMD_ID(NEXUS_VERB_START, 0x02U)                             /* 0x0202 = 514 */
#define NEXUS_CMD_START_TELEMETRY           NEXUS_CMD_ID(NEXUS_VERB_START, 0x03U)                             /* 0x0203 = 515 */
#define NEXUS_CMD_START_SELF_TEST           NEXUS_CMD_ID(NEXUS_VERB_START, 0x04U)                             /* 0x0204 = 516 */
#define NEXUS_CMD_START_EXECUTIVE           NEXUS_CMD_ID(NEXUS_VERB_START, 0x05U)                             /* 0x0205 = 517 */

/* 03 STOP */
#define NEXUS_CMD_STOP_SYSTEM               NEXUS_CMD_ID(NEXUS_VERB_STOP, 0x01U)                              /* 0x0301 = 769 */
#define NEXUS_CMD_STOP_SENSORS              NEXUS_CMD_ID(NEXUS_VERB_STOP, 0x02U)                              /* 0x0302 = 770 */
#define NEXUS_CMD_STOP_TELEMETRY            NEXUS_CMD_ID(NEXUS_VERB_STOP, 0x03U)                              /* 0x0303 = 771 */
#define NEXUS_CMD_STOP_EXECUTIVE            NEXUS_CMD_ID(NEXUS_VERB_STOP, 0x04U)                              /* 0x0304 = 772 */

/* 04 RESET */
#define NEXUS_CMD_RESET_FAULTS              NEXUS_CMD_ID(NEXUS_VERB_RESET, 0x01U)                             /* 0x0401 = 1025 */
#define NEXUS_CMD_RESET_STATISTICS          NEXUS_CMD_ID(NEXUS_VERB_RESET, 0x02U)                             /* 0x0402 = 1026 */
#define NEXUS_CMD_RESET_SENSOR_STATE        NEXUS_CMD_ID(NEXUS_VERB_RESET, 0x03U)                             /* 0x0403 = 1027 */
#define NEXUS_CMD_RESET_QUEUES              NEXUS_CMD_ID(NEXUS_VERB_RESET, 0x04U)                             /* 0x0404 = 1028 */

/* 05 SET */
#define NEXUS_CMD_SET_PRIORITY              NEXUS_CMD_ID(NEXUS_VERB_SET, 0x01U)                               /* 0x0501 = 1281 */
#define NEXUS_CMD_SET_SAMPLE_INTERVAL       NEXUS_CMD_ID(NEXUS_VERB_SET, 0x02U)                               /* 0x0502 = 1282 */
#define NEXUS_CMD_SET_THRESHOLD            NEXUS_CMD_ID(NEXUS_VERB_SET, 0x03U)                               /* 0x0503 = 1283 */
#define NEXUS_CMD_SET_SENSOR_ENABLE         NEXUS_CMD_ID(NEXUS_VERB_SET, 0x04U)                               /* 0x0504 = 1284 */
#define NEXUS_CMD_SET_TRANSPORT_PREF        NEXUS_CMD_ID(NEXUS_VERB_SET, 0x05U)                               /* 0x0505 = 1285 */
#define NEXUS_CMD_SET_CONFIGURATION         NEXUS_CMD_ID(NEXUS_VERB_SET, 0x06U)                               /* 0x0506 = 1286 */

/* 06 GET */
#define NEXUS_CMD_GET_STATUS                NEXUS_CMD_ID(NEXUS_VERB_GET, 0x01U)                               /* 0x0601 = 1537 */
#define NEXUS_CMD_GET_CONFIGURATION         NEXUS_CMD_ID(NEXUS_VERB_GET, 0x02U)                               /* 0x0602 = 1538 */
#define NEXUS_CMD_GET_SENSOR_LIST           NEXUS_CMD_ID(NEXUS_VERB_GET, 0x03U)                               /* 0x0603 = 1539 */
#define NEXUS_CMD_GET_TIME                  NEXUS_CMD_ID(NEXUS_VERB_GET, 0x04U)                               /* 0x0604 = 1540 */
#define NEXUS_CMD_GET_VERSION               NEXUS_CMD_ID(NEXUS_VERB_GET, 0x05U)                               /* 0x0605 = 1541 */
#define NEXUS_CMD_GET_HEALTH                NEXUS_CMD_ID(NEXUS_VERB_GET, 0x06U)                               /* 0x0606 = 1542 */
#define NEXUS_CMD_GET_CAPABILITIES          NEXUS_CMD_ID(NEXUS_VERB_GET, 0x07U)                               /* 0x0607 = 1543 */

/* 07 ENABLE */
#define NEXUS_CMD_ENABLE_SENSOR             NEXUS_CMD_ID(NEXUS_VERB_ENABLE, 0x01U)                            /* 0x0701 = 1793 */
#define NEXUS_CMD_ENABLE_TRANSPORT          NEXUS_CMD_ID(NEXUS_VERB_ENABLE, 0x02U)                            /* 0x0702 = 1794 */
#define NEXUS_CMD_ENABLE_TELEMETRY          NEXUS_CMD_ID(NEXUS_VERB_ENABLE, 0x03U)                            /* 0x0703 = 1795 */

/* 08 DISABLE */
#define NEXUS_CMD_DISABLE_SENSOR            NEXUS_CMD_ID(NEXUS_VERB_DISABLE, 0x01U)                           /* 0x0801 = 2049 */
#define NEXUS_CMD_DISABLE_TRANSPORT         NEXUS_CMD_ID(NEXUS_VERB_DISABLE, 0x02U)                           /* 0x0802 = 2050 */
#define NEXUS_CMD_DISABLE_TELEMETRY         NEXUS_CMD_ID(NEXUS_VERB_DISABLE, 0x03U)                           /* 0x0803 = 2051 */

/* 09 CALIBRATE */
#define NEXUS_CMD_CALIBRATE_SENSOR          NEXUS_CMD_ID(NEXUS_VERB_CALIBRATE, 0x01U)                         /* 0x0901 = 2305 */
#define NEXUS_CMD_CALIBRATE_ANALOG          NEXUS_CMD_ID(NEXUS_VERB_CALIBRATE, 0x02U)                         /* 0x0902 = 2306 */
#define NEXUS_CMD_CALIBRATE_ENVIRONMENT     NEXUS_CMD_ID(NEXUS_VERB_CALIBRATE, 0x03U)                         /* 0x0903 = 2307 */

/* 10 ACKNOWLEDGE */
#define NEXUS_CMD_ACKNOWLEDGE_FAULT         NEXUS_CMD_ID(NEXUS_VERB_ACKNOWLEDGE, 0x01U)                       /* 0x0A01 = 2561 */
#define NEXUS_CMD_ACKNOWLEDGE_WARNING       NEXUS_CMD_ID(NEXUS_VERB_ACKNOWLEDGE, 0x02U)                       /* 0x0A02 = 2562 */
#define NEXUS_CMD_ACKNOWLEDGE_EVENT         NEXUS_CMD_ID(NEXUS_VERB_ACKNOWLEDGE, 0x03U)                       /* 0x0A03 = 2563 */

/* 11 CLEAR */
#define NEXUS_CMD_CLEAR_FAULTS              NEXUS_CMD_ID(NEXUS_VERB_CLEAR, 0x01U)                             /* 0x0B01 = 2817 */
#define NEXUS_CMD_CLEAR_HISTORY             NEXUS_CMD_ID(NEXUS_VERB_CLEAR, 0x02U)                             /* 0x0B02 = 2818 */
#define NEXUS_CMD_CLEAR_STATISTICS          NEXUS_CMD_ID(NEXUS_VERB_CLEAR, 0x03U)                             /* 0x0B03 = 2819 */

/* 12 TEST */
#define NEXUS_CMD_TEST_SENSOR               NEXUS_CMD_ID(NEXUS_VERB_TEST, 0x01U)                              /* 0x0C01 = 3073 */
#define NEXUS_CMD_TEST_TRANSPORT            NEXUS_CMD_ID(NEXUS_VERB_TEST, 0x02U)                              /* 0x0C02 = 3074 */
#define NEXUS_CMD_TEST_EXECUTIVE            NEXUS_CMD_ID(NEXUS_VERB_TEST, 0x03U)                              /* 0x0C03 = 3075 */
#define NEXUS_CMD_TEST_PERIPHERAL           NEXUS_CMD_ID(NEXUS_VERB_TEST, 0x04U)                              /* 0x0C04 = 3076 */

/* 13 ACTUATE */
#define NEXUS_CMD_ACTUATE_RELAY             NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x01U)                           /* 0x0D01 = 3329 */
#define NEXUS_CMD_ACTUATE_LED               NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x02U)                           /* 0x0D02 = 3330 */
#define NEXUS_CMD_ACTUATE_MOTOR             NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x03U)                           /* 0x0D03 = 3331 */
#define NEXUS_CMD_ACTUATE_SERVO             NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x04U)                           /* 0x0D04 = 3332 */
#define NEXUS_CMD_ACTUATE_BUZZER            NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x05U)                           /* 0x0D05 = 3333 */
#define NEXUS_CMD_ACTUATE_SHIFT_REGISTER    NEXUS_CMD_ID(NEXUS_VERB_ACTUATE, 0x06U)                           /* 0x0D06 = 3334 */

/* 14 CAPTURE */
#define NEXUS_CMD_CAPTURE_TELEMETRY         NEXUS_CMD_ID(NEXUS_VERB_CAPTURE, 0x01U)                           /* 0x0E01 = 3585 */
#define NEXUS_CMD_CAPTURE_SENSOR_SNAPSHOT   NEXUS_CMD_ID(NEXUS_VERB_CAPTURE, 0x02U)                           /* 0x0E02 = 3586 */
#define NEXUS_CMD_CAPTURE_EVENT_SNAPSHOT    NEXUS_CMD_ID(NEXUS_VERB_CAPTURE, 0x03U)                           /* 0x0E03 = 3587 */

/* 15 PUBLISH */
#define NEXUS_CMD_PUBLISH_TELEMETRY         NEXUS_CMD_ID(NEXUS_VERB_PUBLISH, 0x01U)                           /* 0x0F01 = 3841 */
#define NEXUS_CMD_PUBLISH_EVENT             NEXUS_CMD_ID(NEXUS_VERB_PUBLISH, 0x02U)                           /* 0x0F02 = 3842 */
#define NEXUS_CMD_PUBLISH_STATUS            NEXUS_CMD_ID(NEXUS_VERB_PUBLISH, 0x03U)                           /* 0x0F03 = 3843 */

/* 16 DISPLAY */
#define NEXUS_CMD_DISPLAY_STATUS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x01U)                           /* 0x1001 = 4097 */
#define NEXUS_CMD_DISPLAY_EXECUTIVE         NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x02U)                           /* 0x1002 = 4098 */
#define NEXUS_CMD_DISPLAY_QUEUES            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x03U)                           /* 0x1003 = 4099 */
#define NEXUS_CMD_DISPLAY_FAULTS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x04U)                           /* 0x1004 = 4100 */
#define NEXUS_CMD_DISPLAY_SENSORS           NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x05U)                           /* 0x1005 = 4101 */
#define NEXUS_CMD_DISPLAY_TRANSPORTS        NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x06U)                           /* 0x1006 = 4102 */
#define NEXUS_CMD_DISPLAY_CONFIGURATION     NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x07U)                           /* 0x1007 = 4103 */
#define NEXUS_CMD_DISPLAY_ENVIRONMENT       NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x41U)                           /* 0x1041 = 4161 */
#define NEXUS_CMD_DISPLAY_LIGHT             NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x42U)                           /* 0x1042 = 4162 */
#define NEXUS_CMD_DISPLAY_DISTANCE          NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x43U)                           /* 0x1043 = 4163 */
#define NEXUS_CMD_DISPLAY_ANALOG            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x44U)                           /* 0x1044 = 4164 */
#define NEXUS_CMD_DISPLAY_MOTION            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x45U)                           /* 0x1045 = 4165 */
#define NEXUS_CMD_DISPLAY_EVENTS            NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x46U)                           /* 0x1046 = 4166 */
#define NEXUS_CMD_DISPLAY_ACTUATORS         NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x47U)                           /* 0x1047 = 4167 */
#define NEXUS_CMD_DISPLAY_CONNECTIVITY      NEXUS_CMD_ID(NEXUS_VERB_DISPLAY, 0x48U)                           /* 0x1048 = 4168 */

/* 17 HISTORY */
#define NEXUS_CMD_HISTORY_EVENTS            NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x01U)                           /* 0x1101 = 4353 */
#define NEXUS_CMD_HISTORY_FAULTS            NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x02U)                           /* 0x1102 = 4354 */
#define NEXUS_CMD_HISTORY_EXECUTIVE         NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x03U)                           /* 0x1103 = 4355 */
#define NEXUS_CMD_HISTORY_SENSORS           NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x04U)                           /* 0x1104 = 4356 */
#define NEXUS_CMD_HISTORY_TRANSPORTS        NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x05U)                           /* 0x1105 = 4357 */
#define NEXUS_CMD_HISTORY_ENVIRONMENT       NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x41U)                           /* 0x1141 = 4417 */
#define NEXUS_CMD_HISTORY_SENSOR_READINGS   NEXUS_CMD_ID(NEXUS_VERB_HISTORY, 0x42U)                           /* 0x1142 = 4418 */

/* 24 DIAGNOSTICS */
#define NEXUS_CMD_DIAGNOSTICS_SYSTEM        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x01U)                        /* 0x1801 = 6145 */
#define NEXUS_CMD_DIAGNOSTICS_SENSORS       NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x02U)                        /* 0x1802 = 6146 */
#define NEXUS_CMD_DIAGNOSTICS_QUEUES        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x03U)                        /* 0x1803 = 6147 */
#define NEXUS_CMD_DIAGNOSTICS_TIMING        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x04U)                        /* 0x1804 = 6148 */
#define NEXUS_CMD_DIAGNOSTICS_MEMORY        NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x05U)                        /* 0x1805 = 6149 */
#define NEXUS_CMD_DIAGNOSTICS_TRANSPORTS    NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x06U)                        /* 0x1806 = 6150 */
#define NEXUS_CMD_DIAGNOSTICS_EXECUTIVE     NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x07U)                        /* 0x1807 = 6151 */
#define NEXUS_CMD_DIAGNOSTICS_PERIPHERALS   NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x08U)                        /* 0x1808 = 6152 */
#define NEXUS_CMD_DIAGNOSTICS_DATABASE      NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x09U)                        /* 0x1809 = 6153 */
#define NEXUS_CMD_DIAGNOSTICS_AI_SERVICE    NEXUS_CMD_ID(NEXUS_VERB_DIAGNOSTICS, 0x0AU)                        /* 0x180A = 6154 */

/* 30 OPEN */
#define NEXUS_CMD_OPEN_DASHBOARD            NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x01U)                               /* 0x1E01 = 7681 */
#define NEXUS_CMD_OPEN_LOGS                 NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x02U)                               /* 0x1E02 = 7682 */
#define NEXUS_CMD_OPEN_AI                   NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x03U)                               /* 0x1E03 = 7683 */
#define NEXUS_CMD_OPEN_GROUND               NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x04U)                               /* 0x1E04 = 7684 */
#define NEXUS_CMD_OPEN_DATABASE             NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x05U)                               /* 0x1E05 = 7685 */
#define NEXUS_CMD_OPEN_DIAGNOSTICS          NEXUS_CMD_ID(NEXUS_VERB_OPEN, 0x06U)                               /* 0x1E06 = 7686 */

/* 31 ASK */
#define NEXUS_CMD_ASK_SYSTEM                NEXUS_CMD_ID(NEXUS_VERB_ASK, 0x01U)                                /* 0x1F01 = 7937 */
#define NEXUS_CMD_ASK_SENSOR                NEXUS_CMD_ID(NEXUS_VERB_ASK, 0x02U)                                /* 0x1F02 = 7938 */
#define NEXUS_CMD_ASK_EXECUTIVE             NEXUS_CMD_ID(NEXUS_VERB_ASK, 0x03U)                                /* 0x1F03 = 7939 */
#define NEXUS_CMD_ASK_DIAGNOSTICS           NEXUS_CMD_ID(NEXUS_VERB_ASK, 0x04U)                                /* 0x1F04 = 7940 */
#define NEXUS_CMD_ASK_ENVIRONMENT           NEXUS_CMD_ID(NEXUS_VERB_ASK, 0x41U)                                /* 0x1F41 = 8001 */

/* 32 EXPORT */
#define NEXUS_CMD_EXPORT_TELEMETRY          NEXUS_CMD_ID(NEXUS_VERB_EXPORT, 0x01U)                             /* 0x2001 = 8193 */
#define NEXUS_CMD_EXPORT_DIAGNOSTICS        NEXUS_CMD_ID(NEXUS_VERB_EXPORT, 0x02U)                             /* 0x2002 = 8194 */
#define NEXUS_CMD_EXPORT_EVENTS             NEXUS_CMD_ID(NEXUS_VERB_EXPORT, 0x03U)                             /* 0x2003 = 8195 */
#define NEXUS_CMD_EXPORT_FAULTS             NEXUS_CMD_ID(NEXUS_VERB_EXPORT, 0x04U)                             /* 0x2004 = 8196 */
#define NEXUS_CMD_EXPORT_CONFIGURATION      NEXUS_CMD_ID(NEXUS_VERB_EXPORT, 0x05U)                             /* 0x2005 = 8197 */

/* 33 RUN */
#define NEXUS_CMD_RUN_SELF_TEST             NEXUS_CMD_ID(NEXUS_VERB_RUN, 0x01U)                                /* 0x2101 = 8449 */
#define NEXUS_CMD_RUN_SENSOR_TEST           NEXUS_CMD_ID(NEXUS_VERB_RUN, 0x02U)                                /* 0x2102 = 8450 */
#define NEXUS_CMD_RUN_STRESS_TEST           NEXUS_CMD_ID(NEXUS_VERB_RUN, 0x03U)                                /* 0x2103 = 8451 */
#define NEXUS_CMD_RUN_TRANSPORT_TEST        NEXUS_CMD_ID(NEXUS_VERB_RUN, 0x04U)                                /* 0x2104 = 8452 */
#define NEXUS_CMD_RUN_QUALIFICATION_TEST    NEXUS_CMD_ID(NEXUS_VERB_RUN, 0x05U)                                /* 0x2105 = 8453 */

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
    bool is_supported;
    const char *description;
} nexus_cmd_registry_entry_t;

/* Total candidate commands count: exactly 115 canonical entries */
#define NEXUS_CANDIDATE_COMMANDS_COUNT 115U

/* Lookup and validation APIs */
const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_id(uint16_t cmd_id);
const nexus_cmd_registry_entry_t *nexus_cmd_registry_lookup_by_name(const char *verb, const char *noun);
bool nexus_cmd_registry_is_supported_m8(uint16_t cmd_id);
bool nexus_cmd_registry_is_supported(uint16_t cmd_id);
const nexus_cmd_registry_entry_t *nexus_cmd_registry_get_all(size_t *out_count);

const char *nexus_cmd_disposition_str(nexus_cmd_disposition_t disp);
const char *nexus_cmd_status_code_str(nexus_cmd_status_code_t code);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_COMMAND_REGISTRY_H */
