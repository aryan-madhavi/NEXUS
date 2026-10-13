#include "nexus_ring_buffer.h"
#include <string.h>

void nexus_ring_buffer_init(nexus_ring_buffer_t *rb)
{
    if (!rb) {
        return;
    }
    memset(rb, 0, sizeof(*rb));
}

bool nexus_ring_buffer_push(nexus_ring_buffer_t *rb, const nexus_sensor_sample_t *sample)
{
    if (!rb || !sample) {
        return false;
    }

    if (rb->count >= NEXUS_SENSOR_HISTORY_CAPACITY) {
        /* Drop oldest: advance tail to discard oldest sample */
        rb->tail = (uint16_t)((rb->tail + 1U) % NEXUS_SENSOR_HISTORY_CAPACITY);
        rb->total_overwritten++;
    } else {
        rb->count++;
    }

    rb->buffer[rb->head] = *sample;
    rb->head = (uint16_t)((rb->head + 1U) % NEXUS_SENSOR_HISTORY_CAPACITY);
    rb->total_written++;

    return true;
}

bool nexus_ring_buffer_pop(nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample)
{
    if (!rb || rb->count == 0U || !out_sample) {
        return false;
    }

    *out_sample = rb->buffer[rb->tail];
    rb->tail = (uint16_t)((rb->tail + 1U) % NEXUS_SENSOR_HISTORY_CAPACITY);
    rb->count--;

    return true;
}

bool nexus_ring_buffer_peek_newest(const nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample)
{
    if (!rb || rb->count == 0U || !out_sample) {
        return false;
    }

    /* Newest element is at (head - 1 + CAPACITY) % CAPACITY */
    uint16_t idx = (uint16_t)((rb->head + NEXUS_SENSOR_HISTORY_CAPACITY - 1U) % NEXUS_SENSOR_HISTORY_CAPACITY);
    *out_sample = rb->buffer[idx];
    return true;
}

bool nexus_ring_buffer_peek_oldest(const nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample)
{
    if (!rb || rb->count == 0U || !out_sample) {
        return false;
    }

    *out_sample = rb->buffer[rb->tail];
    return true;
}

bool nexus_ring_buffer_is_empty(const nexus_ring_buffer_t *rb)
{
    return (!rb || rb->count == 0U);
}

bool nexus_ring_buffer_is_full(const nexus_ring_buffer_t *rb)
{
    return (rb && rb->count >= NEXUS_SENSOR_HISTORY_CAPACITY);
}

uint16_t nexus_ring_buffer_count(const nexus_ring_buffer_t *rb)
{
    return rb ? rb->count : 0U;
}
