# anonymize-mcp — stdio MCP server (FastMCP)
# Used by Glama (and any container host) to start the server and respond to
# MCP introspection (list_tools). Tool *invocation* additionally needs network
# access to the ÚFAL/LINDAT APIs, but startup + introspection work offline.
FROM python:3.12-slim

WORKDIR /app

# Install the package from source (hatchling build backend).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# stdio transport — the MCP client speaks JSON-RPC over stdin/stdout.
ENTRYPOINT ["anonymize-mcp"]
