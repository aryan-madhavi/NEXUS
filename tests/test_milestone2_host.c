#include <stdio.h>
#include <assert.h>
#include <string.h>

#include "data_structures/nexus_job_table.h"
#include "data_structures/nexus_ready_queue.h"
#include "data_structures/nexus_event_queue.h"
#include "data_structures/nexus_ring_buffer.h"
#include "executive/nexus_executive.h"

static int s_dummy_run_count = 0;
static bool dummy_job_fn(void *user_ctx)
{
    (void)user_ctx;
    s_dummy_run_count++;
    return true;
}

static bool failing_job_fn(void *user_ctx)
{
    (void)user_ctx;
    return false;
}

static void test_job_table(void)
{
    printf("  [TEST] nexus_job_table...\n");
    nexus_job_table_t table;
    nexus_job_table_init(&table);

    assert(table.active_count == 0);
    assert(table.registration_failures == 0);

    /* Register up to capacity */
    uint16_t ids[NEXUS_JOB_TABLE_CAPACITY];
    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        ids[i] = nexus_job_register(&table, "test_job", NEXUS_PRIORITY_CLASS_1, dummy_job_fn, NULL, 1000, 50);
        assert(ids[i] > 0);
        assert(table.active_count == i + 1);
    }

    /* Capacity exhaustion test */
    uint16_t overflow_id = nexus_job_register(&table, "overflow", NEXUS_PRIORITY_CLASS_1, dummy_job_fn, NULL, 1000, 50);
    assert(overflow_id == 0);
    assert(table.registration_failures == 1);

    /* Lookup */
    nexus_job_descriptor_t *job = nexus_job_get(&table, ids[0]);
    assert(job != NULL);
    assert(strcmp(job->name, "test_job") == 0);

    /* Unregister and slot reclamation */
    assert(nexus_job_unregister(&table, ids[0]));
    assert(table.active_count == NEXUS_JOB_TABLE_CAPACITY - 1);
    assert(nexus_job_get(&table, ids[0]) == NULL);

    /* Re-register into reclaimed slot */
    uint16_t new_id = nexus_job_register(&table, "reclaimed", NEXUS_PRIORITY_CLASS_0, dummy_job_fn, NULL, 500, 10);
    assert(new_id > 0);
    assert(table.active_count == NEXUS_JOB_TABLE_CAPACITY);

    printf("  [PASS] nexus_job_table\n");
}

static void test_ready_queue(void)
{
    printf("  [TEST] nexus_ready_queue...\n");
    nexus_ready_queue_t queue;
    nexus_ready_queue_init(&queue);

    assert(nexus_ready_queue_is_empty(&queue));
    assert(!nexus_ready_queue_is_full(&queue));

    /* Insert out of order: Priority 2 (job 20), Priority 0 (job 10), Priority 1 (job 15), Priority 0 (job 11) */
    assert(nexus_ready_queue_push(&queue, 20, NEXUS_PRIORITY_CLASS_2));
    assert(nexus_ready_queue_push(&queue, 10, NEXUS_PRIORITY_CLASS_0));
    assert(nexus_ready_queue_push(&queue, 15, NEXUS_PRIORITY_CLASS_1));
    assert(nexus_ready_queue_push(&queue, 11, NEXUS_PRIORITY_CLASS_0));

    assert(nexus_ready_queue_count(&queue) == 4);

    /* Expected pop order:
     * Priority 0: job 10 (first P0)
     * Priority 0: job 11 (second P0, FIFO preserved)
     * Priority 1: job 15
     * Priority 2: job 20 */
    uint16_t popped_id = 0;
    assert(nexus_ready_queue_pop(&queue, &popped_id) && popped_id == 10);
    assert(nexus_ready_queue_pop(&queue, &popped_id) && popped_id == 11);
    assert(nexus_ready_queue_pop(&queue, &popped_id) && popped_id == 15);
    assert(nexus_ready_queue_pop(&queue, &popped_id) && popped_id == 20);
    assert(nexus_ready_queue_is_empty(&queue));

    /* Test fill to capacity and overflow count */
    for (uint16_t i = 1; i <= NEXUS_READY_QUEUE_CAPACITY; i++) {
        assert(nexus_ready_queue_push(&queue, i, NEXUS_PRIORITY_CLASS_1));
    }
    assert(nexus_ready_queue_is_full(&queue));
    assert(queue.overflow_count == 0);

    /* Push when full -> should fail and increment overflow count */
    assert(!nexus_ready_queue_push(&queue, 999, NEXUS_PRIORITY_CLASS_0));
    assert(queue.overflow_count == 1);
    assert(queue.high_water_mark == NEXUS_READY_QUEUE_CAPACITY);

    printf("  [PASS] nexus_ready_queue\n");
}

static void test_event_queue(void)
{
    printf("  [TEST] nexus_event_queue...\n");
    nexus_event_queue_t eq;
    nexus_event_queue_init(&eq);

    assert(nexus_event_queue_is_empty(&eq));

    /* Push events up to capacity */
    for (uint16_t i = 0; i < NEXUS_EVENT_QUEUE_CAPACITY; i++) {
        assert(nexus_event_queue_push(&eq, NEXUS_EVENT_TYPE_SYSTEM_BOOT, NEXUS_SEVERITY_INFO, i, (int32_t)i, 1000LL * i));
    }
    assert(nexus_event_queue_is_full(&eq));
    assert(eq.overflow_drop_count == 0);

    /* Push when full -> must be rejected and increment overflow_drop_count */
    assert(!nexus_event_queue_push(&eq, NEXUS_EVENT_TYPE_FAULT_LATCHED, NEXUS_SEVERITY_ERROR, 99, -1, 99999LL));
    assert(eq.overflow_drop_count == 1);

    /* Pop events and verify FIFO sequence */
    nexus_event_t ev;
    for (uint16_t i = 0; i < NEXUS_EVENT_QUEUE_CAPACITY; i++) {
        assert(nexus_event_queue_pop(&eq, &ev));
        assert(ev.source_id == i);
        assert(ev.payload_i32 == (int32_t)i);
    }
    assert(nexus_event_queue_is_empty(&eq));

    /* Wraparound test: push and pop in a cycle */
    for (int cycle = 0; cycle < 50; cycle++) {
        assert(nexus_event_queue_push(&eq, NEXUS_EVENT_TYPE_JOB_COMPLETED, NEXUS_SEVERITY_DEBUG, (uint16_t)cycle, cycle, 100LL));
        assert(nexus_event_queue_pop(&eq, &ev));
        assert(ev.source_id == (uint16_t)cycle);
    }

    printf("  [PASS] nexus_event_queue\n");
}

static void test_sensor_history_ring_buffer(void)
{
    printf("  [TEST] nexus_ring_buffer...\n");
    nexus_ring_buffer_t rb;
    nexus_ring_buffer_init(&rb);

    assert(nexus_ring_buffer_is_empty(&rb));

    /* Push up to capacity */
    for (uint16_t i = 0; i < NEXUS_SENSOR_HISTORY_CAPACITY; i++) {
        nexus_sensor_sample_t s = {
            .sensor_id = 1,
            .flags = NEXUS_SAMPLE_FLAG_VALID,
            .channel = 0,
            .timestamp_us = 1000LL * i,
            .raw_value = (int32_t)(100 + i),
            .processed_value = (int32_t)(100 + i)
        };
        assert(nexus_ring_buffer_push(&rb, &s));
    }
    assert(nexus_ring_buffer_is_full(&rb));
    assert(rb.total_overwritten == 0);

    /* Push when full -> must overwrite oldest (drop-oldest policy) */
    nexus_sensor_sample_t s_new = {
        .sensor_id = 1,
        .flags = NEXUS_SAMPLE_FLAG_VALID,
        .channel = 0,
        .timestamp_us = 99999LL,
        .raw_value = 999,
        .processed_value = 999
    };
    assert(nexus_ring_buffer_push(&rb, &s_new));
    assert(rb.total_overwritten == 1);
    assert(nexus_ring_buffer_count(&rb) == NEXUS_SENSOR_HISTORY_CAPACITY);

    /* Peek newest */
    nexus_sensor_sample_t peek_sample;
    assert(nexus_ring_buffer_peek_newest(&rb, &peek_sample));
    assert(peek_sample.raw_value == 999);

    /* Peek oldest should now be i=1 sample (since i=0 was overwritten) */
    assert(nexus_ring_buffer_peek_oldest(&rb, &peek_sample));
    assert(peek_sample.raw_value == 101);

    printf("  [PASS] nexus_ring_buffer\n");
}

static void test_executive_lifecycle_and_dispatch(void)
{
    printf("  [TEST] nexus_executive_lifecycle_and_dispatch...\n");
    nexus_executive_t exec;
    nexus_executive_init(&exec, 100);

    assert(exec.state == NEXUS_EXEC_STATE_INITIALIZED);

    /* Register one periodic dummy job and one failing job */
    s_dummy_run_count = 0;
    uint16_t j1 = nexus_executive_register_job(&exec, "dummy_p1", NEXUS_PRIORITY_CLASS_1, dummy_job_fn, NULL, 100, 50);
    uint16_t j2 = nexus_executive_register_job(&exec, "fail_p0", NEXUS_PRIORITY_CLASS_0, failing_job_fn, NULL, 0, 50);

    assert(j1 > 0 && j2 > 0);

    /* Manual submit of j2 */
    assert(nexus_executive_submit_job(&exec, j2));

    /* Tick at t = 100ms (100,000 us) */
    nexus_executive_tick(&exec, 100000LL);

    assert(exec.state == NEXUS_EXEC_STATE_RUNNING);
    assert(exec.stats.ticks == 1);
    /* j2 (P0) and j1 (P1 periodic) should have both dispatched */
    assert(exec.stats.jobs_dispatched == 2);
    assert(exec.stats.jobs_completed == 1); /* j1 passed */
    assert(exec.stats.jobs_failed == 1);    /* j2 failed */
    assert(s_dummy_run_count == 1);

    /* Tick again before period -> j1 should not dispatch yet */
    nexus_executive_tick(&exec, 150000LL);
    assert(exec.stats.ticks == 2);
    assert(s_dummy_run_count == 1);

    /* Tick after period (at t = 200ms) -> j1 should dispatch again */
    nexus_executive_tick(&exec, 200000LL);
    assert(exec.stats.ticks == 3);
    assert(s_dummy_run_count == 2);

    printf("  [PASS] nexus_executive_lifecycle_and_dispatch\n");
}

int main(void)
{
    printf("========================================\n");
    printf("NEXUS Milestone 2 Host Unit Test Suite\n");
    printf("========================================\n");

    test_job_table();
    test_ready_queue();
    test_event_queue();
    test_sensor_history_ring_buffer();
    test_executive_lifecycle_and_dispatch();

    printf("========================================\n");
    printf("ALL HOST UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("========================================\n");
    return 0;
}
