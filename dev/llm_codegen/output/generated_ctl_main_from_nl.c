// generated ctl_main-style code body

void ctl_init(void)
{
    ctl_step_ptr_adc_channel(&adc_channel_ia);
    ctl_step_ptr_adc_channel(&adc_channel_ib);
    ctl_step_pos_encoder(&encoder, 0);
    ctl_step_spwm_modulator(&pwm_modulator);
}

GMP_STATIC_INLINE void ctl_dispatch(void)
{
    ctl_step_current_controller(&current_controller);
    ctl_step_mech_ctrl(&speed_controller);
    ctl_step_mtr_protect_fast(&motor_protection);
    // fault body from schedule
    ctl_step_trip_protector(&trip_protector);

}

void ctl_mainloop(void)
{
    cia402_dispatch(&cia402_sm);
}
