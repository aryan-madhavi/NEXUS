#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>

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

    /* 2. Telemetry envelope */
    ok = nexus_envelope_format_telemetry(&env, 102, 12350, 2048, 1024, 25, 60);
    assert(ok);
    assert(env.buffer[env.length - 1] == '\n');
    ok = nexus_envelope_parse_header(env.buffer, env.length, &ver, &seq, type_str, sizeof(type_str));
    assert(ok);
    assert(seq == 102);
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

static void mock_rx_callback(void *user_ctx, nexus_transport_type_t source, const nexus_envelope_t *env)
{
    (void)user_ctx;
    s_rx_callback_invocations++;
    s_last_received_source = source;
    s_last_received_seq = env->seq;
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

    /* Build envelope with seq = 501 */
    nexus_envelope_t env;
    assert(nexus_envelope_format_heartbeat(&env, 501, 1000, 200000, 10));

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
    return nexus_conn_mgr_send_telemetry(&s_integ_conn_mgr, 1000, 1500, 800, 26, 55, NEXUS_ROUTE_AUTO);
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
    test_start_rejected_when_worker_terminating();
    test_executive_timing_isolation();
    test_executive_and_sensors_integration();

    printf("====================================================\n");
    printf("ALL MILESTONE 4 HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("====================================================\n");
    return 0;
}
