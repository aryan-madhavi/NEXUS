#include <inttypes.h>
#include <stdio.h>

#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define HEARTBEAT_PERIOD_MS 1000U
#define MONITOR_STACK_WORDS 3072U
#define MONITOR_PRIORITY 2U

static const char *TAG = "apollo_boot";

static void heartbeat_task(void *arg)
{
    (void)arg;
    const esp_app_desc_t *app = esp_app_get_description();

    ESP_LOGI(TAG, "project=%s version=%s build=%s %s",
             app->project_name, app->version, app->date, app->time);
    ESP_LOGI(TAG, "target=classic_esp32 framework=esp-idf executive=bootstrap");

    for (;;) {
        const int64_t uptime_us = esp_timer_get_time();
        ESP_LOGI(TAG, "heartbeat uptime_ms=%" PRId64 " free_heap=%" PRIu32,
                 uptime_us / 1000, (uint32_t)esp_get_free_heap_size());
        vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_PERIOD_MS));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "Apollo EDU_ROBO bootstrap starting");
    ESP_LOGI(TAG, "reset_reason=%d", (int)esp_reset_reason());

    BaseType_t created = xTaskCreate(heartbeat_task,
                                     "heartbeat",
                                     MONITOR_STACK_WORDS,
                                     NULL,
                                     MONITOR_PRIORITY,
                                     NULL);
    if (created != pdPASS) {
        ESP_LOGE(TAG, "failed to create heartbeat task; restarting");
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_restart();
    }
}
