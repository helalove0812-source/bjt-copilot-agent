# Unknown Device Auto Routing

Date: 2026-06-06

## Stage Goal

Route high-level unknown-device autonomy requests into the tool-calling experimental agent by default.

## Problem Found

The `/api/ai-chat` endpoint could run the tool-calling agent when `agent_mode=tool_calling` was explicitly provided. However, a natural request such as:

```text
这有个不知道型号的三脚器件，你自己搞清楚它是什么，并给我一份表征报告
```

was still interpreted by the classic planner as `create_plan`, producing a generic UNKNOWN test plan instead of executing the autonomous unknown-device workflow.

## Implemented Changes

- Added a narrow unknown-device autonomy detector in `api_server.py`.
- Auto-routes requests containing both:
  - unknown three-pin device language
  - autonomous characterization/report language
- Keeps regular plan requests on the classic path unless `agent_mode=tool_calling` is explicitly set.
- Added API regression coverage for natural-language unknown-device autonomy routing.

## Optimization Effect

Before:

- User had to know to enable `agent_mode=tool_calling`.
- Natural demo request could be downgraded to a static test-plan response.

After:

- The high-level demo goal enters `autonomous_unknown_device_report` automatically.
- The response includes topology hypothesis, relay-matrix probe evidence, measurement program, critic/refinement, SPICE model, residual followup, and pulse diagnosis.

## Verification Targets

- `tests/test_api_server.py::test_ai_chat_auto_routes_unknown_device_autonomy_to_tool_agent`
- `/api/ai-chat` natural unknown-device autonomy request
