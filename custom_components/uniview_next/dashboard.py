"""Dashboard auto-generator for Uniview Next.

Writes directly to HA's .storage directory, exactly as HA does internally.
Creates two files:
  - .storage/lovelace_dashboards  → registru dashboarduri (lista)
  - .storage/lovelace.uniview-cameras → config views+cards

Dashboard-ul este creat DOAR dacă nu există deja (varianta mixtă).
Dacă există, nu se atinge — utilizatorul poate edita manual după creare.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

DASHBOARD_SLUG = "uniview-cameras"
DASHBOARD_TITLE = "Uniview"
DASHBOARD_ICON = "mdi:cctv"

# Fișiere .storage
STORAGE_DASHBOARDS = "lovelace_dashboards"
STORAGE_DASHBOARD_CONFIG = f"lovelace.{DASHBOARD_SLUG}"


def _storage_path(hass: HomeAssistant, filename: str) -> str:
    return hass.config.path(".storage", filename)


def _read_json(path: str) -> dict[str, Any] | None:
    """Citește un fișier JSON din .storage. Returnează None dacă nu există."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Nu pot citi %s: %s", path, err)
        return None


def _write_json(path: str, data: dict[str, Any]) -> bool:
    """Scrie un fișier JSON în .storage, cu același format ca HA."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.error("Nu pot scrie %s: %s", path, err)
        return False


def _dashboard_already_exists(hass: HomeAssistant) -> bool:
    """Verifică dacă dashboard-ul există deja în registru sau ca fișier config."""
    dashboards_path = _storage_path(hass, STORAGE_DASHBOARDS)
    data = _read_json(dashboards_path)
    if data:
        for item in data.get("data", {}).get("items", []):
            if item.get("url_path") == DASHBOARD_SLUG:
                _LOGGER.debug("Dashboard '%s' există deja în registru", DASHBOARD_SLUG)
                return True

    config_path = _storage_path(hass, STORAGE_DASHBOARD_CONFIG)
    if os.path.exists(config_path):
        _LOGGER.debug("Config dashboard '%s' există deja ca fișier", DASHBOARD_SLUG)
        return True

    return False


def _get_camera_pairs(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> list[dict[str, str]]:
    """Returnează perechile sub/main stream pentru toate camerele din integrare."""
    ent_reg = er.async_get(hass)

    sub_map: dict[str, str] = {}
    main_map: dict[str, str] = {}
    name_map: dict[str, str] = {}

    for ent in ent_reg.entities.values():
        if ent.config_entry_id != entry.entry_id:
            continue
        if ent.domain != "camera":
            continue

        eid = ent.entity_id

        if eid.endswith("_sub_stream"):
            base = eid[: -len("_sub_stream")]
            sub_map[base] = eid
            raw_name = ent.original_name or ent.name or ""
            camera_name = (
                raw_name
                .replace(" Sub Stream", "")
                .replace(" sub stream", "")
                .strip()
            )
            name_map[base] = camera_name

        elif eid.endswith("_main_stream"):
            base = eid[: -len("_main_stream")]
            main_map[base] = eid

    pairs = []
    for base in sorted(sub_map.keys()):
        if base in main_map:
            pairs.append(
                {
                    "sub": sub_map[base],
                    "main": main_map[base],
                    "name": name_map.get(base, base.split("_")[-1].capitalize()),
                }
            )

    return pairs


def _build_camera_card(pair: dict[str, str]) -> dict[str, Any]:
    """Card vertical: thumbnail sub stream + 2 butoane (sub/main)."""
    return {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "picture-entity",
                "entity": pair["sub"],
                "name": pair["name"],
                "show_name": False,
                "show_state": False,
                "camera_view": "auto",
                "tap_action": {
                    "action": "more-info",
                    "entity": pair["sub"],
                },
            },
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "button",
                        "name": "Sub",
                        "icon": "mdi:video-outline",
                        "show_name": False,
                        "show_icon": True,
                        "show_state": False,
                        "entity": pair["sub"],
                        "tap_action": {
                            "action": "more-info",
                            "entity": pair["sub"],
                        },
                    },
                    {
                        "type": "button",
                        "name": "Main",
                        "icon": "mdi:video-high-definition",
                        "show_name": False,
                        "show_icon": True,
                        "show_state": False,
                        "entity": pair["main"],
                        "tap_action": {
                            "action": "more-info",
                            "entity": pair["main"],
                        },
                    },
                ],
            },
        ],
    }


def _build_dashboard_config(pairs: list[dict[str, str]]) -> dict[str, Any]:
    """Construiește config-ul complet al dashboard-ului (format .storage HA)."""
    camera_cards = [_build_camera_card(p) for p in pairs]

    return {
        "key": STORAGE_DASHBOARD_CONFIG,
        "version": 1,
        "minor_version": 1,
        "data": {
            "config": {
                "title": DASHBOARD_TITLE,
                "views": [
                    {
                        "title": "Camere",
                        "path": "camere",
                        "icon": DASHBOARD_ICON,
                        "type": "masonry",
                        "cards": [
                            {
                                "type": "grid",
                                "columns": 3,
                                "square": False,
                                "cards": camera_cards,
                            }
                        ],
                    }
                ],
            }
        },
    }


def _build_dashboards_registry_entry() -> dict[str, Any]:
    """Construiește entry-ul pentru registrul lovelace_dashboards."""
    return {
        "id": DASHBOARD_SLUG,
        "url_path": DASHBOARD_SLUG,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": True,
        "mode": "storage",
    }


async def async_create_dashboard_if_missing(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    _LOGGER.warning("Dashboard function called — starting")  # temporar

    """Creează dashboard-ul Uniview dacă nu există deja.

    Scrie direct în .storage — același mecanism folosit de HA intern.
    Nu suprascrie dacă există (varianta mixtă).
    """
    exists = await hass.async_add_executor_job(
        _dashboard_already_exists, hass
    )
    if exists:
        _LOGGER.debug("Dashboard Uniview există deja — nu se recreează")
        return

    pairs = _get_camera_pairs(hass, entry)
    if not pairs:
        _LOGGER.warning(
            "Nu s-au găsit perechi sub/main stream — dashboard nu se creează"
        )
        return

    _LOGGER.info(
        "Creez dashboard Uniview cu %d camere: %s",
        len(pairs),
        [p["name"] for p in pairs],
    )

    def _write_storage_files() -> bool:
        # 1. Scrie config-ul dashboard-ului
        config_path = _storage_path(hass, STORAGE_DASHBOARD_CONFIG)
        config_data = _build_dashboard_config(pairs)
        if not _write_json(config_path, config_data):
            return False

        # 2. Actualizează registrul dashboardurilor
        dashboards_path = _storage_path(hass, STORAGE_DASHBOARDS)
        registry = _read_json(dashboards_path)

        if registry is None:
            # Registrul nu există — creăm unul nou
            registry = {
                "key": STORAGE_DASHBOARDS,
                "version": 1,
                "minor_version": 1,
                "data": {"items": []},
            }

        items: list[dict] = registry.setdefault("data", {}).setdefault("items", [])

        # Evităm duplicate
        if not any(item.get("url_path") == DASHBOARD_SLUG for item in items):
            items.append(_build_dashboards_registry_entry())

        if not _write_json(dashboards_path, registry):
            return False

        return True

    success = await hass.async_add_executor_job(_write_storage_files)

    if success:
        _LOGGER.info(
            "Dashboard '%s' creat cu succes. "
            "Reîncarcă interfața HA (F5) pentru a-l vedea în sidebar.",
            DASHBOARD_SLUG,
        )
    else:
        _LOGGER.error("Eroare la crearea dashboard-ului Uniview")
