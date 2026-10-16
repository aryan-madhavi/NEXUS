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

#define EXECUTIVE_TICK_PERIOD_MS 100U
#define EXECUTIVE_TASK_STACK_WORDS 4096U
#define EXECUTIVE_TASK_PRIORITY 3U

#define HEARTBEAT_JOB_PERIOD_MS 1000U
#define METRICS_JOB_PERIOD_MS 5000U

static const char *TAG = "nexus_main";

/* Global static executive instance (bounded memory, zero heap allocation for structures) */
static nexus_executive_t s_executive;

/* Global static sensor registry instance */
static nexus_sensor_registry_t s_sensor_registry;

/* Application periodic heartbeat job (Priority Class 0) */
static bool job_heartbeat(void *user_ctx)
{
    (void)user_ctx;
    const int64_t uptime_us = esp_timer_get_time();
    ESP_LOGI(TAG, "heartbeat uptime_ms=%" PRId64 " free_heap=%" PRIu32,
             uptime_us / 1000LL, (uint32_t)esp_get_free_heap_size());
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
                  " ready_hwm=%" PRIu16 " ev_hwm=%" PRIu16,
             exec->stats.ticks,
             exec->stats.jobs_dispatched,
             exec->stats.jobs_completed,
             exec->stats.jobs_failed,
             exec->stats.deadline_misses,
             exec->stats.queue_overflows,
             exec->ready_queue.high_water_mark,
             exec->event_queue.high_water_mark);

    for (uint16_t i = 0; i < s_sensor_registry.count; i++) {
        nexus_sensor_descriptor_t *s = nexus_sensor_get_by_index(&s_sensor_registry, i);
        if (s) {
            ESP_LOGI(TAG, "sensor[%s]: raw=%" PRId32 " proc=%" PRId32 " flags=0x%02X samples=%" PRIu32 " errs=%" PRIu32,
                     s->name, s->latest_raw, s->latest_processed, s->sample_flags, s->sample_count, s->error_count);
        }
    }
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
    ESP_LOGI(TAG, "NEXUS Milestone 3 Executive & Sensors initializing");
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

    /* 4. Spawn FreeRTOS task hosting executive tick */
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
