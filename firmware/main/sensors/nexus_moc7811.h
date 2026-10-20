#ifndef NEXUS_MOC7811_H
#define NEXUS_MOC7811_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"

#ifdef __cplusplus
extern "C" {
#endif

/* MOC7811 Optical Slot Sensor Pin on EDU_ROBO V14.
 * Note: GPIO34 is input-only (GPI) and lacks internal pull-up or pull-down resistors.
 * Electrical validity requires external pull-up resistors on the PCB. */
#define NEXUS_GPIO_MOC7811        34U
#define NEXUS_MOC7811_INTERVAL_MS 1000U

/* Initialize MOC7811 GPIO input and register with sensor registry. */
bool nexus_moc7811_init(nexus_sensor_registry_t *registry);

/* Read the direct digital state of the slot sensor.
 * out_raw: 0 (unblocked / beam intact) or 1 (blocked / beam interrupted)
 * out_blocked: true if object is in slot, false if clear. */
bool nexus_moc7811_read_state(int *out_raw, bool *out_blocked);

/* Acquire MOC7811 sample, update registry, record to executive ring buffer. */
bool nexus_moc7811_acquire(nexus_sensor_registry_t *registry,
                           nexus_executive_t *executive,
                           int64_t timestamp_us);

/* Executive Priority Class 1 job callback for MOC7811 slot sensor */
bool nexus_moc7811_job_fn(void *user_ctx);

#ifndef ESP_PLATFORM
/* Host test mock helper */
void nexus_moc7811_set_mock_state(int raw_val, bool success);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_MOC7811_H */
