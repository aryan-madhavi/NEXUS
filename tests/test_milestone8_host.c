#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>
#include <stdbool.h>

#include "command/nexus_command_registry.h"
#include "command/nexus_command_dispatcher.h"
#include "executive/nexus_executive.h"
#include "sensors/nexus_sensor_registry.h"
#include "transports/nexus_transport.h"
#include "transports/nexus_envelope.h"
#include "transports/nexus_connection_manager.h"

/* Helper macro for assertion reporting */
#define TEST_ASSERT(cond, msg) do { \
    if (!(cond)) { \
        fprintf(stderr, "ASSERTION FAILED: %s at %s:%d\n", msg, __FILE__, __LINE__); \
        assert(cond); \
    } \
} while(0)

/* Test 1: Canonical Command Registry Integrity */
static void test_registry_integrity(void)
{
    printf("  [TEST] Canonical command registry completeness, unique IDs, and mappings...\n");

    size_t count = 0;
    const nexus_cmd_registry_entry_t *all_entries = nexus_cmd_registry_get_all(&count);
    TEST_ASSERT(count == 115, "Expected exactly 115 candidate command entries");
    TEST_ASSERT(count == NEXUS_CANDIDATE_COMMANDS_COUNT, "Expected count to match NEXUS_CANDIDATE_COMMANDS_COUNT macro");

    /* Check for duplicate IDs or duplicate verb-noun pairs */
    for (size_t i = 0; i < count; ++i) {
        const nexus_cmd_registry_entry_t *a = &all_entries[i];
        TEST_ASSERT(a->cmd_id != 0 || (a->verb_code == 0 && a->noun_code == 0), "Valid cmd_id or NOP");
        TEST_ASSERT(a->verb_name != NULL && strlen(a->verb_name) > 0, "Non-empty verb name");
        TEST_ASSERT(a->noun_name != NULL && strlen(a->noun_name) > 0, "Non-empty noun name");

        /* Lookup by ID must return same entry */
        const nexus_cmd_registry_entry_t *found_id = nexus_cmd_registry_lookup_by_id(a->cmd_id);
        TEST_ASSERT(found_id == a, "Lookup by ID must match entry");

        /* Lookup by Name must return same entry */
        const nexus_cmd_registry_entry_t *found_name = nexus_cmd_registry_lookup_by_name(a->verb_name, a->noun_name);
        TEST_ASSERT(found_name == a, "Lookup by Name must match entry");

        /* Check against subsequent entries for duplicates */
        for (size_t j = i + 1; j < count; ++j) {
            const nexus_cmd_registry_entry_t *b = &all_entries[j];
            TEST_ASSERT(a->cmd_id != b->cmd_id, "Duplicate command ID detected in registry");
            bool same_name = (strcasecmp(a->verb_name, b->verb_name) == 0 &&
                              strcasecmp(a->noun_name, b->noun_name) == 0);
            TEST_ASSERT(!same_name, "Duplicate verb-noun pair detected in registry");
        }
    }

    /* Verify disposition strings */
    TEST_ASSERT(strcmp(nexus_cmd_disposition_str(NEXUS_CMD_DISP_REQUIRED_M8), "REQUIRED_M8") == 0, "Disposition str");
    TEST_ASSERT(strcmp(nexus_cmd_disposition_str(NEXUS_CMD_DISP_UNSUPPORTED), "UNSUPPORTED") == 0, "Disposition str");
    TEST_ASSERT(strcmp(nexus_cmd_disposition_str(NEXUS_CMD_DISP_DEFERRED_M9_M10), "DEFERRED_M9_M10") == 0, "Disposition str");

    printf("  [PASS] Canonical command registry integrity verified\n");
}

/* Test 2: Valid Supported Command Execution (NOP, GET STATUS, GET CONFIGURATION, GET TIME) */
static void test_supported_commands_execution(void)
{
    printf("  [TEST] Dispatcher execution of valid supported commands...\n");

    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    nexus_sensor_registry_t sensors;
    nexus_sensor_registry_init(&sensors);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_LDR, "ldr", NEXUS_SENSOR_TYPE_LDR, 34, 100);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, "dht11_temp", NEXUS_SENSOR_TYPE_DHT11_TEMP, 4, 1000);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_DHT11_HUM, "dht11_hum", NEXUS_SENSOR_TYPE_DHT11_HUM, 4, 1000);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_MUX_GAS_X0, "mux_x0", NEXUS_SENSOR_TYPE_ANALOG_MUX, 35, 200);

    nexus_command_dispatcher_t disp;
    bool init_ok = nexus_command_dispatcher_init(&disp, &exec, &sensors, NULL);
    TEST_ASSERT(init_ok, "Dispatcher initialization");

    /* 1. NOP NONE */
    const char *cmd_nop = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":1,\"type\":\"cmd\",\"verb\":\"NOP\",\"noun\":\"NONE\"}\n";
    nexus_envelope_t resp;
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_nop, strlen(cmd_nop), &resp);
    TEST_ASSERT(ok, "NOP command execution");
    TEST_ASSERT(resp.length > 0 && resp.length < NEXUS_ENVELOPE_MAX_LEN, "Response bounded");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"completed\"") != NULL, "Status completed");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"code\":0") != NULL, "Code 0");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"cmd_id\":0") != NULL, "Cmd id 0");

    /* 2. GET STATUS */
    const char *cmd_status = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":2,\"type\":\"cmd\",\"cmd_id\":1537,\"verb\":\"GET\",\"noun\":\"STATUS\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_status, strlen(cmd_status), &resp);
    TEST_ASSERT(ok, "GET STATUS execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"completed\"") != NULL, "Status completed");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"heap\":") != NULL, "Heap present");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"ticks\":") != NULL, "Ticks present");

    /* 3. GET CONFIGURATION */
    const char *cmd_cfg = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":3,\"type\":\"cmd\",\"verb\":\"GET\",\"noun\":\"CONFIGURATION\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_MQTT, (const uint8_t *)cmd_cfg, strlen(cmd_cfg), &resp);
    TEST_ASSERT(ok, "GET CONFIGURATION execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"proto\":1") != NULL, "Protocol version 1");

    /* 4. GET SENSOR_LIST */
    const char *cmd_sl = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":4,\"type\":\"cmd\",\"verb\":\"GET\",\"noun\":\"SENSOR_LIST\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_sl, strlen(cmd_sl), &resp);
    TEST_ASSERT(ok, "GET SENSOR_LIST execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"sensors\":[") != NULL &&
                strstr((char *)resp.buffer, "\"ldr\"") != NULL &&
                strstr((char *)resp.buffer, "\"dht11\"") != NULL, "Sensors list matches");

    /* 5. GET TIME */
    const char *cmd_time = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":5,\"type\":\"cmd\",\"verb\":\"GET\",\"noun\":\"TIME\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_time, strlen(cmd_time), &resp);
    TEST_ASSERT(ok, "GET TIME execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"uptime_ms\":") != NULL, "Uptime ms present");

    /* 6. RUN SELF_TEST */
    const char *cmd_st = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":6,\"type\":\"cmd\",\"verb\":\"RUN\",\"noun\":\"SELF_TEST\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_st, strlen(cmd_st), &resp);
    TEST_ASSERT(ok, "RUN SELF_TEST execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"selftest\":true") != NULL, "Self-test passed");

    /* 7. RUN SENSOR_TEST */
    const char *cmd_sens_test = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":7,\"type\":\"cmd\",\"verb\":\"RUN\",\"noun\":\"SENSOR_TEST\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_sens_test, strlen(cmd_sens_test), &resp);
    TEST_ASSERT(ok, "RUN SENSOR_TEST execution");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"sensor_test\":true") != NULL, "Sensor test passed");

    printf("  [PASS] Valid supported commands executed successfully\n");
}

/* Test 3: Display & Diagnostics Handlers */
static void test_display_and_diagnostics_handlers(void)
{
    printf("  [TEST] Display and diagnostics command handlers...\n");

    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    nexus_sensor_registry_t sensors;
    nexus_sensor_registry_init(&sensors);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_LDR, "ldr", NEXUS_SENSOR_TYPE_LDR, 34, 100);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, "dht11_temp", NEXUS_SENSOR_TYPE_DHT11_TEMP, 4, 1000);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_DHT11_HUM, "dht11_hum", NEXUS_SENSOR_TYPE_DHT11_HUM, 4, 1000);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_MUX_GAS_X0, "mux_x0", NEXUS_SENSOR_TYPE_ANALOG_MUX, 35, 200);

    /* Update sample readings */
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_LDR, 1850, 1850, 0, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, 26, 26, 0, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_DHT11_HUM, 55, 55, 0, 1000);
    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_MUX_GAS_X0, 3100, 3100, 0, 1000);

    nexus_command_dispatcher_t disp;
    nexus_command_dispatcher_init(&disp, &exec, &sensors, NULL);

    nexus_envelope_t resp;

    /* DISPLAY ENVIRONMENT */
    const char *cmd_env = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":10,\"type\":\"cmd\",\"verb\":\"DISPLAY\",\"noun\":\"ENVIRONMENT\"}\n";
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_env, strlen(cmd_env), &resp);
    TEST_ASSERT(ok, "DISPLAY ENVIRONMENT");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"temp\":26") != NULL, "Temp 26");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"hum\":55") != NULL, "Hum 55");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"valid\":true") != NULL, "Valid true");

    /* Verify DISPLAY ENVIRONMENT reports valid:false during active error, and recovers to valid:true on subsequent sample */
    nexus_sensor_record_error(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, false);
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_env, strlen(cmd_env), &resp);
    TEST_ASSERT(ok, "DISPLAY ENVIRONMENT during error");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"valid\":false") != NULL, "Valid false on active error");

    nexus_sensor_update_sample(&sensors, NEXUS_SENSOR_ID_DHT11_TEMP, 27, 27, 0, 2000);
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_env, strlen(cmd_env), &resp);
    TEST_ASSERT(ok, "DISPLAY ENVIRONMENT after recovery");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"temp\":27") != NULL, "Temp 27");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"valid\":true") != NULL, "Valid true after recovery despite error_count > 0");

    /* DISPLAY LIGHT */
    const char *cmd_light = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":11,\"type\":\"cmd\",\"verb\":\"DISPLAY\",\"noun\":\"LIGHT\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_light, strlen(cmd_light), &resp);
    TEST_ASSERT(ok, "DISPLAY LIGHT");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"ldr_raw\":1850") != NULL, "LDR raw 1850");

    /* DISPLAY ANALOG */
    const char *cmd_analog = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":12,\"type\":\"cmd\",\"verb\":\"DISPLAY\",\"noun\":\"ANALOG\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_analog, strlen(cmd_analog), &resp);
    TEST_ASSERT(ok, "DISPLAY ANALOG");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"mux_x0\":3100") != NULL, "Mux x0 3100");

    /* DIAGNOSTICS SYSTEM */
    const char *cmd_diag_sys = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":13,\"type\":\"cmd\",\"verb\":\"DIAGNOSTICS\",\"noun\":\"SYSTEM\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_diag_sys, strlen(cmd_diag_sys), &resp);
    TEST_ASSERT(ok, "DIAGNOSTICS SYSTEM");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"completed\"") != NULL, "Completed");

    /* DIAGNOSTICS SENSORS */
    const char *cmd_diag_sens = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":14,\"type\":\"cmd\",\"verb\":\"DIAGNOSTICS\",\"noun\":\"SENSORS\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_diag_sens, strlen(cmd_diag_sens), &resp);
    TEST_ASSERT(ok, "DIAGNOSTICS SENSORS");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"reads\":5") != NULL, "Reads 5");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"errors\":1") != NULL, "Errors 1");

    printf("  [PASS] Display and diagnostics handlers verified\n");
}

/* Test 4: Unsupported and Deferred Commands Handling */
static void test_unsupported_and_deferred_commands(void)
{
    printf("  [TEST] Safe rejection of unsupported and deferred commands...\n");

    nexus_command_dispatcher_t disp;
    nexus_command_dispatcher_init(&disp, NULL, NULL, NULL);

    nexus_envelope_t resp;

    /* 1. INITIALIZE SYSTEM (Unsupported) */
    const char *cmd_init = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":20,\"type\":\"cmd\",\"verb\":\"INITIALIZE\",\"noun\":\"SYSTEM\"}\n";
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_init, strlen(cmd_init), &resp);
    TEST_ASSERT(ok, "Processed unsupported command");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"unsupported\"") != NULL, "Status unsupported");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"code\":3") != NULL, "Code 3");

    /* 2. SET PRIORITY (Unsupported for safety) */
    const char *cmd_pri = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":21,\"type\":\"cmd\",\"verb\":\"SET\",\"noun\":\"PRIORITY\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_pri, strlen(cmd_pri), &resp);
    TEST_ASSERT(ok, "Processed unsupported command");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"unsupported\"") != NULL, "Status unsupported");

    /* 3. ACTUATE RELAY (Unsupported: unmounted relay K1) */
    const char *cmd_relay = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":22,\"type\":\"cmd\",\"verb\":\"ACTUATE\",\"noun\":\"RELAY\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_relay, strlen(cmd_relay), &resp);
    TEST_ASSERT(ok, "Processed unsupported command");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"unsupported\"") != NULL, "Status unsupported");

    /* 4. ACTUATE SERVO (Unsupported: unmounted servo on GPIO33) */
    const char *cmd_servo = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":23,\"type\":\"cmd\",\"verb\":\"ACTUATE\",\"noun\":\"SERVO\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_servo, strlen(cmd_servo), &resp);
    TEST_ASSERT(ok, "Processed unsupported command");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"unsupported\"") != NULL, "Status unsupported");

    /* 5. ACTUATE MOTOR (Unsupported: unmounted L293D DC motors) */
    const char *cmd_motor = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":24,\"type\":\"cmd\",\"verb\":\"ACTUATE\",\"noun\":\"MOTOR\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_motor, strlen(cmd_motor), &resp);
    TEST_ASSERT(ok, "Processed unsupported command");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"unsupported\"") != NULL, "Status unsupported");

    printf("  [PASS] Unsupported and deferred commands rejected safely with code 3\n");
}

/* Test: Capabilities reporting and non-rebooting RESET FAULTS */
static void test_capabilities_and_fault_reset(void)
{
    printf("  [TEST] GET CAPABILITIES and non-rebooting RESET FAULTS...\n");

    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    nexus_sensor_registry_t sensors;
    nexus_sensor_registry_init(&sensors);
    nexus_sensor_register(&sensors, NEXUS_SENSOR_ID_LDR, "ldr", NEXUS_SENSOR_TYPE_LDR, 34, 100);
    nexus_sensor_record_error(&sensors, NEXUS_SENSOR_ID_LDR, false);

    nexus_command_dispatcher_t disp;
    nexus_command_dispatcher_init(&disp, &exec, &sensors, NULL);

    nexus_envelope_t resp;

    /* 1. GET CAPABILITIES */
    const char *cmd_cap = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":40,\"type\":\"cmd\",\"verb\":\"GET\",\"noun\":\"CAPABILITIES\"}\n";
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_cap, strlen(cmd_cap), &resp);
    TEST_ASSERT(ok, "GET CAPABILITIES executed");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"mounted\":\"ldr,dht,cd4051,moc,dist,led,buz\"") != NULL, "Truthful mounted hardware");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"unmounted\":\"touch,vib,snd,servo,lm35,relay\"") != NULL, "Truthful unmounted hardware");

    /* 2. RESET FAULTS (must clear fault count without rebooting) */
    const char *cmd_rf = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":41,\"type\":\"cmd\",\"verb\":\"RESET\",\"noun\":\"FAULTS\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_rf, strlen(cmd_rf), &resp);
    TEST_ASSERT(ok, "RESET FAULTS executed");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"completed\"") != NULL, "Status completed");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"faults_cleared\":true") != NULL, "Faults cleared");

    /* Verify sensor error count was reset */
    nexus_sensor_descriptor_t *d = nexus_sensor_get(&sensors, NEXUS_SENSOR_ID_LDR);
    TEST_ASSERT(d != NULL && d->error_count == 0, "Sensor error count cleared by RESET FAULTS");

    printf("  [PASS] GET CAPABILITIES and non-rebooting RESET FAULTS verified\n");
}

/* Test 5: Rejection of Malformed, Oversized, and Invalid Inputs */
static void test_malformed_and_invalid_inputs(void)
{
    printf("  [TEST] Validation and rejection of malformed, oversized, and invalid inputs...\n");

    nexus_command_dispatcher_t disp;
    nexus_command_dispatcher_init(&disp, NULL, NULL, NULL);

    nexus_envelope_t resp;

    /* 1. Missing required field (no type) */
    const char *cmd_missing_type = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":30,\"verb\":\"NOP\",\"noun\":\"NONE\"}\n";
    bool ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_missing_type, strlen(cmd_missing_type), &resp);
    TEST_ASSERT(ok, "Processed invalid");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected missing type");

    /* 2. Malformed JSON (unclosed brace) */
    const char *cmd_malformed = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":31,\"type\":\"cmd\"\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_malformed, strlen(cmd_malformed), &resp);
    TEST_ASSERT(ok, "Processed malformed JSON");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected malformed JSON");

    /* 3. Unknown verb */
    const char *cmd_unk_verb = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":32,\"type\":\"cmd\",\"verb\":\"INVALID_VERB\",\"noun\":\"NONE\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_unk_verb, strlen(cmd_unk_verb), &resp);
    TEST_ASSERT(ok, "Processed unknown verb");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected unknown verb");

    /* 4. Unknown noun */
    const char *cmd_unk_noun = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":33,\"type\":\"cmd\",\"verb\":\"NOP\",\"noun\":\"INVALID_NOUN\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_unk_noun, strlen(cmd_unk_noun), &resp);
    TEST_ASSERT(ok, "Processed unknown noun");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected unknown noun");

    /* 5. Unknown command ID */
    const char *cmd_unk_id = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":34,\"type\":\"cmd\",\"cmd_id\":59999}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_unk_id, strlen(cmd_unk_id), &resp);
    TEST_ASSERT(ok, "Processed unknown cmd_id");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected unknown cmd_id");

    /* 6. Mismatched command ID and verb-noun */
    const char *cmd_mismatch = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":35,\"type\":\"cmd\",\"cmd_id\":1537,\"verb\":\"NOP\",\"noun\":\"NONE\"}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_mismatch, strlen(cmd_mismatch), &resp);
    TEST_ASSERT(ok, "Processed mismatched cmd_id");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected mismatched cmd_id");

    /* 7. Oversized envelope (>= 256 bytes) */
    char oversized[300];
    memset(oversized, 'x', sizeof(oversized));
    const char *prefix = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":36,\"type\":\"cmd\",\"padding\":\"";
    memcpy(oversized, prefix, strlen(prefix));
    oversized[298] = '}';
    oversized[299] = '\n';
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)oversized, sizeof(oversized), &resp);
    TEST_ASSERT(ok, "Processed oversized");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected oversized envelope");

    /* 8. Wrong message type (e.g. telemetry fed to command dispatcher) */
    const char *cmd_wrong_type = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":37,\"type\":\"telem\",\"temp\":25}\n";
    ok = nexus_command_dispatcher_process(&disp, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_wrong_type, strlen(cmd_wrong_type), &resp);
    TEST_ASSERT(ok, "Processed wrong type");
    TEST_ASSERT(strstr((char *)resp.buffer, "\"status\":\"rejected\"") != NULL, "Rejected wrong message type");

    printf("  [PASS] Malformed, oversized, and invalid inputs rejected safely\n");
}

/* Test 6: Bounded Response Formatting and ESP32 OPEN Command Generation */
static void test_open_command_generation_and_bounds(void)
{
    printf("  [TEST] Bounded response formatting and ESP32-originated OPEN command formatting...\n");

    nexus_envelope_t open_env;
    nexus_envelope_init(&open_env);

    /* Format OPEN DASHBOARD */
    bool ok = nexus_command_format_open_request(&open_env, 101, 12345, NEXUS_CMD_OPEN_DASHBOARD);
    TEST_ASSERT(ok, "Format OPEN DASHBOARD");
    TEST_ASSERT(open_env.length < NEXUS_ENVELOPE_MAX_LEN, "Bounded length");
    TEST_ASSERT(strstr((char *)open_env.buffer, "\"verb\":\"OPEN\"") != NULL, "Verb OPEN");
    TEST_ASSERT(strstr((char *)open_env.buffer, "\"noun\":\"DASHBOARD\"") != NULL, "Noun DASHBOARD");
    TEST_ASSERT(strstr((char *)open_env.buffer, "\"cmd_id\":7681") != NULL, "Cmd ID 7681 (0x1E01)");

    /* Format OPEN AI */
    ok = nexus_command_format_open_request(&open_env, 102, 12346, NEXUS_CMD_OPEN_AI);
    TEST_ASSERT(ok, "Format OPEN AI");
    TEST_ASSERT(strstr((char *)open_env.buffer, "\"noun\":\"AI\"") != NULL, "Noun AI");
    TEST_ASSERT(strstr((char *)open_env.buffer, "\"cmd_id\":7683") != NULL, "Cmd ID 7683 (0x1E03)");

    /* Reject non-OPEN command as open request */
    ok = nexus_command_format_open_request(&open_env, 103, 12347, NEXUS_CMD_GET_STATUS);
    TEST_ASSERT(!ok, "Non-OPEN command rejected by format_open_request");

    printf("  [PASS] OPEN command formatting and length bounds verified\n");
}

/* Test 7: Connection Manager End-to-End RX Callback Integration */
static void test_connection_manager_rx_callback_integration(void)
{
    printf("  [TEST] Connection Manager RX callback integration and auto-response...\n");

    nexus_conn_mgr_t mgr;
    nexus_conn_mgr_config_t cfg = {
        .default_route = NEXUS_ROUTE_AUTO
    };
    bool ok = nexus_conn_mgr_init(&mgr, &cfg);
    TEST_ASSERT(ok, "Connection manager init");
    ok = nexus_conn_mgr_start(&mgr);
    TEST_ASSERT(ok, "Connection manager start");
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);

    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    nexus_command_dispatcher_t disp;
    ok = nexus_command_dispatcher_init(&disp, &exec, NULL, &mgr);
    TEST_ASSERT(ok, "Dispatcher init");

    /* Register dispatcher callback with connection manager */
    nexus_conn_mgr_set_rx_callback(&mgr, nexus_command_dispatcher_rx_callback, &disp);

    /* Simulate inbound command via serial transport */
    const char *cmd_serial = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":101,\"type\":\"cmd\",\"verb\":\"NOP\",\"noun\":\"NONE\"}\n";
    ok = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)cmd_serial, strlen(cmd_serial));
    TEST_ASSERT(ok, "Process RX serial command");

    /* Verify response envelope was enqueued to connection manager TX queue */
    TEST_ASSERT(mgr.tx_queue.count == 1, "Response envelope enqueued to TX queue");
    const nexus_tx_queue_item_t *item = &mgr.tx_queue.items[mgr.tx_queue.tail];
    TEST_ASSERT(item->envelope.type == NEXUS_MSG_TYPE_RESPONSE, "Response type");
    TEST_ASSERT(item->route == NEXUS_ROUTE_SERIAL_ONLY, "Response routed back to SERIAL_ONLY");
    TEST_ASSERT(strstr((char *)item->envelope.buffer, "\"status\":\"completed\"") != NULL, "Status completed");

    /* Simulate inbound command via MQTT transport */
    const char *cmd_mqtt = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":202,\"type\":\"cmd\",\"verb\":\"GET\",\"noun\":\"STATUS\"}\n";
    ok = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, (const uint8_t *)cmd_mqtt, strlen(cmd_mqtt));
    TEST_ASSERT(ok, "Process RX MQTT command");

    TEST_ASSERT(mgr.tx_queue.count == 2, "Second response envelope enqueued");

    /* Drain TX queue */
    nexus_conn_mgr_process_tx_queue(&mgr);
    TEST_ASSERT(mgr.tx_queue.count == 0, "TX queue drained");

    /* Verify telemetry does not trigger command callback */
    const char *telem = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":303,\"type\":\"telem\",\"uptime\":12000,\"ldr\":100,\"x0\":200}\n";
    ok = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, (const uint8_t *)telem, strlen(telem));
    TEST_ASSERT(ok, "Telemetry processed by connection manager");
    TEST_ASSERT(mgr.tx_queue.count == 0, "Telemetry does not trigger response enqueue");

    /* Stop connection manager */
    nexus_conn_mgr_stop(&mgr);

    printf("  [PASS] Connection manager RX callback integration verified\n");
}

int main(void)
{
    printf("====================================================\n");
    printf("NEXUS Milestone 8 Host Unit Test Suite\n");
    printf("====================================================\n");

    test_registry_integrity();
    test_supported_commands_execution();
    test_display_and_diagnostics_handlers();
    test_unsupported_and_deferred_commands();
    test_capabilities_and_fault_reset();
    test_malformed_and_invalid_inputs();
    test_open_command_generation_and_bounds();
    test_connection_manager_rx_callback_integration();

    printf("====================================================\n");
    printf("ALL MILESTONE 8 HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("====================================================\n");
    return 0;
}
