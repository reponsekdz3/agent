"""Lazy exports for optional computer-control adapters.

Importing a controller package must not initialize Playwright, desktop APIs, or
Android dependencies when a task only needs the API, planner, or shell module.
"""
from importlib import import_module

_EXPORTS = {
    "browser_controller": (".browser_controller", "browser_controller"),
    "desktop_controller": (".desktop_controller", "desktop_controller"),
    "mobile_controller": (".mobile_controller", "mobile_controller"),
    "shell_controller": (".shell_controller", "shell_controller"),
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
