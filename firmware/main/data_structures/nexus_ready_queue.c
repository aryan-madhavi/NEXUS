#include "nexus_ready_queue.h"
#include <string.h>

void nexus_ready_queue_init(nexus_ready_queue_t *queue)
{
    if (!queue) {
        return;
    }
    memset(queue, 0, sizeof(*queue));
}

bool nexus_ready_queue_push(nexus_ready_queue_t *queue,
                            uint16_t job_id,
                            nexus_priority_class_t priority)
{
    if (!queue || job_id == 0U || priority >= NEXUS_PRIORITY_CLASS_COUNT) {
        return false;
    }

    if (queue->count >= NEXUS_READY_QUEUE_CAPACITY) {
        queue->overflow_count++;
        return false;
    }

    /* Find insertion point:
     * Lower numerical priority value = Higher priority (0 is highest).
     * To maintain FIFO tie-breaking for equal priority, insert AFTER all existing
     * entries with priority <= new priority. */
    uint16_t insert_idx = queue->count;
    for (uint16_t i = 0; i < queue->count; i++) {
        if (priority < queue->priorities[i]) {
            insert_idx = i;
            break;
        }
    }

    /* Shift elements right from insert_idx */
    for (uint16_t i = queue->count; i > insert_idx; i--) {
        queue->job_ids[i] = queue->job_ids[i - 1];
        queue->priorities[i] = queue->priorities[i - 1];
    }

    queue->job_ids[insert_idx] = job_id;
    queue->priorities[insert_idx] = priority;
    queue->count++;
    queue->enqueue_count++;

    if (queue->count > queue->high_water_mark) {
        queue->high_water_mark = queue->count;
    }

    return true;
}

bool nexus_ready_queue_pop(nexus_ready_queue_t *queue, uint16_t *out_job_id)
{
    if (!queue || queue->count == 0U || !out_job_id) {
        return false;
    }

    *out_job_id = queue->job_ids[0];

    /* Shift elements left */
    for (uint16_t i = 0; i < queue->count - 1; i++) {
        queue->job_ids[i] = queue->job_ids[i + 1];
        queue->priorities[i] = queue->priorities[i + 1];
    }

    queue->count--;
    queue->dequeue_count++;
    return true;
}

bool nexus_ready_queue_peek(const nexus_ready_queue_t *queue, uint16_t *out_job_id)
{
    if (!queue || queue->count == 0U || !out_job_id) {
        return false;
    }
    *out_job_id = queue->job_ids[0];
    return true;
}

bool nexus_ready_queue_contains(const nexus_ready_queue_t *queue, uint16_t job_id)
{
    if (!queue || job_id == 0U) {
        return false;
    }
    for (uint16_t i = 0; i < queue->count; i++) {
        if (queue->job_ids[i] == job_id) {
            return true;
        }
    }
    return false;
}

bool nexus_ready_queue_is_empty(const nexus_ready_queue_t *queue)
{
    return (!queue || queue->count == 0U);
}

bool nexus_ready_queue_is_full(const nexus_ready_queue_t *queue)
{
    return (queue && queue->count >= NEXUS_READY_QUEUE_CAPACITY);
}

uint16_t nexus_ready_queue_count(const nexus_ready_queue_t *queue)
{
    return queue ? queue->count : 0U;
}
