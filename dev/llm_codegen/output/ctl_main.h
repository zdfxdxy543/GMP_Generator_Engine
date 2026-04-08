#ifndef CTL_MAIN_H
#define CTL_MAIN_H

#include "ctl/component/digital_power/dcdc/buck.h"
#include "ctl/component/interface/adc_ptr_channel.h"
#include "ctl/component/interface/pwm_channel.h"
#include "ctl/component/digital_power/basic/protectoion_strategy.h"
#include "ctl/component/intrinsic/protection/itoc_protection.h"
#include "ctl/component/interface/gmp_standard_interface.h"
#include "ctl/component/digital_power.h"
#include "ctl/component/intrinsic.h"

extern buck_ctrl_t buck_ctrl;
extern ptr_adc_channel_t adc_channel;
extern pwm_channel_t pwm_channel;
extern std_vip_protection_t protection;
extern ctl_trip_protector_t trip_protector;
extern std_interface_t std_interface;

void ctl_init(void);
void ctl_mainloop(void);
void clear_all_controllers(void);
void tsk_protect(void);
void ctl_enable_pwm(void);
void ctl_disable_pwm(void);

static inline void ctl_dispatch_fast_loop(void)
{
    ctl_step_buck_ctrl(&buck_ctrl);
    ctl_step_vip_protection(&protection);
}

static inline void ctl_dispatch_fault(void)
{
    ctl_step_trip_protector(&trip_protector);
}

#endif /* CTL_MAIN_H */
