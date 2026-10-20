#ifndef NEXUS_CD4051_H
#define NEXUS_CD4051_H

#include <stdint.h>
#include <stdbool.h>

#include "nexus_sensor_registry.h"
#include "nexus_executive.h"

#ifdef __cplusplus
extern "C" {
#endif

/* CD4051 control pins on EDU_ROBO V14 */
#define NEXUS_GPIO_CD4051_SEL_A 4U
#define NEXUS_GPIO_CD4051_SEL_B 2U
#define NEXUS_GPIO_CD4051_SEL_C 5U
#define NEXUS_GPIO_CD4051_OUT   36U /* ADC1 Channel 0, input-only */

#define NEXUS_CD4051_CHANNEL_COUNT 8U
#define NEXUS_CD4051_INTERVAL_MS   1000U
#define NEXUS_CD4051_SETTLE_US     20U

#define NEXUS_CD4051_CH_GAS_X0     0U
#define NEXUS_CD4051_CH_HALL_X1    1U

/* Initialize CD4051 GPIO select lines and register active mux channels with sensor registry. */
bool nexus_cd4051_init(nexus_sensor_registry_t *registry);

/* Select mux channel X0..X7 and wait for analog settling. Channel must be 0..7. */
bool nexus_cd4051_select_channel(uint8_t channel);

/* Atomically select channel, settle, and sample ADC1 Ch0. */
bool nexus_cd4051_sample_channel(uint8_t channel, int *out_raw);

/* Acquire X0 (HW-870 Gas/IR) analog sample, update registry, record to executive ring buffer. */
bool nexus_cd4051_acquire_x0(nexus_sensor_registry_t *registry,
                             nexus_executive_t *executive,
                             int64_t timestamp_us);

/* Acquire X1 (Hall Effect IC2) analog sample, update registry, record to executive ring buffer. */
bool nexus_cd4051_acquire_x1(nexus_sensor_registry_t *registry,
                             nexus_executive_t *executive,
                             int64_t timestamp_us);

/* Acquire all active channels (X0 and X1) sequentially with settling delay. */
bool nexus_cd4051_acquire_all(nexus_sensor_registry_t *registry,
                              nexus_executive_t *executive,
                              int64_t timestamp_us);

/* Executive Priority Class 1 job callback for CD4051 multi-channel acquisition */
bool nexus_cd4051_job_fn(void *user_ctx);

#ifndef ESP_PLATFORM
/* Host test helper to read current select lines */
void nexus_cd4051_get_mock_select_lines(uint8_t *out_a, uint8_t *out_b, uint8_t *out_c);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_CD4051_H */
