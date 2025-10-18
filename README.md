# MCP Discovery Hub

Automatic discovery and management of Model Context Protocol (MCP) servers across your network.

Inspired by DLNA (Digital Living Network Alliance) and UPnP (Universal Plug and Play), MCP Discovery Hub brings zero-configuration networking to AI tool discovery. Just as your TV automatically finds Chromecast devices and your phone discovers AirPlay speakers, MCP Discovery Hub automatically finds and connects to MCP servers on your local network.

## Philosophy

Why DLNA/UPnP? Because they work. Your devices have been discovering each other without configuration for decades. We're applying the same battle-tested principles to AI:

| Problem                 | DLNA/UPnP Solution            | MCP Discovery Hub                   |
| ----------------------- | ----------------------------- | ----------------------------------- |
| **Discovery**           | Devices broadcast "I'm here!" | Servers broadcast via multicast UDP |
| **Configuration**       | Zero config, just works™      | Zero config, just works™            |
| **Service Description** | XML descriptors               | JSON tool schemas                   |
| **Control**             | SOAP/HTTP protocol            | REST/WebSocket + JSON-RPC           |
| **Multi-device**        | Seamless integration          | Multi-server orchestration          |

Instead of manually configuring each MCP server, just start them and the hub discovers everything automatically.

## The Problem

You have multiple MCP servers running across your network, but:

- 😫 No easy way to discover them
- 🔌 Each server requires manual configuration
- 🤝 No unified interface to interact with multiple servers
- 🚀 Switching between LLM providers means reconfiguring everything

## The Solution

```
Scan Network → Discover Tools → Chat with Any LLM
(Just like DLNA discovers your smart TV)
```

**Core Features:**

- **Auto-discover MCP servers** on your network (UPnP-style discovery)
- **Browse tools** from all discovered servers in one interface
- **Select tools** you want to use (drag-and-drop style)
- **Chat with your LLM** using selected tools seamlessly
- **Multi-LLM support**: Ollama, OpenAI, Claude, Gemini, vLLM, and more
- **Beautiful UI** with real-time discovery and streaming responses
- **Zero configuration** - just start servers and they appear

## How It Works

### Discovery Process

**DLNA/UPnP Discovery:**

1. Device broadcasts: "I'm here! I'm a media server!"
2. Control point listens and catalogs devices
3. User selects device from list
4. Control point connects and uses device services

**MCP Discovery Hub Process:**

1. Hub listens for multicast announcements: "Who's an MCP server?"
2. Servers broadcast: "I'm here! Here are my tools"
3. Tools appear in real-time in your interface
4. User selects tools and chats with LLM

### Architecture

```
MCP Servers (any type)
├── Traditional (JSON-RPC)
├── FastMCP HTTP (JSON-RPC)
└── FastMCP Streamable (Simplified)
        ↓
   Multicast UDP 239.255.255.250:5353
   (Like SSDP in UPnP)
        ↓
┌─────────────────────────────────────┐
│   Discovery Hub (port 8000)         │
│   (Like UPnP Control Point)         │
├─────────────────────────────────────┤
│ • Network Listening & Probing       │
│ • Tool Catalog Management           │
│ • Multi-protocol Execution          │
│ • LLM Integration (multi-provider)  │
└─────────────────────────────────────┘
        ↓
   WebSocket & REST API
        ↓
┌──────────────┬──────────────┬──────────┐
│  Web UI      │  CLI Tools   │ LLM Apps │
│  (Like DLNA  │              │          │
│   Control    │              │          │
│   Point App) │              │          │
└──────────────┴──────────────┴──────────┘
```

### Sequence Diagram

```
Client         Discovery Hub    MCP Server
│              │                │
├─ Scan ─────>│                │
│              │                │
│              ├─ Listen for broadcasts or probe
│              ├──────────────────────────>│
│              │                │
│              │<─ Service Description ──│
│              │ (Tools, capabilities)   │
│              │                │
│<─ Server Found─┤                │
│  (Real-time)   │                │
│                │                │
├─ Chat + Tools─>│                │
│                ├─ Execute Tool──>│
│                │                │
│                │<─ Tool Result ─┤
│<─ LLM Response-┤                │
│  (Streaming)   │                │
```

## Supported Server Types

The hub intelligently handles three different MCP implementations:

| Protocol               | Format       | Sessions      | Discovery        | Best For                        |
| ---------------------- | ------------ | ------------- | ---------------- | ------------------------------- |
| **Traditional MCP**    | JSON-RPC 2.0 | Session-based | HTTP probing     | Stateful production deployments |
| **FastMCP HTTP**       | JSON-RPC 2.0 | Session-based | Multicast + HTTP | Containerized deployments       |
| **FastMCP Streamable** | Simplified   | Stateless     | Multicast + HTTP | Lightweight operations          |

## Quick Start

### 1. Install & Run Discovery Hub

```bash
git clone https://github.com/kunwarmahen/mcp-discovery-hub-mcast.git
cd mcp-discovery-hub-mcast

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python mcp_discovery.py
```

The hub will start on port 8000 and automatically listen for server announcements on the multicast address.

### 2. Launch MCP Servers

Servers announce themselves automatically via multicast. Start any MCP server:

**Traditional MCP Server**

```bash
python sample_mcp_server.py
```

**FastMCP HTTP Mode**

```bash
MCP_TRANSPORT=http MCP_PORT=3001 uv run main.py
```

**FastMCP Streamable-HTTP Mode**

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=3001 uv run main.py
```

Servers are discovered automatically as they come online.

### 3. Setup Frontend (Optional - for beautiful UI)

```bash
# In a new terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` to see servers appear in real-time.

### 4. Query via API

```bash
# Get all discovered servers
curl http://localhost:8000/servers

# List all available tools
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

```bash
# Environment variables for discovery hub
MCP_ENABLE_PASSIVE_DISCOVERY=true      # Listen for multicast broadcasts
DEBUG_LOGGING=false                     # Enable debug output
NETWORK_SCAN_PORTS=[3000,3001,3002]    # Fallback ports for manual scanning
WEBSOCKET_HEARTBEAT_INTERVAL=30        # Heartbeat interval in seconds
```

### Server Configuration

**All Servers**

```bash
MCP_TRANSPORT=http                  # Transport mode
MCP_PORT=3001                       # Server port
MCP_SERVER_NAME="My Server"         # Display name in hub
```

**Broadcasting Servers (Multicast Discovery)**

```bash
MCP_ENABLE_BROADCAST=true           # Enable multicast announcements
MCP_BROADCAST_INTERVAL=30           # Broadcast every N seconds (like UPnP SSDP)
MCP_MULTICAST_ADDRESS=239.255.255.250  # Multicast group
MCP_MULTICAST_PORT=5353             # Multicast port (like UPnP)
```

## API Reference

### GET /servers

List all discovered servers and their tools.

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
    "protocol_type": "MCP-HTTP",
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

### POST /execute-tool

Execute a tool on a specific server.

**Request:**

```json
{
  "server_id": "192.168.1.1:3001",
  "tool_name": "list_containers",
  "arguments": { "all": false }
}
```

### POST /scan-network

Manually scan network for servers (fallback if multicast unavailable).

**Request:**

```json
{
  "ports": [3000, 3001, 3002, 8080, 9000]
}
```

### POST /chat

Send a chat message with selected tools to configured LLM.

**Request:**

```json
{
  "message": "List my files and create a summary",
  "selected_tools": [
    { "server_id": "192.168.1.1:3001", "tool_name": "read_file" },
    { "server_id": "192.168.1.1:3001", "tool_name": "list_directory" }
  ]
}
```

### WS /ws

Real-time WebSocket connection for server discovery and status updates.

**Message Types:**

- `server_discovered` - New server found
- `server_offline` - Server went offline
- `chat_chunk` - Streaming chat response
- `tool_executed` - Tool execution result
- `error` - Error message

## Discovery Protocol Details

### Multicast Broadcasting (Like UPnP SSDP)

Servers broadcast UDP packets on the multicast address `239.255.255.250:5353` every 30 seconds:

```json
{
  "type": "mcp-announcement",
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Podman MCP Server",
  "host": "192.168.1.44",
  "port": 3001,
  "endpoint": "/mcp",
  "transport": "http",
  "protocol_type": "MCP-HTTP",
  "tools_count": 5,
  "ttl": 120
}
```

**Benefits:**

- Zero manual configuration required
- Automatic server detection across networks
- Low overhead (30-second broadcast intervals)
- Survives network interruptions
- Works with network segmentation

### HTTP Probing (Fallback)

If multicast is unavailable (some networks block UDP), the hub can manually probe configurable port ranges:

```bash
POST /scan-network
{
  "ports": [3000, 3001, 3002, 8080, 9000],
  "timeout": 5000
}
```

This ensures discovery works in any environment.

## Firewall Configuration

The hub uses multicast UDP for server discovery (like UPnP/SSDP). If servers aren't being discovered but work when the firewall is disabled, firewall rules are blocking the traffic.

### Multicast Basics

- **Address**: `239.255.255.250` (SSDP multicast group, same as UPnP)
- **Port**: `5353` (UDP)
- **Type**: Multicast (one-to-many, local network only)
- **Protocol**: IGMP (Internet Group Management Protocol) for group membership

### UFW (Ubuntu/Debian) - The Most Common Issue

This is a very common and frustrating problem when dealing with multicast traffic on Linux firewalls, specifically UFW.

**Why It Fails**

The reason it works when you disable UFW but not when the rule is in place is that UFW's simple rules don't always correctly handle the complexity of multicast and IGMP (Internet Group Management Protocol) packets.

When a firewall is active, it may block not just the data packets but also the IGMP packets that the kernel uses to join the multicast group (`239.255.255.250`). Your application's code may be joining the group, but the firewall is preventing the kernel from receiving the packets, even if you open port 5353/UDP.

**The Fix: Modify UFW's `before.rules`**

For multicast to work reliably with UFW, you often need to insert specific rules into the underlying `iptables` configuration file that UFW uses, which is `/etc/ufw/before.rules`. These rules allow traffic to the entire multicast address range (`224.0.0.0/4`) and explicitly allow the IGMP protocol.

> **Note**: You must be careful when editing this file.

**Step 1: Open the `before.rules` File**

Use a text editor like `nano` or `vim` with `sudo`:

```bash
sudo nano /etc/ufw/before.rules
```

**Step 2: Add Multicast and IGMP Rules**

Scroll down in the file until you find the section for allowing incoming traffic, usually near the top, before the line that says `# drop invalid packets`. Add the following block of rules above the `COMMIT` line, and ideally near where other basic protocols (like ICMP/ping) are allowed:

```bash
#
# START MCP DISCOVERY MULTICAST RULES
#
# Allow all incoming UDP traffic to the multicast address range
# for the SSDP/MCP Discovery data packets (239.255.255.250 is in 224.0.0.0/4)
-A ufw-before-input -p udp -d 224.0.0.0/4 -j ACCEPT

# Allow IGMP (Protocol 2) for joining and maintaining multicast groups
# This is often the critical missing piece.
-A ufw-before-input -p igmp -j ACCEPT

# Allow incoming UDP packets specifically on port 5353 (SSDP)
-A ufw-before-input -p udp --dport 5353 -d 239.255.255.250 -j ACCEPT
#
# END MCP DISCOVERY MULTICAST RULES
#
```

**Rule Explanations:**

- `-p udp -d 224.0.0.0/4 -j ACCEPT`: This is a broad rule that allows all incoming UDP multicast traffic.
- `-p igmp -j ACCEPT`: This explicitly allows the IGMP control traffic (Protocol 2) needed for your Linux kernel to properly subscribe to the `239.255.255.250` multicast group. **This is often the critical missing piece.**
- `-p udp --dport 5353 -d 239.255.255.250 -j ACCEPT`: This is the specific rule you were likely trying to add with the simple UFW command, but placing it in `before.rules` with the destination address makes it more reliable.

**Step 3: Save and Reload UFW**

Save the file and exit the editor (`Ctrl+X`, then `Y`, then `Enter` in `nano`).

Now, reload the UFW service to apply the changes to the underlying `iptables` chains:

```bash
sudo ufw reload
```

After the reload, your UFW firewall will be active, but the special `before.rules` should now correctly permit the necessary multicast control (IGMP) and data (UDP 5353) packets, allowing your MCP discovery to work.

### Windows Firewall

If using Windows, allow UDP port 5353 for multicast:

```powershell
# PowerShell (as Administrator)
New-NetFirewallRule -DisplayName "MCP Discovery Multicast" `
  -Direction Inbound `
  -Action Allow `
  -Protocol UDP `
  -LocalPort 5353 `
  -RemoteAddress "239.255.255.250" `
  -Group "MCP Discovery Hub"
```

### macOS Firewall

macOS typically allows multicast by default. If issues occur:

```bash
# Check if firewall is blocking mDNS/multicast
sudo launchctl list | grep firewall

# Allow multicast if needed (usually not required)
sudo defaults write /Library/Preferences/com.apple.alf globalstate -int 1
```

### Docker/Podman Networks

Containers need explicit network configuration for multicast:

```bash
# Docker - use host network for multicast
docker run --network host -e MCP_ENABLE_BROADCAST=true my-server

# Podman - similar approach
podman run --network host -e MCP_ENABLE_BROADCAST=true my-server

# Or use macvlan for container-specific IPs with multicast
docker network create -d macvlan -o parent=eth0 macvlan-net
docker run --network macvlan-net -e MCP_ENABLE_BROADCAST=true my-server
```

### Enterprise/Corporate Networks

Some corporate networks block multicast entirely. Solutions:

1. **Use fallback HTTP probing**:

   ```bash
   curl -X POST http://localhost:8000/scan-network \
     -H "Content-Type: application/json" \
     -d '{"ports": [3000, 3001, 3002, 8080, 9000]}'
   ```

2. **Request network team to allow multicast range** `224.0.0.0/4` and IGMP protocol

3. **Use VPN with multicast support** if connecting from outside network

4. **Deploy hub on same subnet** as servers to reduce firewall complexity

## Use Cases

### Single Network Deployment

```
192.168.1.0/24
├─ 192.168.1.10: Podman Server (port 3001)
├─ 192.168.1.20: Database Server (port 3002)
├─ 192.168.1.30: File System Server (port 3001)
└─ 192.168.1.40: Discovery Hub (port 8000)
    └─ Auto-discovers all three servers instantly
```

### Containerized Environment

Deploy multiple MCP servers in Docker/Podman with automatic discovery:

```bash
docker run -p 3001:3001 \
  -e MCP_TRANSPORT=http \
  -e MCP_PORT=3001 \
  -e MCP_ENABLE_BROADCAST=true \
  podman-mcp-server
```

### Multi-Tool Orchestration

```
1. Discover: File System MCP, Database MCP, Web Scraper MCP
2. Select: read_file, query_sql, fetch_url
3. Chat: "Read data.json, query matching records, scrape additional info"
4. LLM orchestrates all tools automatically
```

### LLM Integration

Route tool calls from multiple LLM providers to appropriate MCP servers:

```python
response = client.messages.create(
  model="claude-3-sonnet",
  tools=hub.get_all_tools(),
  messages=[...]
)
```

## Protocol Comparison

### Traditional MCP (JSON-RPC)

- Full JSON-RPC 2.0 compliance
- Session-based via `Mcp-Session-Id` header
- Stateful communication across requests
- Best for: Complex workflows requiring state

### FastMCP HTTP Mode (JSON-RPC)

- JSON-RPC 2.0 with automatic sessions
- Requires `notifications/initialized` after initialize
- Returns SSE or JSON responses
- Best for: FastMCP library users wanting HTTP mode

### FastMCP Streamable-HTTP (Simplified)

- Simplified format without JSON-RPC wrapper
- No session management required
- Direct HTTP requests with plain JSON
- Best for: Lightweight stateless operations

## Installation

### Prerequisites

- Python 3.8+
- Node.js 16+ (for frontend)
- An LLM provider (Ollama, OpenAI, Claude, etc.)

### Full Setup

```bash
# Clone repository
git clone https://github.com/kunwarmahen/mcp-discovery-hub-mcast.git
cd mcp-discovery-hub-mcast

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup (optional)
cd ../frontend
npm install

# Run both (in separate terminals)
# Terminal 1: Backend
python ../backend/mcp_discovery.py

# Terminal 2: Frontend
npm run dev

# Terminal 3: LLM (if using Ollama)
ollama serve

# Terminal 4+: MCP Servers
python sample_mcp_server.py
```

## Troubleshooting

| Problem                                            | Solutions                                                                                                                                                                                                                  |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Servers not discovered**                         | ✅ Ensure servers are running<br>✅ Verify servers have `MCP_ENABLE_BROADCAST=true`<br>✅ Check firewall allows UDP 5353 AND IGMP<br>✅ Test: `sudo tcpdump -i any udp port 5353`<br>✅ Try fallback: `POST /scan-network` |
| **Works without firewall, fails with UFW enabled** | ✅ Edit `/etc/ufw/before.rules` (see Firewall Configuration above)<br>✅ Add IGMP protocol rule<br>✅ Run `sudo ufw reload`                                                                                                |
| **Works on Linux, not in Docker**                  | ✅ Use `--network host` for containers<br>✅ Or configure `macvlan` network for multicast<br>✅ Check container network isolation                                                                                          |
| **WebSocket disconnected**                         | ✅ Backend running?<br>✅ Check firewall/proxy settings<br>✅ Verify WebSocket URL in frontend config                                                                                                                      |
| **Tools not executing**                            | ✅ Server online? (Check status badge)<br>✅ Tool parameters correct?<br>✅ LLM configured and running?                                                                                                                    |
| **No multicast on network**                        | ✅ Use fallback: `POST /scan-network`<br>✅ Manually specify IP ranges<br>✅ Check with network admin if multicast is allowed<br>✅ Consider VPN or on-subnet deployment                                                   |

### Debugging Multicast

Check if multicast is working:

```bash
# Listen for multicast packets
sudo tcpdump -i any udp port 5353 -v

# In another terminal, trigger a server announcement
# (should see packets in tcpdump output)

# Test IGMP group membership (Linux)
netstat -gn | grep 239.255.255.250

# Check multicast routing
ip mroute
```

## Version History

| Feature          | v1.0         | v2.0                         |
| ---------------- | ------------ | ---------------------------- |
| Discovery Method | HTTP probing | Multicast UDP + HTTP probing |
| Server Types     | 1            | 3                            |
| Configuration    | Manual       | Zero-config broadcasts       |
| Protocol Support | JSON-RPC     | JSON-RPC + Simplified        |
| UI               | Vite React   | Real-time updates            |
| Multi-LLM        | Basic        | Full support                 |

## Contributing

We welcome contributions! Areas for enhancement include:

- Additional transport protocols
- Authentication & authorization
- Server performance monitoring
- Advanced tool chaining and workflows
- Web UI improvements
- Documentation & examples
- Test coverage

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Resources

- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification
- [UPnP/DLNA](https://en.wikipedia.org/wiki/Universal_Plug_and_Play) - Zero-config inspiration
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Ollama](https://ollama.ai/) - Local LLM runtime

## Support

- 📖 [Documentation](./docs)
- 🐛 [Issues](https://github.com/kunwarmahen/mcp-discovery-hub-mcast/issues)
- 💬 [Discussions](https://github.com/kunwarmahen/mcp-discovery-hub-mcast/discussions)

## Project Evolution

- **v1.0**: [Original blog post](https://medium.com/@kunwarmahen/introducing-mcp-discovery-hub-upnp-dlna-for-ai-tools-54d6ba72ce31) - The inception of the DLNA/UPnP concept
- **v1.0 Repository**: [github.com/kunwarmahen/mcp-discovery-hub](https://github.com/kunwarmahen/mcp-discovery-hub) - HTTP probing based discovery
- **v2.0 Repository**: [github.com/kunwarmahen/mcp-discovery-hub-mcast](https://github.com/kunwarmahen/mcp-discovery-hub-mcast) - Multicast UDP discovery (this version)

---

Built with ❤️ by developers, for developers. If you find this useful, please star it! ⭐
