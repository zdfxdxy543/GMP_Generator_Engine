// init function body
{
    ERROR_UNRESOLVED_API(motor_if);
    ERROR_UNRESOLVED_API(spd_loop);
    ERROR_UNRESOLVED_API(pmsm_ctrl);
}

// fast_loop function body
{
    ctl_step_pmsm_ctrl(&pmsm_ctrl);
}

// slow_loop function body
{
    ctl_step_ladrc_spd_ctrl(&spd_loop);
}

// fault function body
{

}
