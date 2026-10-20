#ifndef NEXUS_SENSOR_REGISTRY_H
#define NEXUS_SENSOR_REGISTRY_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_ring_buffer.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_SENSOR_REGISTRY_CAPACITY 8U
#define NEXUS_SENSOR_NAME_MAX_LEN      16U

/* Well-known sensor identifiers */
#define NEXUS_SENSOR_ID_LDR            1U
#define NEXUS_SENSOR_ID_DHT11_TEMP     2U
#define NEXUS_SENSOR_ID_DHT11_HUM      3U
#define NEXUS_SENSOR_ID_MUX_GAS_X0     4U
#define NEXUS_SENSOR_ID_HALL_X1        5U
#define NEXUS_SENSOR_ID_MOC7811        6U
#define NEXUS_SENSOR_ID_HCSR04         7U

typedef enum {
    NEXUS_SENSOR_TYPE_UNKNOWN = 0,
    NEXUS_SENSOR_TYPE_LDR,
    NEXUS_SENSOR_TYPE_DHT11_TEMP,
    NEXUS_SENSOR_TYPE_DHT11_HUM,
    NEXUS_SENSOR_TYPE_ANALOG_MUX,
    NEXUS_SENSOR_TYPE_OPTICAL_SLOT,
    NEXUS_SENSOR_TYPE_ULTRASONIC
} nexus_sensor_type_t;

typedef struct {
    uint16_t sensor_id;
    char name[NEXUS_SENSOR_NAME_MAX_LEN];
    nexus_sensor_type_t type;
    uint8_t pin_or_channel;
    bool enabled;
    uint32_t interval_ms;
    int64_t last_sample_time_us;
    int32_t latest_raw;
    int32_t latest_processed;
    uint8_t sample_flags;   /* NEXUS_SAMPLE_FLAG_* from nexus_ring_buffer.h */
    uint32_t sample_count;
    uint32_t error_count;
    uint32_t timeout_count;
} nexus_sensor_descriptor_t;

typedef struct {
    nexus_sensor_descriptor_t entries[NEXUS_SENSOR_REGISTRY_CAPACITY];
    uint16_t count;
    uint32_t registration_failures;
} nexus_sensor_registry_t;

void nexus_sensor_registry_init(nexus_sensor_registry_t *reg);

/* Register a sensor descriptor. Returns true on success, false if full or invalid params. */
bool nexus_sensor_register(nexus_sensor_registry_t *reg,
                           uint16_t sensor_id,
                           const char *name,
                           nexus_sensor_type_t type,
                           uint8_t pin_or_channel,
                           uint32_t interval_ms);

nexus_sensor_descriptor_t *nexus_sensor_get(nexus_sensor_registry_t *reg, uint16_t sensor_id);

nexus_sensor_descriptor_t *nexus_sensor_get_by_index(nexus_sensor_registry_t *reg, uint16_t index);

/* Update latest measurement for a registered sensor */
bool nexus_sensor_update_sample(nexus_sensor_registry_t *reg,
                                uint16_t sensor_id,
                                int32_t raw_value,
                                int32_t processed_value,
                                uint8_t flags,
                                int64_t timestamp_us);

/* Record an acquisition error or timeout for a sensor */
bool nexus_sensor_record_error(nexus_sensor_registry_t *reg, uint16_t sensor_id, bool is_timeout);

/* Freshness check: returns true if latest sample is within max_age_ms and valid */
bool nexus_sensor_is_fresh(const nexus_sensor_registry_t *reg,
                           uint16_t sensor_id,
                           int64_t current_time_us,
                           uint32_t max_age_ms);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_SENSOR_REGISTRY_H */
