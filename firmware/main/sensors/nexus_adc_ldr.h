#ifndef NEXUS_ADC_LDR_H
#define NEXUS_ADC_LDR_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_LDR_INTERVAL_MS 500U

/* Initialize LDR hardware (GPIO 35 / ADC1 Ch7) and register with sensor registry. */
bool nexus_ldr_init(nexus_sensor_registry_t *registry);

/* Acquisition function: reads ADC1 Ch7, updates registry, records to executive ring buffer.
 * Can be called directly or run as an executive Priority Class 1 job. */
bool nexus_ldr_acquire(nexus_sensor_registry_t *registry,
                       nexus_executive_t *executive,
                       int64_t timestamp_us);

/* Executive job callback wrapper */
bool nexus_ldr_job_fn(void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_ADC_LDR_H */
