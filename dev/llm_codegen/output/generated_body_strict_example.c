// init function body
{
    ERROR_UNRESOLVED_API(boost_ctrl);
    ERROR_UNRESOLVED_API(buck_ctrl);
}

// fast_loop function body
{
    ctl_step_boost_ctrl(&boost_ctrl);
    ctl_step_buck_ctrl(&buck_ctrl);
}

// slow_loop function body
{

}

// fault function body
{

}
