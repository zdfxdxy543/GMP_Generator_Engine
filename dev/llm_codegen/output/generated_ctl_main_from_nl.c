// generated ctl_main-style code body

#include <gmp_core.h>
#include <xplt.peripheral.h>
#include <ctrl_settings.h>
#include <core/pm/function_scheduler.h>
#include <ctl/framework/cia402_state_machine.h>
#include <ctl/component/interface/adc_channel.h>
#include <ctl/component/interface/pwm_channel.h>
#include <ctl/component/interface/spwm_modulator.h>
#include <ctl/component/motor_control/basic/mtr_protection.h>
#include <ctl/component/motor_control/current_loop/foc_core.h>
#include <ctl/component/motor_control/mechanical_loop/basic_mech_ctrl.h>

// auto-generated instance declarations
// unresolved type for instance: motor_params (PMSM_GBM2804H_PARAMETERS__hardware_preset_pmsm_motor_gbm2804h_100t)
static uint8_t motor_params;
// unresolved type for instance: inverter_hal (hal_boostxl_drv8301__hardware_preset_inverter_3ph_ti_boostxl_drv8301)
static uint8_t inverter_hal;
static ptr_adc_channel_t adc_channel;
static pwm_channel_t pwm_channel;
static pos_encoder_t encoder;
static ctl_mech_ctrl_t speed_controller;
static mtr_current_ctrl_t current_controller;
static spwm_modulator_t modulator;
static ctl_mtr_protect_t motor_protection;
static ctl_trip_protector_t trip_protector;
// unresolved type for instance: mc_lib (CTL_MC_LIB__motor_control)
static uint8_t mc_lib;
// unresolved type for instance: intrinsic_lib (CTL_INTRINSIC_LIB__intrinsic)
static uint8_t intrinsic_lib;

// framework globals
cia402_sm_t cia402_sm;
volatile fast_gt flag_system_running = 0;
volatile fast_gt flag_error = 0;

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
    ctl_disable_pwm();
    init_cia402_state_machine(&cia402_sm);
    ctl_init_mtr_protect(&motor_protection, CONTROLLER_FREQUENCY);
    ctl_apply_tunable_params();

}

GMP_STATIC_INLINE void ctl_dispatch(void)
{
    ctl_step_ptr_adc_channel(&adc_channel);
    ctl_step_mech_ctrl(&speed_controller);
    ctl_step_current_controller(&current_controller);
    ctl_step_mtr_protect_fast(&motor_protection);
    // fault body from schedule
    ctl_step_trip_protector(&trip_protector);

}

void ctl_mainloop(void)
{
    cia402_dispatch(&cia402_sm);
}

void clear_all_controllers(void)
{
    // Optional clear hook: ctl_clear_ptr_adc_channel(&adc_channel);
    // Optional clear hook: ctl_clear_pwm_channel(&pwm_channel);
    // Optional clear hook: ctl_clear_pos_encoder(&encoder);
    // Optional clear hook: ctl_clear_mech_ctrl(&speed_controller);
    // Optional clear hook: ctl_clear_current_controller(&current_controller);
    // Optional clear hook: ctl_clear_spwm_modulator(&modulator);
    // Optional clear hook: ctl_clear_mtr_protect_fast(&motor_protection);
    // Optional clear hook: ctl_clear_trip_protector(&trip_protector);
}

gmp_task_status_t tsk_protect(gmp_task_t* tsk)
{
    GMP_UNUSED_VAR(tsk);
#ifdef ENABLE_MOTOR_FAULT_PROTECTION
    if (ctl_dispatch_mtr_protect_slow(&motor_protection))
    {
        cia402_fault_request(&cia402_sm);
    }
#endif
    return GMP_TASK_DONE;
}

void ctl_enable_pwm(void)
{
    ctl_fast_enable_output();
}

void ctl_disable_pwm(void)
{
    ctl_fast_disable_output();
}
