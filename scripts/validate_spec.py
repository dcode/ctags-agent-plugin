#!/usr/bin/env python3
"""Validates an Agent Plugin directory against the Agent Plugins Specification v1.0.0.

See: https://agent-plugins.org/ and https://github.com/agentplugins/agent-plugins-spec
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

PLUGIN_NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
ALLOWED_MANIFEST_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
ALLOWED_AUTHOR_FIELDS = {"name", "email", "url"}
ALLOWED_MCP_ROOT_FIELDS = {"$schema", "mcpServers"}
ALLOWED_STDIO_FIELDS = {"type", "command", "args", "env", "cwd"}
ALLOWED_STREAMABLE_HTTP_FIELDS = {"type", "url", "headers"}
ALLOWED_SSE_FIELDS = {"type", "url", "headers"}


class ValidationError(Exception):
    """Raised when spec validation fails."""


def validate_plugin(root_dir: Path) -> list[str]:
    """Validates the plugin at root_dir against Agent Plugins v1.0.0.

    Returns a list of warning messages, or raises ValidationError on failure.
    """
    root_dir = root_dir.resolve()
    warnings: list[str] = []

    # 1. Manifest (plugin.json) existence & basic JSON
    manifest_path = root_dir / "plugin.json"
    if not manifest_path.is_file():
        raise ValidationError(f"Missing required manifest: 'plugin.json' at root ({root_dir})")

    # Path containment check (§4.1)
    if not manifest_path.resolve().is_relative_to(root_dir):
        raise ValidationError("Manifest 'plugin.json' resolves outside plugin root")

    try:
        manifest_raw = manifest_path.read_text(encoding="utf-8")
        manifest: dict[str, Any] = json.loads(manifest_raw)
    except Exception as e:
        raise ValidationError(f"Invalid JSON in 'plugin.json': {e}") from e

    if not isinstance(manifest, dict):
        raise ValidationError("'plugin.json' must contain a top-level JSON object")

    # 2. Required manifest fields (§5.3)
    if "$schema" not in manifest:
        raise ValidationError("Manifest 'plugin.json' missing required field: '$schema'")
    if manifest["$schema"] != PLUGIN_SCHEMA_ID:
        raise ValidationError(
            f"Invalid '$schema' in 'plugin.json'. "
            f"Expected '{PLUGIN_SCHEMA_ID}', got '{manifest['$schema']}'"
        )

    if "name" not in manifest:
        raise ValidationError("Manifest 'plugin.json' missing required field: 'name'")

    name = manifest["name"]
    if not isinstance(name, str):
        raise ValidationError("Manifest 'name' must be a string")
    if len(name) < 1 or len(name) > 64:
        raise ValidationError(f"Plugin name '{name}' length ({len(name)}) must be between 1 and 64")
    if not PLUGIN_NAME_PATTERN.match(name):
        raise ValidationError(
            f"Plugin name '{name}' violates naming constraints: lowercase alphanumeric, "
            "hyphens, periods only; cannot start/end with non-alphanumeric; no '--' or '..'"
        )

    # 3. Closed manifest schema check (§5.2)
    for key in manifest:
        if key not in ALLOWED_MANIFEST_FIELDS:
            warnings.append(f"Unknown top-level field '{key}' in plugin.json will be ignored")

    # Validate author field if present
    if "author" in manifest and manifest["author"] is not None:
        if not isinstance(manifest["author"], dict):
            raise ValidationError("Field 'author' in plugin.json must be an object")
        for author_key in manifest["author"]:
            if author_key not in ALLOWED_AUTHOR_FIELDS:
                raise ValidationError(
                    f"Invalid key '{author_key}' in 'author' object. Only name, email, url allowed."
                )
            if not isinstance(manifest["author"][author_key], str):
                raise ValidationError(f"Author field '{author_key}' must be a string")

    # Validate extensions field if present
    if (
        "extensions" in manifest
        and manifest["extensions"] is not None
        and not isinstance(manifest["extensions"], dict)
    ):
        warnings.append("Non-object 'extensions' field in plugin.json will be ignored")

    # 4. MCP Configuration (mcp.json) if present (§7.2)
    mcp_path = root_dir / "mcp.json"
    if mcp_path.exists():
        if not mcp_path.is_file():
            raise ValidationError("'mcp.json' exists but is not a regular file")
        if not mcp_path.resolve().is_relative_to(root_dir):
            raise ValidationError("'mcp.json' resolves outside plugin root")

        try:
            mcp_raw = mcp_path.read_text(encoding="utf-8")
            mcp_data: dict[str, Any] = json.loads(mcp_raw)
        except Exception as e:
            raise ValidationError(f"Invalid JSON in 'mcp.json': {e}") from e

        if not isinstance(mcp_data, dict):
            raise ValidationError("'mcp.json' must contain a top-level JSON object")

        # Top-level fields (§7.2.1)
        for key in mcp_data:
            if key not in ALLOWED_MCP_ROOT_FIELDS:
                raise ValidationError(f"Unexpected top-level field '{key}' in 'mcp.json'")

        if "$schema" not in mcp_data:
            raise ValidationError("'mcp.json' missing required field: '$schema'")
        if mcp_data["$schema"] != MCP_SCHEMA_ID:
            raise ValidationError(
                f"Invalid '$schema' in 'mcp.json'. "
                f"Expected '{MCP_SCHEMA_ID}', got '{mcp_data['$schema']}'"
            )

        if "mcpServers" not in mcp_data or not isinstance(mcp_data["mcpServers"], dict):
            raise ValidationError("'mcp.json' missing required object field: 'mcpServers'")

        # Validate each server entry
        for srv_name, srv_config in mcp_data["mcpServers"].items():
            if not isinstance(srv_config, dict):
                raise ValidationError(f"Server '{srv_name}' configuration must be an object")

            srv_type = srv_config.get("type")
            if srv_type not in {"stdio", "streamable-http", "sse"}:
                raise ValidationError(
                    f"Server '{srv_name}' has invalid or missing 'type': '{srv_type}'"
                )

            if srv_type == "stdio":
                for field in srv_config:
                    if field not in ALLOWED_STDIO_FIELDS:
                        raise ValidationError(
                            f"Server '{srv_name}' contains unrecognized stdio field: '{field}'"
                        )
                if "command" not in srv_config or not isinstance(srv_config["command"], str):
                    raise ValidationError(f"stdio server '{srv_name}' missing string 'command'")

                cmd = srv_config["command"]
                if not cmd:
                    raise ValidationError(f"stdio server '{srv_name}' command cannot be empty")
                if "${PLUGIN_ROOT}" in cmd or "${PLUGIN_DATA}" in cmd:
                    raise ValidationError(
                        f"stdio server '{srv_name}' command contains placeholder expansion; "
                        "clients MUST NOT expand placeholders in 'command' (§7.2.1)"
                    )
                if " " in cmd:
                    raise ValidationError(
                        f"stdio server '{srv_name}' command must be a single executable token, "
                        f"not a shell command string: '{cmd}'"
                    )
                if not (cmd.startswith("./") or "/" not in cmd):
                    raise ValidationError(
                        f"stdio server '{srv_name}' command must be a bare name or "
                        f"plugin-relative (starting with './'): '{cmd}'"
                    )

                # Args
                if "args" in srv_config:
                    if not isinstance(srv_config["args"], list):
                        raise ValidationError(f"stdio server '{srv_name}' 'args' must be an array")
                    for arg in srv_config["args"]:
                        if not isinstance(arg, str):
                            raise ValidationError(
                                f"stdio server '{srv_name}' arg must be a string: {arg}"
                            )

                # Env
                if "env" in srv_config:
                    if not isinstance(srv_config["env"], dict):
                        raise ValidationError(f"stdio server '{srv_name}' 'env' must be an object")
                    if "PLUGIN_ROOT" in srv_config["env"] or "PLUGIN_DATA" in srv_config["env"]:
                        raise ValidationError(
                            f"stdio server '{srv_name}' 'env' contains reserved variable "
                            "PLUGIN_ROOT or PLUGIN_DATA (§9.2)"
                        )

                # Cwd
                if "cwd" in srv_config:
                    cwd = srv_config["cwd"]
                    if not isinstance(cwd, str):
                        raise ValidationError(f"stdio server '{srv_name}' 'cwd' must be a string")
                    if not (
                        cwd.startswith("./")
                        or cwd == "${PLUGIN_ROOT}"
                        or cwd.startswith("${PLUGIN_ROOT}/")
                        or cwd == "${PLUGIN_DATA}"
                        or cwd.startswith("${PLUGIN_DATA}/")
                    ):
                        raise ValidationError(
                            f"stdio server '{srv_name}' 'cwd' must begin with "
                            "'./', '${PLUGIN_ROOT}', or '${PLUGIN_DATA}'"
                        )

            elif srv_type == "streamable-http":
                for field in srv_config:
                    if field not in ALLOWED_STREAMABLE_HTTP_FIELDS:
                        raise ValidationError(
                            f"Server '{srv_name}' contains unrecognized "
                            f"streamable-http field: '{field}'"
                        )
                if "url" not in srv_config or not isinstance(srv_config["url"], str):
                    raise ValidationError(f"Server '{srv_name}' missing string 'url'")

            elif srv_type == "sse":
                for field in srv_config:
                    if field not in ALLOWED_SSE_FIELDS:
                        raise ValidationError(
                            f"Server '{srv_name}' contains unrecognized sse field: '{field}'"
                        )
                if "url" not in srv_config or not isinstance(srv_config["url"], str):
                    raise ValidationError(f"Server '{srv_name}' missing string 'url'")

    # 5. Skills directory check (§6.1, §7.1)
    skills_dir = root_dir / "skills"
    if skills_dir.exists():
        if not skills_dir.is_dir():
            raise ValidationError("'skills' exists at root but is not a directory")
        for skill_child in skills_dir.iterdir():
            if skill_child.is_dir():
                skill_md = skill_child / "SKILL.md"
                if not skill_md.is_file():
                    warnings.append(
                        f"Skill directory '{skill_child.name}' does not contain 'SKILL.md'"
                    )

    # 6. Check for directory traversal / containment of package files
    ignored_package_dirs = {".git", ".venv", "venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
    for item in root_dir.rglob("*"):
        if any(part in ignored_package_dirs for part in item.parts):
            continue
        if item.is_symlink():
            resolved = item.resolve()
            if not resolved.is_relative_to(root_dir):
                rel_symlink = item.relative_to(root_dir)
                raise ValidationError(
                    f"Symlink '{rel_symlink}' resolves outside plugin root to '{resolved}'"
                )

    return warnings


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Validating Agent Plugin specification compliance for: {target}")
    try:
        warnings = validate_plugin(target)
        for w in warnings:
            print(f"[WARN] {w}")
        print("Agent Plugin specification compliance: PASSED")
        return 0
    except ValidationError as err:
        print(f"[ERROR] Specification validation failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
