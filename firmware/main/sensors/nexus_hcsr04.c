#include "nexus_hcsr04.h"

#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
static const char *TAG = "nexus_hcsr04";
#endif

typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} nexus_hcsr04_ctx_t;

static nexus_hcsr04_ctx_t s_hcsr04_ctx = { 0 };
static bool s_hcsr04_initialized = false;
static bool s_live_hw_enabled = false; /* Inhibited by default for 5V echo protection */

#ifndef ESP_PLATFORM
static bool s_mock_success = true;
static uint32_t s_mock_echo_us = 1160U; /* Default ~20 cm */
static int32_t s_mock_dist_cm = 20;
static bool s_mock_direct_mode = false;
static bool s_mock_direct_valid = true;

void nexus_hcsr04_set_mock_pulse(uint32_t echo_us, bool success)
{
    s_mock_echo_us = echo_us;
    s_mock_success = success;
    s_mock_direct_mode = false;
}

void nexus_hcsr04_set_mock_distance(int32_t distance_cm, bool valid)
{
    s_mock_dist_cm = distance_cm;
    s_mock_direct_valid = valid;
    s_mock_direct_mode = true;
}
#endif

void nexus_hcsr04_set_live_enabled(bool enabled)
{
    s_live_hw_enabled = enabled;
#ifdef ESP_PLATFORM
    if (enabled) {
        gpio_config_t trig_conf = {
            .pin_bit_mask = (1ULL << NEXUS_GPIO_HCSR04_TRIG),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        esp_err_t err = gpio_config(&trig_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure TRIG GPIO %u: %s",
                     NEXUS_GPIO_HCSR04_TRIG, esp_err_to_name(err));
        } else {
            gpio_set_level((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG, 0);
        }

        gpio_config_t echo_conf = {
            .pin_bit_mask = (1ULL << NEXUS_GPIO_HCSR04_ECHO),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        err = gpio_config(&echo_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure ECHO GPIO %u: %s",
                     NEXUS_GPIO_HCSR04_ECHO, esp_err_to_name(err));
        }
    } else {
        gpio_reset_pin((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG);
        gpio_reset_pin((gpio_num_t)NEXUS_GPIO_HCSR04_ECHO);
    }
    ESP_LOGW(TAG, "HC-SR04 live hardware acquisition %s",
             enabled ? "ENABLED (User verified Echo <= 3.3V)" : "DISABLED (Safety inhibited)");
#endif
}

bool nexus_hcsr04_is_live_enabled(void)
{
    return s_live_hw_enabled;
}

bool nexus_hcsr04_calculate_distance(uint32_t echo_us, int32_t *out_dist_cm)
{
    if (!out_dist_cm) {
        return false;
    }

    /* Sound speed in air: ~343 m/s = 0.0343 cm/us
     * Distance = (echo_us * 0.0343) / 2 = echo_us / 58.3
     * Valid range: 2 cm to 400 cm (approx 116 us to 23320 us) */
    if (echo_us < 116U || echo_us > 23320U) {
        *out_dist_cm = -1;
        return false;
    }

    *out_dist_cm = (int32_t)(echo_us / 58U);
    return true;
}

bool nexus_hcsr04_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

#ifdef ESP_PLATFORM
    if (s_live_hw_enabled) {
        gpio_config_t trig_conf = {
            .pin_bit_mask = (1ULL << NEXUS_GPIO_HCSR04_TRIG),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        esp_err_t err = gpio_config(&trig_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure TRIG GPIO %u: %s",
                     NEXUS_GPIO_HCSR04_TRIG, esp_err_to_name(err));
            return false;
        }
        gpio_set_level((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG, 0);

        gpio_config_t echo_conf = {
            .pin_bit_mask = (1ULL << NEXUS_GPIO_HCSR04_ECHO),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        err = gpio_config(&echo_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure ECHO GPIO %u: %s",
                     NEXUS_GPIO_HCSR04_ECHO, esp_err_to_name(err));
            return false;
        }
    } else {
        ESP_LOGI(TAG, "HC-SR04 initialized (safe inhibited mode; GPIOs %u and %u unconfigured pending voltage check).",
                 NEXUS_GPIO_HCSR04_TRIG, NEXUS_GPIO_HCSR04_ECHO);
    }
#endif

    s_hcsr04_ctx.registry = registry;
    s_hcsr04_initialized = true;

    return nexus_sensor_register(registry,
                                 NEXUS_SENSOR_ID_HCSR04,
                                 "hcsr04",
                                 NEXUS_SENSOR_TYPE_ULTRASONIC,
                                 (uint8_t)NEXUS_GPIO_HCSR04_TRIG,
                                 NEXUS_HCSR04_INTERVAL_MS);
}

bool nexus_hcsr04_read(nexus_hcsr04_reading_t *out_reading)
{
    if (!out_reading) {
        return false;
    }

    out_reading->distance_cm = -1;
    out_reading->echo_duration_us = 0;
    out_reading->valid = false;

    if (!s_live_hw_enabled) {
        out_reading->status = NEXUS_HCSR04_STATUS_UNVERIFIED_VOLTAGE;
        return false;
    }

#ifndef ESP_PLATFORM
    /* Host testing mock mode */
    if (s_mock_direct_mode) {
        if (!s_mock_direct_valid) {
            out_reading->status = NEXUS_HCSR04_STATUS_OUT_OF_RANGE;
            return false;
        }
        out_reading->distance_cm = s_mock_dist_cm;
        out_reading->echo_duration_us = (uint32_t)(s_mock_dist_cm * 58);
        out_reading->status = NEXUS_HCSR04_STATUS_OK;
        out_reading->valid = true;
        return true;
    }

    if (!s_mock_success) {
        out_reading->status = NEXUS_HCSR04_STATUS_TIMEOUT;
        return false;
    }

    int32_t dist = 0;
    if (!nexus_hcsr04_calculate_distance(s_mock_echo_us, &dist)) {
        out_reading->status = NEXUS_HCSR04_STATUS_OUT_OF_RANGE;
        return false;
    }

    out_reading->distance_cm = dist;
    out_reading->echo_duration_us = s_mock_echo_us;
    out_reading->status = NEXUS_HCSR04_STATUS_OK;
    out_reading->valid = true;
    return true;
#else
    /* Target platform physical hardware mode (s_live_hw_enabled already verified at entry) */

    /* 1. Send 10 us trigger pulse */
    gpio_set_level((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG, 0);
    esp_rom_delay_us(4);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG, 1);
    esp_rom_delay_us(10);
    gpio_set_level((gpio_num_t)NEXUS_GPIO_HCSR04_TRIG, 0);

    /* 2. Wait for Echo to rise (bounded timeout: 2000 us) */
    int64_t wait_start = esp_timer_get_time();
    while (gpio_get_level((gpio_num_t)NEXUS_GPIO_HCSR04_ECHO) == 0) {
        if ((esp_timer_get_time() - wait_start) > 2000LL) {
            out_reading->status = NEXUS_HCSR04_STATUS_TIMEOUT;
            return false;
        }
    }

    /* 3. Measure Echo high duration (bounded timeout: 25000 us ~ 4.3 meters) */
    int64_t echo_start = esp_timer_get_time();
    while (gpio_get_level((gpio_num_t)NEXUS_GPIO_HCSR04_ECHO) == 1) {
        if ((esp_timer_get_time() - echo_start) > (int64_t)NEXUS_HCSR04_DEFAULT_TIMEOUT_US) {
            out_reading->status = NEXUS_HCSR04_STATUS_TIMEOUT;
            return false;
        }
    }
    int64_t echo_end = esp_timer_get_time();
    uint32_t echo_duration = (uint32_t)(echo_end - echo_start);

    /* 4. Calculate distance */
    int32_t dist = 0;
    if (!nexus_hcsr04_calculate_distance(echo_duration, &dist)) {
        out_reading->status = NEXUS_HCSR04_STATUS_OUT_OF_RANGE;
        return false;
    }

    out_reading->distance_cm = dist;
    out_reading->echo_duration_us = echo_duration;
    out_reading->status = NEXUS_HCSR04_STATUS_OK;
    out_reading->valid = true;
    return true;
#endif
}

bool nexus_hcsr04_acquire(nexus_sensor_registry_t *registry,
                          nexus_executive_t *executive,
                          int64_t timestamp_us)
{
    if (!registry) {
        return false;
    }

    nexus_hcsr04_reading_t reading;
    if (!nexus_hcsr04_read(&reading)) {
        bool is_timeout = (reading.status == NEXUS_HCSR04_STATUS_TIMEOUT);
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_HCSR04, is_timeout);
        return false;
    }

    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_HCSR04,
                               (int32_t)reading.echo_duration_us,
                               reading.distance_cm,
                               NEXUS_SAMPLE_FLAG_VALID,
                               timestamp_us);

    if (executive) {
        nexus_sensor_sample_t sample = {
            .sensor_id = NEXUS_SENSOR_ID_HCSR04,
            .flags = NEXUS_SAMPLE_FLAG_VALID,
            .channel = (uint8_t)NEXUS_GPIO_HCSR04_TRIG,
            .timestamp_us = timestamp_us,
            .raw_value = (int32_t)reading.echo_duration_us,
            .processed_value = reading.distance_cm,
        };
        nexus_executive_record_sample(executive, &sample);
    }

    return true;
}

bool nexus_hcsr04_job_fn(void *user_ctx)
{
    nexus_hcsr04_ctx_t *ctx = (nexus_hcsr04_ctx_t *)user_ctx;
    if (!ctx) {
        ctx = &s_hcsr04_ctx;
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

    return nexus_hcsr04_acquire(ctx->registry, ctx->executive, now_us);
}
