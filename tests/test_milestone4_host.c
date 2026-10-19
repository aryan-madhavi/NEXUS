#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdatomic.h>

#include "transports/nexus_transport.h"
#include "transports/nexus_envelope.h"
#include "transports/nexus_serial_transport.h"
#include "transports/nexus_wifi_mqtt_transport.h"
#include "transports/nexus_connection_manager.h"
#include "executive/nexus_executive.h"
#include "sensors/nexus_sensor_registry.h"

static void test_envelope_serialization_and_framing(void)
{
    printf("  [TEST] Envelope serialization, framing, and header parsing...\n");

    nexus_envelope_t env;
    nexus_envelope_init(&env);

    /* 1. Heartbeat envelope */
    bool ok = nexus_envelope_format_heartbeat(&env, 101, 12345, 245000, 120);
    assert(ok);
    assert(env.length > 0);
    assert(env.length < NEXUS_ENVELOPE_MAX_LEN);
    assert(env.buffer[env.length - 1] == '\n'); /* Newline-delimited framing */

    uint32_t ver = 0, seq = 0;
    char type_str[16] = {0};
    char dev_str[NEXUS_DEV_ID_MAX_LEN] = {0};

    ok = nexus_envelope_parse_header_ext(env.buffer, env.length, &ver, dev_str, sizeof(dev_str), &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(ver == NEXUS_PROTOCOL_VERSION);
    assert(seq == 101);
    assert(strcmp(type_str, "hb") == 0);
    assert(strcmp(dev_str, NEXUS_DEVICE_ID_DEFAULT) == 0);

    /* 2. Telemetry envelope (with valid DHT11) */
    ok = nexus_envelope_format_telemetry(&env, 102, 12350, 2048, 1024, 25, 60, true);
    assert(ok);
    assert(env.buffer[env.length - 1] == '\n');
    assert(strstr((char *)env.buffer, "\"temp\":25") != NULL);
    assert(strstr((char *)env.buffer, "\"hum\":60") != NULL);
    assert(strstr((char *)env.buffer, "\"dht_valid\":true") != NULL);
    ok = nexus_envelope_parse_header(env.buffer, env.length, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(seq == 102);
    assert(strcmp(type_str, "telem") == 0);

    /* 2b. Telemetry envelope (uninitialized/invalid DHT11: temp/hum omitted, dht_valid:false) */
    ok = nexus_envelope_format_telemetry(&env, 105, 12355, 2048, 1024, 0, 0, false);
    assert(ok);
    assert(env.buffer[env.length - 1] == '\n');
    assert(strstr((char *)env.buffer, "\"temp\"") == NULL);
    assert(strstr((char *)env.buffer, "\"hum\"") == NULL);
    assert(strstr((char *)env.buffer, "\"dht_valid\":false") != NULL);
    ok = nexus_envelope_parse_header(env.buffer, env.length, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(seq == 105);
    assert(strcmp(type_str, "telem") == 0);

    /* 3. Status envelope */
    ok = nexus_envelope_format_status(&env, 103, 12360, 50, 48, 2, 1200, 450);
    assert(ok);
    assert(env.buffer[env.length - 1] == '\n');
    ok = nexus_envelope_parse_header(env.buffer, env.length, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(seq == 103);
    assert(strcmp(type_str, "status") == 0);

    /* 4. Event envelope */
    ok = nexus_envelope_format_event(&env, 104, 12370, 1, 2, 42, 999);
    assert(ok);
    assert(env.buffer[env.length - 1] == '\n');
    ok = nexus_envelope_parse_header(env.buffer, env.length, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(seq == 104);
    assert(strcmp(type_str, "event") == 0);

    printf("  [PASS] Envelope serialization, framing, and header parsing\n");
}

static void test_f01_bounded_envelope_parser_regression(void)
{
    printf("  [TEST] F-01: Bounded envelope parser security & boundary regression...\n");

    uint32_t ver = 0xAA;
    uint32_t seq = 0xBB;
    char type_str[16] = "initial";
    char dev_str[16] = "initial";

    /* 1. NULL parameter rejection */
    assert(!nexus_envelope_parse_header(NULL, 10, &ver, &seq, type_str, sizeof(type_str)));
    assert(!nexus_envelope_parse_header((const uint8_t *)"{}", 2, NULL, &seq, type_str, sizeof(type_str)));
    assert(!nexus_envelope_parse_header((const uint8_t *)"{}", 2, &ver, NULL, type_str, sizeof(type_str)));
    assert(!nexus_envelope_parse_header((const uint8_t *)"{}", 0, &ver, &seq, type_str, sizeof(type_str)));

    /* 2. Non-NUL-terminated buffer without trailing NUL in memory */
    uint8_t unterminated_buf[64];
    memset(unterminated_buf, 'Z', sizeof(unterminated_buf)); /* No NUL anywhere */
    const char *valid_msg = "{\"ver\":1,\"seq\":777,\"type\":\"hb\"}";
    size_t valid_len = strlen(valid_msg);
    memcpy(unterminated_buf, valid_msg, valid_len);
    /* Parse with exact length without NUL terminator */
    ver = 0; seq = 0; memset(type_str, 0, sizeof(type_str));
    bool ok = nexus_envelope_parse_header(unterminated_buf, valid_len, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(ver == 1);
    assert(seq == 777);
    assert(strcmp(type_str, "hb") == 0);

    /* 3. Oversized input rejection: strictly reject len >= NEXUS_ENVELOPE_MAX_LEN (256 bytes) */
    uint8_t oversized_buf[512];
    memset(oversized_buf, ' ', sizeof(oversized_buf));
    oversized_buf[0] = '{';
    oversized_buf[511] = '}';
    assert(!nexus_envelope_parse_header(oversized_buf, 256, &ver, &seq, type_str, sizeof(type_str)));
    assert(!nexus_envelope_parse_header(oversized_buf, 300, &ver, &seq, type_str, sizeof(type_str)));
    assert(!nexus_envelope_parse_header(oversized_buf, 512, &ver, &seq, type_str, sizeof(type_str)));

    /* 4. Maximum permitted envelope size boundary (exactly 255 bytes) */
    char max_valid[NEXUS_ENVELOPE_MAX_LEN];
    /* Construct 255-byte valid JSON envelope */
    int written = snprintf(max_valid, sizeof(max_valid), "{\"ver\":1,\"seq\":999,\"type\":\"hb\",\"pad\":\"");
    assert(written > 0);
    size_t cur = (size_t)written;
    while (cur < 253) {
        max_valid[cur++] = 'A';
    }
    max_valid[253] = '\"';
    max_valid[254] = '}';
    /* Length is exactly 255 bytes (< 256) */
    ver = 0; seq = 0;
    ok = nexus_envelope_parse_header((const uint8_t *)max_valid, 255, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(ver == 1);
    assert(seq == 999);

    /* 5. Output structure preservation on partial parse failure */
    ver = 0x12345678;
    seq = 0x87654321;
    strcpy(type_str, "preserve");
    /* Has valid ver=1, but malformed seq (non-numeric) */
    const char *partial_bad = "{\"ver\":1,\"seq\":INVALID_NUMBER,\"type\":\"hb\"}";
    ok = nexus_envelope_parse_header((const uint8_t *)partial_bad, strlen(partial_bad), &ver, &seq, type_str, sizeof(type_str));
    assert(!ok);
    assert(ver == 0x12345678);  /* Output MUST NOT be partially modified! */
    assert(seq == 0x87654321);
    assert(strcmp(type_str, "preserve") == 0);

    /* 6. Missing fields */
    const char *no_ver = "{\"seq\":10,\"type\":\"hb\"}";
    assert(!nexus_envelope_parse_header((const uint8_t *)no_ver, strlen(no_ver), &ver, &seq, type_str, sizeof(type_str)));
    const char *no_seq = "{\"ver\":1,\"type\":\"hb\"}";
    assert(!nexus_envelope_parse_header((const uint8_t *)no_seq, strlen(no_seq), &ver, &seq, type_str, sizeof(type_str)));
    const char *no_type = "{\"ver\":1,\"seq\":10}";
    assert(!nexus_envelope_parse_header((const uint8_t *)no_type, strlen(no_type), &ver, &seq, type_str, sizeof(type_str)));

    /* 7. Malformed delimiters */
    const char *unclosed_quote = "{\"ver\":1,\"seq\":10,\"type\":\"hb}";
    assert(!nexus_envelope_parse_header((const uint8_t *)unclosed_quote, strlen(unclosed_quote), &ver, &seq, type_str, sizeof(type_str)));
    const char *missing_colon = "{\"ver\" 1,\"seq\":10,\"type\":\"hb\"}";
    assert(!nexus_envelope_parse_header((const uint8_t *)missing_colon, strlen(missing_colon), &ver, &seq, type_str, sizeof(type_str)));

    /* 8. Extended parsing with dev field */
    const char *with_dev = "{\"ver\":1,\"dev\":\"custom_host\",\"seq\":42,\"type\":\"cmd\"}";
    ver = 0; seq = 0; memset(dev_str, 0, sizeof(dev_str)); memset(type_str, 0, sizeof(type_str));
    ok = nexus_envelope_parse_header_ext((const uint8_t *)with_dev, strlen(with_dev), &ver, dev_str, sizeof(dev_str), &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(ver == 1);
    assert(seq == 42);
    assert(strcmp(type_str, "cmd") == 0);
    assert(strcmp(dev_str, "custom_host") == 0);

    printf("  [PASS] F-01: Bounded envelope parser security & boundary regression\n");
}

static void test_tx_queue_saturation_and_overflow_rejection(void)
{
    printf("  [TEST] Bounded TX queue saturation, overflow rejection, and high-water mark...\n");

    nexus_conn_mgr_t mgr;
    nexus_conn_mgr_config_t cfg = {
        .default_route = NEXUS_ROUTE_AUTO
    };
    assert(nexus_conn_mgr_init(&mgr, &cfg));
    assert(nexus_conn_mgr_start(&mgr));

    nexus_envelope_t env;
    nexus_envelope_init(&env);
    assert(nexus_envelope_format_heartbeat(&env, 1, 100, 200000, 1));

    /* Fill queue exactly to capacity (16 slots) */
    for (uint16_t i = 0; i < NEXUS_CONN_TX_QUEUE_CAPACITY; i++) {
        assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
        assert(mgr.tx_queue.count == i + 1U);
        assert(mgr.tx_queue.high_water_mark == i + 1U);
    }

    assert(mgr.tx_queue.count == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(mgr.tx_queue.high_water_mark == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(mgr.tx_queue.total_dropped == 0);

    /* Overflow attempt 1: must reject immediately without altering existing items */
    bool enqueued = nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO);
    assert(!enqueued);
    assert(mgr.tx_queue.count == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(mgr.tx_queue.total_dropped == 1);

    /* Overflow attempt 2 */
    enqueued = nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO);
    assert(!enqueued);
    assert(mgr.tx_queue.total_dropped == 2);

    /* Process all 16 queued items */
    size_t processed = nexus_conn_mgr_process_tx_queue(&mgr);
    assert(processed == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(mgr.tx_queue.count == 0);
    assert(mgr.tx_queue.total_dispatched == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(mgr.tx_queue.high_water_mark == NEXUS_CONN_TX_QUEUE_CAPACITY);

    /* Enqueue now succeeds after drain */
    assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    assert(mgr.tx_queue.count == 1);

    nexus_conn_mgr_stop(&mgr);
    printf("  [PASS] Bounded TX queue saturation, overflow rejection, and high-water mark\n");
}

static void test_transport_state_transitions_and_diagnostics(void)
{
    printf("  [TEST] Transport state transitions and observable diagnostics...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));

    /* Before start: both DISCONNECTED */
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_DISCONNECTED);
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_MQTT) == NEXUS_CONN_STATE_DISCONNECTED);
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_DISCONNECTED);

    /* Start manager: Serial connects; MQTT mock starts disconnected/connecting */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_CONNECTED);

    /* Mock MQTT connect */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_MQTT) == NEXUS_CONN_STATE_CONNECTED);
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_CONNECTED);

    /* Verify diagnostics snapshot */
    nexus_conn_mgr_stats_t stats;
    nexus_conn_mgr_get_stats(&mgr, &stats);
    assert(stats.overall_state == NEXUS_CONN_STATE_CONNECTED);
    assert(stats.serial_stats.connect_count >= 1);
    assert(stats.mqtt_stats.connect_count >= 1);

    /* Mock MQTT failure / degradation */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, false);
    mgr.mqtt_transport.state = NEXUS_CONN_STATE_DEGRADED;
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_DEGRADED);

    /* Stop manager */
    assert(nexus_conn_mgr_stop(&mgr));
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_DISCONNECTED);

    printf("  [PASS] Transport state transitions and observable diagnostics\n");
}

static void test_routing_policies(void)
{
    printf("  [TEST] Routing policies (AUTO, SERIAL_ONLY, MQTT_ONLY, BROADCAST)...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(nexus_conn_mgr_start(&mgr));

    nexus_serial_transport_mock_reset(&mgr.serial_transport);
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);

    uint8_t rx_buf[512];

    /* 1. NEXUS_ROUTE_AUTO with MQTT connected -> sends to MQTT */
    nexus_conn_mgr_send_heartbeat(&mgr, 1000, 200000, 10, NEXUS_ROUTE_AUTO);
    nexus_conn_mgr_process_tx_queue(&mgr);

    size_t mqtt_tx = nexus_wifi_mqtt_mock_get_tx(&mgr.mqtt_transport, rx_buf, sizeof(rx_buf));
    size_t serial_tx = nexus_serial_transport_mock_get_tx(&mgr.serial_transport, rx_buf, sizeof(rx_buf));
    assert(mqtt_tx > 0);
    assert(serial_tx == 0); /* Serial untouched */

    /* 2. Disconnect MQTT -> NEXUS_ROUTE_AUTO falls back transparently to Serial! */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, false);
    nexus_serial_transport_mock_reset(&mgr.serial_transport);

    nexus_conn_mgr_send_heartbeat(&mgr, 2000, 200000, 20, NEXUS_ROUTE_AUTO);
    nexus_conn_mgr_process_tx_queue(&mgr);

    serial_tx = nexus_serial_transport_mock_get_tx(&mgr.serial_transport, rx_buf, sizeof(rx_buf));
    assert(serial_tx > 0); /* Successfully routed to Serial */

    /* 3. NEXUS_ROUTE_SERIAL_ONLY -> Always routes to Serial even when MQTT is online */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);
    nexus_serial_transport_mock_reset(&mgr.serial_transport);

    nexus_conn_mgr_send_heartbeat(&mgr, 3000, 200000, 30, NEXUS_ROUTE_SERIAL_ONLY);
    nexus_conn_mgr_process_tx_queue(&mgr);

    serial_tx = nexus_serial_transport_mock_get_tx(&mgr.serial_transport, rx_buf, sizeof(rx_buf));
    assert(serial_tx > 0);

    /* 4. NEXUS_ROUTE_MQTT_ONLY when MQTT disconnected -> Fails gracefully, counts failure */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, false);
    uint32_t prev_failed = mgr.tx_queue.total_failed;
    nexus_conn_mgr_send_heartbeat(&mgr, 4000, 200000, 40, NEXUS_ROUTE_MQTT_ONLY);
    nexus_conn_mgr_process_tx_queue(&mgr);
    assert(mgr.tx_queue.total_failed == prev_failed + 1);

    /* 5. NEXUS_ROUTE_BROADCAST -> Transmits to both Serial and MQTT */
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);
    nexus_serial_transport_mock_reset(&mgr.serial_transport);

    nexus_conn_mgr_send_heartbeat(&mgr, 5000, 200000, 50, NEXUS_ROUTE_BROADCAST);
    nexus_conn_mgr_process_tx_queue(&mgr);

    serial_tx = nexus_serial_transport_mock_get_tx(&mgr.serial_transport, rx_buf, sizeof(rx_buf));
    assert(serial_tx > 0);

    nexus_conn_mgr_stop(&mgr);
    printf("  [PASS] Routing policies (AUTO, SERIAL_ONLY, MQTT_ONLY, BROADCAST)\n");
}

static uint32_t s_rx_callback_invocations = 0;
static uint32_t s_last_received_seq = 0;
static nexus_transport_type_t s_last_received_source = NEXUS_TRANSPORT_TYPE_SERIAL;
static nexus_msg_type_t s_last_received_type = NEXUS_MSG_TYPE_HEARTBEAT;

static void mock_rx_callback(void *user_ctx, nexus_transport_type_t source, const nexus_envelope_t *env)
{
    (void)user_ctx;
    s_rx_callback_invocations++;
    s_last_received_source = source;
    s_last_received_seq = env->seq;
    s_last_received_type = env->type;
}

static void test_f02_composite_deduplication_and_isolation(void)
{
    printf("  [TEST] F-02: Deduplication with composite identity (source, dev, seq)...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(nexus_conn_mgr_start(&mgr));

    nexus_conn_mgr_set_rx_callback(&mgr, mock_rx_callback, NULL);
    s_rx_callback_invocations = 0;
    s_last_received_seq = 0;

    /* Build command envelope with seq = 501 */
    nexus_envelope_t env;
    nexus_envelope_init(&env);
    env.seq = 501;
    env.type = NEXUS_MSG_TYPE_COMMAND;
    const char *cmd_501 = "{\"ver\":1,\"dev\":\"nexus_esp32\",\"seq\":501,\"type\":\"cmd\"}\n";
    memcpy(env.buffer, cmd_501, strlen(cmd_501) + 1);
    env.length = (uint16_t)strlen(cmd_501);

    /* 1. Packet arrives over Serial (source = SERIAL, seq = 501) -> Processed */
    bool processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, env.buffer, env.length);
    assert(processed);
    assert(s_rx_callback_invocations == 1);
    assert(s_last_received_source == NEXUS_TRANSPORT_TYPE_SERIAL);
    assert(s_last_received_seq == 501);
    assert(mgr.dedup.duplicates_detected == 0);

    /* 2. Genuine duplicate on the SAME transport (SERIAL, seq = 501) -> SUPPRESSED */
    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, env.buffer, env.length);
    assert(!processed); /* Suppressed as duplicate */
    assert(s_rx_callback_invocations == 1);
    assert(mgr.dedup.duplicates_detected == 1);

    /* 3. Packet with IDENTICAL sequence number (501) arrives from a DIFFERENT source (MQTT)
     * -> Must be ACCEPTED because it originates from a different transport source! (F-02 fix) */
    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, env.buffer, env.length);
    assert(processed); /* ACCEPTED! Distinct source */
    assert(s_rx_callback_invocations == 2);
    assert(s_last_received_source == NEXUS_TRANSPORT_TYPE_MQTT);
    assert(s_last_received_seq == 501);
    assert(mgr.dedup.duplicates_detected == 1); /* Duplicate count unchanged */

    /* 4. Genuine duplicate on MQTT (MQTT, seq = 501) -> SUPPRESSED */
    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, env.buffer, env.length);
    assert(!processed); /* Suppressed */
    assert(s_rx_callback_invocations == 2);
    assert(mgr.dedup.duplicates_detected == 2);

    /* 5. Distinct device IDs on the same transport (e.g., ground_station vs operator)
     * using the same sequence number -> both accepted */
    const char *cmd_a = "{\"ver\":1,\"dev\":\"client_A\",\"seq\":600,\"type\":\"cmd\"}\n";
    const char *cmd_b = "{\"ver\":1,\"dev\":\"client_B\",\"seq\":600,\"type\":\"cmd\"}\n";

    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, (const uint8_t *)cmd_a, strlen(cmd_a));
    assert(processed);
    assert(s_rx_callback_invocations == 3);

    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, (const uint8_t *)cmd_b, strlen(cmd_b));
    assert(processed); /* Accepted because client_B != client_A */
    assert(s_rx_callback_invocations == 4);

    /* Duplicate client_A with seq 600 -> suppressed */
    processed = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_MQTT, (const uint8_t *)cmd_a, strlen(cmd_a));
    assert(!processed);
    assert(s_rx_callback_invocations == 4);

    /* 6. Sliding window wrap and eviction across 35 entries */
    for (uint32_t s = 1000; s < 1035; s++) {
        nexus_conn_mgr_record_seq(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", s);
    }
    assert(mgr.dedup.count == NEXUS_CONN_DEDUP_WINDOW); /* Clamped to 32 */

    /* Most recent (1034) is present in window */
    assert(nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1034));
    /* Oldest (1000, 1001, 1002) dropped off the 32-entry sliding window */
    assert(!nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1000));
    assert(!nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1001));
    assert(!nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1002));

    /* 7. Sequence restart / reset handling */
    assert(nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1034));
    nexus_conn_mgr_reset_dedup(&mgr);
    assert(mgr.dedup.count == 0);
    assert(!nexus_conn_mgr_is_duplicate(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL, "test", 1034));

    nexus_conn_mgr_stop(&mgr);
    printf("  [PASS] F-02: Deduplication with composite identity (source, dev, seq)\n");
}

static void test_f04_reconnect_backoff_calculation(void)
{
    printf("  [TEST] F-04: Wi-Fi reconnect backoff progression & ceiling clamp...\n");

    uint32_t base_ms = 1000;
    uint32_t max_ms = 60000;

    /* Progression: 1000 -> 2000 -> 4000 -> 8000 -> 16000 -> 32000 -> 60000 (clamped) -> 60000 */
    uint32_t b = base_ms;
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 2000);
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 4000);
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 8000);
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 16000);
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 32000);
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 60000); /* Clamped to max_ms */
    b = nexus_wifi_mqtt_compute_next_backoff(b, max_ms);
    assert(b == 60000); /* Stays clamped at max_ms */

    /* Zero input handling */
    assert(nexus_wifi_mqtt_compute_next_backoff(0, max_ms) == 1000);

    /* Overflow prevention for near-UINT32_MAX values */
    assert(nexus_wifi_mqtt_compute_next_backoff(0x80000000U, max_ms) == max_ms);
    assert(nexus_wifi_mqtt_compute_next_backoff(0xFFFFFFFFU, max_ms) == max_ms);

    printf("  [PASS] F-04: Wi-Fi reconnect backoff progression & ceiling clamp\n");
}

static void test_f05_f06_unconfigured_defaults_and_lifecycle(void)
{
    printf("  [TEST] F-05 & F-06: Unconfigured defaults and safe stop lifecycle...\n");

    /* Default configuration with empty SSID must remain in DISCONNECTED cleanly */
    nexus_conn_mgr_t mgr;
    nexus_conn_mgr_config_t default_cfg = {
        .default_route = NEXUS_ROUTE_AUTO,
        .serial_cfg = { .baud_rate = 115200, .uart_port = 0 },
        .wifi_mqtt_cfg = {
            .ssid = "", /* Empty SSID by default */
            .password = "",
            .broker_uri = "mqtt://localhost:1883",
            .client_id = "nexus_esp32",
            .topic_prefix = "nexus/nexus_esp32",
            .username = "",
            .mqtt_password = "",
            .reconnect_base_ms = 1000,
            .reconnect_max_ms = 60000
        }
    };

    assert(nexus_conn_mgr_init(&mgr, &default_cfg));
    assert(!nexus_conn_mgr_is_running(&mgr));

    /* 1. Initial start */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 2. Duplicate start must be safe and idempotent (no task duplication) */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    /* Serial is connected; MQTT is safely disconnected / idle */
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);

    /* Enqueue and process works exclusively via serial */
    nexus_envelope_t env;
    assert(nexus_envelope_format_heartbeat(&env, 1, 100, 200000, 1));
    assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    assert(nexus_conn_mgr_process_tx_queue(&mgr) == 1);

    /* 3. Self-stop rejection: calling stop from within worker context must be rejected */
    mgr.mock_in_worker_context = true;
    assert(!nexus_conn_mgr_stop(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);
    mgr.mock_in_worker_context = false;

    /* 4. Stop timeout and safe retry: timeout must preserve handle and allow retry */
    mgr.mock_task_exit_timeout = true;
    assert(!nexus_conn_mgr_stop(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);

    /* 4b. When worker is not running but previous task is still active/terminating, start must return false */
    assert(!nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);

    /* Retry stop after timeout cleared: must succeed and halt transports */
    mgr.mock_task_exit_timeout = false;
    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_DISCONNECTED);

    /* 5. Repeated stop must be idempotent and safe */
    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));

    /* 6. Startup rollback on worker task creation failure */
    mgr.mock_task_create_fail = true;
    assert(!nexus_conn_mgr_start(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_DISCONNECTED);
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_MQTT) == NEXUS_CONN_STATE_DISCONNECTED);
    mgr.mock_task_create_fail = false;

    /* 7. Clean restart after rollback: must successfully start and process */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 8. Queue shutdown behavior: process_tx_queue breaks early when stopped */
    assert(nexus_envelope_format_heartbeat(&env, 2, 200, 195000, 2));
    assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    assert(nexus_envelope_format_heartbeat(&env, 3, 300, 190000, 3));
    assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));

    /* Stop manager while items are queued */
    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));

    /* Process while stopped must yield 0 and break early */
    assert(nexus_conn_mgr_process_tx_queue(&mgr) == 0);

    /* Restart manager: now items can be drained */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));
    assert(nexus_conn_mgr_process_tx_queue(&mgr) == 2);

    /* 9. Final clean stop */
    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));

    printf("  [PASS] F-05 & F-06: Unconfigured defaults, safe stop lifecycle, self-stop rejection, and rollback\n");
}

static void test_mqtt_auth_configuration_and_rejection_of_missing_credentials(void)
{
    printf("  [TEST] MQTT authentication configuration and explicit rejection of missing credentials...\n");

    nexus_transport_t transport;

    /* Case 1: SSID configured, but empty username and empty password -> MUST FAIL and reject anonymous fallback */
    nexus_wifi_mqtt_config_t cfg_missing_all = {
        .ssid = "TestWiFi",
        .password = "wifipass",
        .broker_uri = "mqtt://127.0.0.1:1883",
        .client_id = "nexus_esp32",
        .topic_prefix = "nexus/nexus_esp32",
        .username = "",
        .mqtt_password = "",
        .reconnect_base_ms = 1000,
        .reconnect_max_ms = 60000
    };
    bool init_ok = nexus_wifi_mqtt_transport_init(&transport, &cfg_missing_all);
    assert(!init_ok);
    assert(transport.state == NEXUS_CONN_STATE_FAILED);

    /* Connection manager init must also reject invalid/anonymous Wi-Fi configuration */
    nexus_conn_mgr_t mgr;
    nexus_conn_mgr_config_t conn_cfg_missing = {
        .default_route = NEXUS_ROUTE_AUTO,
        .serial_cfg = { .baud_rate = 115200, .uart_port = 0 },
        .wifi_mqtt_cfg = cfg_missing_all
    };
    assert(!nexus_conn_mgr_init(&mgr, &conn_cfg_missing));

    /* Case 2: SSID configured, valid username, but empty password -> MUST FAIL */
    nexus_wifi_mqtt_config_t cfg_missing_pass = cfg_missing_all;
    strncpy(cfg_missing_pass.username, "nexus_device", sizeof(cfg_missing_pass.username) - 1);
    cfg_missing_pass.mqtt_password[0] = '\0';
    init_ok = nexus_wifi_mqtt_transport_init(&transport, &cfg_missing_pass);
    assert(!init_ok);
    assert(transport.state == NEXUS_CONN_STATE_FAILED);

    /* Case 3: SSID configured, empty username, non-empty password -> MUST FAIL */
    nexus_wifi_mqtt_config_t cfg_missing_user = cfg_missing_all;
    cfg_missing_user.username[0] = '\0';
    strncpy(cfg_missing_user.mqtt_password, "some_pass", sizeof(cfg_missing_user.mqtt_password) - 1);
    init_ok = nexus_wifi_mqtt_transport_init(&transport, &cfg_missing_user);
    assert(!init_ok);
    assert(transport.state == NEXUS_CONN_STATE_FAILED);

    /* Case 4: SSID configured with valid username and password -> MUST SUCCEED in DISCONNECTED state */
    nexus_wifi_mqtt_config_t cfg_valid = cfg_missing_all;
    strncpy(cfg_valid.username, "nexus_device", sizeof(cfg_valid.username) - 1);
    strncpy(cfg_valid.mqtt_password, "test_pass_123", sizeof(cfg_valid.mqtt_password) - 1);
    init_ok = nexus_wifi_mqtt_transport_init(&transport, &cfg_valid);
    assert(init_ok);
    assert(transport.state == NEXUS_CONN_STATE_DISCONNECTED);

    /* Case 5: SSID empty (unconfigured) -> MUST SUCCEED and remain idle in DISCONNECTED state */
    nexus_wifi_mqtt_config_t cfg_unconfigured = cfg_missing_all;
    cfg_unconfigured.ssid[0] = '\0';
    init_ok = nexus_wifi_mqtt_transport_init(&transport, &cfg_unconfigured);
    assert(init_ok);
    assert(transport.state == NEXUS_CONN_STATE_DISCONNECTED);

    /* Verify conn_mgr works in unconfigured Wi-Fi mode while preserving Serial */
    nexus_conn_mgr_config_t conn_cfg_unconfigured = {
        .default_route = NEXUS_ROUTE_AUTO,
        .serial_cfg = { .baud_rate = 115200, .uart_port = 0 },
        .wifi_mqtt_cfg = cfg_unconfigured
    };
    assert(nexus_conn_mgr_init(&mgr, &conn_cfg_unconfigured));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_DISCONNECTED);
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_MQTT) == NEXUS_CONN_STATE_DISCONNECTED);
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_get_transport_state(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL) == NEXUS_CONN_STATE_CONNECTED);
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_CONNECTED);
    assert(nexus_conn_mgr_stop(&mgr));
    assert(nexus_conn_mgr_get_state(&mgr) == NEXUS_CONN_STATE_DISCONNECTED);

    printf("  [PASS] MQTT authentication configuration and explicit rejection of missing credentials\n");
}

static void test_start_rejected_when_worker_terminating(void)
{
    printf("  [TEST] Start rejection when previous worker task is terminating...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(!nexus_conn_mgr_is_running(&mgr));

    /* 1. Initial start succeeds */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 2. Idempotent start when genuinely running returns true */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 3. Simulate stop timeout: worker requested to stop (running=false), but task active */
    mgr.mock_task_exit_timeout = true;
    assert(!nexus_conn_mgr_stop(&mgr));

    /* Verification of state: running is false, but task handle/mock active is true */
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 4. start() must return false without creating a worker or restarting transports */
    assert(!nexus_conn_mgr_start(&mgr));
    assert(mgr.mock_task_active);
    assert(nexus_conn_mgr_is_running(&mgr));

    /* 5. Retry stop: successfully terminates worker */
    mgr.mock_task_exit_timeout = false;
    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));
    assert(!mgr.mock_task_active);

    /* 6. Clean start after complete worker exit succeeds */
    assert(nexus_conn_mgr_start(&mgr));
    assert(nexus_conn_mgr_is_running(&mgr));

    assert(nexus_conn_mgr_stop(&mgr));
    assert(!nexus_conn_mgr_is_running(&mgr));
    printf("  [PASS] Start rejection when previous worker task is terminating\n");
}

static void test_executive_timing_isolation(void)
{
    printf("  [TEST] Executive timing isolation and non-blocking enqueue...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(nexus_conn_mgr_start(&mgr));

    nexus_envelope_t env;
    assert(nexus_envelope_format_heartbeat(&env, 1, 100, 200000, 1));

    /* Measure duration of 100 back-to-back enqueue and drain operations */
    struct timespec ts_start, ts_end;
    clock_gettime(CLOCK_MONOTONIC, &ts_start);

    for (int i = 0; i < 100; i++) {
        bool ok = nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO);
        assert(ok);
        nexus_conn_mgr_process_tx_queue(&mgr);
    }

    clock_gettime(CLOCK_MONOTONIC, &ts_end);
    int64_t total_ns = ((int64_t)(ts_end.tv_sec - ts_start.tv_sec) * 1000000000LL) + (ts_end.tv_nsec - ts_start.tv_nsec);
    int64_t per_op_ns = total_ns / 100LL;

    /* Verify each operation takes < 50 microseconds on host */
    assert(per_op_ns < 50000LL);

    /* Invalid parameters reject safely without fault */
    assert(!nexus_conn_mgr_enqueue(NULL, &env, NEXUS_ROUTE_AUTO));
    assert(!nexus_conn_mgr_enqueue(&mgr, NULL, NEXUS_ROUTE_AUTO));

    env.length = 0;
    assert(!nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));

    nexus_conn_mgr_stop(&mgr);
    printf("  [PASS] Executive timing isolation and non-blocking enqueue (avg %" PRId64 " ns/op)\n", per_op_ns);
}

static nexus_conn_mgr_t s_integ_conn_mgr;

static bool job_integ_heartbeat(void *ctx)
{
    (void)ctx;
    return nexus_conn_mgr_send_heartbeat(&s_integ_conn_mgr, 1000, 200000, 1, NEXUS_ROUTE_AUTO);
}

static bool job_integ_metrics(void *ctx)
{
    nexus_executive_t *exec = (nexus_executive_t *)ctx;
    return nexus_conn_mgr_send_status(&s_integ_conn_mgr, 1000, exec->stats.jobs_dispatched,
                                      exec->stats.jobs_completed, exec->stats.jobs_failed,
                                      exec->stats.max_dispatch_latency_us, exec->stats.max_job_duration_us,
                                      NEXUS_ROUTE_AUTO);
}

static bool job_integ_telemetry(void *ctx)
{
    (void)ctx;
    return nexus_conn_mgr_send_telemetry(&s_integ_conn_mgr, 1000, 1500, 800, 26, 55, true, NEXUS_ROUTE_AUTO);
}

static void test_executive_and_sensors_integration(void)
{
    printf("  [TEST] End-to-end integration: Executive jobs enqueuing to Connection Manager...\n");

    /* 1. Initialize Connection Manager */
    assert(nexus_conn_mgr_init(&s_integ_conn_mgr, NULL));
    assert(nexus_conn_mgr_start(&s_integ_conn_mgr));

    /* 2. Initialize Executive */
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    /* Register heartbeat (Priority Class 0, period 1000, deadline 20) */
    uint16_t hb_id = nexus_executive_register_job(&exec, "hb", NEXUS_PRIORITY_CLASS_0,
                                                   job_integ_heartbeat, NULL, 1000, 20);
    assert(hb_id > 0);

    /* Register telemetry (Priority Class 2, period 2000, deadline 20) */
    uint16_t telem_id = nexus_executive_register_job(&exec, "telem", NEXUS_PRIORITY_CLASS_2,
                                                      job_integ_telemetry, NULL, 2000, 20);
    assert(telem_id > 0);

    /* Register metrics (Priority Class 2, period 5000, deadline 50) */
    uint16_t metrics_id = nexus_executive_register_job(&exec, "metrics", NEXUS_PRIORITY_CLASS_2,
                                                        job_integ_metrics, &exec, 5000, 50);
    assert(metrics_id > 0);

    /* 3. Run executive ticks across 6000 ms */
    for (int64_t t = 100000LL; t <= 6000000LL; t += 100000LL) {
        nexus_executive_tick(&exec, t);
        /* In background (simulating worker task), process queue */
        nexus_conn_mgr_process_tx_queue(&s_integ_conn_mgr);
    }

    /* Verify zero false deadline misses in executive */
    assert(exec.stats.deadline_misses == 0);
    assert(exec.stats.jobs_failed == 0);
    assert(exec.stats.jobs_completed > 0);

    /* Verify envelopes were generated and dispatched through connection manager */
    nexus_conn_mgr_stats_t cstats;
    nexus_conn_mgr_get_stats(&s_integ_conn_mgr, &cstats);
    assert(cstats.tx_enqueued > 0);
    assert(cstats.tx_dispatched == cstats.tx_enqueued);
    assert(cstats.tx_dropped == 0);
    assert(cstats.tx_failed == 0);

    nexus_conn_mgr_stop(&s_integ_conn_mgr);
    printf("  [PASS] End-to-end integration: Executive jobs enqueuing to Connection Manager\n");
}

static void test_mqtt_inbound_rx_and_fragmentation(void)
{
    printf("  [TEST] MQTT Inbound Receive Path: validation, fragmentation, and deduplication...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(nexus_conn_mgr_start(&mgr));

    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);
    nexus_conn_mgr_set_rx_callback(&mgr, mock_rx_callback, NULL);
    s_rx_callback_invocations = 0;
    s_last_received_seq = 0;
    s_last_received_type = NEXUS_MSG_TYPE_HEARTBEAT;

    const char *cmd_topic = "nexus/nexus_esp32/cmd";
    int cmd_topic_len = (int)strlen(cmd_topic);

    /* 1. Complete unfragmented valid inbound envelope */
    const char *msg1 = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":701,\"type\":\"cmd\"}\n";
    int msg1_len = (int)strlen(msg1);

    bool ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                         cmd_topic, cmd_topic_len,
                                                         msg1, msg1_len, 0, msg1_len);
    assert(ok);
    assert(s_rx_callback_invocations == 1);
    assert(s_last_received_source == NEXUS_TRANSPORT_TYPE_MQTT);
    assert(s_last_received_seq == 701);
    assert(s_last_received_type == NEXUS_MSG_TYPE_COMMAND);

    nexus_transport_stats_t mstats;
    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_packets == 1);
    assert(mstats.rx_bytes == (uint32_t)msg1_len);
    assert(mstats.rx_errors == 0);

    /* 2. Valid multi-fragment inbound envelope (65 bytes in 3 chunks: 20, 25, 20) */
    const char *msg2 = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":702,\"type\":\"cmd\",\"val\":99}\n";
    int msg2_len = (int)strlen(msg2);
    assert(msg2_len == 65);

    /* Chunk 1: offset 0, len 20 */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg2, 20, 0, msg2_len);
    assert(ok);
    assert(s_rx_callback_invocations == 1); /* Not yet complete! */

    /* Chunk 2: offset 20, len 25 (topic NULL as per ESP-IDF MQTT spec) */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    NULL, 0,
                                                    msg2 + 20, 25, 20, msg2_len);
    assert(ok);
    assert(s_rx_callback_invocations == 1); /* Still not complete */

    /* Chunk 3: offset 45, len 20 (completes message) */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    NULL, 0,
                                                    msg2 + 45, 20, 45, msg2_len);
    assert(ok);
    assert(s_rx_callback_invocations == 2); /* Dispatched exactly once! */
    assert(s_last_received_source == NEXUS_TRANSPORT_TYPE_MQTT);
    assert(s_last_received_seq == 702);
    assert(s_last_received_type == NEXUS_MSG_TYPE_COMMAND);

    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_packets == 2);
    assert(mstats.rx_bytes == (uint32_t)(msg1_len + msg2_len));
    assert(mstats.rx_errors == 0);

    /* 3. Inbound envelope type enforcement: non-cmd types on /cmd topic rejected */
    const char *bad_type_telem = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":703,\"type\":\"telem\"}\n";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    bad_type_telem, (int)strlen(bad_type_telem),
                                                    0, (int)strlen(bad_type_telem));
    assert(!ok); /* Rejected: telem on /cmd topic disallowed */
    assert(s_rx_callback_invocations == 2);

    const char *bad_type_bogus = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":704,\"type\":\"bogus\"}\n";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    bad_type_bogus, (int)strlen(bad_type_bogus),
                                                    0, (int)strlen(bad_type_bogus));
    assert(!ok); /* Rejected: unrecognized type */
    assert(s_rx_callback_invocations == 2);

    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_errors == 2);

    /* 4. Protocol version enforcement: version != NEXUS_PROTOCOL_VERSION rejected */
    const char *bad_ver_2 = "{\"ver\":2,\"dev\":\"ground_station\",\"seq\":705,\"type\":\"cmd\"}\n";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    bad_ver_2, (int)strlen(bad_ver_2),
                                                    0, (int)strlen(bad_ver_2));
    assert(!ok); /* Rejected: unsupported version 2 */
    assert(s_rx_callback_invocations == 2);

    const char *bad_ver_0 = "{\"ver\":0,\"dev\":\"ground_station\",\"seq\":706,\"type\":\"cmd\"}\n";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    bad_ver_0, (int)strlen(bad_ver_0),
                                                    0, (int)strlen(bad_ver_0));
    assert(!ok); /* Rejected: version 0 invalid */
    assert(s_rx_callback_invocations == 2);

    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_errors == 4);

    /* 5. Malformed JSON and missing required fields */
    /* Missing "ver" */
    const char *malformed_no_ver = "{\"dev\":\"ground_station\",\"seq\":707,\"type\":\"cmd\"}\n";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    malformed_no_ver, (int)strlen(malformed_no_ver),
                                                    0, (int)strlen(malformed_no_ver));
    assert(!ok);
    assert(s_rx_callback_invocations == 2);

    /* Broken syntax */
    const char *malformed_syntax = "{\"ver\":1,\"seq\":708,\"broken";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    malformed_syntax, (int)strlen(malformed_syntax),
                                                    0, (int)strlen(malformed_syntax));
    assert(!ok);
    assert(s_rx_callback_invocations == 2);

    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_errors == 6);

    /* 6. Payload boundary limits: 255 bytes accepted, 256 bytes rejected */
    /* Syntactically valid 255-byte command envelope */
    char valid_255[256];
    int p1 = snprintf(valid_255, sizeof(valid_255), "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":730,\"type\":\"cmd\",\"pad\":\"");
    int pad_len = 255 - p1 - 3;
    memset(valid_255 + p1, 'X', pad_len);
    valid_255[p1 + pad_len] = '\"';
    valid_255[p1 + pad_len + 1] = '}';
    valid_255[p1 + pad_len + 2] = '\n';
    valid_255[255] = '\0';
    assert(strlen(valid_255) == 255);

    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    valid_255, 255, 0, 255);
    assert(ok); /* Accepted: exactly 255 bytes */
    assert(s_rx_callback_invocations == 3);
    assert(s_last_received_seq == 730);
    assert(s_last_received_type == NEXUS_MSG_TYPE_COMMAND);

    /* 256-byte payload (rejection threshold) */
    char invalid_256[257];
    int p2 = snprintf(invalid_256, sizeof(invalid_256), "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":731,\"type\":\"cmd\",\"pad\":\"");
    pad_len = 256 - p2 - 3;
    memset(invalid_256 + p2, 'X', pad_len);
    invalid_256[p2 + pad_len] = '\"';
    invalid_256[p2 + pad_len + 1] = '}';
    invalid_256[p2 + pad_len + 2] = '\n';
    invalid_256[256] = '\0';
    assert(strlen(invalid_256) == 256);

    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    invalid_256, 256, 0, 256);
    assert(!ok); /* Rejected: >= 256 bytes */
    assert(s_rx_callback_invocations == 3);

    /* Oversized (300 bytes) */
    char oversized[300];
    memset(oversized, 'A', sizeof(oversized));
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    oversized, 100, 0, 300);
    assert(!ok); /* Rejected */
    assert(s_rx_callback_invocations == 3);

    mgr.mqtt_transport.ops->get_stats(&mgr.mqtt_transport, &mstats);
    assert(mstats.rx_errors == 8);

    /* 7. Empty payloads and invalid fragment offsets/lengths */
    /* Empty chunk */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg1, 0, 0, msg1_len);
    assert(!ok);
    /* total_len = 0 */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg1, msg1_len, 0, 0);
    assert(!ok);
    /* Negative offset */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg1, msg1_len, -1, msg1_len);
    assert(!ok);
    /* Bounds overflow (offset + len > total) */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg1, 30, 20, 40);
    assert(!ok);

    /* 8. Wrong topic handling */
    const char *wrong_topic = "nexus/nexus_esp32/telemetry";
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    wrong_topic, (int)strlen(wrong_topic),
                                                    msg1, msg1_len, 0, msg1_len);
    assert(!ok); /* Rejected due to unexpected topic */
    assert(s_rx_callback_invocations == 3);

    /* 9. Duplicate inbound messages and source-aware deduplication */
    const char *msg_dup = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":710,\"type\":\"cmd\"}\n";
    int msg_dup_len = (int)strlen(msg_dup);

    /* First arrival over MQTT: accepted */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg_dup, msg_dup_len, 0, msg_dup_len);
    assert(ok);
    assert(s_rx_callback_invocations == 4);
    assert(s_last_received_seq == 710);
    assert(s_last_received_type == NEXUS_MSG_TYPE_COMMAND);
    assert(mgr.dedup.duplicates_detected == 0);

    /* Duplicate arrival over MQTT: suppressed */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg_dup, msg_dup_len, 0, msg_dup_len);
    assert(!ok); /* Rejected as duplicate */
    assert(s_rx_callback_invocations == 4); /* NOT called again */
    assert(mgr.dedup.duplicates_detected == 1);

    /* Same sequence number (710) arriving over SERIAL: accepted (distinct source) */
    bool serial_ok = nexus_conn_mgr_process_rx(&mgr, NEXUS_TRANSPORT_TYPE_SERIAL,
                                               (const uint8_t *)msg_dup, (size_t)msg_dup_len);
    assert(serial_ok);
    assert(s_rx_callback_invocations == 5);
    assert(s_last_received_source == NEXUS_TRANSPORT_TYPE_SERIAL);
    assert(s_last_received_seq == 710);
    assert(s_last_received_type == NEXUS_MSG_TYPE_COMMAND);
    assert(mgr.dedup.duplicates_detected == 1);

    /* 10. Fragment error recovery: gap, overlap, interruption, restart */
    /* 10a. Gap offset rejection */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg2, 20, 0, msg2_len);
    assert(ok);
    /* Send gap offset: expected 20, send 35 */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    NULL, 0,
                                                    msg2 + 20, 20, 35, msg2_len);
    assert(!ok); /* Rejected */

    /* Verify subsequent fresh message succeeds (clean recovery) */
    const char *msg_recovery = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":720,\"type\":\"cmd\"}\n";
    int msg_recovery_len = (int)strlen(msg_recovery);
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg_recovery, msg_recovery_len, 0, msg_recovery_len);
    assert(ok);
    assert(s_rx_callback_invocations == 6);
    assert(s_last_received_seq == 720);

    /* 10b. Overlapping offset rejection */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg2, 20, 0, msg2_len);
    assert(ok);
    /* Send overlapping offset: expected 20, send 15 */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    NULL, 0,
                                                    msg2 + 15, 20, 15, msg2_len);
    assert(!ok); /* Rejected */

    /* Recovery after overlap */
    const char *msg_overlap_rec = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":722,\"type\":\"cmd\"}\n";
    int msg_overlap_rec_len = (int)strlen(msg_overlap_rec);
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg_overlap_rec, msg_overlap_rec_len, 0, msg_overlap_rec_len);
    assert(ok);
    assert(s_rx_callback_invocations == 7);
    assert(s_last_received_seq == 722);

    /* 10c. Interrupted message */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg2, 20, 0, msg2_len);
    assert(ok);
    /* New start fragment interrupts previous assembly */
    const char *msg_interrupted = "{\"ver\":1,\"dev\":\"ground_station\",\"seq\":721,\"type\":\"cmd\"}\n";
    int msg_interrupted_len = (int)strlen(msg_interrupted);
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg_interrupted, msg_interrupted_len, 0, msg_interrupted_len);
    assert(ok);
    assert(s_rx_callback_invocations == 8);
    assert(s_last_received_seq == 721);

    /* 10d. Disconnect/stop reset */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    cmd_topic, cmd_topic_len,
                                                    msg2, 20, 0, msg2_len);
    assert(ok);
    assert(nexus_conn_mgr_stop(&mgr));
    assert(nexus_conn_mgr_start(&mgr));
    nexus_wifi_mqtt_mock_set_connected(&mgr.mqtt_transport, true);

    /* Sending continuation fragment without start after restart must be rejected */
    ok = nexus_wifi_mqtt_transport_process_rx_chunk(&mgr.mqtt_transport,
                                                    NULL, 0,
                                                    msg2 + 20, 25, 20, msg2_len);
    assert(!ok);

    assert(nexus_conn_mgr_stop(&mgr));
    printf("  [PASS] MQTT Inbound Receive Path: validation, fragmentation, and deduplication\n");
}

static void test_telemetry_schema_and_dht_validity(void)
{
    printf("  [TEST] Telemetry schema compatibility: omitted temp/hum vs valid dht11...\n");
    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));

    /* 1. Send telemetry with uninitialized/invalid DHT11 */
    assert(nexus_conn_mgr_send_telemetry(&mgr, 366, 0, 3087, 0, 0, false, NEXUS_ROUTE_SERIAL_ONLY));
    assert(mgr.tx_queue.count == 1);
    nexus_envelope_t *env_invalid = &mgr.tx_queue.items[mgr.tx_queue.tail].envelope;
    assert(env_invalid->type == NEXUS_MSG_TYPE_TELEMETRY);
    assert(strstr((const char *)env_invalid->buffer, "\"dht_valid\":false") != NULL);
    assert(strstr((const char *)env_invalid->buffer, "\"temp\"") == NULL);
    assert(strstr((const char *)env_invalid->buffer, "\"hum\"") == NULL);
    assert(strstr((const char *)env_invalid->buffer, "\"ldr\":0") != NULL);
    assert(strstr((const char *)env_invalid->buffer, "\"x0\":3087") != NULL);

    /* Verify header parser succeeds on this envelope */
    uint32_t ver = 0, seq = 0;
    char type_str[16] = {0};
    assert(nexus_envelope_parse_header(env_invalid->buffer, env_invalid->length, &ver, &seq, type_str, sizeof(type_str)));
    assert(ver == NEXUS_PROTOCOL_VERSION);
    assert(strcmp(type_str, "telem") == 0);

    /* 2. Send telemetry with valid DHT11 */
    assert(nexus_conn_mgr_send_telemetry(&mgr, 2955, 350, 3087, 32, 52, true, NEXUS_ROUTE_SERIAL_ONLY));
    assert(mgr.tx_queue.count == 2);
    uint16_t next_idx = (mgr.tx_queue.tail + 1) % NEXUS_CONN_TX_QUEUE_CAPACITY;
    nexus_envelope_t *env_valid = &mgr.tx_queue.items[next_idx].envelope;
    assert(env_valid->type == NEXUS_MSG_TYPE_TELEMETRY);
    assert(strstr((const char *)env_valid->buffer, "\"dht_valid\":true") != NULL);
    assert(strstr((const char *)env_valid->buffer, "\"temp\":32") != NULL);
    assert(strstr((const char *)env_valid->buffer, "\"hum\":52") != NULL);
    assert(strstr((const char *)env_valid->buffer, "\"ldr\":350") != NULL);
    assert(strstr((const char *)env_valid->buffer, "\"x0\":3087") != NULL);

    assert(nexus_envelope_parse_header(env_valid->buffer, env_valid->length, &ver, &seq, type_str, sizeof(type_str)));
    assert(ver == NEXUS_PROTOCOL_VERSION);
    assert(strcmp(type_str, "telem") == 0);

    printf("  [PASS] Telemetry schema compatibility: omitted temp/hum vs valid dht11\n");
}

typedef struct {
    nexus_conn_mgr_t *mgr;
    atomic_bool stop_consumer;
    int items_to_produce;
    int items_produced;
} concurrent_test_ctx_t;

static void *concurrent_consumer_worker(void *arg)
{
    concurrent_test_ctx_t *ctx = (concurrent_test_ctx_t *)arg;
    while (!atomic_load(&ctx->stop_consumer)) {
        size_t n = nexus_conn_mgr_process_tx_queue(ctx->mgr);
        if (n > 0) {
            nexus_serial_transport_mock_reset(&ctx->mgr->serial_transport);
        }
        struct timespec ts = {.tv_sec = 0, .tv_nsec = 10000}; /* 10 us */
        nanosleep(&ts, NULL);
    }
    /* Drain any remaining items */
    nexus_conn_mgr_process_tx_queue(ctx->mgr);
    nexus_serial_transport_mock_reset(&ctx->mgr->serial_transport);
    return NULL;
}

static void *concurrent_producer_worker(void *arg)
{
    concurrent_test_ctx_t *ctx = (concurrent_test_ctx_t *)arg;
    nexus_envelope_t env;
    nexus_envelope_init(&env);

    for (int i = 0; i < ctx->items_to_produce; i++) {
        assert(nexus_envelope_format_heartbeat(&env, (uint32_t)(i + 1), 1000 + i, 200000, (uint32_t)i));
        /* Producer simulates periodic executive callback enqueues under concurrent worker activity.
         * Under the critical section, lock contention never causes a spurious drop. */
        bool enqueued = nexus_conn_mgr_enqueue(ctx->mgr, &env, NEXUS_ROUTE_AUTO);
        assert(enqueued);
        ctx->items_produced++;
        struct timespec ts = {.tv_sec = 0, .tv_nsec = 50000}; /* 50 us */
        nanosleep(&ts, NULL);
    }
    return NULL;
}

static void test_tx_queue_concurrency_and_contention_safety(void)
{
    printf("  [TEST] Concurrency and contention safety: multi-threaded producer/consumer & drop invariant...\n");

    nexus_conn_mgr_t mgr;
    assert(nexus_conn_mgr_init(&mgr, NULL));
    assert(nexus_conn_mgr_start(&mgr));

    /* 1. Multi-threaded stress test: 200 envelopes enqueued and drained concurrently */
    concurrent_test_ctx_t ctx = {
        .mgr = &mgr,
        .stop_consumer = false,
        .items_to_produce = 200,
        .items_produced = 0
    };

    pthread_t consumer_thread, producer_thread;
    assert(pthread_create(&consumer_thread, NULL, concurrent_consumer_worker, &ctx) == 0);
    assert(pthread_create(&producer_thread, NULL, concurrent_producer_worker, &ctx) == 0);

    /* Wait for producer to finish producing all items */
    assert(pthread_join(producer_thread, NULL) == 0);
    assert(ctx.items_produced == 200);

    /* Let consumer drain remaining items */
    struct timespec drain_sleep = {.tv_sec = 0, .tv_nsec = 10000000}; /* 10 ms */
    nanosleep(&drain_sleep, NULL);
    atomic_store(&ctx.stop_consumer, true);
    assert(pthread_join(consumer_thread, NULL) == 0);

    /* Final drain */
    nexus_conn_mgr_process_tx_queue(&mgr);

    nexus_conn_mgr_stats_t cstats;
    nexus_conn_mgr_get_stats(&mgr, &cstats);

    /* Invariant: zero dropped envelopes during concurrent interleaved execution when queue has space */
    assert(cstats.tx_enqueued == 200);
    assert(cstats.tx_dispatched == 200);
    assert(cstats.tx_dropped == 0);
    assert(cstats.tx_failed == 0);
    assert(cstats.tx_queue_depth == 0);

    /* 2. Strict queue saturation invariant: total_dropped increments ONLY on true capacity exhaustion */
    nexus_envelope_t env;
    nexus_envelope_init(&env);
    assert(nexus_envelope_format_heartbeat(&env, 9999, 50000, 190000, 500));

    /* Fill all 16 slots without consumer running */
    for (uint16_t i = 0; i < NEXUS_CONN_TX_QUEUE_CAPACITY; i++) {
        assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    }
    nexus_conn_mgr_get_stats(&mgr, &cstats);
    assert(cstats.tx_queue_depth == NEXUS_CONN_TX_QUEUE_CAPACITY);
    assert(cstats.tx_dropped == 0);

    /* 17th item must be rejected and increment tx_dropped */
    assert(!nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    nexus_conn_mgr_get_stats(&mgr, &cstats);
    assert(cstats.tx_dropped == 1);

    /* 18th item must also be rejected and increment tx_dropped */
    assert(!nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    nexus_conn_mgr_get_stats(&mgr, &cstats);
    assert(cstats.tx_dropped == 2);

    /* Drain queue */
    assert(nexus_conn_mgr_process_tx_queue(&mgr) == NEXUS_CONN_TX_QUEUE_CAPACITY);
    nexus_conn_mgr_get_stats(&mgr, &cstats);
    assert(cstats.tx_queue_depth == 0);
    assert(cstats.tx_dropped == 2);

    /* Enqueue now succeeds */
    assert(nexus_conn_mgr_enqueue(&mgr, &env, NEXUS_ROUTE_AUTO));
    nexus_conn_mgr_get_stats(&mgr, &cstats);
    assert(cstats.tx_queue_depth == 1);
    assert(cstats.tx_dropped == 2);

    /* Clean stop */
    assert(nexus_conn_mgr_stop(&mgr));
    printf("  [PASS] Concurrency and contention safety: multi-threaded producer/consumer & drop invariant\n");
}

int main(void)
{
    printf("====================================================\n");
    printf("NEXUS Milestone 4 Unified Connection Manager Test Suite\n");
    printf("====================================================\n");

    test_envelope_serialization_and_framing();
    test_f01_bounded_envelope_parser_regression();
    test_tx_queue_saturation_and_overflow_rejection();
    test_transport_state_transitions_and_diagnostics();
    test_routing_policies();
    test_f02_composite_deduplication_and_isolation();
    test_f04_reconnect_backoff_calculation();
    test_f05_f06_unconfigured_defaults_and_lifecycle();
    test_mqtt_auth_configuration_and_rejection_of_missing_credentials();
    test_start_rejected_when_worker_terminating();
    test_executive_timing_isolation();
    test_executive_and_sensors_integration();
    test_mqtt_inbound_rx_and_fragmentation();
    test_telemetry_schema_and_dht_validity();
    test_tx_queue_concurrency_and_contention_safety();

    printf("====================================================\n");
    printf("ALL MILESTONE 4 HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("====================================================\n");
    return 0;
}
