#ifndef USER_MAIN_H
#define USER_MAIN_H

#include "ctl/scheduler.h"
#include "ctl/at_core.h"
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

void init(void);
void mainloop(void);
void setup_peripheral(void);
void ctl_init(void);
void ctl_mainloop(void);

#endif /* USER_MAIN_H */
