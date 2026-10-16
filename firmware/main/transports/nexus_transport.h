#ifndef NEXUS_TRANSPORT_H
#define NEXUS_TRANSPORT_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    NEXUS_TRANSPORT_TYPE_SERIAL = 0,
    NEXUS_TRANSPORT_TYPE_MQTT   = 1,
    NEXUS_TRANSPORT_TYPE_COUNT  = 2
} nexus_transport_type_t;

typedef enum {
    NEXUS_CONN_STATE_DISCONNECTED = 0,
    NEXUS_CONN_STATE_CONNECTING   = 1,
    NEXUS_CONN_STATE_CONNECTED    = 2,
    NEXUS_CONN_STATE_DEGRADED     = 3,
    NEXUS_CONN_STATE_FAILED       = 4
} nexus_conn_state_t;

typedef enum {
    NEXUS_ROUTE_AUTO        = 0, /* Send to MQTT if connected, fallback to Serial */
    NEXUS_ROUTE_SERIAL_ONLY = 1, /* Transmit over USB serial only */
    NEXUS_ROUTE_MQTT_ONLY   = 2, /* Transmit over MQTT only */
    NEXUS_ROUTE_BROADCAST   = 3  /* Transmit over all connected transports */
} nexus_route_policy_t;

typedef struct {
    uint32_t tx_packets;
    uint32_t tx_bytes;
    uint32_t tx_errors;
    uint32_t rx_packets;
    uint32_t rx_bytes;
    uint32_t rx_errors;
    uint32_t connect_count;
    uint32_t disconnect_count;
    int64_t last_tx_time_us;
    int64_t last_rx_time_us;
} nexus_transport_stats_t;

/* Forward declaration */
struct nexus_transport;

typedef struct {
    bool (*init)(struct nexus_transport *t);
    bool (*start)(struct nexus_transport *t);
    bool (*stop)(struct nexus_transport *t);
    bool (*send)(struct nexus_transport *t, const uint8_t *data, size_t len, uint32_t timeout_ms);
    bool (*is_connected)(const struct nexus_transport *t);
    nexus_conn_state_t (*get_state)(const struct nexus_transport *t);
    void (*get_stats)(const struct nexus_transport *t, nexus_transport_stats_t *out_stats);
} nexus_transport_ops_t;

typedef struct nexus_transport {
    nexus_transport_type_t type;
    const char *name;
    const nexus_transport_ops_t *ops;
    void *driver_ctx;
    nexus_conn_state_t state;
    nexus_transport_stats_t stats;
} nexus_transport_t;

const char *nexus_conn_state_str(nexus_conn_state_t state);
const char *nexus_transport_type_str(nexus_transport_type_t type);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_TRANSPORT_H */
