#include "nexus_serial_transport.h"
#include <string.h>
#include <stdio.h>

#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "driver/uart.h"
#else
#include <time.h>
static inline int64_t esp_timer_get_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((int64_t)ts.tv_sec * 1000000LL) + ((int64_t)ts.tv_nsec / 1000LL);
}
#endif

#ifndef ESP_PLATFORM
/* Mock storage for host tests */
#define MOCK_SERIAL_BUF_SIZE 2048
typedef struct {
    uint8_t buffer[MOCK_SERIAL_BUF_SIZE];
    size_t length;
    bool force_failure;
} mock_serial_ctx_t;
static mock_serial_ctx_t s_mock_serial;
#endif

static bool serial_init(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }
    t->state = NEXUS_CONN_STATE_DISCONNECTED;
#ifndef ESP_PLATFORM
    s_mock_serial.length = 0;
    s_mock_serial.force_failure = false;
    t->driver_ctx = &s_mock_serial;
#endif
    return true;
}

static bool serial_start(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }
    t->state = NEXUS_CONN_STATE_CONNECTED;
    t->stats.connect_count++;
    return true;
}

static bool serial_stop(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }
    t->state = NEXUS_CONN_STATE_DISCONNECTED;
    t->stats.disconnect_count++;
    return true;
}

static bool serial_send(nexus_transport_t *t, const uint8_t *data, size_t len, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (!t || !data || len == 0 || t->state != NEXUS_CONN_STATE_CONNECTED) {
        if (t) {
            t->stats.tx_errors++;
        }
        return false;
    }

#ifdef ESP_PLATFORM
    /* Output to stdout line-buffered; non-blocking with bounded buffer */
    size_t written = fwrite(data, 1, len, stdout);
    fflush(stdout);
    if (written != len) {
        t->stats.tx_errors++;
        return false;
    }
#else
    mock_serial_ctx_t *mock = (mock_serial_ctx_t *)t->driver_ctx;
    if (!mock || mock->force_failure) {
        t->stats.tx_errors++;
        return false;
    }
    if (mock->length + len <= MOCK_SERIAL_BUF_SIZE) {
        memcpy(mock->buffer + mock->length, data, len);
        mock->length += len;
    } else {
        t->stats.tx_errors++;
        return false;
    }
#endif

    t->stats.tx_packets++;
    t->stats.tx_bytes += (uint32_t)len;
    t->stats.last_tx_time_us = esp_timer_get_time();
    return true;
}

static bool serial_is_connected(const nexus_transport_t *t)
{
    return (t && t->state == NEXUS_CONN_STATE_CONNECTED);
}

static nexus_conn_state_t serial_get_state(const nexus_transport_t *t)
{
    return t ? t->state : NEXUS_CONN_STATE_FAILED;
}

static void serial_get_stats(const nexus_transport_t *t, nexus_transport_stats_t *out_stats)
{
    if (t && out_stats) {
        memcpy(out_stats, &t->stats, sizeof(nexus_transport_stats_t));
    }
}

static const nexus_transport_ops_t s_serial_ops = {
    .init         = serial_init,
    .start        = serial_start,
    .stop         = serial_stop,
    .send         = serial_send,
    .is_connected = serial_is_connected,
    .get_state    = serial_get_state,
    .get_stats    = serial_get_stats
};

bool nexus_serial_transport_init(nexus_transport_t *transport, const nexus_serial_config_t *config)
{
    (void)config;
    if (!transport) {
        return false;
    }

    memset(transport, 0, sizeof(*transport));
    transport->type = NEXUS_TRANSPORT_TYPE_SERIAL;
    transport->name = "serial";
    transport->ops = &s_serial_ops;
    transport->state = NEXUS_CONN_STATE_DISCONNECTED;

    return transport->ops->init(transport);
}

#ifndef ESP_PLATFORM
void nexus_serial_transport_mock_reset(nexus_transport_t *transport)
{
    (void)transport;
    s_mock_serial.length = 0;
    s_mock_serial.force_failure = false;
}

size_t nexus_serial_transport_mock_get_tx(nexus_transport_t *transport, uint8_t *out_buf, size_t max_len)
{
    (void)transport;
    if (!out_buf || max_len == 0) {
        return s_mock_serial.length;
    }
    size_t to_copy = (s_mock_serial.length < max_len) ? s_mock_serial.length : max_len;
    memcpy(out_buf, s_mock_serial.buffer, to_copy);
    return to_copy;
}

void nexus_serial_transport_mock_set_fail(nexus_transport_t *transport, bool fail)
{
    (void)transport;
    s_mock_serial.force_failure = fail;
}
#endif
