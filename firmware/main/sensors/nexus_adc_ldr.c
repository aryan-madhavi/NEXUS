#include "nexus_adc_ldr.h"
#include "nexus_adc.h"

#ifdef ESP_PLATFORM
#include "esp_log.h"
#include "esp_timer.h"
static const char *TAG = "nexus_ldr";
#endif

typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} nexus_ldr_ctx_t;

static nexus_ldr_ctx_t s_ldr_ctx = { 0 };

bool nexus_ldr_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

    if (!nexus_adc_init()) {
        return false;
    }

    s_ldr_ctx.registry = registry;

    bool registered = nexus_sensor_register(registry,
                                            NEXUS_SENSOR_ID_LDR,
                                            "ldr",
                                            NEXUS_SENSOR_TYPE_LDR,
                                            NEXUS_GPIO_LDR_ADC1,
                                            NEXUS_LDR_INTERVAL_MS);
#ifdef ESP_PLATFORM
    if (registered) {
        ESP_LOGI(TAG, "LDR registered on GPIO35 (ADC1_CH7)");
    }
#endif
    return registered;
}

bool nexus_ldr_acquire(nexus_sensor_registry_t *registry,
                       nexus_executive_t *executive,
                       int64_t timestamp_us)
{
    if (!registry) {
        return false;
    }

    int raw_val = 0;
    if (!nexus_adc_read_raw(NEXUS_ADC_CHANNEL_LDR, &raw_val)) {
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_LDR, false);
        return false;
    }

    /* Relative light index: 0..100% scaled from 12-bit ADC (0..4095) */
    int32_t relative_light_pct = (int32_t)((raw_val * 100) / 4095);

    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_LDR,
                               raw_val,
                               relative_light_pct,
                               NEXUS_SAMPLE_FLAG_VALID,
                               timestamp_us);

    if (executive) {
        nexus_sensor_sample_t sample = {
            .sensor_id = NEXUS_SENSOR_ID_LDR,
            .flags = NEXUS_SAMPLE_FLAG_VALID,
            .channel = NEXUS_GPIO_LDR_ADC1,
            .timestamp_us = timestamp_us,
            .raw_value = raw_val,
            .processed_value = relative_light_pct,
        };
        nexus_executive_record_sample(executive, &sample);
    }

    return true;
}

bool nexus_ldr_job_fn(void *user_ctx)
{
    nexus_ldr_ctx_t *ctx = (nexus_ldr_ctx_t *)user_ctx;
    if (!ctx) {
        ctx = &s_ldr_ctx;
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

    return nexus_ldr_acquire(ctx->registry, ctx->executive, now_us);
}
