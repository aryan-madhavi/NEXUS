#ifndef NEXUS_ADC_H
#define NEXUS_ADC_H

#include <stdint.h>
#include <stdbool.h>

#ifdef ESP_PLATFORM
#include "esp_adc/adc_oneshot.h"
#else
/* Minimal types for host compilation */
typedef enum {
    ADC_CHANNEL_0 = 0,
    ADC_CHANNEL_1,
    ADC_CHANNEL_2,
    ADC_CHANNEL_3,
    ADC_CHANNEL_4,
    ADC_CHANNEL_5,
    ADC_CHANNEL_6,
    ADC_CHANNEL_7,
} adc_channel_t;
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* GPIO assignments on classic ESP32 for ADC1 */
#define NEXUS_GPIO_LDR_ADC1      35U /* ADC1 Channel 7 (input-only) */
#define NEXUS_GPIO_CD4051_ADC1   36U /* ADC1 Channel 0 (input-only) */

#define NEXUS_ADC_CHANNEL_LDR    ADC_CHANNEL_7
#define NEXUS_ADC_CHANNEL_CD4051 ADC_CHANNEL_0

/* Initialize ADC1 unit and configure channels 7 (LDR) and 0 (CD4051).
 * Returns true if successful or already initialized. */
bool nexus_adc_init(void);

/* Read raw 12-bit ADC value (0..4095) from specified ADC1 channel. */
bool nexus_adc_read_raw(adc_channel_t channel, int *out_raw);

#ifndef ESP_PLATFORM
/* Host unit test helper to set mock ADC return value */
void nexus_adc_set_mock_raw(adc_channel_t channel, int mock_val, bool success);
#endif

#ifdef __cplusplus
}
#endif

#endif /* NEXUS_ADC_H */
