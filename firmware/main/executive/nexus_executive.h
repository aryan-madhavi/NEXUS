#ifndef NEXUS_EXECUTIVE_H
#define NEXUS_EXECUTIVE_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_job_table.h"
#include "nexus_ready_queue.h"
#include "nexus_event_queue.h"
#include "nexus_ring_buffer.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    NEXUS_EXEC_STATE_UNINITIALIZED = 0,
    NEXUS_EXEC_STATE_INITIALIZED,
    NEXUS_EXEC_STATE_RUNNING,
    NEXUS_EXEC_STATE_STOPPED,
    NEXUS_EXEC_STATE_FAULTED
} nexus_exec_state_t;

typedef struct {
    uint32_t ticks;
    uint32_t jobs_dispatched;
    uint32_t jobs_completed;
    uint32_t jobs_failed;
    uint32_t deadline_misses;
    uint32_t queue_overflows;
    uint32_t latched_faults;
    uint32_t max_dispatch_latency_us;
    uint32_t max_job_duration_us;
} nexus_executive_stats_t;

typedef struct {
    nexus_exec_state_t state;
    nexus_job_table_t job_table;
    nexus_ready_queue_t ready_queue;
    nexus_event_queue_t event_queue;
    nexus_ring_buffer_t sensor_history;
    nexus_executive_stats_t stats;
    int64_t last_tick_us;
    uint32_t tick_period_ms;
    uint32_t last_fault_code;
} nexus_executive_t;

/* Initialize executive data structures and stats.
 * Uses caller-allocated (static) storage; no heap allocation. */
void nexus_executive_init(nexus_executive_t *exec, uint32_t tick_period_ms);

/* Register an application job with the executive.
 * Returns assigned job_id (1..N) or 0 on error. */
uint16_t nexus_executive_register_job(nexus_executive_t *exec,
                                      const char *name,
                                      nexus_priority_class_t priority,
                                      nexus_job_fn_t work_fn,
                                      void *user_ctx,
                                      uint32_t period_ms,
                                      uint32_t deadline_ms);

/* Manually submit a job to the ready queue (e.g. for event/command-triggered execution). */
bool nexus_executive_submit_job(nexus_executive_t *exec, uint16_t job_id);

/* Unregister job and reclaim slot. */
bool nexus_executive_unregister_job(nexus_executive_t *exec, uint16_t job_id);

/* Push an event into the executive event queue. */
bool nexus_executive_emit_event(nexus_executive_t *exec,
                                nexus_event_type_t event_type,
                                nexus_event_severity_t severity,
                                uint16_t source_id,
                                int32_t payload_i32);

/* Record a sensor sample into the history ring buffer. */
bool nexus_executive_record_sample(nexus_executive_t *exec, const nexus_sensor_sample_t *sample);

/* Core scheduler tick function. Evaluates periodic jobs, schedules runnable tasks,
 * and dispatches jobs from ready queue. Designed to be called from the executive FreeRTOS task,
 * or step-by-step from host-side unit tests without FreeRTOS dependencies. */
void nexus_executive_tick(nexus_executive_t *exec, int64_t current_time_us);

/* Run self-test verifying bounded data structures and state transitions.
 * Returns true if all tests pass. */
bool nexus_executive_run_selftest(void);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_EXECUTIVE_H */
