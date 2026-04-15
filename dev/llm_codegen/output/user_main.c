#include "gmp_core.h"
#include "user_main.h"
#include "ctl_main.h"

/* Global object definitions */
pmsm_controller_t pmsm_ctrl;
ctl_mech_ctrl_t mech_ctrl;
ctl_mtr_protect_t mtr_protect;
pos_encoder_t encoder;
ptr_adc_channel_t adc_channel;
pwm_tri_channel_t pwm_channel;
ctl_std_interface_t std_interface;

/* Scheduler task table */
static const gmp_task_t task_table[] = {
    {
        .task_id = TASK_ID_PROTECT,
        .task_func = tsk_protect,
        .task_name = "tsk_protect",
        .task_priority = GMP_TASK_PRIORITY_HIGH,
        .task_period = 1000U,
        .task_enabled = true
    }
};

/* Scheduler configuration */
static gmp_scheduler_t scheduler = {
    .task_table = task_table,
    .task_count = sizeof(task_table) / sizeof(task_table[0]),
    .current_time = 0U
};

void setup_peripheral(void)
{
    /* Initialize hardware peripherals */
    ctl_init_ptr_adc_channel(&adc_channel);
    ctl_init_pwm_tri_channel(&pwm_channel);
    ctl_init_pos_encoder(&encoder);
    ctl_init_std_interface(&std_interface);
}

void ctl_init(void)
{
    /* Initialize motor control components */
    ctl_init_pmsm_ctrl(&pmsm_ctrl);
    ctl_init_mech_ctrl(&mech_ctrl);
    ctl_init_mtr_protect(&mtr_protect);
    
    /* Attach components */
    ctl_attach_pmsm_output(&pmsm_ctrl, &pwm_channel.tri_pwm_if);
    ctl_attach_mech_ctrl(&mech_ctrl, &encoder.encif, &encoder.spdif);
    ctl_attach_mtr_protect_port(&mtr_protect, NULL, NULL, NULL, NULL, NULL);
}

void init(void)
{
    /* Initialize scheduler */
    gmp_scheduler_init(&scheduler);
    
    /* Setup hardware */
    setup_peripheral();
    
    /* Initialize control system */
    ctl_init();
    
    /* Enable PWM output */
    ctl_enable_pwm();
}

void mainloop(void)
{
    /* Non-blocking communication check */
    if (gmp_uart_available() > 0) {
        uint8_t byte = gmp_uart_read();
        /* Minimal command processing */
        if (byte == 'E') {
            std_interface.enable = true;
        } else if (byte == 'D') {
            std_interface.enable = false;
        }
    }
    
    /* Execute fast control loop */
    ctl_dispatch_fast_loop();
    
    /* Dispatch scheduler tasks */
    gmp_scheduler_dispatch(&scheduler);
    
    /* Update scheduler time */
    scheduler.current_time++;
}

void tsk_protect(void)
{
    /* Protection task implementation */
    ctl_step_mtr_protect_fast(&mtr_protect);
    
    /* Check protection status and disable PWM if needed */
    if (mtr_protect.fault_status != 0) {
        ctl_disable_pwm();
    }
}
