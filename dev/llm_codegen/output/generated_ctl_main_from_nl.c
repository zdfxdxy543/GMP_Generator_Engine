// generated ctl_main-style code body

void ctl_init(void)
{

}

GMP_STATIC_INLINE void ctl_dispatch(void)
{
    ctl_step_mech_ctrl(&mech_ctrl);
    ctl_step_current_controller(&mtr_ctrl);
    ctl_step_spwm_modulator(&spwm);
}

void ctl_mainloop(void)
{
    cia402_dispatch(&cia402_sm);
}
