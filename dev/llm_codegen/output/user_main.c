#include "gmp_core.h"
#include "user_main.h"
#include "ctl_main.h"

/* Global instances */
buck_ctrl_t buck_ctrl;
ptr_adc_channel_t adc_channel;
pwm_channel_t pwm_channel;
std_vip_protection_t protection;
ctl_trip_protector_t trip_protector;
std_interface_t std_interface;

/* Scheduler task table */
static const gmp_task_t task_table[] = {
    { .task = tsk_protect, .period = 1000, .phase = 0, .enabled = 1 },
};

/* Scheduler instance */
static gmp_scheduler_t scheduler = {
    .tasks = task_table,
    .task_count = sizeof(task_table) / sizeof(task_table[0]),
    .tick = 0
};

void init(void)
{
    /* Initialize scheduler */
    gmp_scheduler_init(&scheduler);
    
    /* Initialize standard interface */
    ctl_init_std_interface(&std_interface);
    
    /* Initialize ADC channel */
    ctl_init_ptr_adc_channel(&adc_channel);
    
    /* Initialize PWM channel */
    ctl_init_pwm_channel(&pwm_channel);
    
    /* Initialize control modules */
    ctl_init();
}

void mainloop(void)
{
    /* Dispatch scheduler tasks */
    gmp_scheduler_dispatch(&scheduler);
    
    /* Execute control main loop */
    ctl_mainloop();
}

void setup_peripheral(void)
{
    /* Peripheral setup would go here */
}

void ctl_init(void)
{
    /* Initialize buck controller */
    ctl_init_buck_ctrl(&buck_ctrl);
    
    /* Initialize protection */
    ctl_init_vip_protection(&protection);
    
    /* Initialize trip protector */
    ctl_init_trip_protector(&trip_protector);
    
    /* Clear all controllers */
    clear_all_controllers();
}

void ctl_mainloop(void)
{
    /* Fast loop dispatch */
    ctl_dispatch_fast_loop();
    
    /* Fault dispatch */
    ctl_dispatch_fault();
    
    /* Non-blocking communication */
    if (ctl_check_comm_ready())
    {
        ctl_process_comm();
    }
}

void clear_all_controllers(void)
{
    /* Clear controller states */
    ctl_clear_buck_ctrl(&buck_ctrl);
    ctl_clear_vip_protection(&protection);
    ctl_clear_trip_protector(&trip_protector);
}

void tsk_protect(void)
{
    /* Protection task implementation */
    ctl_step_trip_protector(&trip_protector);
}

void ctl_enable_pwm(void)
{
    /* Enable PWM output */
    ctl_enable_pwm_channel(&pwm_channel);
}

void ctl_disable_pwm(void)
{
    /* Disable PWM output */
    ctl_disable_pwm_channel(&pwm_channel);
}
