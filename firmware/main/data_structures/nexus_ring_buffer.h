#ifndef NEXUS_RING_BUFFER_H
#define NEXUS_RING_BUFFER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEXUS_SENSOR_HISTORY_CAPACITY 32U

typedef struct {
    uint16_t sensor_id;
    uint8_t flags;          /* Bit 0: valid, Bit 1: calibrated, Bit 2: error/stale */
    uint8_t channel;        /* Physical pin or CD4051 channel X0..X7 */
    int64_t timestamp_us;
    int32_t raw_value;
    int32_t processed_value;/* Fixed-point or scaled reading */
} nexus_sensor_sample_t;

#define NEXUS_SAMPLE_FLAG_VALID      (1U << 0)
#define NEXUS_SAMPLE_FLAG_CALIBRATED (1U << 1)
#define NEXUS_SAMPLE_FLAG_STALE      (1U << 2)
#define NEXUS_SAMPLE_FLAG_ERROR      (1U << 3)

/* Bounded circular ring buffer with documented DROP-OLDEST policy for telemetry history */
typedef struct {
    nexus_sensor_sample_t buffer[NEXUS_SENSOR_HISTORY_CAPACITY];
    uint16_t head;       /* Write index */
    uint16_t tail;       /* Read index */
    uint16_t count;
    uint32_t total_written;
    uint32_t total_overwritten; /* Count of samples dropped by drop-oldest policy */
} nexus_ring_buffer_t;

void nexus_ring_buffer_init(nexus_ring_buffer_t *rb);

/* Push sample with drop-oldest policy. Returns true always unless rb is NULL.
 * If buffer is full, the oldest unread element is overwritten and total_overwritten is incremented. */
bool nexus_ring_buffer_push(nexus_ring_buffer_t *rb, const nexus_sensor_sample_t *sample);

/* Pop the oldest sample. Returns true if popped into *out_sample, false if empty. */
bool nexus_ring_buffer_pop(nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample);

/* Peek the most recently written sample (newest). Returns false if empty. */
bool nexus_ring_buffer_peek_newest(const nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample);

/* Peek the oldest sample. Returns false if empty. */
bool nexus_ring_buffer_peek_oldest(const nexus_ring_buffer_t *rb, nexus_sensor_sample_t *out_sample);

bool nexus_ring_buffer_is_empty(const nexus_ring_buffer_t *rb);

bool nexus_ring_buffer_is_full(const nexus_ring_buffer_t *rb);

uint16_t nexus_ring_buffer_count(const nexus_ring_buffer_t *rb);

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_RING_BUFFER_H */
