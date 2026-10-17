#include "nexus_dht11.h"
#include <stddef.h>

#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "nexus_dht11";
#endif

typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} nexus_dht11_ctx_t;

static nexus_dht11_ctx_t s_dht11_ctx = { 0 };

#ifdef ESP_PLATFORM
typedef struct {
    int16_t temperature_c;
    uint16_t humidity_pct;
    bool valid;
    bool new_sample_ready;
    bool new_error_ready;
    bool is_timeout;
    int64_t timestamp_us;
} nexus_dht11_async_data_t;

static nexus_dht11_async_data_t s_async_data = { 0 };
static TaskHandle_t s_dht11_task_handle = NULL;
static portMUX_TYPE s_dht11_spinlock = portMUX_INITIALIZER_UNLOCKED;

static void dht11_worker_task(void *arg);
#endif

#ifndef ESP_PLATFORM
static uint8_t s_mock_bytes[5] = { 0 };
static bool s_mock_simulate_timeout = false;
static bool s_mock_packet_set = false;

void nexus_dht11_set_mock_packet(const uint8_t *bytes5, bool simulate_timeout)
{
    s_mock_simulate_timeout = simulate_timeout;
    if (bytes5) {
        for (int i = 0; i < 5; i++) {
            s_mock_bytes[i] = bytes5[i];
        }
        s_mock_packet_set = true;
    } else {
        s_mock_packet_set = false;
    }
}
#endif

bool nexus_dht11_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

#ifdef ESP_PLATFORM
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << NEXUS_GPIO_DHT11),
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure GPIO%u: %s", NEXUS_GPIO_DHT11, esp_err_to_name(err));
        return false;
    }
    /* Release bus to idle high */
    gpio_set_level((gpio_num_t)NEXUS_GPIO_DHT11, 1);

    /* Spawn dedicated background acquisition task if not already created.
     * Priority 2 runs below executive task (Priority 3) to prevent starving executive ticks. */
    if (!s_dht11_task_handle) {
        BaseType_t ret = xTaskCreate(dht11_worker_task,
                                     "nexus_dht11",
                                     2048,
                                     NULL,
                                     2,
                                     &s_dht11_task_handle);
        if (ret != pdPASS) {
            ESP_LOGE(TAG, "Failed to create DHT11 worker task");
            return false;
        }
        /* Note: Worker acquisition is triggered cleanly by the executive job callback,
         * ensuring the sensor has >= 1-2s of power-on stabilization before the first read. */
    }
#endif

    s_dht11_ctx.registry = registry;

    bool ok_temp = nexus_sensor_register(registry,
                                         NEXUS_SENSOR_ID_DHT11_TEMP,
                                         "dht11_temp",
                                         NEXUS_SENSOR_TYPE_DHT11_TEMP,
                                         NEXUS_GPIO_DHT11,
                                         NEXUS_DHT11_INTERVAL_MS);

    bool ok_hum = nexus_sensor_register(registry,
                                        NEXUS_SENSOR_ID_DHT11_HUM,
                                        "dht11_hum",
                                        NEXUS_SENSOR_TYPE_DHT11_HUM,
                                        NEXUS_GPIO_DHT11,
                                        NEXUS_DHT11_INTERVAL_MS);

    return (ok_temp && ok_hum);
}

#ifdef ESP_PLATFORM
static inline bool wait_for_level(gpio_num_t pin, int level, uint32_t timeout_us, uint32_t *out_elapsed_us)
{
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(pin) != level) {
        if ((uint32_t)(esp_timer_get_time() - start) > timeout_us) {
            return false;
        }
    }
    if (out_elapsed_us) {
        *out_elapsed_us = (uint32_t)(esp_timer_get_time() - start);
    }
    return true;
}

#define NEXUS_DHT11_BIT_LOW_TIMEOUT_US     80U  /* DHT11 bit start low is ~50us */
#define NEXUS_DHT11_BIT_HIGH_TIMEOUT_US    95U  /* DHT11 '0' is ~28us, '1' is ~70us */

bool nexus_dht11_read_with_status(nexus_dht11_reading_t *out_reading, nexus_dht11_status_t *out_status)
{
    if (!out_reading) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_INVALID_ARG;
        }
        return false;
    }
    out_reading->valid = false;
    if (out_status) {
        *out_status = NEXUS_DHT11_STATUS_OK;
    }

    gpio_num_t pin = (gpio_num_t)NEXUS_GPIO_DHT11;

    /* 1. Host start signal: Pull LOW for at least 18ms (20-30ms).
     * At 100 Hz FreeRTOS tick, pdMS_TO_TICKS(20) is 2 ticks, which can wake up in ~10.1 ms if unaligned.
     * pdMS_TO_TICKS(20) + 1 guarantees >= 20 ms and <= 30 ms sleep, allowing other tasks to run. */
    gpio_set_level(pin, 0);
    vTaskDelay(pdMS_TO_TICKS(20) + 1);

    /* 2. Release line: set open-drain high and wait 30 us for line to float and DHT11 to detect rising edge */
    gpio_set_level(pin, 1);
    esp_rom_delay_us(30);

    /* 3. Handshake response from DHT11 */
    /* Wait for DHT11 response LOW (~80us) */
    if (!wait_for_level(pin, 0, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_TIMEOUT_HANDSHAKE;
        }
        return false;
    }

    /* Wait for DHT11 response HIGH (~80us) */
    if (!wait_for_level(pin, 1, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_TIMEOUT_HANDSHAKE;
        }
        return false;
    }

    /* Wait for DHT11 pull LOW to start bit transmission (~50us) */
    if (!wait_for_level(pin, 0, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_TIMEOUT_HANDSHAKE;
        }
        return false;
    }

    /* 4. Read 40 data bits */
    uint8_t data[5] = { 0 };
    for (int bit = 0; bit < 40; bit++) {
        /* Line is currently LOW (50us low phase starting this bit).
         * Atomically measure rising edge and falling edge within a single bounded critical section.
         * This completely eliminates preemption between detecting the rising edge and starting pulse timing,
         * which would otherwise shorten the measured HIGH duration and corrupt '1' bits into '0' bits.
         * Bounded to NEXUS_DHT11_BIT_LOW_TIMEOUT_US (80us) + NEXUS_DHT11_BIT_HIGH_TIMEOUT_US (95us). */
        portENTER_CRITICAL(&s_dht11_spinlock);

        /* Wait for rising edge: line goes LOW -> HIGH (~50us) */
        int64_t t_low_start = esp_timer_get_time();
        while (gpio_get_level(pin) == 0) {
            if ((uint32_t)(esp_timer_get_time() - t_low_start) > NEXUS_DHT11_BIT_LOW_TIMEOUT_US) {
                portEXIT_CRITICAL(&s_dht11_spinlock);
                if (out_status) {
                    *out_status = NEXUS_DHT11_STATUS_TIMEOUT_DATA;
                }
                return false;
            }
        }
        int64_t t_rise = esp_timer_get_time();

        /* Wait for falling edge: line goes HIGH -> LOW (26-28us for '0', ~70us for '1') */
        while (gpio_get_level(pin) == 1) {
            if ((uint32_t)(esp_timer_get_time() - t_rise) > NEXUS_DHT11_BIT_HIGH_TIMEOUT_US) {
                portEXIT_CRITICAL(&s_dht11_spinlock);
                if (out_status) {
                    *out_status = NEXUS_DHT11_STATUS_TIMEOUT_DATA;
                }
                return false;
            }
        }
        int64_t t_fall = esp_timer_get_time();
        portEXIT_CRITICAL(&s_dht11_spinlock);

        uint32_t high_duration_us = (uint32_t)(t_fall - t_rise);

        int byte_idx = bit / 8;
        data[byte_idx] <<= 1;
        /* '1' pulse is ~70us, '0' pulse is ~26-28us. Threshold 45us is halfway between them. */
        if (high_duration_us > 45U) {
            data[byte_idx] |= 1U;
        }
    }

    /* 5. End of transmission: DHT11 pulls low for 50us then releases line */
    wait_for_level(pin, 1, NEXUS_DHT11_TIMEOUT_US, NULL);

    /* 6. Verify checksum */
    uint8_t checksum = (uint8_t)(data[0] + data[1] + data[2] + data[3]);
    if (checksum != data[4]) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_ERROR_CHECKSUM;
        }
        ESP_LOGW(TAG, "DHT11 checksum mismatch: calc=0x%02x recv=0x%02x [data: %u %u %u %u]",
                 checksum, data[4], data[0], data[1], data[2], data[3]);
        return false;
    }

    out_reading->humidity_pct = data[0];
    out_reading->temperature_c = data[2];
    out_reading->valid = true;
    if (out_status) {
        *out_status = NEXUS_DHT11_STATUS_OK;
    }
    return true;
}

bool nexus_dht11_read(nexus_dht11_reading_t *out_reading)
{
    return nexus_dht11_read_with_status(out_reading, NULL);
}

#else
/* Host unit test mock implementation */
bool nexus_dht11_read_with_status(nexus_dht11_reading_t *out_reading, nexus_dht11_status_t *out_status)
{
    if (!out_reading) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_INVALID_ARG;
        }
        return false;
    }
    out_reading->valid = false;
    if (out_status) {
        *out_status = NEXUS_DHT11_STATUS_OK;
    }

    if (s_mock_simulate_timeout || !s_mock_packet_set) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_TIMEOUT_HANDSHAKE;
        }
        return false;
    }

    uint8_t checksum = (uint8_t)(s_mock_bytes[0] + s_mock_bytes[1] + s_mock_bytes[2] + s_mock_bytes[3]);
    if (checksum != s_mock_bytes[4]) {
        if (out_status) {
            *out_status = NEXUS_DHT11_STATUS_ERROR_CHECKSUM;
        }
        return false; /* CRC failure */
    }

    out_reading->humidity_pct = s_mock_bytes[0];
    out_reading->temperature_c = s_mock_bytes[2];
    out_reading->valid = true;
    if (out_status) {
        *out_status = NEXUS_DHT11_STATUS_OK;
    }
    return true;
}

bool nexus_dht11_read(nexus_dht11_reading_t *out_reading)
{
    return nexus_dht11_read_with_status(out_reading, NULL);
}
#endif

bool nexus_dht11_acquire(nexus_sensor_registry_t *registry,
                         nexus_executive_t *executive,
                         int64_t timestamp_us)
{
    (void)executive;
    if (!registry) {
        return false;
    }

    nexus_dht11_reading_t reading;
    nexus_dht11_status_t status = NEXUS_DHT11_STATUS_OK;
    bool success = nexus_dht11_read_with_status(&reading, &status);

    if (!success) {
        bool is_timeout = (status != NEXUS_DHT11_STATUS_ERROR_CHECKSUM);
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_DHT11_TEMP, is_timeout);
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_DHT11_HUM, is_timeout);
        return false;
    }

    /* Update temperature in registry */
    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_DHT11_TEMP,
                               (int32_t)reading.temperature_c,
                               (int32_t)reading.temperature_c,
                               NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                               timestamp_us);

    /* Update humidity in registry */
    nexus_sensor_update_sample(registry,
                               NEXUS_SENSOR_ID_DHT11_HUM,
                               (int32_t)reading.humidity_pct,
                               (int32_t)reading.humidity_pct,
                               NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                               timestamp_us);

    /* Record samples to executive ring buffer */
    if (executive) {
        nexus_sensor_sample_t sample_temp = {
            .sensor_id = NEXUS_SENSOR_ID_DHT11_TEMP,
            .flags = NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
            .channel = NEXUS_GPIO_DHT11,
            .timestamp_us = timestamp_us,
            .raw_value = (int32_t)reading.temperature_c,
            .processed_value = (int32_t)reading.temperature_c,
        };
        nexus_executive_record_sample(executive, &sample_temp);

        nexus_sensor_sample_t sample_hum = {
            .sensor_id = NEXUS_SENSOR_ID_DHT11_HUM,
            .flags = NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
            .channel = NEXUS_GPIO_DHT11,
            .timestamp_us = timestamp_us,
            .raw_value = (int32_t)reading.humidity_pct,
            .processed_value = (int32_t)reading.humidity_pct,
        };
        nexus_executive_record_sample(executive, &sample_hum);
    }

    return true;
}

#ifdef ESP_PLATFORM
static void dht11_worker_task(void *arg)
{
    (void)arg;
    static int64_t s_last_read_start_us = 0;
    static uint32_t s_success_count = 0;
    static uint32_t s_fail_count = 0;
    static int64_t s_last_diag_log_us = 0;

    for (;;) {
        /* Wait for trigger from executive job (or 2500ms safety timeout) */
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2500));

        /* Guard minimum acquisition interval (DHT11 requires >= 1.5-2.0s between reads) */
        int64_t now_us = esp_timer_get_time();
        if (s_last_read_start_us > 0) {
            int64_t elapsed_ms = (now_us - s_last_read_start_us) / 1000;
            if (elapsed_ms < (int64_t)NEXUS_DHT11_INTERVAL_MS) {
                int64_t wait_ms = (int64_t)NEXUS_DHT11_INTERVAL_MS - elapsed_ms;
                vTaskDelay(pdMS_TO_TICKS(wait_ms));
            }
        }
        s_last_read_start_us = esp_timer_get_time();

        nexus_dht11_reading_t reading = { 0 };
        nexus_dht11_status_t status = NEXUS_DHT11_STATUS_OK;
        bool success = nexus_dht11_read_with_status(&reading, &status);
        now_us = esp_timer_get_time();

        /* Concise, rate-limited diagnostics distinguishing failure categories */
        if (success) {
            s_success_count++;
            if (s_success_count == 1 || (now_us - s_last_diag_log_us) >= 30000000LL) {
                ESP_LOGI(TAG, "DHT11 read OK: temp=%d°C, hum=%u%% (total_ok=%lu, total_err=%lu)",
                         reading.temperature_c, reading.humidity_pct,
                         (unsigned long)s_success_count, (unsigned long)s_fail_count);
                s_last_diag_log_us = now_us;
            }
        } else {
            s_fail_count++;
            if (s_fail_count == 1 || (now_us - s_last_diag_log_us) >= 10000000LL) {
                const char *reason = "unknown";
                switch (status) {
                    case NEXUS_DHT11_STATUS_TIMEOUT_HANDSHAKE: reason = "handshake timeout"; break;
                    case NEXUS_DHT11_STATUS_TIMEOUT_DATA:      reason = "data bit timeout"; break;
                    case NEXUS_DHT11_STATUS_ERROR_CHECKSUM:    reason = "checksum mismatch"; break;
                    default: break;
                }
                ESP_LOGW(TAG, "DHT11 read FAIL: %s (status=%d, total_ok=%lu, total_err=%lu)",
                         reason, (int)status, (unsigned long)s_success_count, (unsigned long)s_fail_count);
                s_last_diag_log_us = now_us;
            }
        }

        portENTER_CRITICAL(&s_dht11_spinlock);
        if (success) {
            s_async_data.temperature_c = reading.temperature_c;
            s_async_data.humidity_pct = reading.humidity_pct;
            s_async_data.valid = true;
            s_async_data.new_sample_ready = true;
            s_async_data.new_error_ready = false;
            s_async_data.is_timeout = false;
            s_async_data.timestamp_us = now_us;
        } else {
            s_async_data.valid = false;
            s_async_data.new_sample_ready = false;
            s_async_data.new_error_ready = true;
            s_async_data.is_timeout = (status != NEXUS_DHT11_STATUS_ERROR_CHECKSUM);
            s_async_data.timestamp_us = now_us;
        }
        portEXIT_CRITICAL(&s_dht11_spinlock);

        /* Drain any pending notification queued while worker was executing */
        ulTaskNotifyTake(pdTRUE, 0);
    }
}
#endif

bool nexus_dht11_job_fn(void *user_ctx)
{
    nexus_dht11_ctx_t *ctx = (nexus_dht11_ctx_t *)user_ctx;
    if (!ctx) {
        ctx = &s_dht11_ctx;
    }
    if (!ctx->registry) {
        return false;
    }

#ifdef ESP_PLATFORM
    /* Non-blocking callback: snapshot shared async data from background worker */
    nexus_dht11_async_data_t snapshot;
    portENTER_CRITICAL(&s_dht11_spinlock);
    snapshot = s_async_data;
    s_async_data.new_sample_ready = false;
    s_async_data.new_error_ready = false;
    portEXIT_CRITICAL(&s_dht11_spinlock);

    /* Trigger background worker for next 2-second acquisition cycle */
    if (s_dht11_task_handle) {
        xTaskNotifyGive(s_dht11_task_handle);
    }

    if (snapshot.new_sample_ready) {
        int64_t ts = (snapshot.timestamp_us > 0) ? snapshot.timestamp_us : esp_timer_get_time();

        nexus_sensor_update_sample(ctx->registry,
                                   NEXUS_SENSOR_ID_DHT11_TEMP,
                                   (int32_t)snapshot.temperature_c,
                                   (int32_t)snapshot.temperature_c,
                                   NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                                   ts);

        nexus_sensor_update_sample(ctx->registry,
                                   NEXUS_SENSOR_ID_DHT11_HUM,
                                   (int32_t)snapshot.humidity_pct,
                                   (int32_t)snapshot.humidity_pct,
                                   NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                                   ts);

        if (ctx->executive) {
            nexus_sensor_sample_t sample_temp = {
                .sensor_id = NEXUS_SENSOR_ID_DHT11_TEMP,
                .flags = NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                .channel = NEXUS_GPIO_DHT11,
                .timestamp_us = ts,
                .raw_value = (int32_t)snapshot.temperature_c,
                .processed_value = (int32_t)snapshot.temperature_c,
            };
            nexus_executive_record_sample(ctx->executive, &sample_temp);

            nexus_sensor_sample_t sample_hum = {
                .sensor_id = NEXUS_SENSOR_ID_DHT11_HUM,
                .flags = NEXUS_SAMPLE_FLAG_VALID | NEXUS_SAMPLE_FLAG_CALIBRATED,
                .channel = NEXUS_GPIO_DHT11,
                .timestamp_us = ts,
                .raw_value = (int32_t)snapshot.humidity_pct,
                .processed_value = (int32_t)snapshot.humidity_pct,
            };
            nexus_executive_record_sample(ctx->executive, &sample_hum);
        }
        return true;
    } else if (snapshot.new_error_ready) {
        nexus_sensor_record_error(ctx->registry, NEXUS_SENSOR_ID_DHT11_TEMP, snapshot.is_timeout);
        nexus_sensor_record_error(ctx->registry, NEXUS_SENSOR_ID_DHT11_HUM, snapshot.is_timeout);
        return false;
    }

    return true; /* Awaiting initial sample */
#else
    int64_t now_us = (ctx->executive && ctx->executive->last_tick_us > 0) ?
                     ctx->executive->last_tick_us : 0;
    return nexus_dht11_acquire(ctx->registry, ctx->executive, now_us);
#endif
}
