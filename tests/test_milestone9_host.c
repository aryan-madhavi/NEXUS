#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>
#include <stdbool.h>

#include "sensors/nexus_sensor_registry.h"
#include "sensors/nexus_adc.h"
#include "sensors/nexus_cd4051.h"
#include "sensors/nexus_moc7811.h"
#include "sensors/nexus_hcsr04.h"
#include "sensors/nexus_sensors.h"
#include "transports/nexus_envelope.h"
#include "transports/nexus_connection_manager.h"
#include "command/nexus_command_registry.h"
#include "command/nexus_command_dispatcher.h"
#include "executive/nexus_executive.h"

/* Helper macro for assertion reporting */
#define TEST_ASSERT(cond, msg) do { \
    if (!(cond)) { \
        fprintf(stderr, "ASSERTION FAILED: %s at %s:%d\n", msg, __FILE__, __LINE__); \
        assert(cond); \
    } \
} while(0)

/* Test 1: CD4051 Multiplexer Channel Selection, X0/X1 Isolation, and Serialized Acquisition */
static void test_cd4051_x1_integration(void)
{
    printf("  [TEST] CD4051 X1 Hall-effect integration & serialized acquisition...\n");

    nexus_sensor_registry_t registry;
    nexus_sensor_registry_init(&registry);

    bool ok = nexus_cd4051_init(&registry);
    TEST_ASSERT(ok, "CD4051 initialization");

    /* Verify registration of both X0 and X1 */
    nexus_sensor_descriptor_t *d_x0 = nexus_sensor_get(&registry, NEXUS_SENSOR_ID_MUX_GAS_X0);
    nexus_sensor_descriptor_t *d_x1 = nexus_sensor_get(&registry, NEXUS_SENSOR_ID_HALL_X1);
    TEST_ASSERT(d_x0 != NULL, "X0 descriptor registered");
    TEST_ASSERT(d_x1 != NULL, "X1 descriptor registered");
    TEST_ASSERT(strcmp(d_x0->name, "hw870_x0") == 0, "X0 sensor name");
    TEST_ASSERT(strcmp(d_x1->name, "hall_x1") == 0, "X1 sensor name");
    TEST_ASSERT(d_x0->type == NEXUS_SENSOR_TYPE_ANALOG_MUX, "X0 type analog mux");
    TEST_ASSERT(d_x1->type == NEXUS_SENSOR_TYPE_ANALOG_MUX, "X1 type analog mux");

    /* Test channel selection truth table */
    nexus_cd4051_select_channel(0);
    uint8_t a = 0, b = 0, c = 0;
    nexus_cd4051_get_mock_select_lines(&a, &b, &c);
    TEST_ASSERT(a == 0 && b == 0 && c == 0, "Mux Ch0 truth table: A=0, B=0, C=0");

    nexus_cd4051_select_channel(1);
    nexus_cd4051_get_mock_select_lines(&a, &b, &c);
    TEST_ASSERT(a == 1 && b == 0 && c == 0, "Mux Ch1 truth table: A=1, B=0, C=0");

    /* Test serialized acquisition with isolated values */
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    /* Acquire X0 with mock ADC = 1200 */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_CD4051, 1200, true);
    ok = nexus_cd4051_acquire_x0(&registry, &exec, 100000);
    TEST_ASSERT(ok, "CD4051 X0 acquisition");
    TEST_ASSERT(d_x0->sample_count == 1, "X0 sample count 1");
    TEST_ASSERT(d_x0->latest_raw == 1200, "X0 raw value 1200");
    TEST_ASSERT((d_x0->sample_flags & NEXUS_SAMPLE_FLAG_VALID) != 0, "X0 sample valid");

    /* Acquire X1 with mock ADC = 2400 */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_CD4051, 2400, true);
    ok = nexus_cd4051_acquire_x1(&registry, &exec, 100000);
    TEST_ASSERT(ok, "CD4051 X1 acquisition");
    TEST_ASSERT(d_x1->sample_count == 1, "X1 sample count 1");
    TEST_ASSERT(d_x1->latest_raw == 2400, "X1 raw value 2400");
    TEST_ASSERT((d_x1->sample_flags & NEXUS_SAMPLE_FLAG_VALID) != 0, "X1 sample valid");

    /* Acquire all sequentially */
    nexus_adc_set_mock_raw(NEXUS_ADC_CHANNEL_CD4051, 1850, true);
    ok = nexus_cd4051_acquire_all(&registry, &exec, 150000);
    TEST_ASSERT(ok, "CD4051 serialized acquire_all");
    TEST_ASSERT(d_x0->sample_count == 2, "X0 sample count 2");
    TEST_ASSERT(d_x1->sample_count == 2, "X1 sample count 2");

    /* Verify periodic job callback execution */
    ok = nexus_cd4051_job_fn(NULL);
    TEST_ASSERT(ok, "CD4051 job function executed");

    printf("  [PASS] CD4051 X1 Hall-effect integration verified\n");
}

/* Test 2: MOC7811 Optical Slot Sensor Driver & Logic States */
static void test_moc7811_integration(void)
{
    printf("  [TEST] MOC7811 optical slot sensor driver and logic states...\n");

    nexus_sensor_registry_t registry;
    nexus_sensor_registry_init(&registry);

    bool ok = nexus_moc7811_init(&registry);
    TEST_ASSERT(ok, "MOC7811 driver initialization");

    nexus_sensor_descriptor_t *d_moc = nexus_sensor_get(&registry, NEXUS_SENSOR_ID_MOC7811);
    TEST_ASSERT(d_moc != NULL, "MOC7811 descriptor registered");
    TEST_ASSERT(strcmp(d_moc->name, "moc7811") == 0, "MOC7811 sensor name");
    TEST_ASSERT(d_moc->type == NEXUS_SENSOR_TYPE_OPTICAL_SLOT, "MOC7811 type optical slot");
    TEST_ASSERT(d_moc->pin_or_channel == NEXUS_GPIO_MOC7811, "MOC7811 GPIO34 channel");

    /* State 1: Unblocked (GPIO level 0 -> blocked = false, processed = 0) */
    nexus_moc7811_set_mock_state(0, true);
    ok = nexus_moc7811_acquire(&registry, NULL, 200000);
    TEST_ASSERT(ok, "MOC7811 acquire unblocked state");
    TEST_ASSERT(d_moc->sample_count == 1, "Sample count 1");
    TEST_ASSERT(d_moc->latest_raw == 0, "Raw level 0");
    TEST_ASSERT(d_moc->latest_processed == 0, "Processed state 0 (unblocked)");
    TEST_ASSERT((d_moc->sample_flags & NEXUS_SAMPLE_FLAG_VALID) != 0, "Valid flag set");

    /* State 2: Blocked (GPIO level 1 -> blocked = true, processed = 1) */
    nexus_moc7811_set_mock_state(1, true);
    ok = nexus_moc7811_acquire(&registry, NULL, 300000);
    TEST_ASSERT(ok, "MOC7811 acquire blocked state");
    TEST_ASSERT(d_moc->sample_count == 2, "Sample count 2");
    TEST_ASSERT(d_moc->latest_raw == 1, "Raw level 1");
    TEST_ASSERT(d_moc->latest_processed == 1, "Processed state 1 (blocked)");

    /* State 3: Failure handling */
    nexus_moc7811_set_mock_state(0, false);
    ok = nexus_moc7811_acquire(&registry, NULL, 400000);
    TEST_ASSERT(!ok, "MOC7811 acquire handles mock failure");
    TEST_ASSERT(d_moc->error_count == 1, "Error count incremented");

    printf("  [PASS] MOC7811 optical slot sensor driver verified\n");
}

/* Test 3: HC-SR04 Ultrasonic Distance Sensor Driver & Electrical Safety */
static void test_hcsr04_integration(void)
{
    printf("  [TEST] HC-SR04 ultrasonic sensor driver, math, and safety inhibitor...\n");

    nexus_sensor_registry_t registry;
    nexus_sensor_registry_init(&registry);

    bool ok = nexus_hcsr04_init(&registry);
    TEST_ASSERT(ok, "HC-SR04 driver initialization");

    nexus_sensor_descriptor_t *d_dist = nexus_sensor_get(&registry, NEXUS_SENSOR_ID_HCSR04);
    TEST_ASSERT(d_dist != NULL, "HC-SR04 descriptor registered");
    TEST_ASSERT(strcmp(d_dist->name, "hcsr04") == 0, "HC-SR04 sensor name");
    TEST_ASSERT(d_dist->type == NEXUS_SENSOR_TYPE_ULTRASONIC, "HC-SR04 type ultrasonic");

    /* Verify safety inhibitor: default hardware mode prohibits acquisition pending voltage check */
    TEST_ASSERT(!nexus_hcsr04_is_live_enabled(), "Live HW acquisition inhibited by default");

    nexus_hcsr04_reading_t inhibited_reading;
    bool read_ok = nexus_hcsr04_read(&inhibited_reading);
    TEST_ASSERT(!read_ok, "Read fails when live acquisition is inhibited");
    TEST_ASSERT(inhibited_reading.status == NEXUS_HCSR04_STATUS_UNVERIFIED_VOLTAGE, "Status is UNVERIFIED_VOLTAGE");
    TEST_ASSERT(!inhibited_reading.valid, "Inhibited reading is not valid");
    TEST_ASSERT(inhibited_reading.distance_cm == -1, "Inhibited distance is -1");

    /* Acquire must also fail while inhibited */
    ok = nexus_hcsr04_acquire(&registry, NULL, 450000);
    TEST_ASSERT(!ok, "Acquire fails when live acquisition is inhibited");
    TEST_ASSERT(d_dist->error_count == 1, "Error recorded for inhibited acquire");
    TEST_ASSERT((d_dist->sample_flags & NEXUS_SAMPLE_FLAG_VALID) == 0, "No valid sample flag while inhibited");

    /* Test distance calculation arithmetic */
    int32_t dist_cm = 0;
    /* 580 us / 58 = 10 cm */
    ok = nexus_hcsr04_calculate_distance(580, &dist_cm);
    TEST_ASSERT(ok, "Calculate 10 cm from 580 us");
    TEST_ASSERT(dist_cm == 10, "Distance is exactly 10 cm");

    /* 2900 us / 58 = 50 cm */
    ok = nexus_hcsr04_calculate_distance(2900, &dist_cm);
    TEST_ASSERT(ok, "Calculate 50 cm from 2900 us");
    TEST_ASSERT(dist_cm == 50, "Distance is exactly 50 cm");

    /* Boundary checks: < 2 cm (100 us / 58 = 1 cm) is out of range */
    ok = nexus_hcsr04_calculate_distance(100, &dist_cm);
    TEST_ASSERT(!ok, "Reject < 2 cm as out of range");

    /* Boundary checks: > 400 cm (24000 us / 58 = 413 cm) is out of range */
    ok = nexus_hcsr04_calculate_distance(24000, &dist_cm);
    TEST_ASSERT(!ok, "Reject > 400 cm as out of range");

    /* Explicitly enable live mode for mock acquisition testing */
    nexus_hcsr04_set_live_enabled(true);
    TEST_ASSERT(nexus_hcsr04_is_live_enabled(), "Live HW acquisition explicitly enabled");

    /* Test mock acquisition */
    nexus_hcsr04_set_mock_pulse(1450, true); /* 1450 us / 58 = 25 cm */
    ok = nexus_hcsr04_acquire(&registry, NULL, 500000);
    TEST_ASSERT(ok, "HC-SR04 acquire mock pulse");
    TEST_ASSERT(d_dist->sample_count == 1, "Sample count 1");
    TEST_ASSERT(d_dist->latest_raw == 1450, "Raw echo pulse duration 1450 us");
    TEST_ASSERT(d_dist->latest_processed == 25, "Processed distance 25 cm");
    TEST_ASSERT((d_dist->sample_flags & NEXUS_SAMPLE_FLAG_VALID) != 0, "Valid sample flag");

    /* Test timeout handling and stale data invalidation */
    nexus_hcsr04_set_mock_pulse(0, false);
    ok = nexus_hcsr04_acquire(&registry, NULL, 600000);
    TEST_ASSERT(!ok, "HC-SR04 handles timeout");
    TEST_ASSERT(d_dist->error_count == 2, "Error count incremented on timeout");
    TEST_ASSERT((d_dist->sample_flags & NEXUS_SAMPLE_FLAG_VALID) == 0, "VALID flag cleared on timeout (no stale leak)");
    TEST_ASSERT((d_dist->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) != 0, "ERROR flag set on timeout");

    /* Restore default safety-inhibited state */
    nexus_hcsr04_set_live_enabled(false);
    TEST_ASSERT(!nexus_hcsr04_is_live_enabled(), "Live HW acquisition re-inhibited to safe state");

    printf("  [PASS] HC-SR04 ultrasonic sensor driver verified\n");
}

/* Test 4: Full Sensor Suite Integration & Registry Capacity */
static void test_full_sensor_suite_capacity(void)
{
    printf("  [TEST] Sensor registry capacity with all 7 active sensors...\n");

    nexus_sensor_registry_t registry;
    nexus_sensor_registry_init(&registry);

    bool ok = nexus_sensors_init(&registry);
    TEST_ASSERT(ok, "Full nexus_sensors_init succeeds");

    /* Verify count is exactly 7 sensors, fitting within capacity of 8 */
    TEST_ASSERT(registry.count == 7, "Registry count is exactly 7");
    TEST_ASSERT(registry.count <= NEXUS_SENSOR_REGISTRY_CAPACITY, "Fits within registry capacity 8");

    /* Verify each sensor ID exists */
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_LDR) != NULL, "LDR registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_DHT11_TEMP) != NULL, "DHT11 Temp registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_DHT11_HUM) != NULL, "DHT11 Hum registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_MUX_GAS_X0) != NULL, "Gas X0 registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_HALL_X1) != NULL, "Hall X1 registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_MOC7811) != NULL, "MOC7811 registered");
    TEST_ASSERT(nexus_sensor_get(&registry, NEXUS_SENSOR_ID_HCSR04) != NULL, "HC-SR04 registered");

    /* Register Priority Class 1 jobs with executive */
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);
    ok = nexus_sensors_register_jobs(&registry, &exec);
    TEST_ASSERT(ok, "All sensor jobs registered with executive");

    printf("  [PASS] Full sensor suite capacity verified\n");
}

/* Test 5: Telemetry Envelope Formatting & 256-Byte Envelope Ceiling */
static void test_envelope_m9_formatting(void)
{
    printf("  [TEST] Extended telemetry envelope formatting & 256-byte ceiling...\n");

    nexus_envelope_t env;
    memset(&env, 0, sizeof(env));

    /* Case A: Full extended telemetry with all sensors active */
    bool ok = nexus_envelope_format_telemetry_ext(&env,
                                                  123456U,
                                                  987654321LL,
                                                  4095, /* ldr */
                                                  4095, /* x0 */
                                                  4095, /* x1 */
                                                  50,   /* temp */
                                                  100,  /* hum */
                                                  true, /* dht_valid */
                                                  1,    /* slot */
                                                  400); /* dist */
    TEST_ASSERT(ok, "Format extended telemetry");
    TEST_ASSERT(env.length > 0, "Envelope length positive");
    TEST_ASSERT(env.length < NEXUS_ENVELOPE_MAX_LEN, "Envelope length within 256-byte ceiling");

    printf("    -> Worst-case full envelope length: %u bytes (ceiling: %u bytes)\n",
           env.length, NEXUS_ENVELOPE_MAX_LEN);

    /* Verify JSON contents */
    const char *buf = (const char *)env.buffer;
    TEST_ASSERT(strstr(buf, "\"ldr\":4095") != NULL, "LDR field present");
    TEST_ASSERT(strstr(buf, "\"x0\":4095") != NULL, "X0 field present");
    TEST_ASSERT(strstr(buf, "\"x1\":4095") != NULL, "X1 field present");
    TEST_ASSERT(strstr(buf, "\"temp\":50") != NULL, "Temp field present");
    TEST_ASSERT(strstr(buf, "\"hum\":100") != NULL, "Hum field present");
    TEST_ASSERT(strstr(buf, "\"slot\":1") != NULL, "Slot field present");
    TEST_ASSERT(strstr(buf, "\"dist\":400") != NULL, "Dist field present");
    TEST_ASSERT(strstr(buf, "\"dht_valid\":true") != NULL, "dht_valid field present");

    /* Case B: Backward compatibility - legacy nexus_envelope_format_telemetry omits x1, slot, dist */
    memset(&env, 0, sizeof(env));
    ok = nexus_envelope_format_telemetry(&env, 100U, 5000LL, 1200, 3100, 24, 60, true);
    TEST_ASSERT(ok, "Format legacy telemetry");
    buf = (const char *)env.buffer;
    TEST_ASSERT(strstr(buf, "\"x1\"") == NULL, "Legacy envelope omits x1");
    TEST_ASSERT(strstr(buf, "\"slot\"") == NULL, "Legacy envelope omits slot");
    TEST_ASSERT(strstr(buf, "\"dist\"") == NULL, "Legacy envelope omits dist");

    printf("  [PASS] Extended telemetry formatting & bounds verified\n");
}

/* Test 6: Updated Commands: DISPLAY ANALOG (0x1044) & DIAGNOSTICS SENSORS (0x1802) */
static void test_m9_commands_and_diagnostics(void)
{
    printf("  [TEST] Updated DISPLAY ANALOG (0x1044) & DIAGNOSTICS SENSORS (0x1802)...\n");

    nexus_sensor_registry_t sensors;
    nexus_sensor_registry_init(&sensors);
    nexus_sensors_init(&sensors);

    /* Populate samples */
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_LDR, 1850, 1850, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, 26, 26, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_DHT11_HUM, 55, 55, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_MUX_GAS_X0, 3100, 3100, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_HALL_X1, 2450, 2450, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_MOC7811, 1, 1, NEXUS_SAMPLE_FLAG_VALID, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_HCSR04, 2900, 50, NEXUS_SAMPLE_FLAG_VALID, 1000);

    nexus_command_dispatcher_t disp;
    nexus_command_dispatcher_init(&disp, NULL, &sensors, NULL);

    nexus_envelope_t resp;

    /* 1. DISPLAY ANALOG (0x1044) */
    const char *cmd_analog = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":10,\"type\":\"cmd\",\"verb\":\"DISPLAY\",\"noun\":\"ANALOG\"}\n";
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL,
                                              (const uint8_t *)cmd_analog, strlen(cmd_analog), &resp);
    TEST_ASSERT(ok, "DISPLAY ANALOG processed");
    const char *buf = (const char *)resp.buffer;
    TEST_ASSERT(strstr(buf, "\"mux_x0\":3100") != NULL, "Mux X0 in DISPLAY ANALOG");
    TEST_ASSERT(strstr(buf, "\"valid\":true") != NULL, "Valid X0 in DISPLAY ANALOG");
    TEST_ASSERT(strstr(buf, "\"mux_x1\":2450") != NULL, "Mux X1 in DISPLAY ANALOG");
    TEST_ASSERT(strstr(buf, "\"valid_x1\":true") != NULL, "Valid X1 in DISPLAY ANALOG");

    /* 2. DIAGNOSTICS SENSORS (0x1802) */
    const char *cmd_diag_sens = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":11,\"type\":\"cmd\",\"verb\":\"DIAGNOSTICS\",\"noun\":\"SENSORS\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL,
                                          (const uint8_t *)cmd_diag_sens, strlen(cmd_diag_sens), &resp);
    TEST_ASSERT(ok, "DIAGNOSTICS SENSORS processed");
    buf = (const char *)resp.buffer;
    TEST_ASSERT(strstr(buf, "\"registered\":7") != NULL, "Registered count 7");
    TEST_ASSERT(strstr(buf, "\"valid_sensors\":7") != NULL, "Valid sensors count 7");
    TEST_ASSERT(strstr(buf, "\"reads\":7") != NULL, "Reads count 7");
    TEST_ASSERT(strstr(buf, "\"errors\":0") != NULL, "Errors count 0");

    printf("  [PASS] Commands and diagnostics verified\n");
}

int main(void)
{
    printf("====================================================\n");
    printf("NEXUS Milestone 9 Sensor Integration Host Test Suite\n");
    printf("====================================================\n");

    test_cd4051_x1_integration();
    test_moc7811_integration();
    test_hcsr04_integration();
    test_full_sensor_suite_capacity();
    test_envelope_m9_formatting();
    test_m9_commands_and_diagnostics();

    printf("====================================================\n");
    printf("ALL MILESTONE 9 HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("====================================================\n");
    return 0;
}
