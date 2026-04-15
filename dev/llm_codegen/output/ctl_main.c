#include "ctl_main.h"
#include "ctl/component/motor_control/suite_pmsm/pmsm_ctrl.h"
#include "ctl/component/motor_control/mechanical_loop/basic_mech_ctrl.h"
#include "ctl/component/motor_control/basic/mtr_protection.h"
#include "ctl/component/motor_control/interface/encoder.h"
#include "ctl/component/hardware_preset/pmsm_motor/GBM2804H_100T.h"
#include "ctl/component/interface/gmp_standard_interface.h"
#include "ctl/component/interface/pwm_channel.h"
#include "ctl/component/interface/adc_ptr_channel.h"
#include "ctl/component/motor_control.h"
#include "ctl/component/intrinsic.h"
#include "ctl/component/interface/CiA402.h"

/* Global controller instances */
pmsm_controller_t pmsm_ctrl;
ctl_mech_ctrl_t mech_ctrl;
ctl_mtr_protect_t mtr_protect;
pos_encoder_t encoder;
ptr_adc_channel_t adc_channel;
pwm_tri_channel_t pwm_channel;
ctl_std_interface_t std_interface;

/* Local variables */
static cia402_state_t cia402_state;
static uint8_t pwm_enabled = 0;

/* Forward declarations */
static void apply_tunable_params(void);
static void init_cia402(void);
static void init_motor_protection_path(void);

void ctl_init(void)
{
    /* Initialize libraries first */
    ctl_init_motor_control_lib();
    ctl_init_intrinsic_lib();
    
    /* Initialize motor parameters */
    ctl_init_motor_params(&motor_params);
    
    /* Initialize standard interface */
    ctl_init_std_interface(&std_interface);
    
    /* Initialize encoder */
    ctl_init_pos_encoder(&encoder);
    
    /* Initialize ADC channel */
    ctl_init_ptr_adc_channel(&adc_channel);
    
    /* Initialize PWM channel */
    ctl_init_pwm_tri_channel(&pwm_channel);
    
    /* Initialize mechanical controller */
    ctl_init_mech_ctrl(&mech_ctrl);
    
    /* Initialize PMSM controller */
    ctl_init_pmsm_ctrl(&pmsm_ctrl);
    
    /* Initialize motor protection */
    ctl_init_mtr_protect(&mtr_protect);
    
    /* Initialize CiA402 state machine */
    init_cia402();
    
    /* Initialize motor protection path */
    init_motor_protection_path();
    
    /* Attach components */
    ctl_attach_mech_ctrl(&mech_ctrl, &encoder.encif, &encoder.spdif);
    ctl_attach_pmsm_output(&pmsm_ctrl, &pwm_channel.pwm_if);
    
    /* Link motor parameters to PMSM controller */
    pmsm_ctrl.motor_params = &motor_params;
    
    /* Link standard interface to PMSM controller */
    pmsm_ctrl.command_if = &std_interface.command_signals;
    
    /* Link encoder to PMSM controller */
    pmsm_ctrl.position_feedback = &encoder.encif;
    
    /* Link ADC to PMSM controller */
    pmsm_ctrl.current_feedback = &adc_channel.control_port;
    
    /* Link mechanical controller to PMSM controller */
    pmsm_ctrl.current_reference = &mech_ctrl.current_ref;
    
    /* Link PMSM controller to motor protection */
    mtr_protect.protection_signals = &pmsm_ctrl.protection_signals;
    
    /* Link motor protection to PWM channel */
    pwm_channel.protection_override = &mtr_protect.pwm_override;
    
    /* Bind tunable parameter apply hook */
    ctl_bind_param_apply_hook(apply_tunable_params);
    
    /* Apply initial tunable parameters */
    apply_tunable_params();
    
    /* Clear all controllers */
    clear_all_controllers();
}

void ctl_mainloop(void)
{
    /* Update ADC readings */
    ctl_step_ptr_adc_channel(&adc_channel);
    
    /* Update encoder position */
    ctl_step_pos_encoder(&encoder, 0); /* Raw value to be filled by hardware */
    
    /* Update speed calculation */
    ctl_step_spd_calc(&encoder.spd_calc);
    
    /* Execute fast loop controllers */
    ctl_dispatch_fast_loop();
    
    /* Update PWM outputs if enabled */
    if (pwm_enabled)
    {
        ctl_step_pwm_tri_channel(&pwm_channel, &pmsm_ctrl.pwm_out.duty);
    }
    
    /* Update CiA402 state machine */
    ctl_step_cia402(&cia402_state, &std_interface.enable);
    
    /* Execute protection task */
    tsk_protect();
}

void clear_all_controllers(void)
{
    ctl_clear_pmsm_ctrl(&pmsm_ctrl);
    ctl_clear_mech_ctrl(&mech_ctrl);
    ctl_clear_mtr_protect(&mtr_protect);
    
    pmsm_ctrl.flag_enable_output = 0;
    std_interface.enable = 0;
    
    ctl_disable_pwm();
}

void tsk_protect(void)
{
    /* Check motor protection conditions */
    ctl_step_mtr_protect_fast(&mtr_protect);
    
    /* If protection triggered, disable PWM */
    if (mtr_protect.fault_status != 0)
    {
        ctl_disable_pwm();
        std_interface.enable = 0;
        pmsm_ctrl.flag_enable_output = 0;
    }
}

void ctl_enable_pwm(void)
{
    if (mtr_protect.fault_status == 0)
    {
        pwm_enabled = 1;
        pmsm_ctrl.flag_enable_output = 1;
        ctl_enable_pwm_hardware(&pwm_channel);
    }
}

void ctl_disable_pwm(void)
{
    pwm_enabled = 0;
    pmsm_ctrl.flag_enable_output = 0;
    ctl_disable_pwm_hardware(&pwm_channel);
}

static void apply_tunable_params(void)
{
    /* Apply voltage limits */
    pmsm_ctrl.voltage_limit_max = ctl_get_tunable_param("voltage_limit_max");
    pmsm_ctrl.voltage_limit_min = ctl_get_tunable_param("voltage_limit_min");
    
    /* Apply current limits */
    pmsm_ctrl.current_limit_max = ctl_get_tunable_param("current_limit_max");
    pmsm_ctrl.current_limit_min = ctl_get_tunable_param("current_limit_min");
    
    /* Apply mechanical controller parameters */
    mech_ctrl.velocity_kp = ctl_get_tunable_param("velocity_kp");
    mech_ctrl.velocity_ki = ctl_get_tunable_param("velocity_ki");
    mech_ctrl.position_kp = ctl_get_tunable_param("position_kp");
    
    /* Apply protection thresholds */
    mtr_protect.overcurrent_threshold = ctl_get_tunable_param("overcurrent_threshold");
    mtr_protect.overvoltage_threshold = ctl_get_tunable_param("overvoltage_threshold");
    mtr_protect.overtemp_threshold = ctl_get_tunable_param("overtemp_threshold");
}

static void init_cia402(void)
{
    ctl_init_cia402(&cia402_state);
    cia402_state.target_state = CIA402_STATE_OPERATION_ENABLED;
    cia402_state.current_state = CIA402_STATE_SWITCH_ON_DISABLED;
}

static void init_motor_protection_path(void)
{
    /* Attach protection inputs */
    ctl_attach_mtr_protect_port(&mtr_protect,
                               &adc_channel.dc_voltage,
                               &adc_channel.current_meas,
                               &pmsm_ctrl.current_ref,
                               &adc_channel.temp_motor,
                               &adc_channel.temp_inverter);
    
    /* Set default protection parameters */
    mtr_protect.overcurrent_threshold = 1.2f;  /* 120% of rated current */
    mtr_protect.overvoltage_threshold = 1.15f; /* 115% of nominal voltage */
    mtr_protect.overtemp_threshold = 85.0f;    /* 85°C */
    mtr_protect.undervoltage_threshold = 0.85f; /* 85% of nominal voltage */
    
    /* Initialize fault status */
    mtr_protect.fault_status = 0;
}
