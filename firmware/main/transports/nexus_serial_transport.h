#ifndef NEXUS_SERIAL_TRANSPORT_H
#define NEXUS_SERIAL_TRANSPORT_H

#include "nexus_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t baud_rate;
    uint8_t uart_port;
} nexus_serial_config_t;

/* Initialize serial transport structure using caller-allocated storage */
bool nexus_serial_transport_init(nexus_transport_t *transport, const nexus_serial_config_t *config);

#ifndef ESP_PLATFORM
/* Host mock hooks for unit tests */
void nexus_serial_transport_mock_reset(nexus_transport_t *transport);
size_t nexus_serial_transport_mock_get_tx(nexus_transport_t *transport, uint8_t *out_buf, size_t max_len);
void nexus_serial_transport_mock_set_fail(nexus_transport_t *transport, bool fail);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_SERIAL_TRANSPORT_H */
