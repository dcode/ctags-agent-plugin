"""Tests ensuring full adherence to the Agent Plugins Specification v1.0.0.

See: https://agent-plugins.org/
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from scripts.validate_spec import (
    MCP_SCHEMA_ID,
    PLUGIN_NAME_PATTERN,
    PLUGIN_SCHEMA_ID,
    ValidationError,
    validate_plugin,
)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def test_plugin_json_exists_and_is_valid():
    """Verify plugin.json exists at root and matches schema and rules."""
    manifest_file = PLUGIN_ROOT / "plugin.json"
    assert manifest_file.is_file(), "plugin.json must exist at plugin root"

    with manifest_file.open(encoding="utf-8") as f:
        data = json.load(f)

    # Validate against local schema
    schema_file = PLUGIN_ROOT / "schemas" / "1.0.0" / "plugin.schema.json"
    assert schema_file.is_file(), "schemas/1.0.0/plugin.schema.json must exist"

    with schema_file.open(encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=data, schema=schema)

    # Validate spec-specific rules
    assert data["$schema"] == PLUGIN_SCHEMA_ID
    assert "name" in data
    assert 1 <= len(data["name"]) <= 64
    assert PLUGIN_NAME_PATTERN.match(data["name"]) is not None


def test_mcp_json_exists_and_is_valid():
    """Verify mcp.json exists at root and matches schema and rules."""
    mcp_file = PLUGIN_ROOT / "mcp.json"
    assert mcp_file.is_file(), "mcp.json must exist at plugin root"

    with mcp_file.open(encoding="utf-8") as f:
        data = json.load(f)

    # Validate against local schema
    schema_file = PLUGIN_ROOT / "schemas" / "1.0.0" / "mcp.schema.json"
    assert schema_file.is_file(), "schemas/1.0.0/mcp.schema.json must exist"

    with schema_file.open(encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=data, schema=schema)

    # Validate spec-specific rules
    assert data["$schema"] == MCP_SCHEMA_ID
    assert "mcpServers" in data
    assert "ctags" in data["mcpServers"]

    ctags_srv = data["mcpServers"]["ctags"]
    assert ctags_srv["type"] == "stdio"
    assert "command" in ctags_srv
    assert " " not in ctags_srv["command"]
    assert "${" not in ctags_srv["command"], "command must not use placeholders"

    # Verify referenced server script exists within plugin root
    args = ctags_srv.get("args", [])
    for arg in args:
        if "${PLUGIN_ROOT}" in arg:
            expanded = arg.replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT))
            path = Path(expanded)
            assert path.exists(), f"Path referenced in args does not exist: {path}"
            assert path.resolve().is_relative_to(PLUGIN_ROOT)


def test_validate_spec_runner():
    """Verify the validator script completes with zero errors on this repository."""
    warnings = validate_plugin(PLUGIN_ROOT)
    assert isinstance(warnings, list)


def test_validate_spec_rejection_rules(tmp_path: Path):
    """Verify the validator properly rejects non-conformant plugin manifests."""
    # Missing plugin.json
    with pytest.raises(ValidationError, match="Missing required manifest"):
        validate_plugin(tmp_path)

    # Invalid name (uppercase)
    bad_manifest = tmp_path / "plugin.json"
    bad_manifest.write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "Invalid_Uppercase_Name"}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="violates naming constraints"):
        validate_plugin(tmp_path)

    # Invalid placeholder in command
    bad_manifest.write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "valid-name"}),
        encoding="utf-8",
    )
    bad_mcp = tmp_path / "mcp.json"
    bad_mcp.write_text(
        json.dumps(
            {
                "$schema": MCP_SCHEMA_ID,
                "mcpServers": {
                    "bad": {
                        "type": "stdio",
                        "command": "${PLUGIN_ROOT}/bin/test",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="contains placeholder expansion"):
        validate_plugin(tmp_path)
