from __future__ import annotations

import os
import re
from dataclasses import dataclass


DOC_PLANT_CODES: tuple[str, ...] = ("MPC", "202", "205", "209", "401")

_SYBASE_OWNER_BY_PLANT = {
    # Sybase default should follow connection DB; keep owner as dbo.
    # If cross-db qualifier is required, override with DOC_DB_{PLANT}_SYBASE_OWNER.
    "MPC": "dbo",
    "202": "dbo",
}

_ORACLE_OWNER_BY_PLANT = {
    "205": "MNDQ",
    "209": "MNDV",
    "401": "MNDI",
}

_OWNER_ALIAS_TO_PLANT = {
    "MNDQ": "205",
    "MNDV": "209",
    "MNDI": "401",
}


@dataclass(frozen=True)
class DocDBTarget:
    plant: str
    db_type: str
    owner: str
    db_profile: str


def normalize_doc_plant(raw: str, default: str | None = "MPC") -> str:
    fallback = "MPC" if default is None else str(default or "").strip().upper()
    s = str(raw or "").strip().upper()
    if not s:
        return fallback

    if s in DOC_PLANT_CODES:
        return s
    if s in _OWNER_ALIAS_TO_PLANT:
        return _OWNER_ALIAS_TO_PLANT[s]
    if "MPC" in s:
        return "MPC"

    # Keep only letters/digits and retry.
    compact = re.sub(r"[^A-Z0-9]+", "", s)
    if compact in DOC_PLANT_CODES:
        return compact
    if compact in _OWNER_ALIAS_TO_PLANT:
        return _OWNER_ALIAS_TO_PLANT[compact]
    if "MPC" in compact:
        return "MPC"

    m = re.search(r"(202|205|209|401)", compact)
    if m:
        return m.group(1)
    return fallback


def _default_doc_plant() -> str:
    return normalize_doc_plant(os.getenv("DOC_DEFAULT_PLANT", "MPC"), default="MPC")


def resolve_plant_from_employee(*, user_name: str = "", user_id: str = "") -> str:
    name = str(user_name or "").strip()
    emp_id = str(user_id or "").strip()
    if not name and not emp_id:
        return ""

    try:
        from webapps.portal.oracle_emp import get_factory_plant_by_id, get_factory_plant_by_name

        plant = ""
        if name:
            plant = get_factory_plant_by_name(name, emp_id=emp_id) or ""
        if not plant and emp_id:
            plant = get_factory_plant_by_id(emp_id) or ""
        return normalize_doc_plant(plant, default="")
    except Exception:
        return ""


def resolve_doc_db_target(*, plant: str = "", user_name: str = "", user_id: str = "") -> DocDBTarget:
    explicit = normalize_doc_plant(plant, default="") if plant else ""
    resolved = explicit or resolve_plant_from_employee(user_name=user_name, user_id=user_id)
    final_plant = normalize_doc_plant(resolved or _default_doc_plant(), default="MPC")

    if final_plant in _SYBASE_OWNER_BY_PLANT:
        owner = (os.getenv(f"DOC_DB_{final_plant}_SYBASE_OWNER") or _SYBASE_OWNER_BY_PLANT[final_plant]).strip()
        return DocDBTarget(
            plant=final_plant,
            db_type="sybase",
            owner=owner,
            db_profile=final_plant,
        )
    owner = (os.getenv(f"DOC_DB_{final_plant}_ORA_OWNER") or _ORACLE_OWNER_BY_PLANT.get(final_plant, "MNDQ")).strip()
    return DocDBTarget(
        plant=final_plant,
        db_type="oracle",
        owner=owner,
        db_profile=final_plant,
    )
