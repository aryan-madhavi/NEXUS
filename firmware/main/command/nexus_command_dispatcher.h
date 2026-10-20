#ifndef NEXUS_COMMAND_DISPATCHER_H
#define NEXUS_COMMAND_DISPATCHER_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include "nexus_command_registry.h"
#include "transports/nexus_envelope.h"
#include "transports/nexus_transport.h"
#include "transports/nexus_connection_manager.h"
#include "executive/nexus_executive.h"
#include "sensors/nexus_sensor_registry.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t commands_received;
    uint32_t commands_executed;
    uint32_t commands_rejected;
    uint32_t commands_unsupported;
    uint32_t commands_failed;
    uint32_t responses_sent;
    uint32_t last_cmd_id;
    int64_t last_cmd_time_us;
} nexus_command_stats_t;

typedef struct {
    nexus_executive_t *executive;
    nexus_sensor_registry_t *sensors;
    nexus_conn_mgr_t *conn_mgr;
    nexus_command_stats_t stats;
    bool initialized;
} nexus_command_dispatcher_t;

/**
 * @brief Initializes the command dispatcher with required subsystem references.
 */
bool nexus_command_dispatcher_init(nexus_command_dispatcher_t *dispatcher,
                                   nexus_executive_t *executive,
                                   nexus_sensor_registry_t *sensors,
                                   nexus_conn_mgr_t *conn_mgr);

/**
 * @brief Parses an incoming raw JSON command envelope, validates it, executes the
 *        appropriate handler, and formats a structured response envelope.
 *
 * @param dispatcher Pointer to initialized dispatcher.
 * @param source Transport provenance (Serial, MQTT).
 * @param data Raw wire data.
 * @param len Length in bytes.
 * @param out_resp_env Output envelope buffer populated with structured response.
 * @return true if command was parsed and a response envelope was produced.
 */
bool nexus_command_dispatcher_process(nexus_command_dispatcher_t *dispatcher,
                                     nexus_transport_type_t source,
                                     const uint8_t *data,
                                     size_t len,
                                     nexus_envelope_t *out_resp_env);

/**
 * @brief Connection Manager RX callback trampoline.
 *
 * Can be registered directly with nexus_conn_mgr_set_rx_callback.
 */
void nexus_command_dispatcher_rx_callback(void *user_ctx,
                                         nexus_transport_type_t source,
                                         const nexus_envelope_t *env);

/**
 * @brief Formats an ESP32-originated OPEN command envelope to launch a laptop application.
 */
bool nexus_command_format_open_request(nexus_envelope_t *env,
                                      uint32_t seq,
                                      int64_t uptime_ms,
                                      uint16_t cmd_id);

/**
 * @brief Sends an ESP32-originated OPEN command to the Ground Station via the connection manager.
 */
bool nexus_command_send_open_request(nexus_conn_mgr_t *conn_mgr,
                                    uint16_t cmd_id,
                                    nexus_route_policy_t route);

/**
 * @brief Retrieves dispatcher statistics snapshot.
 */
void nexus_command_dispatcher_get_stats(const nexus_command_dispatcher_t *dispatcher,
                                       nexus_command_stats_t *out_stats);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_COMMAND_DISPATCHER_H */
