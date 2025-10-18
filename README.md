# MCP Discovery Hub

**Automatic discovery and management of Model Context Protocol (MCP) servers across your network.**

## What is MCP Discovery Hub?

MCP Discovery Hub is a centralized discovery and orchestration platform that automatically finds, catalogs, and manages MCP servers running on your network. It enables seamless integration of multiple MCP servers with AI tools and applications without manual configuration.

## What's New (v2.0)

### Multi-Transport Support

The hub now supports three different MCP server implementations:

1. **Traditional MCP Servers** (JSON-RPC with session management)

   - Full JSON-RPC 2.0 compliance
   - Session-based communication
   - Best for stateful, production deployments

2. **FastMCP HTTP Mode** (JSON-RPC with automatic sessions)

   - Uses the FastMCP library's HTTP transport
   - JSON-RPC format with session management
   - Requires `notifications/initialized` after initialization
   - Ideal for containerized deployments

3. **FastMCP Streamable-HTTP** (Simplified format)
   - No JSON-RPC wrapper (simpler protocol)
   - No session management required
   - Cleaner, more efficient for stateless operations
   - Best for lightweight deployments

### Automatic Multicast Broadcasting

Servers now broadcast their presence using multicast UDP, enabling truly zero-configuration discovery:

- Servers announce themselves periodically on `239.255.255.250:5353`
- Hub listens passively for announcements
- No manual registration or DNS configuration needed
- Servers are discovered automatically as they come online

### Enhanced Tool Execution

The hub intelligently handles tool execution across different server types:

- Detects server protocol version automatically
- Uses appropriate request format for each server type
- Handles both SSE and JSON responses
- Manages sessions transparently

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   MCP Servers                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  │ Traditional  │  │ FastMCP HTTP │  │ Streamable   │
│  │ MCP Server   │  │ Mode         │  │ HTTP Mode    │
│  │ (JSON-RPC)   │  │ (JSON-RPC)   │  │ (Simplified) │
│  └──────────────┘  └──────────────┘  └──────────────┘
│        │                  │                  │
│        └──────────────────┴──────────────────┘
│                     │
│        Multicast UDP 239.255.255.250:5353
│                     │
│        ┌────────────▼────────────┐
│        │  MCP Discovery Hub      │
│        │  ┌────────────────────┐ │
│        │  │ Server Probing     │ │
│        │  │ (Auto-detection)   │ │
│        │  ├────────────────────┤ │
│        │  │ Tool Catalog       │ │
│        │  ├────────────────────┤ │
│        │  │ Tool Execution     │ │
│        │  │ (Multi-protocol)   │ │
│        │  ├────────────────────┤ │
│        │  │ LLM Integration    │ │
│        │  │ (Ollama/OpenAI)    │ │
│        │  └────────────────────┘ │
│        └─────────────────────────┘
│                     │
└─────────────────────┼──────────────────────────────┘
                      │
              HTTP API & WebSocket
                      │
         ┌────────────┬──────────────┐
         │            │              │
      Web UI       CLI Tools      LLM Apps
```

## Quick Start

### 1. Start the Discovery Hub

```bash
cd mcp_discovery_hub
python mcp_discovery.py
```

The hub will:

- Start on port 8000
- Listen for multicast announcements
- Expose HTTP API at `http://localhost:8000`
- Open WebSocket at `ws://localhost:8000/ws`

### 2. Start MCP Servers

Each server broadcasts automatically:

```bash
# Traditional MCP Server (File System)
python sample_mcp_server.py

# FastMCP Podman Server (HTTP mode)
MCP_TRANSPORT=http MCP_PORT=3001 uv run main.py

# Or FastMCP Podman Server (Streamable-HTTP mode)
MCP_TRANSPORT=streamable-http MCP_PORT=3001 uv run main.py
```

### 3. Access the Hub

```bash
# Get discovered servers
curl http://localhost:8000/servers

# List tools from all servers
curl http://localhost:8000/servers | jq '.[] | .tools'

# Execute a tool
curl -X POST http://localhost:8000/execute-tool \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "192.168.1.1:3001",
    "tool_name": "list_containers",
    "arguments": {"all": true}
  }'
```

## Configuration

### Hub Configuration

```env
MCP_ENABLE_PASSIVE_DISCOVERY=true    # Listen for broadcasts
DEBUG_LOGGING=false                  # Enable debug output
```

### Server Configuration

```env
# For all servers
MCP_TRANSPORT=http                   # Transport mode
MCP_PORT=3001                        # Server port
MCP_SERVER_NAME=My Server            # Display name

# For broadcasting servers
MCP_ENABLE_BROADCAST=true            # Enable multicast
MCP_BROADCAST_INTERVAL=30            # Broadcast every N seconds
```

## API Endpoints

### GET `/servers`

List all discovered servers and their tools

**Response:**

```json
[
  {
    "id": "192.168.1.1:3001",
    "name": "Podman MCP Server",
    "host": "192.168.1.1",
    "port": 3001,
    "endpoint": "/mcp",
    "status": "online",
    "tools": [
      {
        "name": "list_containers",
        "description": "List containers",
        "inputSchema": {...}
      }
    ]
  }
]
```

### POST `/execute-tool`

Execute a tool on a specific server

**Request:**

```json
{
  "server_id": "192.168.1.1:3001",
  "tool_name": "list_containers",
  "arguments": { "all": false }
}
```

### POST `/scan`

Manually scan network for servers (without broadcasts)

**Request:**

```json
{
  "ports": [3000, 3001, 3002, 8080, 9000]
}
```

### WebSocket `/ws`

Real-time server discovery updates

Connect to receive:

- Server discovery events
- Server status changes
- Tool catalog updates

## Protocol Details

### Traditional MCP

- Full JSON-RPC 2.0 format with `jsonrpc` and `id` fields
- Session-based: requires `Mcp-Session-Id` header
- Stateful communication across multiple requests
- Best for: Complex workflows requiring state

### FastMCP HTTP

- JSON-RPC 2.0 with `jsonrpc` and `id` fields
- Session-based: requires `Mcp-Session-Id` header
- Requires `notifications/initialized` after initialize
- Returns SSE or JSON responses
- Best for: FastMCP library users wanting HTTP mode

### FastMCP Streamable-HTTP

- Simplified format: no `jsonrpc` or `id` fields
- No session management required
- Direct HTTP requests
- Plain JSON responses
- Best for: Simple stateless operations

## Multicast Broadcasting Details

Servers broadcast UDP packets containing:

```json
{
  "type": "mcp-announcement",
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Podman MCP Server",
  "host": "192.168.1.44",
  "port": 3001,
  "endpoint": "/mcp",
  "transport": "http",
  "protocol_type": "MCP-HTTP"
}
```

**Benefits:**

- Zero configuration required
- Automatic server detection
- Scales to multiple networks
- Low overhead (30-second intervals)
- Survives network interruptions

## Use Cases

### 1. Containerized Environments

Deploy multiple MCP servers in Docker/Podman and automatically discover them:

```bash
docker run -p 3001:3001 \
  -e MCP_TRANSPORT=http \
  -e MCP_PORT=3001 \
  podman-mcp-server
```

### 2. Development Workflows

Quickly spin up test servers and have them automatically registered:

```bash
# Terminal 1
uv run file-system-server.py

# Terminal 2
uv run database-server.py

# Terminal 3
python mcp_discovery.py  # Automatically finds both!
```

### 3. LLM Integration

Route tool calls from multiple LLMs to appropriate MCP servers:

```python
# Claude with access to all discovered tools
response = client.messages.create(
    model="claude-3-sonnet",
    tools=hub.get_all_tools(),
    messages=[...]
)
```

### 4. Remote Server Networks

Deploy servers across multiple machines on the same network:

```
Network: 192.168.1.0/24
├─ 192.168.1.10: Podman Server (port 3001)
├─ 192.168.1.20: Database Server (port 3002)
├─ 192.168.1.30: File System Server (port 3001)
└─ 192.168.1.40: Discovery Hub (port 8000)
   └─ Auto-discovers all three servers
```

## Comparison: Before vs After

| Feature            | v1.0             | v2.0                                           |
| ------------------ | ---------------- | ---------------------------------------------- |
| Server Types       | 1 (Traditional)  | 3 (Traditional, FastMCP HTTP, Streamable-HTTP) |
| Discovery          | Manual scan only | Automatic multicast + manual scan              |
| Configuration      | Required         | Zero-config with broadcasts                    |
| Protocol Support   | JSON-RPC only    | JSON-RPC + Simplified format                   |
| Session Management | Manual           | Automatic                                      |
| Response Format    | JSON             | JSON + SSE                                     |
| Scaling            | Limited          | Multi-network capable                          |

## Installation

```bash
# Clone repository
git clone https://github.com/kunwarmahen/mcp-discovery-hub
cd mcp-discovery-hub

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run
python mcp_discovery.py
```

## Requirements

- Python 3.10+
- FastAPI
- httpx
- pydantic
- python-dotenv

## Contributing

Contributions are welcome! Areas for enhancement:

- Additional transport protocols
- Authentication mechanisms
- Server performance monitoring
- Advanced routing policies
- Web UI improvements

## License

MIT License - See LICENSE file for details

## Support

- Issues: https://github.com/kunwarmahen/mcp-discovery-hub/issues
- Discussions: https://github.com/kunwarmahen/mcp-discovery-hub/discussions
- Documentation: https://github.com/kunwarmahen/mcp-discovery-hub/wiki
