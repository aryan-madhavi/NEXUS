#include "nexus_event_queue.h"
#include <string.h>

void nexus_event_queue_init(nexus_event_queue_t *queue)
{
    if (!queue) {
        return;
    }
    memset(queue, 0, sizeof(*queue));
    queue->next_sequence_id = 1U;
}

bool nexus_event_queue_push(nexus_event_queue_t *queue,
                            nexus_event_type_t event_type,
                            nexus_event_severity_t severity,
                            uint16_t source_id,
                            int32_t payload_i32,
                            int64_t timestamp_us)
{
    if (!queue) {
        return false;
    }

    if (queue->count >= NEXUS_EVENT_QUEUE_CAPACITY) {
        queue->overflow_drop_count++;
        return false;
    }

    nexus_event_t *slot = &queue->buffer[queue->head];
    slot->sequence_id = queue->next_sequence_id++;
    slot->timestamp_us = timestamp_us;
    slot->event_type = event_type;
    slot->severity = severity;
    slot->source_id = source_id;
    slot->payload_i32 = payload_i32;

    queue->head = (uint16_t)((queue->head + 1U) % NEXUS_EVENT_QUEUE_CAPACITY);
    queue->count++;
    queue->total_pushed++;

    if (queue->count > queue->high_water_mark) {
        queue->high_water_mark = queue->count;
    }

    return true;
}

bool nexus_event_queue_pop(nexus_event_queue_t *queue, nexus_event_t *out_event)
{
    if (!queue || queue->count == 0U || !out_event) {
        return false;
    }

    *out_event = queue->buffer[queue->tail];
    queue->tail = (uint16_t)((queue->tail + 1U) % NEXUS_EVENT_QUEUE_CAPACITY);
    queue->count--;
    queue->total_popped++;

    return true;
}

bool nexus_event_queue_peek(const nexus_event_queue_t *queue, nexus_event_t *out_event)
{
    if (!queue || queue->count == 0U || !out_event) {
        return false;
    }
    *out_event = queue->buffer[queue->tail];
    return true;
}

bool nexus_event_queue_is_empty(const nexus_event_queue_t *queue)
{
    return (!queue || queue->count == 0U);
}

bool nexus_event_queue_is_full(const nexus_event_queue_t *queue)
{
    return (queue && queue->count >= NEXUS_EVENT_QUEUE_CAPACITY);
}

uint16_t nexus_event_queue_count(const nexus_event_queue_t *queue)
{
    return queue ? queue->count : 0U;
}
