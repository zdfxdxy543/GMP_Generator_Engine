#ifndef CTL_MAIN_H
#define CTL_MAIN_H

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

/* Controller global instances */
extern pmsm_controller_t pmsm_ctrl;
extern ctl_mech_ctrl_t mech_ctrl;
extern ctl_mtr_protect_t mtr_protect;
extern pos_encoder_t encoder;
extern ptr_adc_channel_t adc_channel;
extern pwm_tri_channel_t pwm_channel;
extern ctl_std_interface_t std_interface;

/* Function prototypes */
void ctl_init(void);
void ctl_mainloop(void);
void clear_all_controllers(void);
void tsk_protect(void);
void ctl_enable_pwm(void);
void ctl_disable_pwm(void);

/* Inline dispatch function */
static inline void ctl_dispatch_fast_loop(void)
{
    ctl_step_mech_ctrl(&mech_ctrl);
    ctl_step_pmsm_ctrl(&pmsm_ctrl);
    ctl_step_mtr_protect_fast(&mtr_protect);
}

#endif /* CTL_MAIN_H */
