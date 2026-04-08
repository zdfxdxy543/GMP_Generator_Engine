// generated ctl_main-style code body

#include <stdbool.h>
#include <stdint.h>

// auto-generated instance declarations
// unresolved type for instance: pmsm_motor_params (PMSM_GBM2804H_PARAMETERS__hardware_preset_pmsm_motor_gbm2804h_100t)
// unresolved type for instance: inverter_hal (hal_boostxl_drv8301__hardware_preset_inverter_3ph_ti_boostxl_drv8301)
static ptr_adc_channel_t adc_channel_ia;
static ptr_adc_channel_t adc_channel_ib;
static pos_encoder_t encoder;
static spwm_modulator_t pwm_modulator;
static mtr_current_ctrl_t current_controller;
static ctl_mech_ctrl_t speed_controller;
static ctl_mtr_protect_t motor_protection;
static ctl_trip_protector_t trip_protector;

// no scalar tunable parameters were found in control.modules[*].params
typedef struct
{
    uint8_t reserved;
} ctl_tunable_params_t;

ctl_tunable_params_t g_ctl_tunable_params = { 0 };

void ctl_update_tunable_params(const ctl_tunable_params_t* src)
{
    if (!src) {
        return;
    }
    g_ctl_tunable_params = *src;
}

void ctl_apply_tunable_params(void)
{
    // Bind g_ctl_tunable_params to instance fields in your project-specific code.
    (void)g_ctl_tunable_params;
}

void ctl_init(void)
{
    ctl_apply_tunable_params();
    ctl_step_ptr_adc_channel(&adc_channel_ia);
    ctl_step_ptr_adc_channel(&adc_channel_ib);
    ctl_step_pos_encoder(&encoder, 0);
    ctl_step_spwm_modulator(&pwm_modulator);
}

GMP_STATIC_INLINE void ctl_dispatch(void)
{
    ctl_step_mech_ctrl(&speed_controller);
    ctl_step_mtr_protect_fast(&motor_protection);
    ctl_step_current_controller(&current_controller);
    // fault body from schedule
    ctl_step_trip_protector(&trip_protector);

}

void ctl_mainloop(void)
{
    cia402_dispatch(&cia402_sm);
}
