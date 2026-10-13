#ifndef NEXUS_EVENT_QUEUE_H
#define NEXUS_EVENT_QUEUE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_EVENT_QUEUE_CAPACITY 32U

typedef enum {
    NEXUS_EVENT_TYPE_NONE = 0,
    NEXUS_EVENT_TYPE_SYSTEM_BOOT,
    NEXUS_EVENT_TYPE_JOB_STARTED,
    NEXUS_EVENT_TYPE_JOB_COMPLETED,
    NEXUS_EVENT_TYPE_JOB_FAILED,
    NEXUS_EVENT_TYPE_DEADLINE_MISS,
    NEXUS_EVENT_TYPE_QUEUE_OVERFLOW,
    NEXUS_EVENT_TYPE_FAULT_LATCHED,
    NEXUS_EVENT_TYPE_FAULT_CLEARED,
    NEXUS_EVENT_TYPE_SENSOR_SAMPLE,
    NEXUS_EVENT_TYPE_COMMAND_RECEIVED,
    NEXUS_EVENT_TYPE_COMMAND_COMPLETED
} nexus_event_type_t;

typedef enum {
    NEXUS_SEVERITY_DEBUG = 0,
    NEXUS_SEVERITY_INFO,
    NEXUS_SEVERITY_WARN,
    NEXUS_SEVERITY_ERROR,
    NEXUS_SEVERITY_CRITICAL
} nexus_event_severity_t;

typedef struct {
    uint32_t sequence_id;
    int64_t timestamp_us;
    nexus_event_type_t event_type;
    nexus_event_severity_t severity;
    uint16_t source_id; /* job_id, sensor_id, or command_id */
    int32_t payload_i32;
} nexus_event_t;

typedef struct {
    nexus_event_t buffer[NEXUS_EVENT_QUEUE_CAPACITY];
    uint16_t head;       /* Write index */
    uint16_t tail;       /* Read index */
    uint16_t count;
    uint16_t high_water_mark;
    uint32_t total_pushed;
    uint32_t total_popped;
    uint32_t overflow_drop_count;
    uint32_t next_sequence_id;
} nexus_event_queue_t;

void nexus_event_queue_init(nexus_event_queue_t *queue);

/* Push an event. If full, increments overflow_drop_count and returns false (reject policy). */
bool nexus_event_queue_push(nexus_event_queue_t *queue,
                            nexus_event_type_t event_type,
                            nexus_event_severity_t severity,
                            uint16_t source_id,
                            int32_t payload_i32,
                            int64_t timestamp_us);

/* Pop the oldest event into *out_event. Returns true, or false if empty. */
bool nexus_event_queue_pop(nexus_event_queue_t *queue, nexus_event_t *out_event);

/* Peek oldest event without popping. */
bool nexus_event_queue_peek(const nexus_event_queue_t *queue, nexus_event_t *out_event);

bool nexus_event_queue_is_empty(const nexus_event_queue_t *queue);

bool nexus_event_queue_is_full(const nexus_event_queue_t *queue);

uint16_t nexus_event_queue_count(const nexus_event_queue_t *queue);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_EVENT_QUEUE_H */
