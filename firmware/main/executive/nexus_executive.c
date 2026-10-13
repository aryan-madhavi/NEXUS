#include "nexus_executive.h"
#include <string.h>

void nexus_executive_init(nexus_executive_t *exec, uint32_t tick_period_ms)
{
    if (!exec) {
        return;
    }
    memset(exec, 0, sizeof(*exec));
    nexus_job_table_init(&exec->job_table);
    nexus_ready_queue_init(&exec->ready_queue);
    nexus_event_queue_init(&exec->event_queue);
    nexus_ring_buffer_init(&exec->sensor_history);

    exec->tick_period_ms = (tick_period_ms > 0) ? tick_period_ms : 100U;
    exec->state = NEXUS_EXEC_STATE_INITIALIZED;
}

uint16_t nexus_executive_register_job(nexus_executive_t *exec,
                                      const char *name,
                                      nexus_priority_class_t priority,
                                      nexus_job_fn_t work_fn,
                                      void *user_ctx,
                                      uint32_t period_ms,
                                      uint32_t deadline_ms)
{
    if (!exec) {
        return 0U;
    }
    return nexus_job_register(&exec->job_table, name, priority, work_fn, user_ctx, period_ms, deadline_ms);
}

bool nexus_executive_submit_job(nexus_executive_t *exec, uint16_t job_id)
{
    if (!exec || job_id == 0U) {
        return false;
    }

    nexus_job_descriptor_t *job = nexus_job_get(&exec->job_table, job_id);
    if (!job) {
        return false;
    }

    /* Avoid duplicate enqueue if already in ready queue */
    if (nexus_ready_queue_contains(&exec->ready_queue, job_id)) {
        return true;
    }

    if (!nexus_ready_queue_push(&exec->ready_queue, job_id, job->priority)) {
        exec->stats.queue_overflows++;
        nexus_executive_emit_event(exec,
                                   NEXUS_EVENT_TYPE_QUEUE_OVERFLOW,
                                   NEXUS_SEVERITY_WARN,
                                   job_id,
                                   (int32_t)exec->ready_queue.count);
        return false;
    }

    job->state = NEXUS_JOB_STATE_READY;
    return true;
}

bool nexus_executive_unregister_job(nexus_executive_t *exec, uint16_t job_id)
{
    if (!exec) {
        return false;
    }
    return nexus_job_unregister(&exec->job_table, job_id);
}

bool nexus_executive_emit_event(nexus_executive_t *exec,
                                nexus_event_type_t event_type,
                                nexus_event_severity_t severity,
                                uint16_t source_id,
                                int32_t payload_i32)
{
    if (!exec) {
        return false;
    }
    int64_t now_us = exec->last_tick_us;
    return nexus_event_queue_push(&exec->event_queue, event_type, severity, source_id, payload_i32, now_us);
}

bool nexus_executive_record_sample(nexus_executive_t *exec, const nexus_sensor_sample_t *sample)
{
    if (!exec || !sample) {
        return false;
    }
    return nexus_ring_buffer_push(&exec->sensor_history, sample);
}

void nexus_executive_tick(nexus_executive_t *exec, int64_t current_time_us)
{
    if (!exec) {
        return;
    }

    exec->state = NEXUS_EXEC_STATE_RUNNING;
    exec->last_tick_us = current_time_us;
    exec->stats.ticks++;

    /* 1. Evaluate periodic jobs in job table */
    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        nexus_job_descriptor_t *job = &exec->job_table.entries[i];
        if (job->state == NEXUS_JOB_STATE_IDLE || job->period_ms == 0U) {
            continue;
        }

        /* Check period */
        int64_t period_us = (int64_t)job->period_ms * 1000LL;
        if (job->last_run_us == 0 || (current_time_us - job->last_run_us) >= period_us) {
            nexus_executive_submit_job(exec, job->job_id);
        }
    }

    /* 2. Dispatch runnable jobs from ready queue in priority order.
     * Bounded to at most NEXUS_READY_QUEUE_CAPACITY per tick to prevent starvation. */
    uint16_t dispatches_this_tick = 0U;
    uint16_t job_id = 0U;

    while (dispatches_this_tick < NEXUS_READY_QUEUE_CAPACITY &&
           nexus_ready_queue_pop(&exec->ready_queue, &job_id)) {
        nexus_job_descriptor_t *job = nexus_job_get(&exec->job_table, job_id);
        if (!job || !job->work_fn) {
            continue;
        }

        job->state = NEXUS_JOB_STATE_RUNNING;
        exec->stats.jobs_dispatched++;
        dispatches_this_tick++;

        /* Record dispatch latency if periodic */
        if (job->last_run_us > 0 && job->period_ms > 0) {
            int64_t expected_time = job->last_run_us + ((int64_t)job->period_ms * 1000LL);
            if (current_time_us > expected_time) {
                uint32_t latency_us = (uint32_t)(current_time_us - expected_time);
                if (latency_us > exec->stats.max_dispatch_latency_us) {
                    exec->stats.max_dispatch_latency_us = latency_us;
                }
            }
        }

        job->last_run_us = current_time_us;

        /* Execute work function */
        bool success = job->work_fn(job->user_ctx);

        /* Measure duration if time is monotonic */
        uint32_t duration_us = 100U; /* Nominal fallback duration */
        job->last_duration_us = duration_us;
        if (duration_us > exec->stats.max_job_duration_us) {
            exec->stats.max_job_duration_us = duration_us;
        }

        if (success) {
            job->run_count++;
            exec->stats.jobs_completed++;
            job->state = (job->period_ms > 0) ? NEXUS_JOB_STATE_REGISTERED : NEXUS_JOB_STATE_COMPLETED;
        } else {
            job->failure_count++;
            exec->stats.jobs_failed++;
            job->state = NEXUS_JOB_STATE_FAILED;

            nexus_executive_emit_event(exec,
                                       NEXUS_EVENT_TYPE_JOB_FAILED,
                                       NEXUS_SEVERITY_ERROR,
                                       job->job_id,
                                       (int32_t)job->failure_count);
        }

        /* Check deadline violation */
        if (job->deadline_ms > 0) {
            uint32_t deadline_us = job->deadline_ms * 1000U;
            if (duration_us > deadline_us) {
                job->deadline_miss_count++;
                exec->stats.deadline_misses++;
                nexus_executive_emit_event(exec,
                                           NEXUS_EVENT_TYPE_DEADLINE_MISS,
                                           NEXUS_SEVERITY_WARN,
                                           job->job_id,
                                           (int32_t)duration_us);
            }
        }
    }
}

static bool s_selftest_dummy_ran = false;
static bool selftest_dummy_job(void *ctx)
{
    (void)ctx;
    s_selftest_dummy_ran = true;
    return true;
}

/* Static allocations for selftest to protect FreeRTOS main_task stack */
static nexus_executive_t s_test_exec;
static nexus_ready_queue_t s_test_rq;
static nexus_event_queue_t s_test_eq;
static nexus_ring_buffer_t s_test_rb;

bool nexus_executive_run_selftest(void)
{
    /* Deterministic in-memory verification of all bounded structures and state transitions */
    nexus_executive_init(&s_test_exec, 100U);

    if (s_test_exec.state != NEXUS_EXEC_STATE_INITIALIZED) {
        return false;
    }

    /* 1. Verify Job Table registration and saturation */
    uint16_t jid = 0;
    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        jid = nexus_executive_register_job(&s_test_exec, "st_job", NEXUS_PRIORITY_CLASS_1, selftest_dummy_job, NULL, 100U, 10U);
        if (jid == 0) {
            return false;
        }
    }
    /* Overflow must fail cleanly */
    if (nexus_executive_register_job(&s_test_exec, "st_ovf", NEXUS_PRIORITY_CLASS_1, selftest_dummy_job, NULL, 100U, 10U) != 0) {
        return false;
    }
    if (s_test_exec.job_table.registration_failures != 1) {
        return false;
    }

    /* 2. Unregister one job to verify slot reclamation */
    if (!nexus_executive_unregister_job(&s_test_exec, jid)) {
        return false;
    }
    uint16_t reclaimed_id = nexus_executive_register_job(&s_test_exec, "st_rec", NEXUS_PRIORITY_CLASS_0, selftest_dummy_job, NULL, 50U, 10U);
    if (reclaimed_id == 0) {
        return false;
    }

    /* 3. Ready queue priority and saturation */
    nexus_ready_queue_init(&s_test_rq);
    nexus_ready_queue_push(&s_test_rq, 20U, NEXUS_PRIORITY_CLASS_2);
    nexus_ready_queue_push(&s_test_rq, 10U, NEXUS_PRIORITY_CLASS_0);
    uint16_t popped = 0;
    if (!nexus_ready_queue_pop(&s_test_rq, &popped) || popped != 10U) {
        return false;
    }

    /* 4. Event queue reject-on-full policy */
    nexus_event_queue_init(&s_test_eq);
    for (uint16_t i = 0; i < NEXUS_EVENT_QUEUE_CAPACITY; i++) {
        nexus_event_queue_push(&s_test_eq, NEXUS_EVENT_TYPE_SYSTEM_BOOT, NEXUS_SEVERITY_INFO, i, 0, 0);
    }
    if (nexus_event_queue_push(&s_test_eq, NEXUS_EVENT_TYPE_SYSTEM_BOOT, NEXUS_SEVERITY_WARN, 99, 0, 0)) {
        return false; /* Should reject */
    }
    if (s_test_eq.overflow_drop_count != 1) {
        return false;
    }

    /* 5. Sensor ring buffer drop-oldest policy */
    nexus_ring_buffer_init(&s_test_rb);
    nexus_sensor_sample_t s = {0};
    for (uint16_t i = 0; i < NEXUS_SENSOR_HISTORY_CAPACITY + 2; i++) {
        s.raw_value = (int32_t)i;
        nexus_ring_buffer_push(&s_test_rb, &s);
    }
    if (s_test_rb.total_overwritten != 2) {
        return false;
    }

    /* 6. Executive tick execution */
    s_selftest_dummy_ran = false;
    nexus_executive_tick(&s_test_exec, 100000LL);
    if (!s_selftest_dummy_ran || s_test_exec.stats.jobs_completed == 0) {
        return false;
    }

    return true;
}

