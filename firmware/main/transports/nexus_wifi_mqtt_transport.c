#include "nexus_wifi_mqtt_transport.h"
#include <string.h>
#include <stdio.h>
#include <inttypes.h>

uint32_t nexus_wifi_mqtt_compute_next_backoff(uint32_t current_ms, uint32_t max_ms)
{
    if (current_ms == 0) {
        return 1000U;
    }
    uint32_t next = current_ms * 2U;
    if (next < current_ms || next > max_ms) {
        next = max_ms;
    }
    return next;
}

#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "mqtt_client.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "nexus_wifi_mqtt";

/* ESP-IDF classic dual-core spinlock protecting state and multi-field statistics snapshots */
static portMUX_TYPE s_wifi_mqtt_spinlock = portMUX_INITIALIZER_UNLOCKED;
#define WIFI_MQTT_LOCK()    taskENTER_CRITICAL(&s_wifi_mqtt_spinlock)
#define WIFI_MQTT_UNLOCK()  taskEXIT_CRITICAL(&s_wifi_mqtt_spinlock)

typedef struct {
    nexus_wifi_mqtt_config_t config;
    esp_mqtt_client_handle_t mqtt_client;
    esp_timer_handle_t reconnect_timer;
    esp_event_handler_instance_t wifi_handler_instance;
    esp_event_handler_instance_t ip_handler_instance;
    bool wifi_connected;
    bool mqtt_connected;
    bool reconnect_timer_active;
    bool handlers_registered;
    bool is_started;
    uint32_t current_backoff_ms;
    int retry_count;
} esp_wifi_mqtt_ctx_t;

static esp_wifi_mqtt_ctx_t s_esp_ctx;
static nexus_transport_t *s_active_transport = NULL;

static void reconnect_timer_cb(void *arg)
{
    (void)arg;
    bool attempt_connect = false;
    uint32_t backoff = 0;
    int retries = 0;

    WIFI_MQTT_LOCK();
    s_esp_ctx.reconnect_timer_active = false;
    if (s_esp_ctx.is_started && !s_esp_ctx.wifi_connected && s_esp_ctx.config.ssid[0] != '\0') {
        attempt_connect = true;
        backoff = s_esp_ctx.current_backoff_ms;
        retries = s_esp_ctx.retry_count;
    }
    WIFI_MQTT_UNLOCK();

    if (attempt_connect) {
        ESP_LOGI(TAG, "Attempting Wi-Fi reconnect (backoff %" PRIu32 " ms, retry %d)...",
                 backoff, retries);
        esp_wifi_connect();
    }
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    (void)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected to broker");
        WIFI_MQTT_LOCK();
        s_esp_ctx.mqtt_connected = true;
        if (s_active_transport) {
            s_active_transport->state = NEXUS_CONN_STATE_CONNECTED;
            s_active_transport->stats.connect_count++;
        }
        s_esp_ctx.current_backoff_ms = s_esp_ctx.config.reconnect_base_ms;
        s_esp_ctx.retry_count = 0;
        WIFI_MQTT_UNLOCK();

        /* Subscribe to command topic: <topic_prefix>/cmd (outside critical section) */
        if (s_esp_ctx.mqtt_client) {
            char cmd_topic[NEXUS_MQTT_TOPIC_MAX_LEN + 8];
            snprintf(cmd_topic, sizeof(cmd_topic), "%s/cmd", s_esp_ctx.config.topic_prefix);
            esp_mqtt_client_subscribe(s_esp_ctx.mqtt_client, cmd_topic, 1);
        }
        break;

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected from broker");
        WIFI_MQTT_LOCK();
        s_esp_ctx.mqtt_connected = false;
        if (s_active_transport) {
            s_active_transport->state = NEXUS_CONN_STATE_DEGRADED;
            s_active_transport->stats.disconnect_count++;
        }
        WIFI_MQTT_UNLOCK();
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error event occurred");
        WIFI_MQTT_LOCK();
        if (s_active_transport) {
            s_active_transport->stats.tx_errors++;
        }
        WIFI_MQTT_UNLOCK();
        break;

    default:
        break;
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Wi-Fi STA started, connecting...");
        bool do_connect = false;
        WIFI_MQTT_LOCK();
        if (s_esp_ctx.is_started) {
            do_connect = true;
            if (s_active_transport) {
                s_active_transport->state = NEXUS_CONN_STATE_CONNECTING;
            }
        }
        WIFI_MQTT_UNLOCK();
        if (do_connect) {
            esp_wifi_connect();
        }
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        uint32_t delay_ms = 0;
        bool schedule_reconnect = false;

        WIFI_MQTT_LOCK();
        s_esp_ctx.wifi_connected = false;
        s_esp_ctx.mqtt_connected = false;
        if (s_active_transport) {
            s_active_transport->state = NEXUS_CONN_STATE_DEGRADED;
            s_active_transport->stats.disconnect_count++;
        }

        if (s_esp_ctx.is_started && s_esp_ctx.config.ssid[0] != '\0' && !s_esp_ctx.reconnect_timer_active) {
            delay_ms = s_esp_ctx.current_backoff_ms;
            s_esp_ctx.current_backoff_ms = nexus_wifi_mqtt_compute_next_backoff(
                s_esp_ctx.current_backoff_ms,
                s_esp_ctx.config.reconnect_max_ms);
            s_esp_ctx.retry_count++;
            s_esp_ctx.reconnect_timer_active = true;
            schedule_reconnect = true;
        }
        WIFI_MQTT_UNLOCK();

        ESP_LOGW(TAG, "Wi-Fi disconnected; scheduling backoff reconnect in %" PRIu32 " ms", delay_ms);
        if (schedule_reconnect && s_esp_ctx.reconnect_timer) {
            esp_timer_start_once(s_esp_ctx.reconnect_timer, (uint64_t)delay_ms * 1000ULL);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Wi-Fi Got IP: " IPSTR, IP2STR(&event->ip_info.ip));

        bool start_mqtt = false;
        WIFI_MQTT_LOCK();
        s_esp_ctx.wifi_connected = true;
        s_esp_ctx.current_backoff_ms = s_esp_ctx.config.reconnect_base_ms;
        s_esp_ctx.retry_count = 0;
        if (s_esp_ctx.is_started && s_esp_ctx.mqtt_client && !s_esp_ctx.mqtt_connected) {
            start_mqtt = true;
        }
        WIFI_MQTT_UNLOCK();

        if (start_mqtt) {
            esp_mqtt_client_start(s_esp_ctx.mqtt_client);
        }
    }
}

static void register_event_handlers(void)
{
    if (!s_esp_ctx.handlers_registered) {
        esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, &s_esp_ctx.wifi_handler_instance);
        esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, &s_esp_ctx.ip_handler_instance);
        s_esp_ctx.handlers_registered = true;
    }
}

static void unregister_event_handlers(void)
{
    if (s_esp_ctx.handlers_registered) {
        if (s_esp_ctx.wifi_handler_instance) {
            esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, s_esp_ctx.wifi_handler_instance);
            s_esp_ctx.wifi_handler_instance = NULL;
        }
        if (s_esp_ctx.ip_handler_instance) {
            esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, s_esp_ctx.ip_handler_instance);
            s_esp_ctx.ip_handler_instance = NULL;
        }
        s_esp_ctx.handlers_registered = false;
    }
}

#else
#include <time.h>
static inline int64_t esp_timer_get_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((int64_t)ts.tv_sec * 1000000LL) + ((int64_t)ts.tv_nsec / 1000LL);
}

#define MOCK_MQTT_BUF_SIZE 2048
typedef struct {
    uint8_t buffer[MOCK_MQTT_BUF_SIZE];
    size_t length;
    bool force_failure;
    bool connected;
    nexus_wifi_mqtt_config_t config;
} mock_wifi_mqtt_ctx_t;

static mock_wifi_mqtt_ctx_t s_mock_wifi_mqtt;
#define WIFI_MQTT_LOCK()    ((void)0)
#define WIFI_MQTT_UNLOCK()  ((void)0)
#endif

static bool wifi_mqtt_init(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }
    t->state = NEXUS_CONN_STATE_DISCONNECTED;

#ifdef ESP_PLATFORM
    WIFI_MQTT_LOCK();
    s_active_transport = t;
    t->driver_ctx = &s_esp_ctx;
    WIFI_MQTT_UNLOCK();

    /* If SSID is not configured, remain cleanly in DISCONNECTED state */
    if (s_esp_ctx.config.ssid[0] == '\0') {
        ESP_LOGI(TAG, "Wi-Fi SSID not configured; Wi-Fi/MQTT remaining idle");
        t->state = NEXUS_CONN_STATE_DISCONNECTED;
        return true;
    }

    /* Initialize NVS, Netif, Event loop */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, s_esp_ctx.config.ssid, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, s_esp_ctx.config.password, sizeof(wifi_config.sta.password) - 1);

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wifi_config);

    /* Configure MQTT client */
    esp_mqtt_client_config_t mqtt_cfg = {0};
    mqtt_cfg.broker.address.uri = (s_esp_ctx.config.broker_uri[0] != '\0') ?
                                  s_esp_ctx.config.broker_uri : "mqtt://localhost:1883";
    mqtt_cfg.credentials.client_id = (s_esp_ctx.config.client_id[0] != '\0') ?
                                     s_esp_ctx.config.client_id : "nexus_esp32";

    s_esp_ctx.mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_esp_ctx.mqtt_client) {
        esp_mqtt_client_register_event(s_esp_ctx.mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    }

    /* Create one-shot backoff reconnect timer */
    esp_timer_create_args_t timer_args = {
        .callback = &reconnect_timer_cb,
        .name = "nexus_wifi_reconn"
    };
    esp_timer_create(&timer_args, &s_esp_ctx.reconnect_timer);
#else
    s_mock_wifi_mqtt.length = 0;
    s_mock_wifi_mqtt.force_failure = false;
    s_mock_wifi_mqtt.connected = false;
    t->driver_ctx = &s_mock_wifi_mqtt;
#endif

    return true;
}

static bool wifi_mqtt_start(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }

#ifdef ESP_PLATFORM
    if (s_esp_ctx.config.ssid[0] != '\0') {
        register_event_handlers();

        WIFI_MQTT_LOCK();
        s_active_transport = t;
        s_esp_ctx.is_started = true;
        t->state = NEXUS_CONN_STATE_CONNECTING;
        WIFI_MQTT_UNLOCK();

        esp_wifi_start();
        return true;
    }
    WIFI_MQTT_LOCK();
    s_active_transport = t;
    s_esp_ctx.is_started = false;
    t->state = NEXUS_CONN_STATE_DISCONNECTED;
    WIFI_MQTT_UNLOCK();
    return true;
#else
    mock_wifi_mqtt_ctx_t *mock = (mock_wifi_mqtt_ctx_t *)t->driver_ctx;
    if (mock) {
        t->state = mock->connected ? NEXUS_CONN_STATE_CONNECTED : NEXUS_CONN_STATE_CONNECTING;
        t->stats.connect_count++;
    }
    return true;
#endif
}

static bool wifi_mqtt_stop(nexus_transport_t *t)
{
    if (!t) {
        return false;
    }

#ifdef ESP_PLATFORM
    /* 1. Stop reconnect timer first */
    if (s_esp_ctx.reconnect_timer) {
        esp_timer_stop(s_esp_ctx.reconnect_timer);
    }

    /* 2. Transition state and disconnect under lock */
    bool was_mqtt_connected = false;
    WIFI_MQTT_LOCK();
    s_esp_ctx.is_started = false;
    s_esp_ctx.reconnect_timer_active = false;
    was_mqtt_connected = s_esp_ctx.mqtt_connected;
    s_esp_ctx.wifi_connected = false;
    s_esp_ctx.mqtt_connected = false;
    t->state = NEXUS_CONN_STATE_DISCONNECTED;
    t->stats.disconnect_count++;
    s_active_transport = NULL;
    WIFI_MQTT_UNLOCK();

    /* 3. Stop MQTT client and Wi-Fi */
    if (s_esp_ctx.mqtt_client && was_mqtt_connected) {
        esp_mqtt_client_stop(s_esp_ctx.mqtt_client);
    }
    esp_wifi_stop();

    /* 4. Unregister event handlers so no stale callbacks touch deallocated/stopped transport */
    unregister_event_handlers();
#else
    t->state = NEXUS_CONN_STATE_DISCONNECTED;
    t->stats.disconnect_count++;
#endif

    return true;
}

static bool wifi_mqtt_send(nexus_transport_t *t, const uint8_t *data, size_t len, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (!t || !data || len == 0) {
        if (t) {
            WIFI_MQTT_LOCK();
            t->stats.tx_errors++;
            WIFI_MQTT_UNLOCK();
        }
        return false;
    }

    WIFI_MQTT_LOCK();
    bool is_conn = (t->state == NEXUS_CONN_STATE_CONNECTED);
    WIFI_MQTT_UNLOCK();

    if (!is_conn) {
        WIFI_MQTT_LOCK();
        t->stats.tx_errors++;
        WIFI_MQTT_UNLOCK();
        return false;
    }

#ifdef ESP_PLATFORM
    if (!s_esp_ctx.mqtt_client) {
        WIFI_MQTT_LOCK();
        t->stats.tx_errors++;
        WIFI_MQTT_UNLOCK();
        return false;
    }

    char topic[NEXUS_MQTT_TOPIC_MAX_LEN + 16];
    snprintf(topic, sizeof(topic), "%s/telemetry", s_esp_ctx.config.topic_prefix);

    /* Enqueue to MQTT client outbound queue (bounded, non-blocking) */
    int msg_id = esp_mqtt_client_enqueue(s_esp_ctx.mqtt_client, topic, (const char *)data, (int)len, 1, 0, true);
    if (msg_id < 0) {
        WIFI_MQTT_LOCK();
        t->stats.tx_errors++;
        WIFI_MQTT_UNLOCK();
        return false;
    }
#else
    mock_wifi_mqtt_ctx_t *mock = (mock_wifi_mqtt_ctx_t *)t->driver_ctx;
    if (!mock || mock->force_failure || !mock->connected) {
        WIFI_MQTT_LOCK();
        t->stats.tx_errors++;
        WIFI_MQTT_UNLOCK();
        return false;
    }
    if (mock->length + len <= MOCK_MQTT_BUF_SIZE) {
        memcpy(mock->buffer + mock->length, data, len);
        mock->length += len;
    } else {
        WIFI_MQTT_LOCK();
        t->stats.tx_errors++;
        WIFI_MQTT_UNLOCK();
        return false;
    }
#endif

    WIFI_MQTT_LOCK();
    t->stats.tx_packets++;
    t->stats.tx_bytes += (uint32_t)len;
    t->stats.last_tx_time_us = esp_timer_get_time();
    WIFI_MQTT_UNLOCK();
    return true;
}

static bool wifi_mqtt_is_connected(const nexus_transport_t *t)
{
    if (!t) {
        return false;
    }
    WIFI_MQTT_LOCK();
    bool conn = (t->state == NEXUS_CONN_STATE_CONNECTED);
    WIFI_MQTT_UNLOCK();
    return conn;
}

static nexus_conn_state_t wifi_mqtt_get_state(const nexus_transport_t *t)
{
    if (!t) {
        return NEXUS_CONN_STATE_FAILED;
    }
    WIFI_MQTT_LOCK();
    nexus_conn_state_t st = t->state;
    WIFI_MQTT_UNLOCK();
    return st;
}

static void wifi_mqtt_get_stats(const nexus_transport_t *t, nexus_transport_stats_t *out_stats)
{
    if (t && out_stats) {
        WIFI_MQTT_LOCK();
        memcpy(out_stats, &t->stats, sizeof(nexus_transport_stats_t));
        WIFI_MQTT_UNLOCK();
    }
}

static const nexus_transport_ops_t s_wifi_mqtt_ops = {
    .init         = wifi_mqtt_init,
    .start        = wifi_mqtt_start,
    .stop         = wifi_mqtt_stop,
    .send         = wifi_mqtt_send,
    .is_connected = wifi_mqtt_is_connected,
    .get_state    = wifi_mqtt_get_state,
    .get_stats    = wifi_mqtt_get_stats
};

bool nexus_wifi_mqtt_transport_init(nexus_transport_t *transport, const nexus_wifi_mqtt_config_t *config)
{
    if (!transport) {
        return false;
    }

    memset(transport, 0, sizeof(*transport));
    transport->type = NEXUS_TRANSPORT_TYPE_MQTT;
    transport->name = "mqtt";
    transport->ops = &s_wifi_mqtt_ops;
    transport->state = NEXUS_CONN_STATE_DISCONNECTED;

#ifdef ESP_PLATFORM
    WIFI_MQTT_LOCK();
    memset(&s_esp_ctx, 0, sizeof(s_esp_ctx));
    if (config) {
        memcpy(&s_esp_ctx.config, config, sizeof(nexus_wifi_mqtt_config_t));
    }
    if (s_esp_ctx.config.reconnect_base_ms == 0) {
        s_esp_ctx.config.reconnect_base_ms = 1000U;
    }
    if (s_esp_ctx.config.reconnect_max_ms == 0) {
        s_esp_ctx.config.reconnect_max_ms = 60000U;
    }
    if (s_esp_ctx.config.topic_prefix[0] == '\0') {
        strncpy(s_esp_ctx.config.topic_prefix, "nexus/nexus_esp32", sizeof(s_esp_ctx.config.topic_prefix) - 1);
    }
    s_esp_ctx.current_backoff_ms = s_esp_ctx.config.reconnect_base_ms;
    WIFI_MQTT_UNLOCK();
#else
    memset(&s_mock_wifi_mqtt, 0, sizeof(s_mock_wifi_mqtt));
    if (config) {
        memcpy(&s_mock_wifi_mqtt.config, config, sizeof(nexus_wifi_mqtt_config_t));
    }
#endif

    return transport->ops->init(transport);
}

#ifndef ESP_PLATFORM
void nexus_wifi_mqtt_mock_set_connected(nexus_transport_t *transport, bool connected)
{
    if (!transport) {
        return;
    }
    s_mock_wifi_mqtt.connected = connected;
    transport->state = connected ? NEXUS_CONN_STATE_CONNECTED : NEXUS_CONN_STATE_DISCONNECTED;
}

void nexus_wifi_mqtt_mock_set_fail(nexus_transport_t *transport, bool fail)
{
    (void)transport;
    s_mock_wifi_mqtt.force_failure = fail;
}

size_t nexus_wifi_mqtt_mock_get_tx(nexus_transport_t *transport, uint8_t *out_buf, size_t max_len)
{
    (void)transport;
    if (!out_buf || max_len == 0) {
        return s_mock_wifi_mqtt.length;
    }
    size_t to_copy = (s_mock_wifi_mqtt.length < max_len) ? s_mock_wifi_mqtt.length : max_len;
    memcpy(out_buf, s_mock_wifi_mqtt.buffer, to_copy);
    return to_copy;
}
#endif
