#ifndef NEXUS_CONNECTION_MANAGER_H
#define NEXUS_CONNECTION_MANAGER_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
#include <atomic>
typedef std::atomic<bool> nexus_atomic_bool_t;
#else
#include <stdatomic.h>
typedef atomic_bool nexus_atomic_bool_t;
#endif

#include "nexus_transport.h"
#include "nexus_envelope.h"
#include "nexus_serial_transport.h"
#include "nexus_wifi_mqtt_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_CONN_TX_QUEUE_CAPACITY 16U
#define NEXUS_CONN_DEDUP_WINDOW      32U

typedef struct {
    nexus_envelope_t envelope;
    nexus_route_policy_t route;
} nexus_tx_queue_item_t;

typedef struct {
    nexus_tx_queue_item_t items[NEXUS_CONN_TX_QUEUE_CAPACITY];
    uint16_t head;
    uint16_t tail;
    uint16_t count;
    uint16_t high_water_mark;
    uint32_t total_enqueued;
    uint32_t total_dispatched;
    uint32_t total_dropped;
    uint32_t total_failed;
} nexus_conn_tx_queue_t;

typedef struct {
    nexus_transport_type_t source;
    char dev[NEXUS_DEV_ID_MAX_LEN];
    uint32_t seq;
} nexus_conn_dedup_entry_t;

typedef struct {
    nexus_conn_dedup_entry_t history[NEXUS_CONN_DEDUP_WINDOW];
    uint16_t head;
    uint16_t count;
    uint32_t duplicates_detected;
} nexus_conn_dedup_t;

typedef struct {
    nexus_serial_config_t serial_cfg;
    nexus_wifi_mqtt_config_t wifi_mqtt_cfg;
    nexus_route_policy_t default_route;
} nexus_conn_mgr_config_t;

typedef struct {
    nexus_conn_state_t overall_state;
    uint32_t tx_enqueued;
    uint32_t tx_dispatched;
    uint32_t tx_dropped;
    uint32_t tx_failed;
    uint32_t rx_packets;
    uint32_t rx_duplicates;
    uint16_t tx_queue_depth;
    uint16_t tx_queue_hwm;
    nexus_transport_stats_t serial_stats;
    nexus_transport_stats_t mqtt_stats;
} nexus_conn_mgr_stats_t;

typedef void (*nexus_conn_rx_callback_t)(void *user_ctx,
                                         nexus_transport_type_t source,
                                         const nexus_envelope_t *env);

typedef struct nexus_conn_mgr {
    nexus_transport_t serial_transport;
    nexus_transport_t mqtt_transport;
    nexus_transport_t *transports[NEXUS_TRANSPORT_TYPE_COUNT];

    nexus_conn_tx_queue_t tx_queue;
    nexus_conn_dedup_t dedup;
    nexus_route_policy_t default_route;

    nexus_conn_state_t state;
    uint32_t next_seq;

    nexus_conn_rx_callback_t rx_cb;
    void *rx_user_ctx;

    bool initialized;
    nexus_atomic_bool_t running;

#ifdef ESP_PLATFORM
    void *tx_mutex;       /* SemaphoreHandle_t */
    void *task_handle;    /* TaskHandle_t */
    void *task_exit_sem;  /* SemaphoreHandle_t */
#else
    bool mock_task_active;
    bool mock_in_worker_context;
    bool mock_task_exit_timeout;
    bool mock_task_create_fail;
#endif
} nexus_conn_mgr_t;

/* Lifecycle APIs */

/**
 * @brief Initializes the connection manager instance and underlying transports.
 *
 * Calling Context: Task context only. Must NOT be called from an ISR.
 */
bool nexus_conn_mgr_init(nexus_conn_mgr_t *mgr, const nexus_conn_mgr_config_t *config);

/**
 * @brief Starts the connection manager, underlying physical transports, and background worker task.
 *
 * Calling Context: Task context only. Must NOT be called from an ISR.
 * Re-entrant/Concurrent: NOT thread-safe for concurrent calls from multiple tasks.
 * Duplicate calls when already running are safely ignored and return true.
 * If worker task creation fails, all transports started during the call are cleanly rolled back.
 *
 * @param mgr Pointer to initialized connection manager.
 * @return true if successfully started or already running; false on initialization or worker creation failure.
 */
bool nexus_conn_mgr_start(nexus_conn_mgr_t *mgr);

/**
 * @brief Gracefully requests worker task termination and halts underlying physical transports.
 *
 * The call signals the worker task and waits with a bounded timeout (500 ms) for the worker
 * to exit its dispatch loop and acknowledge termination via a binary semaphore.
 *
 * Calling Context: Task context only.
 * RESTRICTIONS:
 * - Must NOT be called from an ISR.
 * - Must NOT be called from the connection manager worker task (nexus_conn) itself.
 *   Calling from the worker context is rejected immediately and returns false.
 * - Must NOT be called concurrently with nexus_conn_mgr_start().
 *
 * Timeout & Recovery Semantics:
 * If the worker task fails to acknowledge termination within the bounded timeout, this
 * function logs an error, leaves the worker handle intact, does NOT stop physical transports,
 * and returns false. The caller may safely retry stop() without corrupting state or orphaning locks.
 *
 * @param mgr Pointer to initialized connection manager.
 * @return true if worker cleanly stopped and transports halted; false on timeout or invalid context.
 */
bool nexus_conn_mgr_stop(nexus_conn_mgr_t *mgr);

/**
 * @brief Checks whether the connection manager worker is running or active.
 */
bool nexus_conn_mgr_is_running(const nexus_conn_mgr_t *mgr);

/* Non-blocking enqueue from executive or any caller */
bool nexus_conn_mgr_enqueue(nexus_conn_mgr_t *mgr,
                            const nexus_envelope_t *env,
                            nexus_route_policy_t route);

/* Format and enqueue helper functions */
bool nexus_conn_mgr_send_heartbeat(nexus_conn_mgr_t *mgr,
                                   int64_t uptime_ms,
                                   uint32_t free_heap,
                                   uint32_t exec_ticks,
                                   nexus_route_policy_t route);

bool nexus_conn_mgr_send_telemetry(nexus_conn_mgr_t *mgr,
                                   int64_t uptime_ms,
                                   int32_t ldr_raw,
                                   int32_t mux_x0_raw,
                                   int32_t dht_temp,
                                   int32_t dht_hum,
                                   nexus_route_policy_t route);

bool nexus_conn_mgr_send_status(nexus_conn_mgr_t *mgr,
                                int64_t uptime_ms,
                                uint32_t dispatched,
                                uint32_t completed,
                                uint32_t failed,
                                uint32_t max_lat_us,
                                uint32_t max_dur_us,
                                nexus_route_policy_t route);

/* Ingress packet handling with framing parsing and deduplication */
bool nexus_conn_mgr_process_rx(nexus_conn_mgr_t *mgr,
                               nexus_transport_type_t source,
                               const uint8_t *data,
                               size_t len);

/* Sequence deduplication check & record (composite key: source + dev + seq) */
bool nexus_conn_mgr_is_duplicate(const nexus_conn_mgr_t *mgr,
                                 nexus_transport_type_t source,
                                 const char *dev,
                                 uint32_t seq);

void nexus_conn_mgr_record_seq(nexus_conn_mgr_t *mgr,
                               nexus_transport_type_t source,
                               const char *dev,
                               uint32_t seq);

void nexus_conn_mgr_reset_dedup(nexus_conn_mgr_t *mgr);

/* State & Diagnostics */
nexus_conn_state_t nexus_conn_mgr_get_state(nexus_conn_mgr_t *mgr);
nexus_conn_state_t nexus_conn_mgr_get_transport_state(const nexus_conn_mgr_t *mgr, nexus_transport_type_t type);
void nexus_conn_mgr_get_stats(const nexus_conn_mgr_t *mgr, nexus_conn_mgr_stats_t *out_stats);
void nexus_conn_mgr_set_rx_callback(nexus_conn_mgr_t *mgr, nexus_conn_rx_callback_t cb, void *user_ctx);

/* Host / synchronous processing helper: pops and dispatches queued envelopes */
size_t nexus_conn_mgr_process_tx_queue(nexus_conn_mgr_t *mgr);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_CONNECTION_MANAGER_H */
