#ifndef NEXUS_DHT11_H
#define NEXUS_DHT11_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_GPIO_DHT11       19U
#define NEXUS_DHT11_INTERVAL_MS 2000U /* DHT11 hardware requires >= 1.5-2.0s between reads */
#define NEXUS_DHT11_TIMEOUT_US  120U  /* Max microsecond timeout per transition */

typedef struct {
    int16_t temperature_c; /* Integer °C */
    uint16_t humidity_pct; /* Integer % RH */
    bool valid;
} nexus_dht11_reading_t;

/* Initialize GPIO 19 and register DHT11 temperature and humidity in sensor registry. */
bool nexus_dht11_init(nexus_sensor_registry_t *registry);

/* Bounded bit-bang read from GPIO 19.
 * Returns true on valid packet and checksum match; false on timeout or CRC error. */
bool nexus_dht11_read(nexus_dht11_reading_t *out_reading);

/* Acquire DHT11 reading, update registry for temp and humidity, record to executive ring buffer. */
bool nexus_dht11_acquire(nexus_sensor_registry_t *registry,
                         nexus_executive_t *executive,
                         int64_t timestamp_us);

/* Executive Priority Class 1 job callback for DHT11 */
bool nexus_dht11_job_fn(void *user_ctx);

#ifndef ESP_PLATFORM
/* Host unit test helper to inject mock pulse packets */
void nexus_dht11_set_mock_packet(const uint8_t *bytes5, bool simulate_timeout);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_DHT11_H */
