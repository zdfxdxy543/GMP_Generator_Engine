# Generation Experience Guide

## Purpose
- This file is manually maintained by developers.
- The code generator reads this file and uses it as extra guidance when generating source files.

## High Priority Rules
- Put only rules that must be followed in every generation.
- Keep each rule short and testable.

- Rule: <one sentence>
- Rule: <one sentence>
- Rule: <one sentence>

## Naming Conventions
- Instance naming pattern: <example>
- Function naming pattern: <example>
- File naming constraints: <example>

## Required Initialization Patterns
- Pattern: <what must be initialized first>
- Pattern: <required attach order>
- Pattern: <required safety checks>

## Dispatch and Scheduling Patterns
- fast_loop: <required calls and order>
- slow_loop: <required calls and order>
- fault path: <required behavior>

## Tunable Parameter Rules
- Where tunables must be stored: <struct name/path>
- How to apply tunables: <hook/function>
- Runtime update constraints: <validation/defaulting>

## Forbidden Patterns
- Do not: <forbidden pattern>
- Do not: <forbidden pattern>
- Do not: <forbidden pattern>

## Recovery and Fallback
- If API signature is ambiguous: <preferred strategy>
- If module type cannot be inferred: <preferred strategy>
- If generated code conflicts with framework style: <preferred strategy>

## Verification Checklist
- [ ] All required global objects are declared and defined.
- [ ] Initialization order follows required patterns.
- [ ] Dispatch contains required loop paths.
- [ ] No placeholder/unresolved APIs are emitted.
- [ ] Generated code is compile-oriented and framework-aligned.

## Notes
- Add concrete examples when possible.
- Remove outdated rules to avoid polluting prompts.
