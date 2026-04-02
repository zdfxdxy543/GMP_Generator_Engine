from __future__ import annotations

from copy import deepcopy

from .generator import build_structure
from .knowledge_base import ModuleCatalog
from .models import CandidateProgram, ControlStructure, LayerSelection, UserRequirement
from .simulator import SimulatorBackend


def _make_candidate(name: str, structure: ControlStructure, kp: float, ki: float) -> CandidateProgram:
    return CandidateProgram(
        name=name,
        structure=structure,
        params={"kp": kp, "ki": ki},
    )


def _mutate_structure(structure: ControlStructure, catalog: ModuleCatalog, round_idx: int) -> ControlStructure:
    new_layers = deepcopy(structure.layers)
    # Alternate observer module as a simple structure-iteration strategy.
    obs_index = 4
    alt = catalog.observer[round_idx % len(catalog.observer)]
    old = new_layers[obs_index]
    new_layers[obs_index] = LayerSelection(old.name, alt, dict(old.params))
    return ControlStructure(new_layers)


def optimize(
    req: UserRequirement,
    catalog: ModuleCatalog,
    simulator: SimulatorBackend,
    weights: dict[str, float],
    rounds: int = 3,
) -> CandidateProgram:
    base_structure = build_structure(req, catalog)
    population = [
        _make_candidate("base_a", base_structure, kp=1.8, ki=90.0),
        _make_candidate("base_b", base_structure, kp=2.2, ki=110.0),
    ]

    for i in range(rounds):
        scored: list[CandidateProgram] = []
        for candidate in population:
            metrics = simulator.run(candidate)
            candidate.metrics = metrics
            candidate.score = metrics.weighted_score(weights)
            scored.append(candidate)

        scored.sort(key=lambda x: x.score if x.score is not None else 1e9)
        survivors = scored[:1]

        # Structure iteration + parameter perturbation.
        parent = survivors[0]
        child_structure = _mutate_structure(parent.structure, catalog, i)
        child = _make_candidate(
            f"mutant_{i}",
            child_structure,
            kp=max(0.5, parent.params["kp"] + 0.15),
            ki=max(20.0, parent.params["ki"] + 10.0),
        )
        population = [parent, child]

    # Final evaluate and return best.
    for candidate in population:
        metrics = simulator.run(candidate)
        candidate.metrics = metrics
        candidate.score = metrics.weighted_score(weights)

    population.sort(key=lambda x: x.score if x.score is not None else 1e9)
    return population[0]
