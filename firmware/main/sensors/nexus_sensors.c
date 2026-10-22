#include "nexus_sensors.h"

#ifdef ESP_PLATFORM
#include "esp_log.h"
static const char *TAG = "nexus_sensors";
#endif

/* Job context storage */
typedef struct {
    nexus_sensor_registry_t *registry;
    nexus_executive_t *executive;
} sensor_job_ctx_t;

static sensor_job_ctx_t s_ldr_job_ctx;
static sensor_job_ctx_t s_cd4051_job_ctx;
static sensor_job_ctx_t s_dht11_job_ctx;
static sensor_job_ctx_t s_moc7811_job_ctx;
static sensor_job_ctx_t s_hcsr04_job_ctx;

static bool ldr_wrapper_job(void *ctx)
{
    sensor_job_ctx_t *jctx = (sensor_job_ctx_t *)ctx;
    return nexus_ldr_job_fn(jctx);
}

static bool cd4051_wrapper_job(void *ctx)
{
    sensor_job_ctx_t *jctx = (sensor_job_ctx_t *)ctx;
    return nexus_cd4051_job_fn(jctx);
}

static bool dht11_wrapper_job(void *ctx)
{
    sensor_job_ctx_t *jctx = (sensor_job_ctx_t *)ctx;
    return nexus_dht11_job_fn(jctx);
}

static bool moc7811_wrapper_job(void *ctx)
{
    sensor_job_ctx_t *jctx = (sensor_job_ctx_t *)ctx;
    return nexus_moc7811_job_fn(jctx);
}

static bool hcsr04_wrapper_job(void *ctx)
{
    sensor_job_ctx_t *jctx = (sensor_job_ctx_t *)ctx;
    return nexus_hcsr04_job_fn(jctx);
}

bool nexus_sensors_init(nexus_sensor_registry_t *registry)
{
    if (!registry) {
        return false;
    }

    nexus_sensor_registry_init(registry);

    bool ldr_ok = nexus_ldr_init(registry);
    bool mux_ok = nexus_cd4051_init(registry);
    bool dht_ok = nexus_dht11_init(registry);
    bool moc_ok = nexus_moc7811_init(registry);
    bool ult_ok = nexus_hcsr04_init(registry);

#ifdef ESP_PLATFORM
    ESP_LOGI(TAG, "Sensors initialized: LDR=%s, CD4051=%s, DHT11=%s, MOC=%s, ULTRA=%s (total registered=%u)",
             ldr_ok ? "OK" : "FAIL",
             mux_ok ? "OK" : "FAIL",
             dht_ok ? "OK" : "FAIL",
             moc_ok ? "OK" : "FAIL",
             ult_ok ? "OK" : "FAIL",
             registry->count);
#endif

    return (ldr_ok && mux_ok && dht_ok && moc_ok && ult_ok);
}

bool nexus_sensors_register_jobs(nexus_sensor_registry_t *registry, nexus_executive_t *executive)
{
    if (!registry || !executive) {
        return false;
    }

    s_ldr_job_ctx.registry = registry;
    s_ldr_job_ctx.executive = executive;

    s_cd4051_job_ctx.registry = registry;
    s_cd4051_job_ctx.executive = executive;

    s_dht11_job_ctx.registry = registry;
    s_dht11_job_ctx.executive = executive;

    s_moc7811_job_ctx.registry = registry;
    s_moc7811_job_ctx.executive = executive;

    s_hcsr04_job_ctx.registry = registry;
    s_hcsr04_job_ctx.executive = executive;

    /* Register Priority Class 1 jobs:
     * - LDR: period 500 ms, deadline 10 ms
     * - CD4051 (X0/X1): period 1000 ms, deadline 10 ms
     * - DHT11: period 2000 ms, deadline 10 ms
     * - MOC7811: period 1000 ms, deadline 10 ms
     * - HC-SR04: period 1000 ms, deadline 10 ms */
    uint16_t id_ldr = nexus_executive_register_job(executive,
                                                  "ldr_acq",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  ldr_wrapper_job,
                                                  &s_ldr_job_ctx,
                                                  NEXUS_LDR_INTERVAL_MS,
                                                  10U);

    uint16_t id_mux = nexus_executive_register_job(executive,
                                                  "mux_acq",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  cd4051_wrapper_job,
                                                  &s_cd4051_job_ctx,
                                                  NEXUS_CD4051_INTERVAL_MS,
                                                  10U);

    uint16_t id_dht = nexus_executive_register_job(executive,
                                                  "dht11_acq",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  dht11_wrapper_job,
                                                  &s_dht11_job_ctx,
                                                  NEXUS_DHT11_INTERVAL_MS,
                                                  10U);

    uint16_t id_moc = nexus_executive_register_job(executive,
                                                  "moc7811_acq",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  moc7811_wrapper_job,
                                                  &s_moc7811_job_ctx,
                                                  NEXUS_MOC7811_INTERVAL_MS,
                                                  10U);

    uint16_t id_ult = nexus_executive_register_job(executive,
                                                  "hcsr04_acq",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  hcsr04_wrapper_job,
                                                  &s_hcsr04_job_ctx,
                                                  NEXUS_HCSR04_INTERVAL_MS,
                                                  20U);

    return (id_ldr != 0 && id_mux != 0 && id_dht != 0 && id_moc != 0 && id_ult != 0);
}
