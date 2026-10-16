#include "nexus_dht11.h"

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
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure GPIO%u: %s", NEXUS_GPIO_DHT11, esp_err_to_name(err));
        return false;
    }

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
        /* Trigger initial acquisition cycle */
        xTaskNotifyGive(s_dht11_task_handle);
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
    uint32_t count = 0;
    while (gpio_get_level(pin) != level) {
        if (++count > timeout_us) {
            return false;
        }
        esp_rom_delay_us(1);
    }
    if (out_elapsed_us) {
        *out_elapsed_us = count;
    }
    return true;
}

bool nexus_dht11_read(nexus_dht11_reading_t *out_reading)
{
    if (!out_reading) {
        return false;
    }
    out_reading->valid = false;

    gpio_num_t pin = (gpio_num_t)NEXUS_GPIO_DHT11;

    /* 1. Host start signal: Pull LOW for 20 ms */
    gpio_set_direction(pin, GPIO_MODE_OUTPUT);
    gpio_set_level(pin, 0);
    vTaskDelay(pdMS_TO_TICKS(20));

    /* 2. Pull HIGH for 30 us and switch to input */
    gpio_set_level(pin, 1);
    esp_rom_delay_us(30);
    gpio_set_direction(pin, GPIO_MODE_INPUT);
    gpio_set_pull_mode(pin, GPIO_PULLUP_ONLY);

    /* 3. Read handshake and 40 bits in critical section to prevent task preempt timing skew */
    portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
    taskENTER_CRITICAL(&mux);

    /* Wait for DHT response LOW (~80us) */
    if (!wait_for_level(pin, 0, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        taskEXIT_CRITICAL(&mux);
        return false;
    }

    /* Wait for DHT response HIGH (~80us) */
    if (!wait_for_level(pin, 1, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        taskEXIT_CRITICAL(&mux);
        return false;
    }

    /* Wait for start of first transmission bit (DHT pulls low) */
    if (!wait_for_level(pin, 0, NEXUS_DHT11_TIMEOUT_US, NULL)) {
        taskEXIT_CRITICAL(&mux);
        return false;
    }

    uint8_t data[5] = { 0 };
    for (int bit = 0; bit < 40; bit++) {
        /* Wait for bit start (HIGH pulse) */
        if (!wait_for_level(pin, 1, NEXUS_DHT11_TIMEOUT_US, NULL)) {
            taskEXIT_CRITICAL(&mux);
            return false;
        }

        /* Measure duration of HIGH pulse */
        uint32_t high_duration_us = 0;
        if (!wait_for_level(pin, 0, NEXUS_DHT11_TIMEOUT_US, &high_duration_us)) {
            taskEXIT_CRITICAL(&mux);
            return false;
        }

        int byte_idx = bit / 8;
        data[byte_idx] <<= 1;
        /* '1' pulse is ~70us, '0' pulse is ~26-28us */
        if (high_duration_us > 40U) {
            data[byte_idx] |= 1U;
        }
    }

    taskEXIT_CRITICAL(&mux);

    /* 4. Verify checksum */
    uint8_t checksum = (uint8_t)(data[0] + data[1] + data[2] + data[3]);
    if (checksum != data[4]) {
        ESP_LOGW(TAG, "DHT11 checksum mismatch: calc=0x%02x recv=0x%02x", checksum, data[4]);
        return false;
    }

    out_reading->humidity_pct = data[0];
    out_reading->temperature_c = data[2];
    out_reading->valid = true;
    return true;
}

#else
/* Host unit test mock implementation */
bool nexus_dht11_read(nexus_dht11_reading_t *out_reading)
{
    if (!out_reading) {
        return false;
    }
    out_reading->valid = false;

    if (s_mock_simulate_timeout || !s_mock_packet_set) {
        return false;
    }

    uint8_t checksum = (uint8_t)(s_mock_bytes[0] + s_mock_bytes[1] + s_mock_bytes[2] + s_mock_bytes[3]);
    if (checksum != s_mock_bytes[4]) {
        return false; /* CRC failure */
    }

    out_reading->humidity_pct = s_mock_bytes[0];
    out_reading->temperature_c = s_mock_bytes[2];
    out_reading->valid = true;
    return true;
}
#endif

bool nexus_dht11_acquire(nexus_sensor_registry_t *registry,
                         nexus_executive_t *executive,
                         int64_t timestamp_us)
{
    if (!registry) {
        return false;
    }

    nexus_dht11_reading_t reading;
    bool success = nexus_dht11_read(&reading);

    if (!success) {
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_DHT11_TEMP, true);
        nexus_sensor_record_error(registry, NEXUS_SENSOR_ID_DHT11_HUM, true);

        if (executive) {
            nexus_executive_emit_event(executive,
                                       NEXUS_EVENT_TYPE_SENSOR_SAMPLE,
                                       NEXUS_SEVERITY_WARN,
                                       NEXUS_SENSOR_ID_DHT11_TEMP,
                                       -1);
        }
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
    for (;;) {
        /* Wait for trigger from executive job (or 2500ms safety timeout) */
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2500));

        nexus_dht11_reading_t reading = { 0 };
        bool success = nexus_dht11_read(&reading);
        int64_t now_us = esp_timer_get_time();

        portENTER_CRITICAL(&s_dht11_spinlock);
        if (success) {
            s_async_data.temperature_c = reading.temperature_c;
            s_async_data.humidity_pct = reading.humidity_pct;
            s_async_data.valid = true;
            s_async_data.new_sample_ready = true;
            s_async_data.new_error_ready = false;
            s_async_data.timestamp_us = now_us;
        } else {
            s_async_data.valid = false;
            s_async_data.new_sample_ready = false;
            s_async_data.new_error_ready = true;
            s_async_data.is_timeout = true;
            s_async_data.timestamp_us = now_us;
        }
        portEXIT_CRITICAL(&s_dht11_spinlock);
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
    /* Non-blocking callback: inspect shared snapshot from background worker */
    nexus_dht11_async_data_t snapshot;
    portENTER_CRITICAL(&s_dht11_spinlock);
    snapshot = s_async_data;
    s_async_data.new_sample_ready = false;
    s_async_data.new_error_ready = false;
    portEXIT_CRITICAL(&s_dht11_spinlock);

    /* Immediately trigger background worker for next 2-second acquisition cycle */
    if (s_dht11_task_handle) {
        xTaskNotifyGive(s_dht11_task_handle);
    }

    if (snapshot.new_sample_ready || snapshot.valid) {
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

        if (ctx->executive) {
            nexus_executive_emit_event(ctx->executive,
                                       NEXUS_EVENT_TYPE_SENSOR_SAMPLE,
                                       NEXUS_SEVERITY_WARN,
                                       NEXUS_SENSOR_ID_DHT11_TEMP,
                                       -1);
        }
        return false;
    }

    return true; /* Awaiting initial sample */
#else
    int64_t now_us = (ctx->executive && ctx->executive->last_tick_us > 0) ?
                     ctx->executive->last_tick_us : 0;
    return nexus_dht11_acquire(ctx->registry, ctx->executive, now_us);
#endif
}
