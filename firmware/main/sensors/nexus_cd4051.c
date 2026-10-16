#include "nexus_cd4051.h"
#include "nexus_adc.h"

#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
static const char *TAG = "nexus_cd4051";
#endif

typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} nexus_cd4051_ctx_t;

static nexus_cd4051_ctx_t s_cd4051_ctx = { 0 };
static bool s_cd4051_initialized = false;

#ifndef ESP_PLATFORM
static uint8_t s_mock_a = 0, s_mock_b = 0, s_mock_c = 0;
void nexus_cd4051_get_mock_select_lines(uint8_t *out_a, uint8_t *out_b, uint8_t *out_c)
{
    if (out_a) *out_a = s_mock_a;
    if (out_b) *out_b = s_mock_b;
    if (out_c) *out_c = s_mock_c;
}
#endif

bool nexus_cd4051_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

    if (!nexus_adc_init()) {
        return false;
    }

#ifdef ESP_PLATFORM
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << NEXUS_GPIO_CD4051_SEL_A) |
                        (1ULL << NEXUS_GPIO_CD4051_SEL_B) |
                        (1ULL << NEXUS_GPIO_CD4051_SEL_C),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure CD4051 select GPIOs: %s", esp_err_to_name(err));
        return false;
    }

    /* Default select channel X0 (000) */
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_A, 0);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_B, 0);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_C, 0);
#else
    s_mock_a = 0;
    s_mock_b = 0;
    s_mock_c = 0;
#endif

    s_cd4051_ctx.registry = registry;
    s_cd4051_initialized = true;

    /* Register verified channel X0 (HW-870 IR/Gas module) */
    return nexus_sensor_register(registry,
                                 NEXUS_SENSOR_ID_MUX_GAS_X0,
                                 "hw870_x0",
                                 NEXUS_SENSOR_TYPE_ANALOG_MUX,
                                 0U, /* Channel X0 */
                                 NEXUS_CD4051_INTERVAL_MS);
}

bool nexus_cd4051_select_channel(uint8_t channel)
{
    if (channel >= NEXUS_CD4051_CHANNEL_COUNT) {
        return false;
    }

    /* Truth table:
     * Bit 0 -> Select A (GPIO 4)
     * Bit 1 -> Select B (GPIO 2)
     * Bit 2 -> Select C (GPIO 5) */
    uint32_t a_val = (channel & 0x01U) ? 1U : 0U;
    uint32_t b_val = (channel & 0x02U) ? 1U : 0U;
    uint32_t c_val = (channel & 0x04U) ? 1U : 0U;

#ifdef ESP_PLATFORM
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_A, a_val);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_B, b_val);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_CD4051_SEL_C, c_val);

    /* Analog settling time delay */
    esp_rom_delay_us(NEXUS_CD4051_SETTLE_US);
#else
    s_mock_a = (uint8_t)a_val;
    s_mock_b = (uint8_t)b_val;
    s_mock_c = (uint8_t)c_val;
#endif

    return true;
}

bool nexus_cd4051_sample_channel(uint8_t channel, int *out_raw)
{
    if (!out_raw || channel >= NEXUS_CD4051_CHANNEL_COUNT) {
        return false;
    }

    if (!nexus_cd4051_select_channel(channel)) {
        return false;
    }

    /* Sample GPIO 36 via ADC1 Channel 0 */
    return nexus_adc_read_raw(NEXUS_ADC_CHANNEL_CD4051, out_raw);
}

bool nexus_cd4051_acquire_x0(nexus_sensor_registry_t *registry,
                             nexus_executive_t *executive,
                             int64_t timestamp_us)
{
    if (!registry) {
        return false;
    }

    int raw_val = 0;
    if (!nexus_cd4051_sample_channel(0U, &raw_val)) {
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_MUX_GAS_X0, false);
        return false;
    }

    /* Per blueprint: publish raw ADC and voltage millivolts;
     * do not claim gas concentration in ppm without physical calibration.
     * 12-bit ADC against nominal ~3300 mV full scale: */
    int32_t voltage_mv = (int32_t)((raw_val * 3300) / 4095);

    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_MUX_GAS_X0,
                               raw_val,
                               voltage_mv,
                               NEXUS_SAMPLE_FLAG_VALID,
                               timestamp_us);

    if (executive) {
        nexus_sensor_sample_t sample = {
            .sensor_id = NEXUS_SENSOR_ID_MUX_GAS_X0,
            .flags = NEXUS_SAMPLE_FLAG_VALID,
            .channel = 0U, /* Mux Channel X0 */
            .timestamp_us = timestamp_us,
            .raw_value = raw_val,
            .processed_value = voltage_mv,
        };
        nexus_executive_record_sample(executive, &sample);
    }

    return true;
}

bool nexus_cd4051_job_fn(void *user_ctx)
{
    nexus_cd4051_ctx_t *ctx = (nexus_cd4051_ctx_t *)user_ctx;
    if (!ctx) {
        ctx = &s_cd4051_ctx;
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

    return nexus_cd4051_acquire_x0(ctx->registry, ctx->executive, now_us);
}
