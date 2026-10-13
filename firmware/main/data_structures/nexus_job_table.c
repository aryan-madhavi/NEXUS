#include "nexus_job_table.h"
#include <string.h>

void nexus_job_table_init(nexus_job_table_t *table)
{
    if (!table) {
        return;
    }
    memset(table, 0, sizeof(*table));
    table->next_job_id = 1U;
}

uint16_t nexus_job_register(nexus_job_table_t *table,
                            const char *name,
                            nexus_priority_class_t priority,
                            nexus_job_fn_t work_fn,
                            void *user_ctx,
                            uint32_t period_ms,
                            uint32_t deadline_ms)
{
    if (!table || !work_fn || priority >= NEXUS_PRIORITY_CLASS_COUNT) {
        if (table) {
            table->registration_failures++;
        }
        return 0U;
    }

    if (table->active_count >= NEXUS_JOB_TABLE_CAPACITY) {
        table->registration_failures++;
        return 0U;
    }

    /* Find first free (IDLE) slot */
    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        if (table->entries[i].state == NEXUS_JOB_STATE_IDLE) {
            nexus_job_descriptor_t *job = &table->entries[i];
            memset(job, 0, sizeof(*job));

            uint16_t assigned_id = table->next_job_id++;
            if (table->next_job_id == 0U) {
                table->next_job_id = 1U; /* Avoid ID 0 */
            }

            job->job_id = assigned_id;
            job->priority = priority;
            job->state = NEXUS_JOB_STATE_REGISTERED;
            job->work_fn = work_fn;
            job->user_ctx = user_ctx;
            job->period_ms = period_ms;
            job->deadline_ms = deadline_ms;

            if (name) {
                strncpy(job->name, name, NEXUS_JOB_NAME_MAX_LEN - 1);
                job->name[NEXUS_JOB_NAME_MAX_LEN - 1] = '\0';
            } else {
                job->name[0] = '\0';
            }

            table->active_count++;
            return assigned_id;
        }
    }

    table->registration_failures++;
    return 0U;
}

bool nexus_job_unregister(nexus_job_table_t *table, uint16_t job_id)
{
    if (!table || job_id == 0U) {
        return false;
    }

    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        if (table->entries[i].job_id == job_id && table->entries[i].state != NEXUS_JOB_STATE_IDLE) {
            memset(&table->entries[i], 0, sizeof(table->entries[i]));
            if (table->active_count > 0) {
                table->active_count--;
            }
            return true;
        }
    }

    return false;
}

nexus_job_descriptor_t *nexus_job_get(nexus_job_table_t *table, uint16_t job_id)
{
    if (!table || job_id == 0U) {
        return NULL;
    }

    for (uint16_t i = 0; i < NEXUS_JOB_TABLE_CAPACITY; i++) {
        if (table->entries[i].job_id == job_id && table->entries[i].state != NEXUS_JOB_STATE_IDLE) {
            return &table->entries[i];
        }
    }

    return NULL;
}

nexus_job_descriptor_t *nexus_job_get_by_index(nexus_job_table_t *table, uint16_t index)
{
    if (!table || index >= NEXUS_JOB_TABLE_CAPACITY) {
        return NULL;
    }
    return &table->entries[index];
}
