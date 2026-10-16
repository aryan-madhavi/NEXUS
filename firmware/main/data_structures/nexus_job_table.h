#ifndef NEXUS_JOB_TABLE_H
#define NEXUS_JOB_TABLE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_JOB_TABLE_CAPACITY 16U
#define NEXUS_JOB_NAME_MAX_LEN   16U

typedef enum {
    NEXUS_JOB_STATE_IDLE = 0,
    NEXUS_JOB_STATE_REGISTERED,
    NEXUS_JOB_STATE_READY,
    NEXUS_JOB_STATE_RUNNING,
    NEXUS_JOB_STATE_COMPLETED,
    NEXUS_JOB_STATE_FAILED,
    NEXUS_JOB_STATE_TIMEOUT
} nexus_job_state_t;

typedef enum {
    NEXUS_PRIORITY_CLASS_0 = 0, /* Critical: Executive tick, health, fault handling */
    NEXUS_PRIORITY_CLASS_1 = 1, /* Sensor acquisition and mux transactions */
    NEXUS_PRIORITY_CLASS_2 = 2  /* Telemetry formatting, reporting, diagnostics */
} nexus_priority_class_t;

#define NEXUS_PRIORITY_CLASS_COUNT 3U

typedef struct nexus_job_descriptor nexus_job_descriptor_t;

/* Callback signature for executing an application job.
 * Returns true if completed successfully, false on error. */
typedef bool (*nexus_job_fn_t)(void *user_ctx);

struct nexus_job_descriptor {
    uint16_t job_id;
    char name[NEXUS_JOB_NAME_MAX_LEN];
    nexus_priority_class_t priority;
    nexus_job_state_t state;
    nexus_job_fn_t work_fn;
    void *user_ctx;
    uint32_t period_ms;          /* 0 for one-shot, >0 for periodic */
    uint32_t deadline_ms;        /* Max permitted callback execution duration (ms); 0 if unspecified */
    uint32_t run_count;          /* Successful runs */
    uint32_t failure_count;      /* Failed runs */
    uint32_t deadline_miss_count;/* Runs that exceeded execution budget */
    int64_t last_run_us;         /* Timestamp of last execution start (microseconds) */
    uint32_t last_duration_us;   /* Duration of last execution (microseconds) */
};

typedef struct {
    nexus_job_descriptor_t entries[NEXUS_JOB_TABLE_CAPACITY];
    uint16_t active_count;
    uint16_t next_job_id;
    uint32_t registration_failures;
} nexus_job_table_t;

void nexus_job_table_init(nexus_job_table_t *table);

/* Register a job into a free slot. Returns assigned job_id (1..65535) or 0 on failure. */
uint16_t nexus_job_register(nexus_job_table_t *table,
                            const char *name,
                            nexus_priority_class_t priority,
                            nexus_job_fn_t work_fn,
                            void *user_ctx,
                            uint32_t period_ms,
                            uint32_t deadline_ms);

/* Unregister / reclaim slot. Returns true if reclaimed, false if not found. */
bool nexus_job_unregister(nexus_job_table_t *table, uint16_t job_id);

nexus_job_descriptor_t *nexus_job_get(nexus_job_table_t *table, uint16_t job_id);

nexus_job_descriptor_t *nexus_job_get_by_index(nexus_job_table_t *table, uint16_t index);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_JOB_TABLE_H */
