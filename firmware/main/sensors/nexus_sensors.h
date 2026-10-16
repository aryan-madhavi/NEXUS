#ifndef NEXUS_SENSORS_H
#define NEXUS_SENSORS_H

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"
#include "nexus_adc_ldr.h"
#include "nexus_cd4051.h"
#include "nexus_dht11.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Initialize all verified Milestone 3 sensors (LDR, CD4051, DHT11) */
bool nexus_sensors_init(nexus_sensor_registry_t *registry);

/* Register all sensor acquisition jobs as Priority Class 1 periodic tasks in the executive */
bool nexus_sensors_register_jobs(nexus_sensor_registry_t *registry, nexus_executive_t *executive);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_SENSORS_H */
