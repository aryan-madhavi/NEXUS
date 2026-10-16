#include "nexus_envelope.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

const char *nexus_msg_type_str(nexus_msg_type_t type)
{
    switch (type) {
    case NEXUS_MSG_TYPE_HEARTBEAT: return "heartbeat";
    case NEXUS_MSG_TYPE_TELEMETRY: return "telemetry";
    case NEXUS_MSG_TYPE_EVENT:     return "event";
    case NEXUS_MSG_TYPE_STATUS:    return "status";
    case NEXUS_MSG_TYPE_COMMAND:   return "command";
    case NEXUS_MSG_TYPE_RESPONSE:  return "response";
    default:                       return "unknown";
    }
}

void nexus_envelope_init(nexus_envelope_t *env)
{
    if (!env) {
        return;
    }
    memset(env, 0, sizeof(*env));
}

bool nexus_envelope_format_heartbeat(nexus_envelope_t *env,
                                     uint32_t seq,
                                     int64_t uptime_ms,
                                     uint32_t free_heap,
                                     uint32_t exec_ticks)
{
    if (!env) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_HEARTBEAT;

    int written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"hb\",\"uptime\":%" PRId64
                           ",\"heap\":%" PRIu32 ",\"ticks\":%" PRIu32 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, uptime_ms, free_heap, exec_ticks);

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        env->length = 0;
        return false;
    }

    env->length = (uint16_t)written;
    return true;
}

bool nexus_envelope_format_telemetry(nexus_envelope_t *env,
                                     uint32_t seq,
                                     int64_t uptime_ms,
                                     int32_t ldr_raw,
                                     int32_t mux_x0_raw,
                                     int32_t dht_temp,
                                     int32_t dht_hum)
{
    if (!env) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_TELEMETRY;

    int written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"telem\",\"uptime\":%" PRId64
                           ",\"ldr\":%" PRId32 ",\"x0\":%" PRId32
                           ",\"temp\":%" PRId32 ",\"hum\":%" PRId32 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, uptime_ms, ldr_raw, mux_x0_raw, dht_temp, dht_hum);

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        env->length = 0;
        return false;
    }

    env->length = (uint16_t)written;
    return true;
}

bool nexus_envelope_format_event(nexus_envelope_t *env,
                                 uint32_t seq,
                                 int64_t uptime_ms,
                                 uint8_t event_type,
                                 uint8_t severity,
                                 uint16_t source_id,
                                 int32_t payload)
{
    if (!env) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_EVENT;

    int written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"event\",\"uptime\":%" PRId64
                           ",\"ev\":%u,\"sev\":%u,\"src\":%u,\"val\":%" PRId32 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, uptime_ms, (unsigned int)event_type,
                           (unsigned int)severity, (unsigned int)source_id, payload);

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        env->length = 0;
        return false;
    }

    env->length = (uint16_t)written;
    return true;
}

bool nexus_envelope_format_status(nexus_envelope_t *env,
                                  uint32_t seq,
                                  int64_t uptime_ms,
                                  uint32_t dispatched,
                                  uint32_t completed,
                                  uint32_t failed,
                                  uint32_t max_lat_us,
                                  uint32_t max_dur_us)
{
    if (!env) {
        return false;
    }

    env->seq = seq;
    env->type = NEXUS_MSG_TYPE_STATUS;

    int written = snprintf((char *)env->buffer, NEXUS_ENVELOPE_MAX_LEN,
                           "{\"ver\":%u,\"dev\":\"%s\",\"seq\":%" PRIu32
                           ",\"type\":\"status\",\"uptime\":%" PRId64
                           ",\"disp\":%" PRIu32 ",\"comp\":%" PRIu32
                           ",\"fail\":%" PRIu32 ",\"lat_us\":%" PRIu32
                           ",\"dur_us\":%" PRIu32 "}\n",
                           NEXUS_PROTOCOL_VERSION, NEXUS_DEVICE_ID_DEFAULT,
                           seq, uptime_ms, dispatched, completed, failed,
                           max_lat_us, max_dur_us);

    if (written <= 0 || (size_t)written >= NEXUS_ENVELOPE_MAX_LEN) {
        env->length = 0;
        return false;
    }

    env->length = (uint16_t)written;
    return true;
}

bool nexus_envelope_parse_header_ext(const uint8_t *data,
                                     size_t len,
                                     uint32_t *out_ver,
                                     char *out_dev,
                                     size_t dev_buf_len,
                                     uint32_t *out_seq,
                                     char *out_type,
                                     size_t type_buf_len)
{
    if (!data || len == 0 || !out_ver || !out_seq) {
        return false;
    }

    /* Enforce maximum envelope size: reject oversized frames without truncating */
    if (len >= NEXUS_ENVELOPE_MAX_LEN) {
        return false;
    }

    /* Bounded, NUL-terminated local copy sized strictly from protocol constants */
    char scratch[NEXUS_ENVELOPE_MAX_LEN];
    memcpy(scratch, data, len);
    scratch[len] = '\0';

    uint32_t parsed_ver = 0;
    uint32_t parsed_seq = 0;
    char temp_type[32] = {0};
    char temp_dev[NEXUS_DEV_ID_MAX_LEN] = {0};

    /* 1. Parse "ver":%u */
    const char *ver_pos = strstr(scratch, "\"ver\":");
    if (!ver_pos) {
        return false;
    }
    const char *p = ver_pos + 6;
    while (*p == ' ') {
        p++;
    }
    if (*p < '0' || *p > '9') {
        return false;
    }
    char *endptr = NULL;
    unsigned long val = strtoul(p, &endptr, 10);
    if (endptr == p || val > UINT32_MAX) {
        return false;
    }
    parsed_ver = (uint32_t)val;

    /* 2. Parse "seq":%u */
    const char *seq_pos = strstr(scratch, "\"seq\":");
    if (!seq_pos) {
        return false;
    }
    const char *q = seq_pos + 6;
    while (*q == ' ') {
        q++;
    }
    if (*q < '0' || *q > '9') {
        return false;
    }
    val = strtoul(q, &endptr, 10);
    if (endptr == q || val > UINT32_MAX) {
        return false;
    }
    parsed_seq = (uint32_t)val;

    /* 3. Parse "type":"<type>" if caller provided a buffer */
    if (out_type) {
        if (type_buf_len == 0) {
            return false;
        }
        const char *type_pos = strstr(scratch, "\"type\":\"");
        if (!type_pos) {
            return false;
        }
        const char *tstart = type_pos + 8;
        const char *tend = strchr(tstart, '\"');
        if (!tend) {
            return false;
        }
        size_t tlen = (size_t)(tend - tstart);
        if (tlen >= type_buf_len || tlen >= sizeof(temp_type)) {
            return false;
        }
        memcpy(temp_type, tstart, tlen);
        temp_type[tlen] = '\0';
    }

    /* 4. Parse "dev":"<dev>" if requested */
    if (out_dev && dev_buf_len > 0) {
        const char *dev_pos = strstr(scratch, "\"dev\":\"");
        if (dev_pos) {
            const char *dstart = dev_pos + 7;
            const char *dend = strchr(dstart, '\"');
            if (dend) {
                size_t dlen = (size_t)(dend - dstart);
                if (dlen >= dev_buf_len) {
                    dlen = dev_buf_len - 1;
                }
                if (dlen >= sizeof(temp_dev)) {
                    dlen = sizeof(temp_dev) - 1;
                }
                memcpy(temp_dev, dstart, dlen);
                temp_dev[dlen] = '\0';
            }
        }
    }

    /* All validations passed; commit to caller outputs atomically */
    *out_ver = parsed_ver;
    *out_seq = parsed_seq;
    if (out_type && type_buf_len > 0) {
        memcpy(out_type, temp_type, strlen(temp_type) + 1);
    }
    if (out_dev && dev_buf_len > 0) {
        memcpy(out_dev, temp_dev, strlen(temp_dev) + 1);
    }

    return true;
}

bool nexus_envelope_parse_header(const uint8_t *data,
                                 size_t len,
                                 uint32_t *out_ver,
                                 uint32_t *out_seq,
                                 char *out_type,
                                 size_t type_buf_len)
{
    return nexus_envelope_parse_header_ext(data, len, out_ver, NULL, 0, out_seq, out_type, type_buf_len);
}
