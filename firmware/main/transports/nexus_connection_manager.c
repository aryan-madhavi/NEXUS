#include "nexus_connection_manager.h"
#include <string.h>
#include <stdio.h>

#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
static const char *TAG = "nexus_conn_mgr";

/* Dual-core spinlock protecting bounded TX queue operations and multi-field statistics snapshots */
static portMUX_TYPE s_conn_mgr_tx_mux = portMUX_INITIALIZER_UNLOCKED;
#define CONN_MGR_LOCK()    taskENTER_CRITICAL(&s_conn_mgr_tx_mux)
#define CONN_MGR_UNLOCK()  taskEXIT_CRITICAL(&s_conn_mgr_tx_mux)

#else
#include <time.h>
#include <pthread.h>
static inline int64_t esp_timer_get_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((int64_t)ts.tv_sec * 1000000LL) + ((int64_t)ts.tv_nsec / 1000LL);
}

/* Host test critical section emulation via pthread mutex */
static pthread_mutex_t s_host_conn_mgr_mutex = PTHREAD_MUTEX_INITIALIZER;
#define CONN_MGR_LOCK()    pthread_mutex_lock(&s_host_conn_mgr_mutex)
#define CONN_MGR_UNLOCK()  pthread_mutex_unlock(&s_host_conn_mgr_mutex)
#endif

#ifdef ESP_PLATFORM
#include <fcntl.h>
#include <unistd.h>

static void conn_mgr_task(void *arg)
{
    nexus_conn_mgr_t *mgr = (nexus_conn_mgr_t *)arg;
    ESP_LOGI(TAG, "Connection manager task started");

    /* Ensure stdin is non-blocking for serial command ingress */
    fcntl(fileno(stdin), F_SETFL, O_NONBLOCK);

    char s_rx_line[NEXUS_ENVELOPE_MAX_LEN];
    size_t s_rx_idx = 0;

    while (mgr && atomic_load_explicit(&mgr->running, memory_order_acquire)) {
        nexus_conn_mgr_process_tx_queue(mgr);

        /* Drain non-blocking serial RX characters from stdin */
        char rx_buf[64];
        ssize_t n = read(fileno(stdin), rx_buf, sizeof(rx_buf));
        if (n > 0) {
            for (ssize_t i = 0; i < n; i++) {
                char ch = rx_buf[i];
                if (ch == '\n' || ch == '\r') {
                    if (s_rx_idx > 0) {
                        s_rx_line[s_rx_idx] = '\0';
                        nexus_conn_mgr_process_rx(mgr, NEXUS_TRANSPORT_TYPE_SERIAL,
                                                  (const uint8_t *)s_rx_line, s_rx_idx);
                        s_rx_idx = 0;
                    }
                } else if (s_rx_idx < sizeof(s_rx_line) - 1) {
                    s_rx_line[s_rx_idx++] = ch;
                } else {
                    s_rx_idx = 0; /* Overflow: discard oversized frame */
                }
            }
        }

        /* Sleep with immediate wakeup on stop notification */
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(10));
    }

    ESP_LOGI(TAG, "Connection manager task exiting");
    if (mgr && mgr->task_exit_sem) {
        xSemaphoreGive((SemaphoreHandle_t)mgr->task_exit_sem);
    }
    vTaskDelete(NULL);
}
#endif

static bool conn_mgr_mqtt_rx_trampoline(void *user_ctx, const uint8_t *data, size_t len)
{
    nexus_conn_mgr_t *mgr = (nexus_conn_mgr_t *)user_ctx;
    return nexus_conn_mgr_process_rx(mgr, NEXUS_TRANSPORT_TYPE_MQTT, data, len);
}

bool nexus_conn_mgr_init(nexus_conn_mgr_t *mgr, const nexus_conn_mgr_config_t *config)
{
    if (!mgr) {
        return false;
    }

    memset(mgr, 0, sizeof(*mgr));
    atomic_init(&mgr->running, false);
    mgr->default_route = config ? config->default_route : NEXUS_ROUTE_AUTO;
    mgr->next_seq = 1U;
    mgr->state = NEXUS_CONN_STATE_DISCONNECTED;

    /* Initialize Serial Transport */
    if (!nexus_serial_transport_init(&mgr->serial_transport, config ? &config->serial_cfg : NULL)) {
        return false;
    }
    mgr->transports[NEXUS_TRANSPORT_TYPE_SERIAL] = &mgr->serial_transport;

    /* Initialize Wi-Fi/MQTT Transport */
    if (!nexus_wifi_mqtt_transport_init(&mgr->mqtt_transport, config ? &config->wifi_mqtt_cfg : NULL)) {
        return false;
    }
    mgr->transports[NEXUS_TRANSPORT_TYPE_MQTT] = &mgr->mqtt_transport;
    nexus_wifi_mqtt_transport_set_rx_handler(&mgr->mqtt_transport, conn_mgr_mqtt_rx_trampoline, mgr);

#ifdef ESP_PLATFORM
    mgr->task_exit_sem = xSemaphoreCreateBinary();
    if (!mgr->task_exit_sem) {
        return false;
    }
#else
    mgr->mock_task_active = false;
    mgr->mock_in_worker_context = false;
    mgr->mock_task_exit_timeout = false;
    mgr->mock_task_create_fail = false;
#endif

    mgr->initialized = true;
    return true;
}

bool nexus_conn_mgr_start(nexus_conn_mgr_t *mgr)
{
    if (!mgr || !mgr->initialized) {
        return false;
    }

    /* If the worker is genuinely running, preserve idempotent-start behavior */
    if (atomic_load_explicit(&mgr->running, memory_order_acquire)) {
        return true;
    }

    /* If a previous worker still has a non-NULL handle / is terminating, log clear error and return false */
#ifdef ESP_PLATFORM
    if (mgr->task_handle != NULL) {
        ESP_LOGE(TAG, "Cannot start connection manager: previous worker task (handle=%p) has not exited",
                 mgr->task_handle);
        return false;
    }
#else
    if (mgr->mock_task_active) {
        return false;
    }
#endif

    /* Start both transports */
    bool serial_started = mgr->serial_transport.ops->start(&mgr->serial_transport);
    bool mqtt_started = mgr->mqtt_transport.ops->start(&mgr->mqtt_transport);
    if (!serial_started && !mqtt_started) {
        return false;
    }

    atomic_store_explicit(&mgr->running, true, memory_order_release);

#ifdef ESP_PLATFORM
    /* Drain any stale token from previous task exit only when safe (previous worker terminated, task_handle == NULL) */
    if (mgr->task_exit_sem) {
        xSemaphoreTake((SemaphoreHandle_t)mgr->task_exit_sem, 0);
    }

    BaseType_t ret = xTaskCreate(conn_mgr_task,
                                 "nexus_conn",
                                 4096,
                                 mgr,
                                 2,
                                 (TaskHandle_t *)&mgr->task_handle);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create connection manager worker task; rolling back");
        atomic_store_explicit(&mgr->running, false, memory_order_release);
        mgr->task_handle = NULL;
        /* Roll back started transports in reverse order */
        if (mqtt_started) {
            mgr->mqtt_transport.ops->stop(&mgr->mqtt_transport);
        }
        if (serial_started) {
            mgr->serial_transport.ops->stop(&mgr->serial_transport);
        }
        mgr->state = NEXUS_CONN_STATE_DISCONNECTED;
        return false;
    }
#else
    if (mgr->mock_task_create_fail) {
        atomic_store_explicit(&mgr->running, false, memory_order_release);
        if (mqtt_started) {
            mgr->mqtt_transport.ops->stop(&mgr->mqtt_transport);
        }
        if (serial_started) {
            mgr->serial_transport.ops->stop(&mgr->serial_transport);
        }
        mgr->state = NEXUS_CONN_STATE_DISCONNECTED;
        return false;
    }
    mgr->mock_task_active = true;
#endif

    nexus_conn_mgr_get_state(mgr);
    return true;
}

bool nexus_conn_mgr_stop(nexus_conn_mgr_t *mgr)
{
    if (!mgr || !mgr->initialized) {
        return false;
    }

    /* B. Reject worker self-stop safely */
#ifdef ESP_PLATFORM
    if (mgr->task_handle && xTaskGetCurrentTaskHandle() == (TaskHandle_t)mgr->task_handle) {
        ESP_LOGE(TAG, "nexus_conn_mgr_stop called from worker task context; rejected");
        return false;
    }
#else
    if (mgr->mock_in_worker_context) {
        return false;
    }
#endif

    /* 1. Request worker task termination and wait for completion */
#ifdef ESP_PLATFORM
    if (mgr->task_handle != NULL) {
        TaskHandle_t th = (TaskHandle_t)mgr->task_handle;
        atomic_store_explicit(&mgr->running, false, memory_order_release);

        /* Wake worker task immediately if sleeping on notification */
        xTaskNotifyGive(th);

        /* Wait with bounded timeout (500 ms) on exit semaphore */
        if (mgr->task_exit_sem) {
            if (xSemaphoreTake((SemaphoreHandle_t)mgr->task_exit_sem, pdMS_TO_TICKS(500)) != pdTRUE) {
                ESP_LOGE(TAG, "Worker task exit timeout (500 ms); worker still active. Preserving handle for retry.");
                return false; /* Stop failed, retryable by caller. Transports remain active! */
            }
        }
        mgr->task_handle = NULL;
    } else {
        atomic_store_explicit(&mgr->running, false, memory_order_release);
    }
#else
    if (mgr->mock_task_exit_timeout) {
        atomic_store_explicit(&mgr->running, false, memory_order_release);
        return false;
    }
    atomic_store_explicit(&mgr->running, false, memory_order_release);
    mgr->mock_task_active = false;
#endif

    /* 2. Stop both transports only AFTER worker task has finished and exited cleanly */
    mgr->mqtt_transport.ops->stop(&mgr->mqtt_transport);
    mgr->serial_transport.ops->stop(&mgr->serial_transport);
    mgr->state = NEXUS_CONN_STATE_DISCONNECTED;

    return true;
}

bool nexus_conn_mgr_is_running(const nexus_conn_mgr_t *mgr)
{
    if (!mgr) {
        return false;
    }
    bool running = atomic_load_explicit(&mgr->running, memory_order_acquire);
#ifdef ESP_PLATFORM
    return (running || mgr->task_handle != NULL);
#else
    return (running || mgr->mock_task_active);
#endif
}

bool nexus_conn_mgr_enqueue(nexus_conn_mgr_t *mgr,
                            const nexus_envelope_t *env,
                            nexus_route_policy_t route)
{
    if (!mgr || !mgr->initialized || !env || env->length == 0) {
        return false;
    }

    /* Bounded non-preemptible critical section guaranteeing deterministic execution duration (< 1 us)
     * without blocking, eliminating priority preemption contention drops while respecting the 50 ms
     * executive callback budget. */
    CONN_MGR_LOCK();

    if (mgr->tx_queue.count >= NEXUS_CONN_TX_QUEUE_CAPACITY) {
        mgr->tx_queue.total_dropped++;
        CONN_MGR_UNLOCK();
        return false;
    }

    /* Bounded enqueue with envelope copy */
    nexus_tx_queue_item_t *item = &mgr->tx_queue.items[mgr->tx_queue.head];
    memcpy(&item->envelope, env, sizeof(nexus_envelope_t));
    item->route = route;

    mgr->tx_queue.head = (mgr->tx_queue.head + 1U) % NEXUS_CONN_TX_QUEUE_CAPACITY;
    mgr->tx_queue.count++;
    if (mgr->tx_queue.count > mgr->tx_queue.high_water_mark) {
        mgr->tx_queue.high_water_mark = mgr->tx_queue.count;
    }
    mgr->tx_queue.total_enqueued++;

    CONN_MGR_UNLOCK();
    return true;
}

bool nexus_conn_mgr_send_heartbeat(nexus_conn_mgr_t *mgr,
                                   int64_t uptime_ms,
                                   uint32_t free_heap,
                                   uint32_t exec_ticks,
                                   nexus_route_policy_t route)
{
    if (!mgr) {
        return false;
    }

    nexus_envelope_t env;
    uint32_t seq = mgr->next_seq++;
    if (!nexus_envelope_format_heartbeat(&env, seq, uptime_ms, free_heap, exec_ticks)) {
        return false;
    }

    return nexus_conn_mgr_enqueue(mgr, &env, route);
}

bool nexus_conn_mgr_send_telemetry_ext(nexus_conn_mgr_t *mgr,
                                       int64_t uptime_ms,
                                       int32_t ldr_raw,
                                       int32_t mux_x0_raw,
                                       int32_t mux_x1_raw,
                                       int32_t dht_temp,
                                       int32_t dht_hum,
                                       bool dht_valid,
                                       int32_t slot_state,
                                       int32_t dist_cm,
                                       nexus_route_policy_t route)
{
    if (!mgr) {
        return false;
    }

    nexus_envelope_t env;
    uint32_t seq = mgr->next_seq++;
    if (!nexus_envelope_format_telemetry_ext(&env, seq, uptime_ms,
                                            ldr_raw, mux_x0_raw, mux_x1_raw,
                                            dht_temp, dht_hum, dht_valid,
                                            slot_state, dist_cm)) {
        return false;
    }

    return nexus_conn_mgr_enqueue(mgr, &env, route);
}

bool nexus_conn_mgr_send_telemetry(nexus_conn_mgr_t *mgr,
                                   int64_t uptime_ms,
                                   int32_t ldr_raw,
                                   int32_t mux_x0_raw,
                                   int32_t dht_temp,
                                   int32_t dht_hum,
                                   bool dht_valid,
                                   nexus_route_policy_t route)
{
    return nexus_conn_mgr_send_telemetry_ext(mgr, uptime_ms,
                                            ldr_raw, mux_x0_raw, -1,
                                            dht_temp, dht_hum, dht_valid,
                                            -1, -1, route);
}

bool nexus_conn_mgr_send_status(nexus_conn_mgr_t *mgr,
                                int64_t uptime_ms,
                                uint32_t dispatched,
                                uint32_t completed,
                                uint32_t failed,
                                uint32_t max_lat_us,
                                uint32_t max_dur_us,
                                nexus_route_policy_t route)
{
    if (!mgr) {
        return false;
    }

    nexus_envelope_t env;
    uint32_t seq = mgr->next_seq++;
    if (!nexus_envelope_format_status(&env, seq, uptime_ms, dispatched, completed, failed, max_lat_us, max_dur_us)) {
        return false;
    }

    return nexus_conn_mgr_enqueue(mgr, &env, route);
}

static bool dispatch_item(nexus_conn_mgr_t *mgr, const nexus_tx_queue_item_t *item)
{
    if (!mgr || !item) {
        return false;
    }

    nexus_route_policy_t policy = item->route;
    if (policy == NEXUS_ROUTE_AUTO) {
        policy = mgr->default_route;
    }

    bool serial_connected = mgr->serial_transport.ops->is_connected(&mgr->serial_transport);
    bool mqtt_connected = mgr->mqtt_transport.ops->is_connected(&mgr->mqtt_transport);
    bool dispatched = false;

    switch (policy) {
    case NEXUS_ROUTE_AUTO:
        /* Prioritize MQTT when online, fallback transparently to USB serial */
        if (mqtt_connected) {
            dispatched = mgr->mqtt_transport.ops->send(&mgr->mqtt_transport,
                                                       item->envelope.buffer,
                                                       item->envelope.length,
                                                       100U);
        } else if (serial_connected) {
            dispatched = mgr->serial_transport.ops->send(&mgr->serial_transport,
                                                         item->envelope.buffer,
                                                         item->envelope.length,
                                                         100U);
        }
        break;

    case NEXUS_ROUTE_SERIAL_ONLY:
        if (serial_connected) {
            dispatched = mgr->serial_transport.ops->send(&mgr->serial_transport,
                                                         item->envelope.buffer,
                                                         item->envelope.length,
                                                         100U);
        }
        break;

    case NEXUS_ROUTE_MQTT_ONLY:
        if (mqtt_connected) {
            dispatched = mgr->mqtt_transport.ops->send(&mgr->mqtt_transport,
                                                       item->envelope.buffer,
                                                       item->envelope.length,
                                                       100U);
        }
        break;

    case NEXUS_ROUTE_BROADCAST:
        /* Transmit to all connected transports */
        if (serial_connected) {
            bool s_ok = mgr->serial_transport.ops->send(&mgr->serial_transport,
                                                        item->envelope.buffer,
                                                        item->envelope.length,
                                                        100U);
            if (s_ok) {
                dispatched = true;
            }
        }
        if (mqtt_connected) {
            bool m_ok = mgr->mqtt_transport.ops->send(&mgr->mqtt_transport,
                                                       item->envelope.buffer,
                                                       item->envelope.length,
                                                       100U);
            if (m_ok) {
                dispatched = true;
            }
        }
        break;
    }

    return dispatched;
}

size_t nexus_conn_mgr_process_tx_queue(nexus_conn_mgr_t *mgr)
{
    if (!mgr || !mgr->initialized) {
        return 0;
    }

    size_t processed = 0;

    for (;;) {
        /* If worker shutdown is requested, stop dequeuing and yield immediately */
        if (!atomic_load_explicit(&mgr->running, memory_order_acquire)) {
            break;
        }

        nexus_tx_queue_item_t item;
        bool has_item = false;

        CONN_MGR_LOCK();
        if (mgr->tx_queue.count > 0) {
            memcpy(&item, &mgr->tx_queue.items[mgr->tx_queue.tail], sizeof(nexus_tx_queue_item_t));
            mgr->tx_queue.tail = (mgr->tx_queue.tail + 1U) % NEXUS_CONN_TX_QUEUE_CAPACITY;
            mgr->tx_queue.count--;
            has_item = true;
        }
        CONN_MGR_UNLOCK();

        if (!has_item) {
            break;
        }

        bool ok = dispatch_item(mgr, &item);
        CONN_MGR_LOCK();
        if (ok) {
            mgr->tx_queue.total_dispatched++;
        } else {
            mgr->tx_queue.total_failed++;
        }
        CONN_MGR_UNLOCK();
        processed++;
    }

    return processed;
}

bool nexus_conn_mgr_is_duplicate(const nexus_conn_mgr_t *mgr,
                                 nexus_transport_type_t source,
                                 const char *dev,
                                 uint32_t seq)
{
    if (!mgr || mgr->dedup.count == 0) {
        return false;
    }

    const char *target_dev = dev ? dev : "";

    for (uint16_t i = 0; i < mgr->dedup.count; i++) {
        const nexus_conn_dedup_entry_t *entry = &mgr->dedup.history[i];
        if (entry->source == source && entry->seq == seq) {
            if (target_dev[0] == '\0' && entry->dev[0] == '\0') {
                return true;
            }
            if (strncmp(entry->dev, target_dev, NEXUS_DEV_ID_MAX_LEN) == 0) {
                return true;
            }
        }
    }
    return false;
}

void nexus_conn_mgr_record_seq(nexus_conn_mgr_t *mgr,
                               nexus_transport_type_t source,
                               const char *dev,
                               uint32_t seq)
{
    if (!mgr) {
        return;
    }

    nexus_conn_dedup_entry_t *entry = &mgr->dedup.history[mgr->dedup.head];
    entry->source = source;
    entry->seq = seq;
    if (dev) {
        strncpy(entry->dev, dev, sizeof(entry->dev) - 1);
        entry->dev[sizeof(entry->dev) - 1] = '\0';
    } else {
        entry->dev[0] = '\0';
    }

    mgr->dedup.head = (mgr->dedup.head + 1U) % NEXUS_CONN_DEDUP_WINDOW;
    if (mgr->dedup.count < NEXUS_CONN_DEDUP_WINDOW) {
        mgr->dedup.count++;
    }
}

void nexus_conn_mgr_reset_dedup(nexus_conn_mgr_t *mgr)
{
    if (!mgr) {
        return;
    }
    memset(&mgr->dedup, 0, sizeof(mgr->dedup));
}

bool nexus_conn_mgr_process_rx(nexus_conn_mgr_t *mgr,
                               nexus_transport_type_t source,
                               const uint8_t *data,
                               size_t len)
{
    if (!mgr || !data || len == 0) {
        return false;
    }

    uint32_t version = 0;
    uint32_t seq = 0;
    char type_str[16] = {0};
    char dev_str[NEXUS_DEV_ID_MAX_LEN] = {0};

    if (!nexus_envelope_parse_header_ext(data, len, &version, dev_str, sizeof(dev_str), &seq, type_str, sizeof(type_str))) {
        return false;
    }

    /* Reject unsupported protocol versions */
    if (version != NEXUS_PROTOCOL_VERSION) {
        return false;
    }

    /* Parse and validate envelope message type */
    nexus_msg_type_t msg_type;
    if (!nexus_envelope_parse_type(type_str, &msg_type)) {
        return false;
    }

    /* Enforce permitted ingress types: MQTT ingress on /cmd topic permits only COMMAND messages */
    if (source == NEXUS_TRANSPORT_TYPE_MQTT && msg_type != NEXUS_MSG_TYPE_COMMAND) {
        return false;
    }

    /* Sequence deduplication filter using composite identity: (source, dev, seq) */
    if (nexus_conn_mgr_is_duplicate(mgr, source, dev_str, seq)) {
        mgr->dedup.duplicates_detected++;
        return false;
    }

    nexus_conn_mgr_record_seq(mgr, source, dev_str, seq);

    if (mgr->rx_cb) {
        nexus_envelope_t env;
        nexus_envelope_init(&env);
        size_t copy_len = (len < NEXUS_ENVELOPE_MAX_LEN) ? len : (NEXUS_ENVELOPE_MAX_LEN - 1);
        memcpy(env.buffer, data, copy_len);
        env.buffer[copy_len] = '\0';
        env.length = (uint16_t)copy_len;
        env.seq = seq;
        env.type = msg_type;
        env.timestamp_us = esp_timer_get_time();

        mgr->rx_cb(mgr->rx_user_ctx, source, &env);
    }

    return true;
}

nexus_conn_state_t nexus_conn_mgr_get_state(nexus_conn_mgr_t *mgr)
{
    if (!mgr || !mgr->initialized) {
        return NEXUS_CONN_STATE_DISCONNECTED;
    }

    bool s_conn = mgr->serial_transport.ops->is_connected(&mgr->serial_transport);
    bool m_conn = mgr->mqtt_transport.ops->is_connected(&mgr->mqtt_transport);
    nexus_conn_state_t m_state = mgr->mqtt_transport.ops->get_state(&mgr->mqtt_transport);

    if (s_conn && m_conn) {
        mgr->state = NEXUS_CONN_STATE_CONNECTED;
    } else if (s_conn) {
        /* Serial is connected; if MQTT is actively degraded/connecting, state reflects degraded dual-link */
        if (m_state == NEXUS_CONN_STATE_DEGRADED) {
            mgr->state = NEXUS_CONN_STATE_DEGRADED;
        } else {
            mgr->state = NEXUS_CONN_STATE_CONNECTED;
        }
    } else if (m_conn) {
        mgr->state = NEXUS_CONN_STATE_CONNECTED;
    } else if (m_state == NEXUS_CONN_STATE_CONNECTING) {
        mgr->state = NEXUS_CONN_STATE_CONNECTING;
    } else {
        mgr->state = NEXUS_CONN_STATE_DISCONNECTED;
    }

    return mgr->state;
}

nexus_conn_state_t nexus_conn_mgr_get_transport_state(const nexus_conn_mgr_t *mgr, nexus_transport_type_t type)
{
    if (!mgr || (int)type >= NEXUS_TRANSPORT_TYPE_COUNT || !mgr->transports[type]) {
        return NEXUS_CONN_STATE_FAILED;
    }
    return mgr->transports[type]->ops->get_state(mgr->transports[type]);
}

void nexus_conn_mgr_get_stats(const nexus_conn_mgr_t *mgr, nexus_conn_mgr_stats_t *out_stats)
{
    if (!mgr || !out_stats) {
        return;
    }

    memset(out_stats, 0, sizeof(nexus_conn_mgr_stats_t));
    out_stats->overall_state = mgr->state;

    CONN_MGR_LOCK();
    out_stats->tx_enqueued = mgr->tx_queue.total_enqueued;
    out_stats->tx_dispatched = mgr->tx_queue.total_dispatched;
    out_stats->tx_dropped = mgr->tx_queue.total_dropped;
    out_stats->tx_failed = mgr->tx_queue.total_failed;
    out_stats->tx_queue_depth = mgr->tx_queue.count;
    out_stats->tx_queue_hwm = mgr->tx_queue.high_water_mark;
    CONN_MGR_UNLOCK();

    out_stats->rx_duplicates = mgr->dedup.duplicates_detected;

    mgr->serial_transport.ops->get_stats(&mgr->serial_transport, &out_stats->serial_stats);
    mgr->mqtt_transport.ops->get_stats(&mgr->mqtt_transport, &out_stats->mqtt_stats);
}

void nexus_conn_mgr_set_rx_callback(nexus_conn_mgr_t *mgr, nexus_conn_rx_callback_t cb, void *user_ctx)
{
    if (mgr) {
        mgr->rx_cb = cb;
        mgr->rx_user_ctx = user_ctx;
    }
}
