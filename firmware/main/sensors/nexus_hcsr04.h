#ifndef NEXUS_HCSR04_H
#define NEXUS_HCSR04_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"

#ifdef __cplusplus
extern "C" {
#endif

/* HC-SR04 Ultrasonic Sensor Pinout on EDU_ROBO V14 ULTRA connector.
 * Trigger: GPIO25 (Output)
 * Echo:    GPIO26 (Input)
 * ⚠ ELECTRICAL SAFETY NOTICE:
 * Classic HC-SR04 modules output a 5V logic HIGH pulse on Echo.
 * The ESP32 is NOT 5V tolerant (maximum 3.3V).
 * An unverified or unattenuated 5V Echo line risks destroying GPIO26.
 * Physical acquisition is inhibited by default until electrical safety
 * (e.g., 3.3V module verified or voltage divider present) is confirmed. */
#define NEXUS_GPIO_HCSR04_TRIG        25U
#define NEXUS_GPIO_HCSR04_ECHO        26U
#define NEXUS_HCSR04_INTERVAL_MS      1000U
#define NEXUS_HCSR04_DEFAULT_TIMEOUT_US 8000U /* 8 ms timeout (~1.37 m) ensuring <= 10 ms executive callback budget */

typedef enum {
    NEXUS_HCSR04_STATUS_OK = 0,
    NEXUS_HCSR04_STATUS_UNVERIFIED_VOLTAGE, /* Electrical protection unverified; acquisition inhibited */
    NEXUS_HCSR04_STATUS_TIMEOUT,
    NEXUS_HCSR04_STATUS_OUT_OF_RANGE,
    NEXUS_HCSR04_STATUS_ERROR
} nexus_hcsr04_status_t;

typedef struct {
    int32_t distance_cm;
    uint32_t echo_duration_us;
    nexus_hcsr04_status_t status;
    bool valid;
} nexus_hcsr04_reading_t;

/* Initialize HC-SR04 driver and register with sensor registry.
 * By default, live physical acquisition is disabled (safe mode) until explicitly enabled. */
bool nexus_hcsr04_init(nexus_sensor_registry_t *registry);

/* Enable/disable live physical hardware acquisition.
 * Live acquisition must only be enabled after verifying Echo voltage <= 3.3V. */
void nexus_hcsr04_set_live_enabled(bool enabled);

/* Check whether live hardware acquisition is enabled. */
bool nexus_hcsr04_is_live_enabled(void);

/* Calculate distance in centimeters from round-trip echo pulse duration in microseconds.
 * Returns true if valid (2..400 cm), false if out of range. */
bool nexus_hcsr04_calculate_distance(uint32_t echo_us, int32_t *out_dist_cm);

/* Sample HC-SR04 reading with explicit status code. */
bool nexus_hcsr04_read(nexus_hcsr04_reading_t *out_reading);

/* Acquire HC-SR04 sample, update sensor registry, record to executive ring buffer. */
bool nexus_hcsr04_acquire(nexus_sensor_registry_t *registry,
                          nexus_executive_t *executive,
                          int64_t timestamp_us);

/* Executive Priority Class 1 job callback for HC-SR04 */
bool nexus_hcsr04_job_fn(void *user_ctx);

#ifndef ESP_PLATFORM
/* Host test mock helpers */
void nexus_hcsr04_set_mock_pulse(uint32_t echo_us, bool success);
void nexus_hcsr04_set_mock_distance(int32_t distance_cm, bool valid);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_HCSR04_H */
