# GMP Generator Engine - v2

## Overview
v2 is an isolated experiment area for controller design generation with LLM.
It is independent from the rest of the repository runtime logic.

Current v2 focus:
- Convert natural-language requirements into controller loop selection.
- Output only selected control loops and stable loop IDs.
- Keep output minimal JSON for downstream steps.

## Main Script
- controller_loop_id_exporter.py

What it does:
- Takes a natural-language requirement (Chinese or English).
- Calls the configured LLM endpoint from llm_settings.json.
- Returns selected loops only (for example speed_loop, current_loop).
- Canonicalizes loop IDs so the same loop name always maps to the same ID.

## Minimal Call
Run from the v2 directory:

```powershell
../.venv/Scripts/python.exe ./controller_loop_id_exporter.py "需要设计吸尘器电机控制器"
```

Optional short form with explicit output file:

```powershell
../.venv/Scripts/python.exe ./controller_loop_id_exporter.py "需要设计吸尘器电机控制器" --output ./controller_loop_ids_cn_test.json
```

## Minimal Output Example
```json
{
  "requirement": "Design a vacuum cleaner motor controller",
  "language": "en",
  "selected_loops": [
    { "id": "loop_current_001", "name": "current_loop" },
    { "id": "loop_speed_001", "name": "speed_loop" }
  ]
}
```

## Notes
- This README documents only the v2 area.
- For successful calls, ensure api_key is available in v2/llm_settings.json or environment variables.
