"""Lazy public exports for the NOVA-APEX core.

Importing a schema should not initialize the LLM provider, persistent memory,
planner, and execution engine as side effects. Public names remain available for
backwards compatibility and initialize only when accessed.
"""
from importlib import import_module

_EXPORTS = {
    "ActionDomain": (".schemas", "ActionDomain"),
    "ActionType": (".schemas", "ActionType"),
    "ActionRequest": (".schemas", "ActionRequest"),
    "StepResult": (".schemas", "StepResult"),
    "PlanStep": (".schemas", "PlanStep"),
    "AgentGoal": (".schemas", "AgentGoal"),
    "GoalStatus": (".schemas", "GoalStatus"),
    "StepStatus": (".schemas", "StepStatus"),
    "agent_logger": (".logger", "agent_logger"),
    "agent_memory": (".memory", "agent_memory"),
    "llm": (".llm_provider", "llm"),
    "planner": (".planner", "planner"),
    "engine": (".engine", "engine"),
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
