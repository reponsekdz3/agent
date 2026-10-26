"""Lazy exports for NOVA-APEX optional skills.

Keep API startup lightweight. Browser/device dependencies are imported only when
the skill that needs them is actually requested.
"""
from importlib import import_module

_EXPORTS = {
    "web_account_creator": (".web_account_creator", "web_account_creator"),
    "doc_generator": (".doc_generator", "doc_generator"),
    "system_admin": (".system_admin", "system_admin"),
    "research_agent": (".research_agent", "research_agent"),
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
