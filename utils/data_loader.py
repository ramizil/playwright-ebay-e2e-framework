"""
Data Loader Module
==================

Provides helpers that read test data from external JSON and YAML files,
satisfying the **Data-Driven Testing** requirement.  All test inputs
(search queries, price limits, expected values) live in ``data/`` files
rather than being hard-coded in test code.

Supported formats:
    * JSON  – ``data/search_data.json``
    * YAML  – ``config/config.yaml``, ``config/environments/*.yaml``

The module also exposes a ``parametrize_from_json`` helper that generates
``pytest.mark.parametrize`` entries from a JSON array, keeping test files
short and readable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from core.logger_config import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_json(filename: str, directory: Path = DATA_DIR) -> Any:
    """Load and parse a JSON file from the given directory.

    Args:
        filename:  Name of the JSON file (e.g. ``'search_data.json'``).
        directory: Folder to look in.  Defaults to the project's ``data/`` dir.

    Returns:
        The parsed JSON content (dict, list, or primitive).

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    filepath = directory / filename
    logger.info("Loading JSON data from %s", filepath)

    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    logger.info("Loaded %d top-level keys/items from %s", len(data), filename)
    return data


def load_yaml(filename: str, directory: Path = CONFIG_DIR) -> Dict[str, Any]:
    """Load and parse a YAML file from the given directory.

    Args:
        filename:  Name of the YAML file (e.g. ``'config.yaml'``).
        directory: Folder to look in.  Defaults to ``config/``.

    Returns:
        A dictionary with the YAML content.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    filepath = directory / filename
    logger.info("Loading YAML config from %s", filepath)

    with open(filepath, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    logger.info("Loaded YAML: %s", filename)
    return data or {}


def load_test_scenarios(filename: str = "search_data.json") -> List[Dict[str, Any]]:
    """Load the ``test_scenarios`` array from the standard test-data file.

    This is a convenience wrapper used by ``conftest.py`` to feed data into
    ``pytest.mark.parametrize``.

    Args:
        filename: JSON file containing a ``"test_scenarios"`` key.

    Returns:
        A list of scenario dictionaries, each containing at minimum:
        ``query``, ``max_price``, ``limit``, and ``budget_per_item``.

    Example::

        scenarios = load_test_scenarios()
        # [{"id": "headphones_50", "query": "wireless headphones", ...}, ...]
    """
    data = load_json(filename)
    scenarios = data.get("test_scenarios", [])
    logger.info("Loaded %d test scenarios from %s", len(scenarios), filename)
    return scenarios


def get_scenario_ids(scenarios: List[Dict[str, Any]]) -> List[str]:
    """Extract human-readable IDs from a list of scenario dicts.

    Used as the ``ids`` parameter for ``pytest.mark.parametrize`` so that
    test reports show descriptive names instead of ``scenario0``, ``scenario1``.

    Args:
        scenarios: List of scenario dicts (each should have an ``"id"`` key).

    Returns:
        List of ID strings (falls back to index-based IDs if key is missing).
    """
    return [s.get("id", f"scenario_{i}") for i, s in enumerate(scenarios)]
