#ifndef NEXUS_READY_QUEUE_H
#define NEXUS_READY_QUEUE_H

#include <stdint.h>
#include <stdbool.h>
#include "nexus_job_table.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_READY_QUEUE_CAPACITY 16U

/* Priority queue with FIFO tie-breaking across priority classes.
 * Priorities 0 (highest), 1, 2 (lowest). */
typedef struct {
    uint16_t job_ids[NEXUS_READY_QUEUE_CAPACITY];
    nexus_priority_class_t priorities[NEXUS_READY_QUEUE_CAPACITY];
    uint16_t count;
    uint16_t high_water_mark;
    uint32_t enqueue_count;
    uint32_t dequeue_count;
    uint32_t overflow_count;
} nexus_ready_queue_t;

void nexus_ready_queue_init(nexus_ready_queue_t *queue);

/* Enqueue a job ID with a priority class.
 * Inserts in priority order; jobs with identical priority preserve FIFO order.
 * Returns true if enqueued, false if queue is full. */
bool nexus_ready_queue_push(nexus_ready_queue_t *queue,
                            uint16_t job_id,
                            nexus_priority_class_t priority);

/* Dequeue the highest-priority runnable job ID.
 * Returns true and writes to *out_job_id, or false if queue is empty. */
bool nexus_ready_queue_pop(nexus_ready_queue_t *queue, uint16_t *out_job_id);

/* Peek highest-priority runnable job without popping. */
bool nexus_ready_queue_peek(const nexus_ready_queue_t *queue, uint16_t *out_job_id);

/* Returns true if the job_id is already present in the ready queue (avoids double enqueue). */
bool nexus_ready_queue_contains(const nexus_ready_queue_t *queue, uint16_t job_id);

bool nexus_ready_queue_is_empty(const nexus_ready_queue_t *queue);

bool nexus_ready_queue_is_full(const nexus_ready_queue_t *queue);

uint16_t nexus_ready_queue_count(const nexus_ready_queue_t *queue);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_READY_QUEUE_H */
