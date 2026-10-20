#include "nexus_moc7811.h"

#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
static const char *TAG = "nexus_moc7811";
#endif

typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} nexus_moc7811_ctx_t;

static nexus_moc7811_ctx_t s_moc7811_ctx = { 0 };
static bool s_moc7811_initialized = false;

#ifndef ESP_PLATFORM
static int s_mock_raw = 0;
static bool s_mock_success = true;

void nexus_moc7811_set_mock_state(int raw_val, bool success)
{
    s_mock_raw = raw_val;
    s_mock_success = success;
}
#endif

bool nexus_moc7811_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

#ifdef ESP_PLATFORM
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << NEXUS_GPIO_MOC7811),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure MOC7811 GPIO %u: %s",
                 NEXUS_GPIO_MOC7811, esp_err_to_name(err));
        return false;
    }
#else
    s_mock_raw = 0;
    s_mock_success = true;
#endif

    s_moc7811_ctx.registry = registry;
    s_moc7811_initialized = true;

    return nexus_sensor_register(registry,
                                 NEXUS_SENSOR_ID_MOC7811,
                                 "moc7811",
                                 NEXUS_SENSOR_TYPE_OPTICAL_SLOT,
                                 (uint8_t)NEXUS_GPIO_MOC7811,
                                 NEXUS_MOC7811_INTERVAL_MS);
}

bool nexus_moc7811_read_state(int *out_raw, bool *out_blocked)
{
    if (!out_raw) {
        return false;
    }

#ifdef ESP_PLATFORM
    int level = gpio_get_level((gpio_num_t)NEXUS_GPIO_MOC7811);
    *out_raw = level;
    if (out_blocked) {
        *out_blocked = (level != 0);
    }
    return true;
#else
    if (!s_mock_success) {
        return false;
    }
    *out_raw = s_mock_raw;
    if (out_blocked) {
        *out_blocked = (s_mock_raw != 0);
    }
    return true;
#endif
}

bool nexus_moc7811_acquire(nexus_sensor_registry_t *registry,
                           nexus_executive_t *executive,
                           int64_t timestamp_us)
{
    if (!registry) {
        return false;
    }

    int raw_val = 0;
    bool blocked = false;
    if (!nexus_moc7811_read_state(&raw_val, &blocked)) {
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_MOC7811, false);
        return false;
    }

    int32_t processed = blocked ? 1 : 0;

    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_MOC7811,
                               raw_val,
                               processed,
                               NEXUS_SAMPLE_FLAG_VALID,
                               timestamp_us);

    if (executive) {
        nexus_sensor_sample_t sample = {
            .sensor_id = NEXUS_SENSOR_ID_MOC7811,
            .flags = NEXUS_SAMPLE_FLAG_VALID,
            .channel = (uint8_t)NEXUS_GPIO_MOC7811,
            .timestamp_us = timestamp_us,
            .raw_value = raw_val,
            .processed_value = processed,
        };
        nexus_executive_record_sample(executive, &sample);
    }

    return true;
}

bool nexus_moc7811_job_fn(void *user_ctx)
{
    nexus_moc7811_ctx_t *ctx = (nexus_moc7811_ctx_t *)user_ctx;
    if (!ctx) {
        ctx = &s_moc7811_ctx;
    }
    if (!ctx->registry) {
        return false;
    }

    int64_t now_us = (ctx->executive && ctx->executive->last_tick_us > 0) ?
                     ctx->executive->last_tick_us : 0;
#ifdef ESP_PLATFORM
    if (now_us == 0) {
        now_us = esp_timer_get_time();
    }
#endif

    return nexus_moc7811_acquire(ctx->registry, ctx->executive, now_us);
}
