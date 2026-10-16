#ifndef NEXUS_ENVELOPE_H
#define NEXUS_ENVELOPE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_ENVELOPE_MAX_LEN      256U
#define NEXUS_PROTOCOL_VERSION      1U
#define NEXUS_DEVICE_ID_DEFAULT     "nexus_esp32"

typedef enum {
    NEXUS_MSG_TYPE_HEARTBEAT = 0,
    NEXUS_MSG_TYPE_TELEMETRY = 1,
    NEXUS_MSG_TYPE_EVENT     = 2,
    NEXUS_MSG_TYPE_STATUS    = 3,
    NEXUS_MSG_TYPE_COMMAND   = 4,
    NEXUS_MSG_TYPE_RESPONSE  = 5
} nexus_msg_type_t;

typedef struct {
    uint8_t buffer[NEXUS_ENVELOPE_MAX_LEN];
    uint16_t length;
    uint32_t seq;
    nexus_msg_type_t type;
    int64_t timestamp_us;
} nexus_envelope_t;

void nexus_envelope_init(nexus_envelope_t *env);

bool nexus_envelope_format_heartbeat(nexus_envelope_t *env,
                                     uint32_t seq,
                                     int64_t uptime_ms,
                                     uint32_t free_heap,
                                     uint32_t exec_ticks);

bool nexus_envelope_format_telemetry(nexus_envelope_t *env,
                                     uint32_t seq,
                                     int64_t uptime_ms,
                                     int32_t ldr_raw,
                                     int32_t mux_x0_raw,
                                     int32_t dht_temp,
                                     int32_t dht_hum);

bool nexus_envelope_format_event(nexus_envelope_t *env,
                                 uint32_t seq,
                                 int64_t uptime_ms,
                                 uint8_t event_type,
                                 uint8_t severity,
                                 uint16_t source_id,
                                 int32_t payload);

bool nexus_envelope_format_status(nexus_envelope_t *env,
                                  uint32_t seq,
                                  int64_t uptime_ms,
                                  uint32_t dispatched,
                                  uint32_t completed,
                                  uint32_t failed,
                                  uint32_t max_lat_us,
                                  uint32_t max_dur_us);

#define NEXUS_DEV_ID_MAX_LEN       16U

bool nexus_envelope_parse_header(const uint8_t *data,
                                 size_t len,
                                 uint32_t *out_ver,
                                 uint32_t *out_seq,
                                 char *out_type,
                                 size_t type_buf_len);

bool nexus_envelope_parse_header_ext(const uint8_t *data,
                                     size_t len,
                                     uint32_t *out_ver,
                                     char *out_dev,
                                     size_t dev_buf_len,
                                     uint32_t *out_seq,
                                     char *out_type,
                                     size_t type_buf_len);

const char *nexus_msg_type_str(nexus_msg_type_t type);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_ENVELOPE_H */
