# Local Resolver Rules (module_id / canonical_id)

## Resolution Priority
1. If canonical_id is provided, match canonical_id exactly.
2. If only module_id is provided:
   - search exact module_id matches first;
   - then search group_ids matches as fallback;
   - for fast_loop or slow_loop, prefer candidates with non-empty step API.
3. If still ambiguous, stop generation and report all candidate canonical_id values.

## Recommended Input Strategy
- During architecture design, module_id can be used.
- Before generation, preprocess module_id to canonical_id so each module is unique.

## Minimal Resolver Output
- canonical_id
- file
- module_name
- api_contract.lifecycle
- api_contract.step
- api_contract.attach
- api_contract.io

## Lifecycle Assembly Rules
1. init phase: use init sequence and attach APIs when available.
2. fast_loop and slow_loop: call step APIs in scheduled order.
3. fault phase: use protection-related APIs only when explicitly present.

## Failure Policy
1. unresolved_module_id: no candidate found.
2. ambiguous_module_id: multiple candidates remain after filtering.
3. missing_step_api_in_loop: module is scheduled in fast/slow loop but has no step API.
