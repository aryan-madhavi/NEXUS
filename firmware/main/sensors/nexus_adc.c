#include "nexus_adc.h"

#ifdef ESP_PLATFORM
#include "esp_log.h"
#include "esp_err.h"

static const char *TAG = "nexus_adc";
static adc_oneshot_unit_handle_t s_adc1_handle = NULL;
static bool s_adc1_initialized = false;

bool nexus_adc_init(void)
{
    if (s_adc1_initialized) {
        return true;
    }

    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };

    esp_err_t err = adc_oneshot_new_unit(&init_config, &s_adc1_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_oneshot_new_unit failed: %s", esp_err_to_name(err));
        return false;
    }

    /* Configure 12dB attenuation for ~0..3.1V range on ADC1 Channel 7 (GPIO 35 - LDR) */
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };

    err = adc_oneshot_config_channel(s_adc1_handle, NEXUS_ADC_CHANNEL_LDR, &chan_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config LDR channel failed: %s", esp_err_to_name(err));
        return false;
    }

    /* Configure 12dB attenuation on ADC1 Channel 0 (GPIO 36 - CD4051) */
    err = adc_oneshot_config_channel(s_adc1_handle, NEXUS_ADC_CHANNEL_CD4051, &chan_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config CD4051 channel failed: %s", esp_err_to_name(err));
        return false;
    }

    s_adc1_initialized = true;
    ESP_LOGI(TAG, "ADC1 initialized for GPIO35 (ch7) and GPIO36 (ch0)");
    return true;
}

bool nexus_adc_read_raw(adc_channel_t channel, int *out_raw)
{
    if (!s_adc1_initialized || !s_adc1_handle || !out_raw) {
        return false;
    }

    esp_err_t err = adc_oneshot_read(s_adc1_handle, channel, out_raw);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "adc_oneshot_read(ch=%d) failed: %s", (int)channel, esp_err_to_name(err));
        return false;
    }

    return true;
}

#else
/* Host unit test mock implementation */
static int s_mock_adc_values[8] = { 0 };
static bool s_mock_adc_success[8] = { true, true, true, true, true, true, true, true };
static bool s_host_adc_init = false;

bool nexus_adc_init(void)
{
    s_host_adc_init = true;
    return true;
}

bool nexus_adc_read_raw(adc_channel_t channel, int *out_raw)
{
    if (!s_host_adc_init || !out_raw || (int)channel < 0 || (int)channel >= 8) {
        return false;
    }
    if (!s_mock_adc_success[(int)channel]) {
        return false;
    }
    *out_raw = s_mock_adc_values[(int)channel];
    return true;
}

void nexus_adc_set_mock_raw(adc_channel_t channel, int mock_val, bool success)
{
    if ((int)channel >= 0 && (int)channel < 8) {
        s_mock_adc_values[(int)channel] = mock_val;
        s_mock_adc_success[(int)channel] = success;
    }
}
#endif
