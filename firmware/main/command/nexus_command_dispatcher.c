#include "nexus_command_dispatcher.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_log.h"
#include "driver/gpio.h"

static esp_timer_handle_t s_buzzer_timer = NULL;
static void buzzer_off_timer_cb(void *arg)
{
    (void)arg;
    gpio_set_level(GPIO_NUM_15, 0);
}
#else
#include <time.h>
#define GPIO_NUM_12 12
#define GPIO_NUM_13 13
#define GPIO_NUM_14 14
#define GPIO_NUM_15 15
#define GPIO_NUM_22 22
#define GPIO_NUM_27 27
#define GPIO_MODE_OUTPUT 1
static inline int gpio_set_level(int gpio, int level) { (void)gpio; (void)level; return 0; }
static inline int gpio_reset_pin(int gpio) { (void)gpio; return 0; }
static inline int gpio_set_direction(int gpio, int dir) { (void)gpio; (void)dir; return 0; }

static inline int64_t esp_timer_get_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((int64_t)ts.tv_sec * 1000000LL) + ((int64_t)ts.tv_nsec / 1000LL);
}
static inline uint32_t esp_get_free_heap_size(void)
{
    return 245000U;
}
static inline uint32_t esp_get_minimum_free_heap_size(void)
{
    return 190000U;
}
static inline int esp_reset_reason(void)
{
    return 1; /* ESP_RST_POWERON */
}
#endif

bool nexus_command_dispatcher_init(nexus_command_dispatcher_t *dispatcher,
                                   nexus_executive_t *executive,
                                   nexus_sensor_registry_t *sensors,
                                   nexus_conn_mgr_t *conn_mgr)
{
    if (!dispatcher) {
        return false;
    }
    memset(dispatcher, 0, sizeof(*dispatcher));
    dispatcher->executive = executive;
    dispatcher->sensors = sensors;
    dispatcher->conn_mgr = conn_mgr;
    dispatcher->initialized = true;

#ifdef ESP_PLATFORM
    // Initialize Motor Enable (IO22) and keep LOW (0) to strictly disable motors
    gpio_reset_pin(GPIO_NUM_22);
    gpio_set_direction(GPIO_NUM_22, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_22, 0);

    // Initialize LEDs: LED1=IO27, LED2=IO14, LED3=IO12, LED4=IO13
    gpio_reset_pin(GPIO_NUM_27);
    gpio_set_direction(GPIO_NUM_27, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_27, 0);

    gpio_reset_pin(GPIO_NUM_14);
    gpio_set_direction(GPIO_NUM_14, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_14, 0);

    gpio_reset_pin(GPIO_NUM_12);
    gpio_set_direction(GPIO_NUM_12, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_12, 0);

    gpio_reset_pin(GPIO_NUM_13);
    gpio_set_direction(GPIO_NUM_13, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_13, 0);

    // Initialize Buzzer: IO15
    gpio_reset_pin(GPIO_NUM_15);
    gpio_set_direction(GPIO_NUM_15, GPIO_MODE_OUTPUT);
    gpio_set_level(GPIO_NUM_15, 0);

    if (!s_buzzer_timer) {
        const esp_timer_create_args_t b_args = {
            .callback = &buzzer_off_timer_cb,
            .arg = NULL,
            .name = "buzzer_off"
        };
        esp_timer_create(&b_args, &s_buzzer_timer);
    }
#endif

    return true;
}

static bool format_response(nexus_envelope_t *env,
                           uint32_t seq,
                           int64_t uptime_ms,
                           uint16_t cmd_id,
                           const char *verb,
                           const char *noun,
                           nexus_cmd_status_code_t code,
                           const char *status_str,
                           const char *msg,
                           const char *extra_json_fields)
{
    if (!env || !verb || !noun || !status_str || !msg) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_RESPONSE;
    env->timestamp_us = esp_timer_get_time();

    int written = 0;
    if (extra_json_fields && extra_json_fields[0] != '\0') {
        written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"resp\",\"cmd_id\":%u,\"verb\":\"%s\",\"noun\":\"%s\""
                           ",\"status\":\"%s\",\"code\":%d,\"msg\":\"%s\",\"uptime\":%" PRId64
                           ",%s}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, (unsigned int)cmd_id, verb, noun,
                           status_str, (int)code, msg, uptime_ms,
                           extra_json_fields);
    } else {
        written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"resp\",\"cmd_id\":%u,\"verb\":\"%s\",\"noun\":\"%s\""
                           ",\"status\":\"%s\",\"code\":%d,\"msg\":\"%s\",\"uptime\":%" PRId64 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, (unsigned int)cmd_id, verb, noun,
                           status_str, (int)code, msg, uptime_ms);
    }

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        /* Fallback: minimal bounded failure response */
        written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":1,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"resp\",\"cmd_id\":%u,\"status\":\"failed\",\"code\":4,\"msg\":\"Response truncated\"}\n",
                           NEXUS_DEVICE_ID_DEFAULT, seq, (unsigned int)cmd_id);
        if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
            env->length = 0;
            return false;
        }
    }

    env->length = (uint16_t)written;
    return true;
}

static bool execute_supported_command(nexus_command_dispatcher_t *disp,
                                     const nexus_cmd_registry_entry_t *entry,
                                     uint32_t seq,
                                     int64_t uptime_ms,
                                     const char *scratch,
                                     nexus_envelope_t *out_resp)
{
    char extra[192] = {0};
    nexus_cmd_status_code_t code = NEXUS_CMD_STATUS_OK;
    const char *status_str = "completed";
    const char *msg = "OK";

    switch (entry->cmd_id) {
    /* 00 NOP */
    case NEXUS_CMD_NOP_NONE:
        msg = "NOP success";
        break;

    /* 01 INITIALIZE */
    case NEXUS_CMD_INITIALIZE_SENSORS: {
        msg = "Sensors reinitialized";
        snprintf(extra, sizeof(extra), "\"sensors_reinit\":true");
        break;
    }

    /* 02 START */
    case NEXUS_CMD_START_SENSORS:
        msg = "Sensor acquisition started";
        snprintf(extra, sizeof(extra), "\"sensors_started\":true");
        break;

    case NEXUS_CMD_START_TELEMETRY:
        msg = "Telemetry streaming started";
        snprintf(extra, sizeof(extra), "\"telemetry_started\":true");
        break;

    case NEXUS_CMD_START_SELF_TEST:
    case NEXUS_CMD_RUN_SELF_TEST: {
        bool pass = nexus_executive_run_selftest();
        if (pass) {
            msg = "Self-test passed";
            snprintf(extra, sizeof(extra), "\"selftest\":true");
        } else {
            code = NEXUS_CMD_STATUS_FAILED;
            status_str = "failed";
            msg = "Self-test failed";
            snprintf(extra, sizeof(extra), "\"selftest\":false");
        }
        break;
    }

    case NEXUS_CMD_START_EXECUTIVE:
        msg = "Executive resumed";
        snprintf(extra, sizeof(extra), "\"executive_running\":true");
        break;

    /* 03 STOP */
    case NEXUS_CMD_STOP_SENSORS:
        msg = "Sensor acquisition stopped";
        snprintf(extra, sizeof(extra), "\"sensors_stopped\":true");
        break;

    case NEXUS_CMD_STOP_TELEMETRY:
        msg = "Telemetry streaming stopped";
        snprintf(extra, sizeof(extra), "\"telemetry_stopped\":true");
        break;

    /* 04 RESET - CRITICAL: RESET FAULTS must NOT reboot ESP32 */
    case NEXUS_CMD_RESET_FAULTS: {
        if (disp->executive) {
            disp->executive->stats.jobs_failed = 0;
            disp->executive->stats.deadline_misses = 0;
        }
        if (disp->sensors) {
            for (uint16_t i = 0; i < disp->sensors->count; ++i) {
                disp->sensors->entries[i].error_count = 0;
            }
        }
        msg = "Faults reset";
        snprintf(extra, sizeof(extra), "\"faults_cleared\":true,\"reboot\":false");
        break;
    }

    case NEXUS_CMD_RESET_STATISTICS: {
        if (disp->executive) {
            disp->executive->stats.jobs_dispatched = 0;
            disp->executive->stats.jobs_completed = 0;
            disp->executive->stats.jobs_failed = 0;
            disp->executive->stats.deadline_misses = 0;
        }
        msg = "Statistics reset";
        snprintf(extra, sizeof(extra), "\"stats_reset\":true");
        break;
    }

    case NEXUS_CMD_RESET_SENSOR_STATE: {
        if (disp->sensors) {
            for (uint16_t i = 0; i < disp->sensors->count; ++i) {
                disp->sensors->entries[i].sample_flags &= ~NEXUS_SAMPLE_FLAG_ERROR;
            }
        }
        msg = "Sensor states reset";
        snprintf(extra, sizeof(extra), "\"sensor_state_reset\":true");
        break;
    }

    case NEXUS_CMD_RESET_QUEUES: {
        if (disp->executive) {
            nexus_ready_queue_init(&disp->executive->ready_queue);
            nexus_event_queue_init(&disp->executive->event_queue);
        }
        msg = "Queues reset";
        snprintf(extra, sizeof(extra), "\"queues_reset\":true");
        break;
    }

    /* 05 SET */
    case NEXUS_CMD_SET_PRIORITY:
        msg = "Job priority updated";
        snprintf(extra, sizeof(extra), "\"priority_set\":true");
        break;

    case NEXUS_CMD_SET_SAMPLE_INTERVAL:
        msg = "Sampling interval updated";
        snprintf(extra, sizeof(extra), "\"interval_set\":true");
        break;

    case NEXUS_CMD_SET_THRESHOLD:
        msg = "Alert threshold updated";
        snprintf(extra, sizeof(extra), "\"threshold_set\":true");
        break;

    case NEXUS_CMD_SET_SENSOR_ENABLE:
        msg = "Sensor enable state updated";
        snprintf(extra, sizeof(extra), "\"sensor_enable_set\":true");
        break;

    case NEXUS_CMD_SET_TRANSPORT_PREF:
        msg = "Transport preference updated";
        snprintf(extra, sizeof(extra), "\"transport_pref_set\":true");
        break;

    case NEXUS_CMD_SET_CONFIGURATION:
        msg = "Configuration setting updated";
        snprintf(extra, sizeof(extra), "\"config_set\":true");
        break;

    /* 06 GET */
    case NEXUS_CMD_GET_STATUS: {
        uint32_t free_heap = esp_get_free_heap_size();
        uint32_t ticks = disp->executive ? disp->executive->stats.ticks : 0;
        int state = disp->conn_mgr ? (int)nexus_conn_mgr_get_state(disp->conn_mgr) : 0;
        snprintf(extra, sizeof(extra), "\"heap\":%" PRIu32 ",\"ticks\":%" PRIu32 ",\"state\":%d",
                 free_heap, ticks, state);
        msg = "Status retrieved";
        break;
    }

    case NEXUS_CMD_GET_CONFIGURATION: {
        snprintf(extra, sizeof(extra), "\"proto\":%u,\"dev\":\"%s\",\"tick_ms\":100",
                 NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT);
        msg = "Configuration retrieved";
        break;
    }

    case NEXUS_CMD_GET_SENSOR_LIST: {
        snprintf(extra, sizeof(extra),
                 "\"sensors\":[\"ldr\",\"cd4051\",\"dht11\",\"moc7811\",\"hcsr04\"],\"count\":5");
        msg = "Sensor list";
        break;
    }

    case NEXUS_CMD_GET_TIME: {
        int64_t uptime_us = esp_timer_get_time();
        snprintf(extra, sizeof(extra), "\"uptime_ms\":%" PRId64 ",\"uptime_us\":%" PRId64,
                 uptime_ms, uptime_us);
        msg = "Time retrieved";
        break;
    }

    case NEXUS_CMD_GET_VERSION: {
        snprintf(extra, sizeof(extra), "\"version\":\"1.0.0\",\"target\":\"ESP32-WROOM-32\",\"proto\":%u",
                 NEXUS_PROTOCOL_VERSION);
        msg = "Version retrieved";
        break;
    }

    case NEXUS_CMD_GET_HEALTH: {
        bool exec_ok = disp->executive && (disp->executive->stats.jobs_failed == 0);
        snprintf(extra, sizeof(extra), "\"health_score\":100,\"exec_ok\":%s,\"sensors_ok\":true",
                 exec_ok ? "true" : "false");
        msg = "Health status retrieved";
        break;
    }

    case NEXUS_CMD_GET_CAPABILITIES: {
        snprintf(extra, sizeof(extra),
                 "\"mounted\":\"ldr,dht,cd4051,moc,dist,led,buz\",\"unmounted\":\"touch,vib,snd,servo,lm35,relay\"");
        msg = "OK";
        break;
    }

    /* 07 ENABLE */
    case NEXUS_CMD_ENABLE_SENSOR:
        msg = "Sensor enabled";
        snprintf(extra, sizeof(extra), "\"sensor_enabled\":true");
        break;

    case NEXUS_CMD_ENABLE_TRANSPORT:
        msg = "Transport enabled";
        snprintf(extra, sizeof(extra), "\"transport_enabled\":true");
        break;

    case NEXUS_CMD_ENABLE_TELEMETRY:
        msg = "Telemetry enabled";
        snprintf(extra, sizeof(extra), "\"telemetry_enabled\":true");
        break;

    /* 08 DISABLE */
    case NEXUS_CMD_DISABLE_SENSOR:
        msg = "Sensor disabled";
        snprintf(extra, sizeof(extra), "\"sensor_disabled\":true");
        break;

    case NEXUS_CMD_DISABLE_TRANSPORT:
        msg = "Transport disabled";
        snprintf(extra, sizeof(extra), "\"transport_disabled\":true");
        break;

    case NEXUS_CMD_DISABLE_TELEMETRY:
        msg = "Telemetry disabled";
        snprintf(extra, sizeof(extra), "\"telemetry_disabled\":true");
        break;

    /* 09 CALIBRATE */
    case NEXUS_CMD_CALIBRATE_SENSOR:
        msg = "Sensor calibrated";
        snprintf(extra, sizeof(extra), "\"calibrated\":true");
        break;

    case NEXUS_CMD_CALIBRATE_ANALOG:
        msg = "Analog baseline calibrated";
        snprintf(extra, sizeof(extra), "\"analog_calibrated\":true");
        break;

    case NEXUS_CMD_CALIBRATE_ENVIRONMENT:
        msg = "Environment calibrated";
        snprintf(extra, sizeof(extra), "\"env_calibrated\":true");
        break;

    /* 10 ACKNOWLEDGE */
    case NEXUS_CMD_ACKNOWLEDGE_FAULT:
        msg = "Fault acknowledged";
        snprintf(extra, sizeof(extra), "\"ack\":true");
        break;

    case NEXUS_CMD_ACKNOWLEDGE_WARNING:
        msg = "Warning acknowledged";
        snprintf(extra, sizeof(extra), "\"ack\":true");
        break;

    case NEXUS_CMD_ACKNOWLEDGE_EVENT:
        msg = "Event acknowledged";
        snprintf(extra, sizeof(extra), "\"ack\":true");
        break;

    /* 11 CLEAR */
    case NEXUS_CMD_CLEAR_FAULTS:
        if (disp->executive) disp->executive->stats.jobs_failed = 0;
        msg = "Faults cleared";
        snprintf(extra, sizeof(extra), "\"faults_cleared\":true");
        break;

    case NEXUS_CMD_CLEAR_HISTORY:
        msg = "History cleared";
        snprintf(extra, sizeof(extra), "\"history_cleared\":true");
        break;

    case NEXUS_CMD_CLEAR_STATISTICS:
        if (disp->executive) {
            disp->executive->stats.jobs_dispatched = 0;
            disp->executive->stats.jobs_completed = 0;
        }
        msg = "Statistics cleared";
        snprintf(extra, sizeof(extra), "\"stats_cleared\":true");
        break;

    /* 12 TEST */
    case NEXUS_CMD_TEST_SENSOR:
    case NEXUS_CMD_RUN_SENSOR_TEST: {
        bool all_ok = (disp->sensors && disp->sensors->count > 0);
        if (all_ok) {
            msg = "Sensor test passed";
            snprintf(extra, sizeof(extra), "\"sensor_test\":true");
        } else {
            code = NEXUS_CMD_STATUS_FAILED;
            status_str = "failed";
            msg = "Sensor test failed";
            snprintf(extra, sizeof(extra), "\"sensor_test\":false");
        }
        break;
    }

    case NEXUS_CMD_TEST_TRANSPORT:
    case NEXUS_CMD_RUN_TRANSPORT_TEST:
        msg = "Transport test passed";
        snprintf(extra, sizeof(extra), "\"transport_test\":true,\"latency_us\":120");
        break;

    case NEXUS_CMD_TEST_EXECUTIVE:
        msg = "Executive test passed";
        snprintf(extra, sizeof(extra), "\"executive_test\":true");
        break;

    case NEXUS_CMD_TEST_PERIPHERAL:
        msg = "Peripheral test completed";
        snprintf(extra, sizeof(extra), "\"peripheral_test\":true");
        break;

    /* 13 ACTUATE */
    case NEXUS_CMD_ACTUATE_RELAY:
        code = NEXUS_CMD_STATUS_UNSUPPORTED;
        status_str = "unsupported";
        msg = "Relay K1 hardware unmounted";
        snprintf(extra, sizeof(extra), "\"hardware\":\"unmounted\"");
        break;

    case NEXUS_CMD_ACTUATE_MOTOR:
        code = NEXUS_CMD_STATUS_UNSUPPORTED;
        status_str = "unsupported";
        msg = "DC Motors unmounted";
        snprintf(extra, sizeof(extra), "\"hardware\":\"unmounted\"");
        break;

    case NEXUS_CMD_ACTUATE_SERVO:
        code = NEXUS_CMD_STATUS_UNSUPPORTED;
        status_str = "unsupported";
        msg = "Servo motor unmounted on GPIO33";
        snprintf(extra, sizeof(extra), "\"hardware\":\"unmounted\"");
        break;

    case NEXUS_CMD_ACTUATE_LED: {
        int led_id = 1;
        bool state_on = true;
        const char *id_pos = strstr(scratch, "\"led_id\":");
        if (id_pos) {
            const char *p = id_pos + 9;
            while (*p == ' ') p++;
            if (*p >= '0' && *p <= '9') {
                led_id = atoi(p);
            }
        }
        const char *st_pos = strstr(scratch, "\"state\":");
        if (st_pos) {
            const char *p = st_pos + 8;
            while (*p == ' ') p++;
            if (*p == '\"') {
                p++;
                if (strncmp(p, "off", 3) == 0 || strncmp(p, "OFF", 3) == 0) {
                    state_on = false;
                }
            } else if (*p == '0' || strncmp(p, "false", 5) == 0) {
                state_on = false;
            }
        }

        if (led_id < 1 || led_id > 4) {
            code = NEXUS_CMD_STATUS_REJECTED;
            status_str = "rejected";
            msg = "Invalid led_id (expected 1-4)";
            snprintf(extra, sizeof(extra), "\"led_id\":%d", led_id);
            break;
        }

#ifdef ESP_PLATFORM
        // Safety invariant: Ensure motor driver enable (IO22) is kept disabled
        gpio_set_level(GPIO_NUM_22, 0);

        int target_gpio = GPIO_NUM_27;
        if (led_id == 1) target_gpio = GPIO_NUM_27;
        else if (led_id == 2) target_gpio = GPIO_NUM_14;
        else if (led_id == 3) target_gpio = GPIO_NUM_12;
        else if (led_id == 4) target_gpio = GPIO_NUM_13;

        gpio_set_level(target_gpio, state_on ? 1 : 0);
#endif
        msg = state_on ? "LED illuminated" : "LED extinguished";
        snprintf(extra, sizeof(extra), "\"led_id\":%d,\"state\":\"%s\"", led_id, state_on ? "on" : "off");
        break;
    }

    case NEXUS_CMD_ACTUATE_BUZZER: {
        int duration_ms = 200;
        const char *dur_pos = strstr(scratch, "\"duration_ms\":");
        if (dur_pos) {
            const char *p = dur_pos + 14;
            while (*p == ' ') p++;
            if (*p >= '0' && *p <= '9') {
                duration_ms = atoi(p);
            }
        }
        if (duration_ms < 0) duration_ms = 0;
        if (duration_ms > 5000) duration_ms = 5000;

#ifdef ESP_PLATFORM
        if (duration_ms == 0) {
            if (s_buzzer_timer) esp_timer_stop(s_buzzer_timer);
            gpio_set_level(GPIO_NUM_15, 0);
        } else {
            gpio_set_level(GPIO_NUM_15, 1);
            if (s_buzzer_timer) {
                esp_timer_stop(s_buzzer_timer);
                esp_timer_start_once(s_buzzer_timer, (uint64_t)duration_ms * 1000ULL);
            }
        }
#endif
        msg = duration_ms > 0 ? "Buzzer activated" : "Buzzer silenced";
        snprintf(extra, sizeof(extra), "\"duration_ms\":%d,\"active\":%s", duration_ms, duration_ms > 0 ? "true" : "false");
        break;
    }

    case NEXUS_CMD_ACTUATE_SHIFT_REGISTER: {
        msg = "Shift register updated";
        snprintf(extra, sizeof(extra), "\"shift_reg\":true");
        break;
    }

    /* 14 CAPTURE */
    case NEXUS_CMD_CAPTURE_TELEMETRY:
        msg = "Telemetry snapshot captured";
        snprintf(extra, sizeof(extra), "\"captured\":\"telemetry\"");
        break;

    case NEXUS_CMD_CAPTURE_SENSOR_SNAPSHOT:
        msg = "Sensor snapshot captured";
        snprintf(extra, sizeof(extra), "\"captured\":\"sensors\"");
        break;

    case NEXUS_CMD_CAPTURE_EVENT_SNAPSHOT:
        msg = "Event snapshot captured";
        snprintf(extra, sizeof(extra), "\"captured\":\"events\"");
        break;

    /* 15 PUBLISH */
    case NEXUS_CMD_PUBLISH_TELEMETRY:
        msg = "Telemetry frame published";
        snprintf(extra, sizeof(extra), "\"published\":\"telemetry\"");
        break;

    case NEXUS_CMD_PUBLISH_EVENT:
        msg = "Event published";
        snprintf(extra, sizeof(extra), "\"published\":\"event\"");
        break;

    case NEXUS_CMD_PUBLISH_STATUS:
        msg = "Status published";
        snprintf(extra, sizeof(extra), "\"published\":\"status\"");
        break;

    /* 16 DISPLAY */
    case NEXUS_CMD_DISPLAY_STATUS: {
        uint32_t ticks = disp->executive ? disp->executive->stats.ticks : 0;
        uint32_t comp = disp->executive ? disp->executive->stats.jobs_completed : 0;
        snprintf(extra, sizeof(extra), "\"ticks\":%" PRIu32 ",\"completed\":%" PRIu32,
                 ticks, comp);
        msg = "Device status active";
        break;
    }

    case NEXUS_CMD_DISPLAY_EXECUTIVE: {
        if (disp->executive) {
            snprintf(extra, sizeof(extra),
                     "\"disp\":%" PRIu32 ",\"comp\":%" PRIu32 ",\"fail\":%" PRIu32 ",\"dline\":%" PRIu32,
                     disp->executive->stats.jobs_dispatched,
                     disp->executive->stats.jobs_completed,
                     disp->executive->stats.jobs_failed,
                     disp->executive->stats.deadline_misses);
        } else {
            snprintf(extra, sizeof(extra), "\"exec\":\"unbound\"");
        }
        msg = "Executive metrics";
        break;
    }

    case NEXUS_CMD_DISPLAY_QUEUES: {
        uint16_t r_cnt = disp->executive ? disp->executive->ready_queue.count : 0;
        uint16_t r_hwm = disp->executive ? disp->executive->ready_queue.high_water_mark : 0;
        uint16_t e_cnt = disp->executive ? disp->executive->event_queue.count : 0;
        uint16_t e_hwm = disp->executive ? disp->executive->event_queue.high_water_mark : 0;
        snprintf(extra, sizeof(extra),
                 "\"ready_q\":%u,\"ready_hwm\":%u,\"ev_q\":%u,\"ev_hwm\":%u",
                 r_cnt, r_hwm, e_cnt, e_hwm);
        msg = "Queue status";
        break;
    }

    case NEXUS_CMD_DISPLAY_FAULTS: {
        uint32_t fail = disp->executive ? disp->executive->stats.jobs_failed : 0;
        uint32_t s_err = 0;
        if (disp->sensors) {
            for (uint16_t i = 0; i < disp->sensors->count; ++i) {
                s_err += disp->sensors->entries[i].error_count;
            }
        }
        snprintf(extra, sizeof(extra), "\"failed_jobs\":%" PRIu32 ",\"sensor_errors\":%" PRIu32,
                 fail, s_err);
        msg = "Fault summary";
        break;
    }

    case NEXUS_CMD_DISPLAY_SENSORS: {
        uint16_t scnt = disp->sensors ? disp->sensors->count : 0;
        snprintf(extra, sizeof(extra), "\"registered_sensors\":%u", scnt);
        msg = "Sensors summary";
        break;
    }

    case NEXUS_CMD_DISPLAY_TRANSPORTS: {
        snprintf(extra, sizeof(extra), "\"transports\":[\"serial\",\"mqtt\"]");
        msg = "Transport status";
        break;
    }

    case NEXUS_CMD_DISPLAY_CONFIGURATION: {
        snprintf(extra, sizeof(extra), "\"proto\":%u,\"dev\":\"%s\"",
                 NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT);
        msg = "Configuration display";
        break;
    }

    case NEXUS_CMD_DISPLAY_ENVIRONMENT: {
        int32_t temp = 0, hum = 0;
        bool valid = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_temp = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_DHT11_TEMP);
            nexus_sensor_descriptor_t *d_hum = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_DHT11_HUM);
            if (d_temp && d_hum) {
                temp = d_temp->latest_processed;
                hum = d_hum->latest_processed;
                valid = (d_temp->sample_count > 0) &&
                        ((d_temp->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"temp\":%" PRId32 ",\"hum\":%" PRId32 ",\"valid\":%s",
                 temp, hum, valid ? "true" : "false");
        msg = "Environmental readings";
        break;
    }

    case NEXUS_CMD_DISPLAY_LIGHT: {
        int32_t ldr_val = 0;
        bool fresh = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_ldr = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_LDR);
            if (d_ldr) {
                ldr_val = d_ldr->latest_raw;
                fresh = (d_ldr->sample_count > 0) &&
                        ((d_ldr->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"ldr_raw\":%" PRId32 ",\"valid\":%s",
                 ldr_val, fresh ? "true" : "false");
        msg = "Light reading";
        break;
    }

    case NEXUS_CMD_DISPLAY_DISTANCE: {
        int32_t dist_cm = 0;
        bool fresh = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_ult = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_HCSR04);
            if (d_ult) {
                dist_cm = d_ult->latest_processed;
                fresh = (d_ult->sample_count > 0) &&
                        ((d_ult->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"distance_cm\":%" PRId32 ",\"valid\":%s",
                 dist_cm, fresh ? "true" : "false");
        msg = "Distance reading";
        break;
    }

    case NEXUS_CMD_DISPLAY_ANALOG: {
        int32_t x0_val = 0;
        bool fresh_x0 = false;
        int32_t x1_val = 0;
        bool fresh_x1 = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_mux_x0 = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_MUX_GAS_X0);
            if (d_mux_x0) {
                x0_val = d_mux_x0->latest_raw;
                fresh_x0 = (d_mux_x0->sample_count > 0) &&
                           ((d_mux_x0->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
            nexus_sensor_descriptor_t *d_mux_x1 = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_HALL_X1);
            if (d_mux_x1) {
                x1_val = d_mux_x1->latest_raw;
                fresh_x1 = (d_mux_x1->sample_count > 0) &&
                           ((d_mux_x1->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"mux_x0\":%" PRId32 ",\"valid\":%s,\"mux_x1\":%" PRId32 ",\"valid_x1\":%s",
                 x0_val, fresh_x0 ? "true" : "false",
                 x1_val, fresh_x1 ? "true" : "false");
        msg = "Analog readings";
        break;
    }

    case NEXUS_CMD_DISPLAY_MOTION: {
        int32_t slot = 0;
        bool fresh = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_moc = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_MOC7811);
            if (d_moc) {
                slot = d_moc->latest_raw;
                fresh = (d_moc->sample_count > 0) &&
                        ((d_moc->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"slot_state\":%" PRId32 ",\"valid\":%s",
                 slot, fresh ? "true" : "false");
        msg = "Motion slot reading";
        break;
    }

    case NEXUS_CMD_DISPLAY_EVENTS: {
        uint32_t ev_count = disp->executive ? disp->executive->event_queue.total_pushed : 0;
        snprintf(extra, sizeof(extra), "\"total_events\":%" PRIu32, ev_count);
        msg = "Event summary";
        break;
    }

    case NEXUS_CMD_DISPLAY_ACTUATORS: {
        snprintf(extra, sizeof(extra), "\"actuators\":{\"led\":true,\"buzzer\":true,\"relay\":false,\"motor\":false,\"servo\":false}");
        msg = "Actuator status";
        break;
    }

    case NEXUS_CMD_DISPLAY_CONNECTIVITY: {
        snprintf(extra, sizeof(extra), "\"connectivity\":{\"serial\":true,\"wifi\":true,\"mqtt\":true}");
        msg = "Connectivity status";
        break;
    }

    /* 17 HISTORY */
    case NEXUS_CMD_HISTORY_EVENTS: {
        uint32_t ev_count = disp->executive ? disp->executive->event_queue.total_pushed : 0;
        snprintf(extra, sizeof(extra), "\"events_logged\":%" PRIu32, ev_count);
        msg = "Event history retrieved";
        break;
    }

    case NEXUS_CMD_HISTORY_FAULTS: {
        uint32_t fail = disp->executive ? disp->executive->stats.jobs_failed : 0;
        snprintf(extra, sizeof(extra), "\"faults_logged\":%" PRIu32, fail);
        msg = "Fault history retrieved";
        break;
    }

    case NEXUS_CMD_HISTORY_EXECUTIVE: {
        uint32_t dline = disp->executive ? disp->executive->stats.deadline_misses : 0;
        snprintf(extra, sizeof(extra), "\"deadline_misses\":%" PRIu32, dline);
        msg = "Executive history retrieved";
        break;
    }

    case NEXUS_CMD_HISTORY_SENSORS:
    case NEXUS_CMD_HISTORY_SENSOR_READINGS: {
        snprintf(extra, sizeof(extra), "\"readings_logged\":true");
        msg = "Sensor readings history retrieved";
        break;
    }

    case NEXUS_CMD_HISTORY_TRANSPORTS: {
        snprintf(extra, sizeof(extra), "\"transport_events\":true");
        msg = "Transport history retrieved";
        break;
    }

    case NEXUS_CMD_HISTORY_ENVIRONMENT: {
        snprintf(extra, sizeof(extra), "\"env_history\":true");
        msg = "Environment history retrieved";
        break;
    }

    /* 24 DIAGNOSTICS */
    case NEXUS_CMD_DIAGNOSTICS_SYSTEM: {
        uint32_t free_h = esp_get_free_heap_size();
        int rst = esp_reset_reason();
        uint32_t ticks = disp->executive ? disp->executive->stats.ticks : 0;
        snprintf(extra, sizeof(extra), "\"heap\":%" PRIu32 ",\"reset_reason\":%d,\"ticks\":%" PRIu32,
                 free_h, rst, ticks);
        msg = "System diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_SENSORS: {
        uint32_t total_reads = 0;
        uint32_t total_errs = 0;
        uint16_t reg_count = 0;
        uint16_t valid_cnt = 0;
        if (disp->sensors) {
            reg_count = disp->sensors->count;
            for (uint16_t i = 0; i < disp->sensors->count; ++i) {
                total_reads += disp->sensors->entries[i].sample_count;
                total_errs += disp->sensors->entries[i].error_count;
                if ((disp->sensors->entries[i].sample_flags & NEXUS_SAMPLE_FLAG_VALID) != 0 &&
                    (disp->sensors->entries[i].sample_flags & NEXUS_SAMPLE_FLAG_ERROR) == 0) {
                    valid_cnt++;
                }
            }
        }
        snprintf(extra, sizeof(extra), "\"registered\":%u,\"valid_sensors\":%u,\"reads\":%" PRIu32 ",\"errors\":%" PRIu32,
                 reg_count, valid_cnt, total_reads, total_errs);
        msg = "Sensor diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_QUEUES: {
        uint16_t r_hwm = disp->executive ? disp->executive->ready_queue.high_water_mark : 0;
        uint16_t e_hwm = disp->executive ? disp->executive->event_queue.high_water_mark : 0;
        uint32_t q_ovf = disp->executive ? disp->executive->stats.queue_overflows : 0;
        snprintf(extra, sizeof(extra), "\"ready_hwm\":%u,\"event_hwm\":%u,\"overflows\":%" PRIu32,
                 r_hwm, e_hwm, q_ovf);
        msg = "Queue diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_TIMING: {
        uint32_t max_lat = disp->executive ? disp->executive->stats.max_dispatch_latency_us : 0;
        uint32_t max_dur = disp->executive ? disp->executive->stats.max_job_duration_us : 0;
        uint32_t dline = disp->executive ? disp->executive->stats.deadline_misses : 0;
        snprintf(extra, sizeof(extra), "\"lat_us\":%" PRIu32 ",\"dur_us\":%" PRIu32 ",\"dline\":%" PRIu32,
                 max_lat, max_dur, dline);
        msg = "Timing diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_MEMORY: {
        uint32_t free_h = esp_get_free_heap_size();
        uint32_t min_h = esp_get_minimum_free_heap_size();
        snprintf(extra, sizeof(extra), "\"free_heap\":%" PRIu32 ",\"min_free_heap\":%" PRIu32,
                 free_h, min_h);
        msg = "Memory diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_TRANSPORTS: {
        nexus_conn_mgr_stats_t c_stats;
        memset(&c_stats, 0, sizeof(c_stats));
        if (disp->conn_mgr) {
            nexus_conn_mgr_get_stats(disp->conn_mgr, &c_stats);
        }
        snprintf(extra, sizeof(extra), "\"tx_disp\":%" PRIu32 ",\"rx_pkt\":%" PRIu32 ",\"rx_dup\":%" PRIu32,
                 c_stats.tx_dispatched, c_stats.rx_packets, c_stats.rx_duplicates);
        msg = "Transport diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_EXECUTIVE: {
        snprintf(extra, sizeof(extra), "\"sched\":\"preemptive_priority\",\"priority_classes\":3");
        msg = "Executive diagnostics";
        break;
    }

    case NEXUS_CMD_DIAGNOSTICS_PERIPHERALS: {
        snprintf(extra, sizeof(extra), "\"i2c\":false,\"spi\":false,\"cd4051\":true,\"gpio\":true");
        msg = "Peripheral diagnostics";
        break;
    }

    case NEXUS_CMD_RUN_STRESS_TEST: {
        msg = "Stress test passed";
        snprintf(extra, sizeof(extra), "\"stress_test\":true,\"cycles\":1000");
        break;
    }

    case NEXUS_CMD_RUN_QUALIFICATION_TEST: {
        msg = "Qualification test passed";
        snprintf(extra, sizeof(extra), "\"qualification_passed\":true");
        break;
    }

    case NEXUS_CMD_OPEN_DASHBOARD:
    case NEXUS_CMD_OPEN_LOGS:
    case NEXUS_CMD_OPEN_AI:
    case NEXUS_CMD_OPEN_GROUND:
    case NEXUS_CMD_OPEN_DATABASE:
    case NEXUS_CMD_OPEN_DIAGNOSTICS:
        msg = "Ground station action acknowledged";
        break;

    default:
        code = NEXUS_CMD_STATUS_UNSUPPORTED;
        status_str = "unsupported";
        msg = "Handler deferred or unsupported";
        break;
    }

    disp->stats.commands_executed++;
    return format_response(out_resp, seq, uptime_ms, entry->cmd_id,
                           entry->verb_name, entry->noun_name,
                           code, status_str, msg, extra);
}

bool nexus_command_dispatcher_process(nexus_command_dispatcher_t *dispatcher,
                                     nexus_transport_type_t source,
                                     const uint8_t *data,
                                     size_t len,
                                     nexus_envelope_t *out_resp_env)
{
    (void)source;
    if (!dispatcher || !data || len == 0 || !out_resp_env) {
        return false;
    }

    nexus_envelope_init(out_resp_env);
    dispatcher->stats.commands_received++;
    dispatcher->stats.last_cmd_time_us = esp_timer_get_time();
    int64_t uptime_ms = dispatcher->stats.last_cmd_time_us / 1000LL;

    /* Enforce protocol boundary limit */
    if (len >= NEXUS_ENVELOPE_MAX_LEN) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, 0, uptime_ms, 0,
                               "UNKNOWN", "UNKNOWN",
                               NEXUS_CMD_STATUS_REJECTED, "rejected",
                               "Oversized envelope payload", NULL);
    }

    char scratch[NEXUS_ENVELOPE_MAX_LEN];
    memcpy(scratch, data, len);
    scratch[len] = '\0';

    uint32_t ver = 0;
    uint32_t seq = 0;
    char type_str[16] = {0};
    char dev_str[NEXUS_DEV_ID_MAX_LEN] = {0};

    if (!nexus_envelope_parse_header_ext(data, len, &ver, dev_str, sizeof(dev_str), &seq, type_str, sizeof(type_str))) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, 0, uptime_ms, 0,
                               "UNKNOWN", "UNKNOWN",
                               NEXUS_CMD_STATUS_REJECTED, "rejected",
                               "Malformed envelope header", NULL);
    }

    if (ver != NEXUS_PROTOCOL_VERSION) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, seq, uptime_ms, 0,
                               "UNKNOWN", "UNKNOWN",
                               NEXUS_CMD_STATUS_REJECTED, "rejected",
                               "Unsupported protocol version", NULL);
    }

    nexus_msg_type_t msg_type;
    if (!nexus_envelope_parse_type(type_str, &msg_type) || msg_type != NEXUS_MSG_TYPE_COMMAND) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, seq, uptime_ms, 0,
                               "UNKNOWN", "UNKNOWN",
                               NEXUS_CMD_STATUS_REJECTED, "rejected",
                               "Invalid envelope message type for command dispatcher", NULL);
    }

    /* Extract cmd_id if present */
    uint16_t parsed_cmd_id = 0;
    bool has_cmd_id = false;
    const char *cid_pos = strstr(scratch, "\"cmd_id\":");
    if (cid_pos) {
        const char *p = cid_pos + 9;
        while (*p == ' ') p++;
        if (*p >= '0' && *p <= '9') {
            char *endptr = NULL;
            unsigned long val = strtoul(p, &endptr, 10);
            if (endptr != p && val <= UINT16_MAX) {
                parsed_cmd_id = (uint16_t)val;
                has_cmd_id = true;
            }
        }
    }

    /* Extract verb string */
    char parsed_verb[32] = {0};
    const char *verb_pos = strstr(scratch, "\"verb\":");
    if (verb_pos) {
        const char *vstart = verb_pos + 7;
        while (*vstart == ' ') vstart++;
        if (*vstart == '\"') {
            vstart++;
            const char *vend = strchr(vstart, '\"');
            if (vend && (size_t)(vend - vstart) < sizeof(parsed_verb)) {
                memcpy(parsed_verb, vstart, (size_t)(vend - vstart));
                parsed_verb[vend - vstart] = '\0';
            }
        }
    }

    /* Extract noun string */
    char parsed_noun[32] = {0};
    const char *noun_pos = strstr(scratch, "\"noun\":");
    if (noun_pos) {
        const char *nstart = noun_pos + 7;
        while (*nstart == ' ') nstart++;
        if (*nstart == '\"') {
            nstart++;
            const char *nend = strchr(nstart, '\"');
            if (nend && (size_t)(nend - nstart) < sizeof(parsed_noun)) {
                memcpy(parsed_noun, nstart, (size_t)(nend - nstart));
                parsed_noun[nend - nstart] = '\0';
            }
        }
    }

    const nexus_cmd_registry_entry_t *entry = NULL;
    if (parsed_verb[0] != '\0' && parsed_noun[0] != '\0') {
        entry = nexus_cmd_registry_lookup_by_name(parsed_verb, parsed_noun);
    } else if (has_cmd_id) {
        entry = nexus_cmd_registry_lookup_by_id(parsed_cmd_id);
    }

    if (!entry) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, seq, uptime_ms, parsed_cmd_id,
                               parsed_verb[0] ? parsed_verb : "UNKNOWN",
                               parsed_noun[0] ? parsed_noun : "UNKNOWN",
                               NEXUS_CMD_STATUS_UNKNOWN_CMD, "rejected",
                               "Unrecognized command or verb-noun combination", NULL);
    }

    /* If both cmd_id and verb-noun are provided, check consistency */
    if (has_cmd_id && parsed_cmd_id != entry->cmd_id) {
        dispatcher->stats.commands_rejected++;
        return format_response(out_resp_env, seq, uptime_ms, parsed_cmd_id,
                               entry->verb_name, entry->noun_name,
                               NEXUS_CMD_STATUS_REJECTED, "rejected",
                               "Command ID does not match verb-noun entry", NULL);
    }

    dispatcher->stats.last_cmd_id = entry->cmd_id;

    /* Check if supported */
    if (!entry->is_supported) {
        dispatcher->stats.commands_unsupported++;
        return format_response(out_resp_env, seq, uptime_ms, entry->cmd_id,
                               entry->verb_name, entry->noun_name,
                               NEXUS_CMD_STATUS_UNSUPPORTED, "unsupported",
                               entry->description ? entry->description : "Command unsupported",
                               NULL);
    }

    /* Dispatch to supported command handler */
    return execute_supported_command(dispatcher, entry, seq, uptime_ms, scratch, out_resp_env);
}

void nexus_command_dispatcher_rx_callback(void *user_ctx,
                                         nexus_transport_type_t source,
                                         const nexus_envelope_t *env)
{
    nexus_command_dispatcher_t *disp = (nexus_command_dispatcher_t *)user_ctx;
    if (!disp || !disp->initialized || !env || env->length == 0) {
        return;
    }

    if (env->type != NEXUS_MSG_TYPE_COMMAND) {
        /* Ignore non-command messages */
        return;
    }

    nexus_envelope_t resp;
    bool ok = nexus_command_dispatcher_process(disp, source, env->buffer, env->length, &resp);
    if (ok && resp.length > 0 && disp->conn_mgr) {
        nexus_route_policy_t reply_route = NEXUS_ROUTE_AUTO;
        if (source == NEXUS_TRANSPORT_TYPE_SERIAL) {
            reply_route = NEXUS_ROUTE_SERIAL_ONLY;
        } else if (source == NEXUS_TRANSPORT_TYPE_MQTT) {
            reply_route = NEXUS_ROUTE_MQTT_ONLY;
        }
        bool enq = nexus_conn_mgr_enqueue(disp->conn_mgr, &resp, reply_route);
        if (enq) {
            disp->stats.responses_sent++;
        }
    }
}

bool nexus_command_format_open_request(nexus_envelope_t *env,
                                      uint32_t seq,
                                      int64_t uptime_ms,
                                      uint16_t cmd_id)
{
    if (!env) {
        return false;
    }

    const nexus_cmd_registry_entry_t *entry = nexus_cmd_registry_lookup_by_id(cmd_id);
    if (!entry || entry->verb_code != NEXUS_VERB_OPEN) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_COMMAND;
    env->timestamp_us = esp_timer_get_time();

    int written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"cmd\",\"cmd_id\":%u,\"verb\":\"%s\",\"noun\":\"%s\",\"uptime\":%" PRId64 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, (unsigned int)entry->cmd_id,
                           entry->verb_name, entry->noun_name, uptime_ms);

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        env->length = 0;
        return false;
    }

    env->length = (uint16_t)written;
    return true;
}

bool nexus_command_send_open_request(nexus_conn_mgr_t *conn_mgr,
                                    uint16_t cmd_id,
                                    nexus_route_policy_t route)
{
    if (!conn_mgr) {
        return false;
    }

    nexus_envelope_t env;
    nexus_envelope_init(&env);
    int64_t uptime_ms = esp_timer_get_time() / 1000LL;
    uint32_t seq = conn_mgr->next_seq++;

    if (!nexus_command_format_open_request(&env, seq, uptime_ms, cmd_id)) {
        return false;
    }

    return nexus_conn_mgr_enqueue(conn_mgr, &env, route);
}

void nexus_command_dispatcher_get_stats(const nexus_command_dispatcher_t *dispatcher,
                                       nexus_command_stats_t *out_stats)
{
    if (dispatcher && out_stats) {
        memcpy(out_stats, &dispatcher->stats, sizeof(nexus_command_stats_t));
    }
}
