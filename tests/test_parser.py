from gmp_generator_engine.parser import parse_requirement


def test_parse_requirement_robot_position() -> None:
    req = parse_requirement("机器人位置控制，要求低纹波和快速响应")
    assert req.scenario == "robotics"
    assert req.control_mode == "position"
    assert "current_ripple_target" in req.constraints
