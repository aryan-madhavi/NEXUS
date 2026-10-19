#ifndef NEXUS_WIFI_MQTT_TRANSPORT_H
#define NEXUS_WIFI_MQTT_TRANSPORT_H

#include "nexus_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_WIFI_SSID_MAX_LEN       33U
#define NEXUS_WIFI_PASS_MAX_LEN       65U
#define NEXUS_MQTT_URI_MAX_LEN        128U
#define NEXUS_MQTT_CLIENT_ID_MAX_LEN  33U
#define NEXUS_MQTT_USERNAME_MAX_LEN   33U
#define NEXUS_MQTT_PASSWORD_MAX_LEN   65U
#define NEXUS_MQTT_TOPIC_MAX_LEN      64U

typedef struct {
    char ssid[NEXUS_WIFI_SSID_MAX_LEN];
    char password[NEXUS_WIFI_PASS_MAX_LEN];
    char broker_uri[NEXUS_MQTT_URI_MAX_LEN];
    char client_id[NEXUS_MQTT_CLIENT_ID_MAX_LEN];
    char username[NEXUS_MQTT_USERNAME_MAX_LEN];
    char mqtt_password[NEXUS_MQTT_PASSWORD_MAX_LEN];
    char topic_prefix[NEXUS_MQTT_TOPIC_MAX_LEN];
    uint32_t reconnect_base_ms;
    uint32_t reconnect_max_ms;
} nexus_wifi_mqtt_config_t;

bool nexus_wifi_mqtt_transport_init(nexus_transport_t *transport, const nexus_wifi_mqtt_config_t *config);

/* Exponential backoff calculation helper (host-testable) */
uint32_t nexus_wifi_mqtt_compute_next_backoff(uint32_t current_ms, uint32_t max_ms);

#define NEXUS_MQTT_MAX_RX_ENVELOPE_LEN 256U

typedef bool (*nexus_wifi_mqtt_rx_handler_t)(void *user_ctx, const uint8_t *data, size_t len);

void nexus_wifi_mqtt_transport_set_rx_handler(nexus_transport_t *transport,
                                              nexus_wifi_mqtt_rx_handler_t handler,
                                              void *user_ctx);

bool nexus_wifi_mqtt_transport_process_rx_chunk(nexus_transport_t *transport,
                                                const char *topic,
                                                int topic_len,
                                                const char *data,
                                                int data_len,
                                                int current_data_offset,
                                                int total_data_len);

#ifndef ESP_PLATFORM
/* Mock hooks for host unit testing */
void nexus_wifi_mqtt_mock_set_connected(nexus_transport_t *transport, bool connected);
void nexus_wifi_mqtt_mock_set_fail(nexus_transport_t *transport, bool fail);
size_t nexus_wifi_mqtt_mock_get_tx(nexus_transport_t *transport, uint8_t *out_buf, size_t max_len);
void nexus_wifi_mqtt_mock_reset_rx(nexus_transport_t *transport);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_WIFI_MQTT_TRANSPORT_H */
