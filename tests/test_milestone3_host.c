#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <unistd.h>

#include "data_structures/nexus_job_table.h"
#include "data_structures/nexus_ready_queue.h"
#include "data_structures/nexus_event_queue.h"
#include "data_structures/nexus_ring_buffer.h"
#include "executive/nexus_executive.h"

#include "sensors/nexus_sensor_registry.h"
#include "sensors/nexus_adc.h"
#include "sensors/nexus_adc_ldr.h"
#include "sensors/nexus_cd4051.h"
#include "sensors/nexus_dht11.h"
#include "sensors/nexus_sensors.h"

static void test_sensor_registry_lifecycle(void)
{
    printf("  [TEST] Sensor registry capacity, duplicates, and bounds...\n");
    nexus_sensor_registry_t reg;
    nexus_sensor_registry_init(&reg);

    assert(reg.count == 0);
    assert(reg.registration_failures == 0);

    /* Register up to capacity */
    for (uint16_t i = 1; i <= NEXUS_SENSOR_REGISTRY_CAPACITY; i++) {
        char name[16];
        snprintf(name, sizeof(name), "sens_%u", i);
        assert(nexus_sensor_register(&reg, i, name, NEXUS_SENSOR_TYPE_LDR, (uint8_t)i, 1000));
        assert(reg.count == i);
    }

    /* Test capacity exhaustion */
    assert(!nexus_sensor_register(&reg, 99, "overflow", NEXUS_SENSOR_TYPE_LDR, 0, 1000));
    assert(reg.registration_failures == 1);

    /* Test duplicate ID rejection */
    nexus_sensor_registry_t reg2;
    nexus_sensor_registry_init(&reg2);
    assert(nexus_sensor_register(&reg2, 1, "s1", NEXUS_SENSOR_TYPE_LDR, 0, 1000));
    assert(!nexus_sensor_register(&reg2, 1, "dup_s1", NEXUS_SENSOR_TYPE_LDR, 1, 1000));
    assert(reg2.registration_failures == 1);

    /* Test invalid params */
    assert(!nexus_sensor_register(&reg2, 0, "zero_id", NEXUS_SENSOR_TYPE_LDR, 0, 1000));
    assert(!nexus_sensor_register(&reg2, 2, "unknown", NEXUS_SENSOR_TYPE_UNKNOWN, 0, 1000));

    printf("  [PASS] Sensor registry capacity and bounds\n");
}

static void test_sensor_registry_sample_freshness_and_errors(void)
{
    printf("  [TEST] Sensor sample update, error accounting, and freshness...\n");
    nexus_sensor_registry_t reg;
    nexus_sensor_registry_init(&reg);

    assert(nexus_sensor_register(&reg, 10, "test_ldr", NEXUS_SENSOR_TYPE_LDR, 35, 500));

    nexus_sensor_descriptor_t *desc = nexus_sensor_get(&reg, 10);
    assert(desc != NULL);
    assert(desc->sample_count == 0);
    assert(desc->error_count == 0);

    /* Freshness check on uninitialized sensor should be false */
    assert(!nexus_sensor_is_fresh(&reg, 10, 1000000LL, 1000));

    /* Update with valid sample at t = 1000 ms (1,000,000 us) */
    assert(nexus_sensor_update_sample(&reg, 10, 2048, 50, NEXUS_SAMPLE_FLAG_VALID, 1000000LL));
    assert(desc->sample_count == 1);
    assert(desc->latest_raw == 2048);
    assert(desc->latest_processed == 50);

    /* At t = 1500 ms, age is 500 ms -> fresh for max_age_ms = 1000 */
    assert(nexus_sensor_is_fresh(&reg, 10, 1500000LL, 1000));

    /* At t = 2500 ms, age is 1500 ms -> stale for max_age_ms = 1000 */
    assert(!nexus_sensor_is_fresh(&reg, 10, 2500000LL, 1000));

    /* Error accounting */
    assert(nexus_sensor_record_error(&reg, 10, true));
    assert(desc->error_count == 1);
    assert(desc->timeout_count == 1);
    assert((desc->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) != 0);

    /* Even if within time window, sample with ERROR flag is not fresh */
    assert(!nexus_sensor_is_fresh(&reg, 10, 1100000LL, 1000));

    printf("  [PASS] Sensor sample update, error accounting, and freshness\n");
}

static void test_ldr_driver(void)
{
    printf("  [TEST] LDR acquisition and scaling...\n");
    nexus_sensor_registry_t reg;
    nexus_sensor_registry_init(&reg);
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    assert(nexus_ldr_init(&reg));

    /* Inject mock raw ADC reading (2048 / 4095 ~ 50%) */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_LDR, 2048, true);

    assert(nexus_ldr_acquire(&reg, &exec, 1000000LL));

    nexus_sensor_descriptor_t *desc = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_LDR);
    assert(desc != NULL);
    assert(desc->sample_count == 1);
    assert(desc->latest_raw == 2048);
    assert(desc->latest_processed == 50);

    /* Verify sample was recorded to executive ring buffer */
    nexus_sensor_sample_t sample;
    assert(nexus_ring_buffer_peek_newest(&exec.sensor_history, &sample));
    assert(sample.sensor_id == NEXUS_SENSOR_ID_LDR);
    assert(sample.raw_value == 2048);
    assert(sample.processed_value == 50);

    /* Test ADC failure path */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_LDR, 0, false);
    assert(!nexus_ldr_acquire(&reg, &exec, 2000000LL));
    assert(desc->error_count == 1);

    printf("  [PASS] LDR acquisition and scaling\n");
}

static void test_cd4051_truth_table_and_sampling(void)
{
    printf("  [TEST] CD4051 truth table and serialized sampling...\n");
    nexus_sensor_registry_t reg;
    nexus_sensor_registry_init(&reg);
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    assert(nexus_cd4051_init(&reg));

    /* Test truth table for all 8 channels */
    for (uint8_t ch = 0; ch < 8; ch++) {
        assert(nexus_cd4051_select_channel(ch));
        uint8_t a = 0, b = 0, c = 0;
        nexus_cd4051_get_mock_select_lines(&a, &b, &c);

        uint8_t expected_a = (ch & 0x01) ? 1 : 0;
        uint8_t expected_b = (ch & 0x02) ? 1 : 0;
        uint8_t expected_c = (ch & 0x04) ? 1 : 0;

        assert(a == expected_a);
        assert(b == expected_b);
        assert(c == expected_c);
    }

    /* Channel > 7 must be rejected */
    assert(!nexus_cd4051_select_channel(8));
    int raw_out = 0;
    assert(!nexus_cd4051_sample_channel(8, &raw_out));

    /* Test acquisition of Channel X0 (HW-870) */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_CD4051, 1234, true);
    assert(nexus_cd4051_acquire_x0(&reg, &exec, 3000000LL));

    nexus_sensor_descriptor_t *desc = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_MUX_GAS_X0);
    assert(desc != NULL);
    assert(desc->sample_count == 1);
    assert(desc->latest_raw == 1234);
    /* 1234 * 3300 / 4095 ~ 994 mV */
    assert(desc->latest_processed == (1234 * 3300) / 4095);

    printf("  [PASS] CD4051 truth table and serialized sampling\n");
}

static void test_dht11_decoder_and_errors(void)
{
    printf("  [TEST] DHT11 packet parsing, checksum, and timeout handling...\n");
    nexus_sensor_registry_t reg;
    nexus_sensor_registry_init(&reg);
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    assert(nexus_dht11_init(&reg));

    /* Case 1: Valid packet (Humidity=45%, Temp=26°C, Checksum=71) */
    uint8_t valid_bytes[5] = { 45, 0, 26, 0, 71 };
    nexus_dht11_set_mock_packet(valid_bytes, false);

    assert(nexus_dht11_acquire(&reg, &exec, 1000000LL));

    nexus_sensor_descriptor_t *temp_desc = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_DHT11_TEMP);
    nexus_sensor_descriptor_t *hum_desc = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_DHT11_HUM);

    assert(temp_desc != NULL && hum_desc != NULL);
    assert(temp_desc->latest_processed == 26);
    assert(hum_desc->latest_processed == 45);
    assert(temp_desc->sample_count == 1);
    assert(hum_desc->sample_count == 1);

    /* Case 2: Checksum failure (Checksum corrupt: 72 instead of 71) */
    uint8_t bad_crc_bytes[5] = { 45, 0, 26, 0, 72 };
    nexus_dht11_set_mock_packet(bad_crc_bytes, false);

    assert(!nexus_dht11_acquire(&reg, &exec, 2000000LL));
    assert(temp_desc->error_count == 1);
    assert(hum_desc->error_count == 1);

    /* Case 3: Timeout simulation */
    nexus_dht11_set_mock_packet(valid_bytes, true);
    assert(!nexus_dht11_acquire(&reg, &exec, 3000000LL));
    assert(temp_desc->error_count == 2);
    assert(temp_desc->timeout_count == 2);

    printf("  [PASS] DHT11 packet parsing, checksum, and timeout handling\n");
}

static void test_sensors_executive_integration(void)
{
    printf("  [TEST] Sensor integration with Executive Priority Class 1 jobs...\n");
    nexus_sensor_registry_t reg;
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    assert(nexus_sensors_init(&reg));
    assert(nexus_sensors_register_jobs(&reg, &exec));

    /* Verify jobs are registered in job table */
    assert(exec.job_table.active_count == 3);

    /* Inject mock sensor data */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_LDR, 3000, true);
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_CD4051, 1500, true);
    uint8_t valid_bytes[5] = { 55, 0, 24, 0, 79 };
    nexus_dht11_set_mock_packet(valid_bytes, false);

    /* Advance executive tick to t = 2000 ms (all jobs should trigger) */
    nexus_executive_tick(&exec, 2000000LL);

    assert(exec.stats.jobs_dispatched == 3);
    assert(exec.stats.jobs_completed == 3);
    assert(exec.stats.jobs_failed == 0);

    /* Verify sensor registry has samples */
    nexus_sensor_descriptor_t *ldr_d = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_LDR);
    nexus_sensor_descriptor_t *mux_d = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_MUX_GAS_X0);
    nexus_sensor_descriptor_t *dht_t = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_DHT11_TEMP);
    nexus_sensor_descriptor_t *dht_h = nexus_sensor_get(&reg, NEXUS_SENSOR_ID_DHT11_HUM);

    assert(ldr_d->sample_count == 1);
    assert(mux_d->sample_count == 1);
    assert(dht_t->sample_count == 1);
    assert(dht_h->sample_count == 1);

    /* Verify freshness at t = 2100 ms */
    assert(nexus_sensor_is_fresh(&reg, NEXUS_SENSOR_ID_LDR, 2100000LL, 1000));
    assert(nexus_sensor_is_fresh(&reg, NEXUS_SENSOR_ID_MUX_GAS_X0, 2100000LL, 1500));
    assert(nexus_sensor_is_fresh(&reg, NEXUS_SENSOR_ID_DHT11_TEMP, 2100000LL, 2500));

    printf("  [PASS] Sensor integration with Executive Priority Class 1 jobs\n");
}

static bool s_overbudget_ran = false;
static bool overbudget_job_fn(void *ctx)
{
    (void)ctx;
    s_overbudget_ran = true;
    /* Sleep 8ms, exceeding 5ms deadline budget */
    usleep(8000);
    return true;
}

static bool s_delayed_dispatch_ran = false;
static bool delayed_dispatch_job_fn(void *ctx)
{
    (void)ctx;
    s_delayed_dispatch_ran = true;
    return true;
}

static void test_executive_scheduling_and_deadline_miss_accounting(void)
{
    printf("  [TEST] Executive deadline accounting (over-budget callback & delayed dispatch)...\n");
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    /* 1. Test Over-budget callback detection:
     * Register a job with 5ms deadline. Callback sleeps for 8ms. */
    s_overbudget_ran = false;
    uint16_t j_ovb = nexus_executive_register_job(&exec, "overbudget",
                                                  NEXUS_PRIORITY_CLASS_0,
                                                  overbudget_job_fn,
                                                  NULL,
                                                  0, /* one-shot */
                                                  5); /* 5 ms deadline */
    assert(j_ovb > 0);
    assert(nexus_executive_submit_job(&exec, j_ovb));

    nexus_executive_tick(&exec, 100000LL);

    assert(s_overbudget_ran);
    assert(exec.stats.jobs_completed == 1);
    assert(exec.stats.deadline_misses == 1);
    nexus_job_descriptor_t *desc_ovb = nexus_job_get(&exec.job_table, j_ovb);
    assert(desc_ovb != NULL);
    assert(desc_ovb->deadline_miss_count == 1);
    assert(desc_ovb->last_duration_us >= 5000); /* Confirmed over 5ms budget */

    /* 2. Test Delayed dispatch detection:
     * Register a periodic job with period = 100ms, deadline = 10ms. */
    nexus_executive_init(&exec, 100);
    s_delayed_dispatch_ran = false;
    uint16_t j_del = nexus_executive_register_job(&exec, "delayed_disp",
                                                  NEXUS_PRIORITY_CLASS_1,
                                                  delayed_dispatch_job_fn,
                                                  NULL,
                                                  100, /* 100 ms period */
                                                  10); /* 10 ms deadline */
    assert(j_del > 0);

    /* Initial tick at t = 100ms -> dispatched on-time */
    nexus_executive_tick(&exec, 100000LL);
    assert(s_delayed_dispatch_ran);
    assert(exec.stats.deadline_misses == 0);
    nexus_job_descriptor_t *desc_del = nexus_job_get(&exec.job_table, j_del);
    assert(desc_del != NULL);
    assert(desc_del->deadline_miss_count == 0);

    /* Next run is expected at t = 200ms.
     * Simulate that the executive tick was delayed by 30ms and only fires at t = 230ms!
     * Dispatch latency is 30ms (30,000 us) which exceeds the 10ms deadline. */
    s_delayed_dispatch_ran = false;
    nexus_executive_tick(&exec, 230000LL);

    assert(s_delayed_dispatch_ran);
    assert(exec.stats.max_dispatch_latency_us >= 30000);
    assert(desc_del->deadline_miss_count == 1);
    assert(exec.stats.deadline_misses == 1);

    printf("  [PASS] Executive deadline accounting (over-budget callback & delayed dispatch)\n");
}

typedef struct {
    nexus_executive_t *exec;
    uint32_t observed_dispatched;
    uint32_t observed_completed;
    uint32_t observed_failed;
    bool in_flight_checked;
} metrics_probe_ctx_t;

static bool probe_metrics_job_fn(void *ctx)
{
    metrics_probe_ctx_t *p = (metrics_probe_ctx_t *)ctx;
    if (!p || !p->exec) {
        return false;
    }
    p->observed_dispatched = p->exec->stats.jobs_dispatched;
    p->observed_completed = p->exec->stats.jobs_completed;
    p->observed_failed = p->exec->stats.jobs_failed;

    /* In-flight snapshot invariant:
     * During execution of a callback, jobs_dispatched has already incremented (+1),
     * while jobs_completed has not yet incremented (increments on return true).
     * Therefore: jobs_dispatched == jobs_completed + jobs_failed + 1. */
    assert(p->observed_dispatched == (p->observed_completed + p->observed_failed + 1U));
    p->in_flight_checked = true;
    return true;
}

static bool failing_job_fn(void *ctx)
{
    (void)ctx;
    return false;
}

static void test_executive_in_flight_metrics_accounting(void)
{
    printf("  [TEST] Executive in-flight snapshot accounting & failure invariant...\n");
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    metrics_probe_ctx_t probe = {
        .exec = &exec,
        .observed_dispatched = 0,
        .observed_completed = 0,
        .observed_failed = 0,
        .in_flight_checked = false,
    };

    /* 1. Register and run a probe metrics job in a clean executive */
    uint16_t j_probe = nexus_executive_register_job(&exec, "probe",
                                                    NEXUS_PRIORITY_CLASS_2,
                                                    probe_metrics_job_fn,
                                                    &probe,
                                                    0, 50);
    assert(j_probe > 0);
    assert(nexus_executive_submit_job(&exec, j_probe));

    nexus_executive_tick(&exec, 100000LL);

    /* In-flight check asserted inside callback */
    assert(probe.in_flight_checked);
    assert(probe.observed_dispatched == 1);
    assert(probe.observed_completed == 0);
    assert(probe.observed_failed == 0);

    /* After callback completed successfully, quiescent invariant holds:
     * jobs_dispatched == jobs_completed + jobs_failed (1 == 1 + 0) */
    assert(exec.stats.jobs_dispatched == 1);
    assert(exec.stats.jobs_completed == 1);
    assert(exec.stats.jobs_failed == 0);

    /* 2. Hardware scenario simulation:
     * Simulate 3 startup job failures (matching the 3 DHT11 startup timeouts).
     * Then run the probe metrics job again. */
    uint16_t j_fail = nexus_executive_register_job(&exec, "fail_job",
                                                   NEXUS_PRIORITY_CLASS_1,
                                                   failing_job_fn,
                                                   NULL,
                                                   0, 10);
    assert(j_fail > 0);

    for (int i = 0; i < 3; i++) {
        assert(nexus_executive_submit_job(&exec, j_fail));
        nexus_executive_tick(&exec, 200000LL + (i * 100000LL));
    }
    assert(exec.stats.jobs_failed == 3);

    /* Now submit probe metrics job (simulating job_executive_metrics on physical board) */
    probe.in_flight_checked = false;
    assert(nexus_executive_submit_job(&exec, j_probe));
    nexus_executive_tick(&exec, 600000LL);

    assert(probe.in_flight_checked);
    /* Inside callback, exactly matches physical board observation:
     * dispatched = completed + failed + 1 = completed + 3 + 1 = completed + 4! */
    assert(probe.observed_dispatched == probe.observed_completed + 4U);

    /* Once callback finishes, quiescent invariant returns to:
     * dispatched = completed + failed = completed + 3 */
    assert(exec.stats.jobs_dispatched == exec.stats.jobs_completed + 3U);

    printf("  [PASS] Executive in-flight snapshot accounting & failure invariant\n");
}

int main(void)
{
    printf("====================================================\n");
    printf("NEXUS Milestone 3 Sensor Host Unit Test Suite\n");
    printf("====================================================\n");

    test_sensor_registry_lifecycle();
    test_sensor_registry_sample_freshness_and_errors();
    test_ldr_driver();
    test_cd4051_truth_table_and_sampling();
    test_dht11_decoder_and_errors();
    test_sensors_executive_integration();
    test_executive_scheduling_and_deadline_miss_accounting();
    test_executive_in_flight_metrics_accounting();

    printf("====================================================\n");
    printf("ALL MILESTONE 3 HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("====================================================\n");
    return 0;
}
