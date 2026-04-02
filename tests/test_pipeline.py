from gmp_generator_engine.generator import generate_program
from gmp_generator_engine.knowledge_base import default_catalog
from gmp_generator_engine.parser import parse_requirement
from gmp_generator_engine.validators import validate_structure


def test_generate_and_validate() -> None:
    req = parse_requirement("PMSM速度控制")
    artifact = generate_program(req, default_catalog())
    result = validate_structure(artifact)
    assert result.ok
