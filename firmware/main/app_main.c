#include <inttypes.h>
#include <stdio.h>

#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "nexus_executive.h"
#include "nexus_sensors.h"
#include "nexus_connection_manager.h"

#define EXECUTIVE_TICK_PERIOD_MS 100U
#define EXECUTIVE_TASK_STACK_WORDS 4096U
#define EXECUTIVE_TASK_PRIORITY 3U

#define HEARTBEAT_JOB_PERIOD_MS 1000U
#define METRICS_JOB_PERIOD_MS 5000U
#define CONN_TELEMETRY_JOB_PERIOD_MS 2000U

/* Kconfig defaults / fallbacks */
#ifndef CONFIG_NEXUS_WIFI_SSID
#define CONFIG_NEXUS_WIFI_SSID ""
#endif

#ifndef CONFIG_NEXUS_WIFI_PASSWORD
#define CONFIG_NEXUS_WIFI_PASSWORD ""
#endif

#ifndef CONFIG_NEXUS_MQTT_BROKER_URI
#define CONFIG_NEXUS_MQTT_BROKER_URI "mqtt://localhost:1883"
#endif

#ifndef CONFIG_NEXUS_MQTT_CLIENT_ID
#define CONFIG_NEXUS_MQTT_CLIENT_ID "nexus_esp32"
#endif

#ifndef CONFIG_NEXUS_MQTT_TOPIC_PREFIX
#define CONFIG_NEXUS_MQTT_TOPIC_PREFIX "nexus/nexus_esp32"
#endif

#ifndef CONFIG_NEXUS_RECONNECT_BASE_MS
#define CONFIG_NEXUS_RECONNECT_BASE_MS 1000U
#endif

#ifndef CONFIG_NEXUS_RECONNECT_MAX_MS
#define CONFIG_NEXUS_RECONNECT_MAX_MS 60000U
#endif

static const char *TAG = "nexus_main";

/* Global static executive instance (bounded memory, zero heap allocation for structures) */
static nexus_executive_t s_executive;

/* Global static sensor registry instance */
static nexus_sensor_registry_t s_sensor_registry;

/* Global static unified connection manager instance */
static nexus_conn_mgr_t s_conn_mgr;

/* Application periodic heartbeat job (Priority Class 0) */
static bool job_heartbeat(void *user_ctx)
{
    (void)user_ctx;
    const int64_t uptime_us = esp_timer_get_time();
    ESP_LOGI(TAG, "heartbeat uptime_ms=%" PRId64 " free_heap=%" PRIu32,
             uptime_us / 1000LL, (uint32_t)esp_get_free_heap_size());
    nexus_conn_mgr_send_heartbeat(&s_conn_mgr,
                                  uptime_us / 1000LL,
                                  (uint32_t)esp_get_free_heap_size(),
                                  s_executive.stats.ticks,
                                  NEXUS_ROUTE_AUTO);
    return true;
}

/* Application periodic executive health and statistics reporting job (Priority Class 2) */
static bool job_executive_metrics(void *user_ctx)
{
    nexus_executive_t *exec = (nexus_executive_t *)user_ctx;
    if (!exec) {
        return false;
    }

    ESP_LOGI(TAG, "exec_stats: ticks=%" PRIu32 " dispatched=%" PRIu32 " completed=%" PRIu32
                  " failed=%" PRIu32 " dline_misses=%" PRIu32 " q_overflows=%" PRIu32
                  " ready_hwm=%" PRIu16 " ev_hwm=%" PRIu16
                  " max_lat_us=%" PRIu32 " max_dur_us=%" PRIu32,
             exec->stats.ticks,
             exec->stats.jobs_dispatched,
             exec->stats.jobs_completed,
             exec->stats.jobs_failed,
             exec->stats.deadline_misses,
             exec->stats.queue_overflows,
             exec->ready_queue.high_water_mark,
             exec->event_queue.high_water_mark,
             exec->stats.max_dispatch_latency_us,
             exec->stats.max_job_duration_us);

    /* Note: Sensor telemetry is continuously streamed via job_connection_telemetry (telem envelopes).
     * To prevent 115200-baud UART FIFO saturation and respect the 50 ms executive deadline budget,
     * unconditional per-sensor verbose lines are omitted from this callback. Only actively degraded
     * sensors with errors are logged. */
    for (uint16_t i = 0; i < s_sensor_registry.count; i++) {
        nexus_sensor_descriptor_t *s = nexus_sensor_get_by_index(&s_sensor_registry, i);
        if (s && s->error_count > 0 && !(s->sample_flags & NEXUS_SAMPLE_FLAG_VALID)) {
            ESP_LOGW(TAG, "sensor[%s]: errs=%" PRIu32 " flags=0x%02X",
                     s->name, s->error_count, s->sample_flags);
        }
    }

    nexus_conn_mgr_stats_t cstats;
    nexus_conn_mgr_get_stats(&s_conn_mgr, &cstats);
    ESP_LOGI(TAG, "conn_stats: state=%s tx_enq=%" PRIu32 " tx_disp=%" PRIu32 " tx_drop=%" PRIu32 " tx_fail=%" PRIu32
                  " q_depth=%" PRIu16 " q_hwm=%" PRIu16 " rx_dup=%" PRIu32,
             nexus_conn_state_str(cstats.overall_state),
             cstats.tx_enqueued,
             cstats.tx_dispatched,
             cstats.tx_dropped,
             cstats.tx_failed,
             cstats.tx_queue_depth,
             cstats.tx_queue_hwm,
             cstats.rx_duplicates);

    nexus_conn_mgr_send_status(&s_conn_mgr,
                               esp_timer_get_time() / 1000LL,
                               exec->stats.jobs_dispatched,
                               exec->stats.jobs_completed,
                               exec->stats.jobs_failed,
                               exec->stats.max_dispatch_latency_us,
                               exec->stats.max_job_duration_us,
                               NEXUS_ROUTE_AUTO);
    return true;
}

/* Application periodic connection telemetry job (Priority Class 2) */
static bool job_connection_telemetry(void *user_ctx)
{
    (void)user_ctx;
    const int64_t uptime_us = esp_timer_get_time();
    int32_t ldr_raw = 0;
    int32_t mux_x0_raw = 0;
    int32_t dht_temp = 0;
    int32_t dht_hum = 0;

    nexus_sensor_descriptor_t *s_ldr = nexus_sensor_get(&s_sensor_registry, NEXUS_SENSOR_ID_LDR);
    if (s_ldr) {
        ldr_raw = s_ldr->latest_raw;
    }
    nexus_sensor_descriptor_t *s_mux = nexus_sensor_get(&s_sensor_registry, NEXUS_SENSOR_ID_MUX_GAS_X0);
    if (s_mux) {
        mux_x0_raw = s_mux->latest_raw;
    }
    nexus_sensor_descriptor_t *s_temp = nexus_sensor_get(&s_sensor_registry, NEXUS_SENSOR_ID_DHT11_TEMP);
    if (s_temp) {
        dht_temp = s_temp->latest_processed;
    }
    nexus_sensor_descriptor_t *s_hum = nexus_sensor_get(&s_sensor_registry, NEXUS_SENSOR_ID_DHT11_HUM);
    if (s_hum) {
        dht_hum = s_hum->latest_processed;
    }

    nexus_conn_mgr_send_telemetry(&s_conn_mgr,
                                  uptime_us / 1000LL,
                                  ldr_raw,
                                  mux_x0_raw,
                                  dht_temp,
                                  dht_hum,
                                  NEXUS_ROUTE_AUTO);
    return true;
}

static void executive_task(void *arg)
{
    nexus_executive_t *exec = (nexus_executive_t *)arg;
    const esp_app_desc_t *app = esp_app_get_description();

    ESP_LOGI(TAG, "project=%s version=%s build=%s %s",
             app->project_name, app->version, app->date, app->time);
    ESP_LOGI(TAG, "target=classic_esp32 framework=esp-idf executive=active");

    /* Register baseline application jobs with executive */
    uint16_t hb_id = nexus_executive_register_job(exec,
                                                 "heartbeat",
                                                 NEXUS_PRIORITY_CLASS_0,
                                                 job_heartbeat,
                                                 NULL,
                                                 HEARTBEAT_JOB_PERIOD_MS,
                                                 20U);
    if (hb_id == 0) {
        ESP_LOGE(TAG, "Failed to register heartbeat job");
    }

    uint16_t metrics_id = nexus_executive_register_job(exec,
                                                       "metrics",
                                                       NEXUS_PRIORITY_CLASS_2,
                                                       job_executive_metrics,
                                                       exec,
                                                       METRICS_JOB_PERIOD_MS,
                                                       50U);
    if (metrics_id == 0) {
        ESP_LOGE(TAG, "Failed to register metrics job");
    }

    uint16_t conn_telem_id = nexus_executive_register_job(exec,
                                                          "conn_telem",
                                                          NEXUS_PRIORITY_CLASS_2,
                                                          job_connection_telemetry,
                                                          NULL,
                                                          CONN_TELEMETRY_JOB_PERIOD_MS,
                                                          20U);
    if (conn_telem_id == 0) {
        ESP_LOGE(TAG, "Failed to register connection telemetry job");
    }

    /* Register Priority Class 1 Sensor Acquisition Jobs (LDR, CD4051, DHT11) */
    if (!nexus_sensors_register_jobs(&s_sensor_registry, exec)) {
        ESP_LOGE(TAG, "Failed to register sensor jobs with executive");
    } else {
        ESP_LOGI(TAG, "Registered Priority Class 1 sensor acquisition jobs");
    }

    nexus_executive_emit_event(exec,
                               NEXUS_EVENT_TYPE_SYSTEM_BOOT,
                               NEXUS_SEVERITY_INFO,
                               0,
                               (int32_t)esp_reset_reason());

    /* Executive main dispatch loop */
    TickType_t last_wake_time = xTaskGetTickCount();
    for (;;) {
        const int64_t now_us = esp_timer_get_time();
        nexus_executive_tick(exec, now_us);
        vTaskDelayUntil(&last_wake_time, pdMS_TO_TICKS(EXECUTIVE_TICK_PERIOD_MS));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "NEXUS Milestone 4 Executive, Sensors & Unified Connection Manager initializing");
    ESP_LOGI(TAG, "reset_reason=%d", (int)esp_reset_reason());

    /* 1. Run deterministic executive and data-structure self-tests */
    bool selftest_passed = nexus_executive_run_selftest();
    if (!selftest_passed) {
        ESP_LOGE(TAG, "CRITICAL: Executive self-test failed! Halting.");
        return;
    }
    ESP_LOGI(TAG, "Executive and bounded data structures self-test PASSED");

    /* 2. Initialize runtime executive instance */
    nexus_executive_init(&s_executive, EXECUTIVE_TICK_PERIOD_MS);

    /* 3. Initialize sensor registry and hardware drivers */
    if (!nexus_sensors_init(&s_sensor_registry)) {
        ESP_LOGW(TAG, "Sensor initialization completed with warnings/partial drivers");
    } else {
        ESP_LOGI(TAG, "All sensor drivers and registry initialized successfully");
    }

    /* 4. Initialize and start Unified Connection Manager */
    nexus_conn_mgr_config_t conn_cfg = {
        .default_route = NEXUS_ROUTE_AUTO,
        .serial_cfg = {
            .baud_rate = 115200,
            .uart_port = 0
        },
        .wifi_mqtt_cfg = {
            .ssid = CONFIG_NEXUS_WIFI_SSID,
            .password = CONFIG_NEXUS_WIFI_PASSWORD,
            .broker_uri = CONFIG_NEXUS_MQTT_BROKER_URI,
            .client_id = CONFIG_NEXUS_MQTT_CLIENT_ID,
            .topic_prefix = CONFIG_NEXUS_MQTT_TOPIC_PREFIX,
            .reconnect_base_ms = CONFIG_NEXUS_RECONNECT_BASE_MS,
            .reconnect_max_ms = CONFIG_NEXUS_RECONNECT_MAX_MS
        }
    };
    if (!nexus_conn_mgr_init(&s_conn_mgr, &conn_cfg)) {
        ESP_LOGE(TAG, "Failed to initialize Unified Connection Manager");
    } else {
        ESP_LOGI(TAG, "Unified Connection Manager initialized successfully");
        if (!nexus_conn_mgr_start(&s_conn_mgr)) {
            ESP_LOGW(TAG, "Connection manager started with degraded or partial transports");
        } else {
            ESP_LOGI(TAG, "Unified Connection Manager started successfully");
        }
    }

    /* 5. Spawn FreeRTOS task hosting executive tick */
    BaseType_t created = xTaskCreate(executive_task,
                                     "nexus_exec",
                                     EXECUTIVE_TASK_STACK_WORDS,
                                     &s_executive,
                                     EXECUTIVE_TASK_PRIORITY,
                                     NULL);
    if (created != pdPASS) {
        ESP_LOGE(TAG, "failed to create executive task; restarting");
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_restart();
    }
}
