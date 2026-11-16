# ctags-agent-plugin

An [Agent Plugins](https://agent-plugins.org/) compliant plugin providing Universal / Exuberant Ctags symbol tools
(`search_symbols`, `list_symbols`, `generate_ctags`) via Model Context Protocol (MCP).

## Tools

| Tool | Read-only | Purpose |
|---|---|---|
| `search_symbols` | yes | Regex search over symbol names with optional filters for path, kind, and language. Supports surrounding code context. |
| `list_symbols` | yes | Lists all indexed declarations under a file or directory, sorted by `file:line`. |
| `generate_ctags` | no | Generates a `tags` index file at the repository root if none exists. Pass `force=True` to rebuild. |

## Requirements

- [uv](https://docs.astral.sh/uv/): Launches `server/ctags_server.py` as a self-contained PEP 723 script with its required dependencies.
- [Universal Ctags](https://ctags.io/) (preferred) or Exuberant Ctags on `PATH`. BSD/POSIX `ctags` is rejected.
  - macOS: `brew install universal-ctags`
  - Ubuntu/Debian: `sudo apt-get install -y universal-ctags`

## Agent Plugins Specification Compliance

This plugin adheres strictly to the [Agent Plugins Specification v1.0.0](https://agent-plugins.org/):

```text
ctags-agent-plugin/
├── plugin.json              # Canonical Agent Plugin manifest
├── mcp.json                 # MCP stdio server configuration
├── server/
│   └── ctags_server.py      # MCP server implementation
├── schemas/1.0.0/           # Local cached Agent Plugins schemas
├── scripts/
│   └── validate_spec.py     # Specification validator script
└── tests/                   # Specification & server test suite
```

- **Manifest (`plugin.json`)**: Declares plugin identity and metadata against
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
- **MCP Configuration (`mcp.json`)**: Declares the stdio server against
  `https://agent-plugins.org/schemas/1.0.0/mcp.schema.json`, using `${PLUGIN_ROOT}` for bundled script resolution.
- **Security & Containment**: All package paths remain safely confined within the plugin root directory.

## Client Usage

### Goose

Add the plugin to Goose using Goose's plugin directory or extension configuration:

```yaml
extensions:
  ctags:
    name: ctags
    type: stdio
    enabled: true
    cmd: uv
    args:
      - run
      - --quiet
      - --script
      - <PATH_TO_PLUGIN>/server/ctags_server.py
    timeout: 300
```

### Any Agent Plugins Compliant Client

Clients supporting the Agent Plugins standard discover `plugin.json` and load the MCP server configured
in `mcp.json` automatically when pointing to this repository.

## Repository Scoping & Behavior

- **Target Repository Root**: Scoped to `CTAGS_REPO_ROOT`, then `CLAUDE_PROJECT_DIR`, then the current working directory,
  widened to its Git top-level. All symbol operations are confined to this target repository root.
- **Index File**: Searches for `tags`, `.tags`, or `.git/tags`. `generate_ctags` writes `tags` at the target
  repository root.

## Development & Verification

### Running Tests

```bash
uv run pytest
```

### Validating Specification Compliance

Run the spec validator directly:

```bash
uv run scripts/validate_spec.py
```

Or using `check-jsonschema`:

```bash
uvx check-jsonschema --schemafile schemas/1.0.0/plugin.schema.json plugin.json
uvx check-jsonschema --schemafile schemas/1.0.0/mcp.schema.json mcp.json
```

### Pre-commit Hooks

Install pre-commit hooks to ensure every commit conforms to formatting, linting, and specification checks:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```
