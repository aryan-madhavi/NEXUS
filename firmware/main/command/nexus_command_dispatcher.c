#include "nexus_command_dispatcher.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_log.h"
#else
#include <time.h>
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
                                     nexus_envelope_t *out_resp)
{
    char extra[128] = {0};
    nexus_cmd_status_code_t code = NEXUS_CMD_STATUS_OK;
    const char *status_str = "completed";
    const char *msg = "OK";

    switch (entry->cmd_id) {
    case NEXUS_CMD_NOP_NONE:
        msg = "NOP success";
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
        snprintf(extra, sizeof(extra), "\"sensors\":[\"ldr\",\"cd4051\",\"dht11\"],\"count\":3");
        msg = "Sensor list retrieved";
        break;
    }

    case NEXUS_CMD_GET_TIME: {
        int64_t uptime_us = esp_timer_get_time();
        snprintf(extra, sizeof(extra), "\"uptime_ms\":%" PRId64 ",\"uptime_us\":%" PRId64,
                 uptime_ms, uptime_us);
        msg = "Time retrieved";
        break;
    }

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

    case NEXUS_CMD_DISPLAY_ENVIRONMENT: {
        int32_t temp = 0, hum = 0;
        bool valid = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_temp = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_DHT11_TEMP);
            nexus_sensor_descriptor_t *d_hum = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_DHT11_HUM);
            if (d_temp && d_hum) {
                temp = d_temp->latest_processed;
                hum = d_hum->latest_processed;
                valid = (d_temp->sample_count > 0 && d_temp->error_count == 0);
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
                fresh = (d_ldr->sample_count > 0 && d_ldr->error_count == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"ldr_raw\":%" PRId32 ",\"valid\":%s",
                 ldr_val, fresh ? "true" : "false");
        msg = "Light reading";
        break;
    }

    case NEXUS_CMD_DISPLAY_ANALOG: {
        int32_t x0_val = 0;
        bool fresh = false;
        if (disp->sensors) {
            nexus_sensor_descriptor_t *d_mux = nexus_sensor_get(disp->sensors, NEXUS_SENSOR_ID_MUX_GAS_X0);
            if (d_mux) {
                x0_val = d_mux->latest_raw;
                fresh = (d_mux->sample_count > 0 && d_mux->error_count == 0);
            }
        }
        snprintf(extra, sizeof(extra), "\"mux_x0\":%" PRId32 ",\"valid\":%s",
                 x0_val, fresh ? "true" : "false");
        msg = "Analog readings";
        break;
    }

    case NEXUS_CMD_DISPLAY_EVENTS: {
        uint32_t ev_count = disp->executive ? disp->executive->event_queue.total_pushed : 0;
        snprintf(extra, sizeof(extra), "\"total_events\":%" PRIu32, ev_count);
        msg = "Event summary";
        break;
    }

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
        if (disp->sensors) {
            for (uint16_t i = 0; i < disp->sensors->count; ++i) {
                total_reads += disp->sensors->entries[i].sample_count;
                total_errs += disp->sensors->entries[i].error_count;
            }
        }
        snprintf(extra, sizeof(extra), "\"reads\":%" PRIu32 ",\"errors\":%" PRIu32,
                 total_reads, total_errs);
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

    case NEXUS_CMD_RUN_SENSOR_TEST: {
        bool all_ok = false;
        if (disp->sensors && disp->sensors->count > 0) {
            all_ok = true;
        }
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

    case NEXUS_CMD_OPEN_DASHBOARD:
    case NEXUS_CMD_OPEN_LOGS:
    case NEXUS_CMD_OPEN_AI:
    case NEXUS_CMD_OPEN_GROUND:
        msg = "Ground station action acknowledged";
        break;

    default:
        code = NEXUS_CMD_STATUS_UNSUPPORTED;
        status_str = "unsupported";
        msg = "Handler not mapped in M8";
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
    char parsed_verb[16] = {0};
    const char *verb_pos = strstr(scratch, "\"verb\":\"");
    if (verb_pos) {
        const char *vstart = verb_pos + 8;
        const char *vend = strchr(vstart, '\"');
        if (vend && (size_t)(vend - vstart) < sizeof(parsed_verb)) {
            memcpy(parsed_verb, vstart, (size_t)(vend - vstart));
            parsed_verb[vend - vstart] = '\0';
        }
    }

    /* Extract noun string */
    char parsed_noun[16] = {0};
    const char *noun_pos = strstr(scratch, "\"noun\":\"");
    if (noun_pos) {
        const char *nstart = noun_pos + 8;
        const char *nend = strchr(nstart, '\"');
        if (nend && (size_t)(nend - nstart) < sizeof(parsed_noun)) {
            memcpy(parsed_noun, nstart, (size_t)(nend - nstart));
            parsed_noun[nend - nstart] = '\0';
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

    /* Check if supported in M8 */
    if (!entry->is_supported_m8) {
        dispatcher->stats.commands_unsupported++;
        return format_response(out_resp_env, seq, uptime_ms, entry->cmd_id,
                               entry->verb_name, entry->noun_name,
                               NEXUS_CMD_STATUS_UNSUPPORTED, "unsupported",
                               entry->description ? entry->description : "Command deferred or unsupported in M8",
                               NULL);
    }

    /* Dispatch to supported command handler */
    return execute_supported_command(dispatcher, entry, seq, uptime_ms, out_resp_env);
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
