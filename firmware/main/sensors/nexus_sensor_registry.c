#include "nexus_sensor_registry.h"
#include <string.h>

void nexus_sensor_registry_init(nexus_sensor_registry_t *reg)
{
    if (!reg) {
        return;
    }
    memset(reg, 0, sizeof(*reg));
}

bool nexus_sensor_register(nexus_sensor_registry_t *reg,
                           uint16_t sensor_id,
                           const char *name,
                           nexus_sensor_type_t type,
                           uint8_t pin_or_channel,
                           uint32_t interval_ms)
{
    if (!reg || sensor_id == 0U || type == NEXUS_SENSOR_TYPE_UNKNOWN) {
        if (reg) {
            reg->registration_failures++;
        }
        return false;
    }

    /* Reject duplicate sensor IDs */
    if (nexus_sensor_get(reg, sensor_id) != NULL) {
        reg->registration_failures++;
        return false;
    }

    if (reg->count >= NEXUS_SENSOR_REGISTRY_CAPACITY) {
        reg->registration_failures++;
        return false;
    }

    nexus_sensor_descriptor_t *desc = &reg->entries[reg->count];
    memset(desc, 0, sizeof(*desc));

    desc->sensor_id = sensor_id;
    desc->type = type;
    desc->pin_or_channel = pin_or_channel;
    desc->enabled = true;
    desc->interval_ms = interval_ms;

    if (name) {
        strncpy(desc->name, name, NEXUS_SENSOR_NAME_MAX_LEN - 1);
        desc->name[NEXUS_SENSOR_NAME_MAX_LEN - 1] = '\0';
    } else {
        desc->name[0] = '\0';
    }

    reg->count++;
    return true;
}

nexus_sensor_descriptor_t *nexus_sensor_get(nexus_sensor_registry_t *reg, uint16_t sensor_id)
{
    if (!reg || sensor_id == 0U) {
        return NULL;
    }

    for (uint16_t i = 0; i < reg->count; i++) {
        if (reg->entries[i].sensor_id == sensor_id) {
            return &reg->entries[i];
        }
    }

    return NULL;
}

nexus_sensor_descriptor_t *nexus_sensor_get_by_index(nexus_sensor_registry_t *reg, uint16_t index)
{
    if (!reg || index >= reg->count) {
        return NULL;
    }
    return &reg->entries[index];
}

bool nexus_sensor_update_sample(nexus_sensor_registry_t *reg,
                                uint16_t sensor_id,
                                int32_t raw_value,
                                int32_t processed_value,
                                uint8_t flags,
                                int64_t timestamp_us)
{
    nexus_sensor_descriptor_t *desc = nexus_sensor_get(reg, sensor_id);
    if (!desc) {
        return false;
    }

    desc->latest_raw = raw_value;
    desc->latest_processed = processed_value;
    desc->sample_flags = flags;
    desc->last_sample_time_us = timestamp_us;
    desc->sample_count++;

    return true;
}

bool nexus_sensor_record_error(nexus_sensor_registry_t *reg, uint16_t sensor_id, bool is_timeout)
{
    nexus_sensor_descriptor_t *desc = nexus_sensor_get(reg, sensor_id);
    if (!desc) {
        return false;
    }

    desc->error_count++;
    if (is_timeout) {
        desc->timeout_count++;
    }
    desc->sample_flags |= (NEXUS_SAMPLE_FLAG_ERROR | NEXUS_SAMPLE_FLAG_STALE);
    desc->sample_flags &= ~NEXUS_SAMPLE_FLAG_VALID;

    return true;
}

bool nexus_sensor_is_fresh(const nexus_sensor_registry_t *reg,
                           uint16_t sensor_id,
                           int64_t current_time_us,
                           uint32_t max_age_ms)
{
    if (!reg || sensor_id == 0U) {
        return false;
    }

    const nexus_sensor_descriptor_t *desc = NULL;
    for (uint16_t i = 0; i < reg->count; i++) {
        if (reg->entries[i].sensor_id == sensor_id) {
            desc = &reg->entries[i];
            break;
        }
    }

    if (!desc || desc->last_sample_time_us == 0) {
        return false;
    }

    if ((desc->sample_flags & NEXUS_SAMPLE_FLAG_VALID) == 0 ||
        (desc->sample_flags & NEXUS_SAMPLE_FLAG_ERROR) != 0) {
        return false;
    }

    int64_t age_us = current_time_us - desc->last_sample_time_us;
    if (age_us < 0) {
        return false;
    }

    int64_t max_age_us = (int64_t)max_age_ms * 1000LL;
    return (age_us <= max_age_us);
}
