from collections.abc import Mapping
from typing import Any, Callable

from . import administration, assessments, catalog, certificates, communication, enrollments, financial, identity, learning


DOMAIN_ACTION_BINDINGS = {
    "identity": identity.ACTION_BINDINGS,
    "catalog": catalog.ACTION_BINDINGS,
    "enrollments": enrollments.ACTION_BINDINGS,
    "learning": learning.ACTION_BINDINGS,
    "assessments": assessments.ACTION_BINDINGS,
    "certificates": certificates.ACTION_BINDINGS,
    "financial": financial.ACTION_BINDINGS,
    "communication": communication.ACTION_BINDINGS,
    "administration": administration.ACTION_BINDINGS,
}


def build_action_registry(namespace: Mapping[str, Any]) -> dict[str, Callable]:
    registry: dict[str, Callable] = {}
    for domain, bindings in DOMAIN_ACTION_BINDINGS.items():
        for action_name, handler_name in bindings:
            if action_name in registry:
                raise RuntimeError(f"A ação {action_name!r} está repetida no domínio {domain!r}.")
            handler = namespace.get(handler_name)
            if not callable(handler):
                raise RuntimeError(
                    f"O handler {handler_name!r} da ação {action_name!r} não está disponível."
                )
            registry[action_name] = handler
    return registry
