"""
MCP Discovery Hub with UPnP/SSDP Listener
Supports both active scanning and passive listening for server announcements
"""

import asyncio
import json
import socket
import aiohttp
from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Set, Any
import httpx
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import uuid
from dotenv import load_dotenv
import os
import struct
from contextlib import asynccontextmanager

load_dotenv()

# Models
class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]

class MCPServer(BaseModel):
    id: str
    name: str
    host: str
    port: int
    endpoint: str
    status: str
    tools: List[MCPTool]
    protocol_version: Optional[str] = None
    session_id: Optional[str] = None
    discovery_method: Optional[str] = "scan"  # "scan" or "broadcast"

class ToolExecutionRequest(BaseModel):
    server_id: str
    tool_name: str
    arguments: Dict

class LLMRequest(BaseModel):
    provider: str
    endpoint: str
    model: str
    messages: List[Dict]
    selected_tools: List[Dict]

class ScanRequest(BaseModel):
    ports: Optional[List[int]] = None

# Storage
discovered_servers: Dict[str, MCPServer] = {}
active_websockets: Set[WebSocket] = set()
server_sessions: Dict[str, str] = {}

# Multicast listener settings
SSDP_ADDR = "239.255.255.250"
MCP_DISCOVERY_PORT = 5353
ENABLE_PASSIVE_DISCOVERY = os.getenv("MCP_ENABLE_PASSIVE_DISCOVERY", "true").lower() == "true"
DEBUG = os.getenv("DEBUG_LOGGING", "false").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup (starting the listener) and shutdown (stopping the listener and cleaning up sessions).
    This replaces the deprecated @app.on_event decorators.
    """
    
    # *** STARTUP LOGIC (replaces @app.on_event("startup")) ***
    if ENABLE_PASSIVE_DISCOVERY:
        # We start the listener as an asyncio task
        asyncio.create_task(listener.start_listening())
        print("Passive discovery started")

    # *** YIELD: The application runs during this time ***
    yield
    
    # *** SHUTDOWN LOGIC (replaces @app.on_event("shutdown")) ***
    print("Initiating shutdown procedures...")
    
    # Stop the listener
    listener.stop_listening()
    
    # Cleanup server sessions
    global server_sessions
    global discovered_servers
    
    # Create a list of cleanup tasks to run concurrently
    cleanup_tasks = []
    
    # Create an async client for efficient connection management
    async with httpx.AsyncClient(timeout=5.0) as client:
        for server_id, session_id in server_sessions.items():
            server = discovered_servers.get(server_id)
            if server:
                async def cleanup_server(s, sid):
                    try:
                        # Send DELETE request to cleanup session
                        await client.delete(
                            f"http://{s.host}:{s.port}{s.endpoint}",
                            headers={"Mcp-Session-Id": sid}
                        )
                        print(f"Cleaned up session {sid} for server {s.name}")
                    except Exception as e:
                        # Log the error but don't fail the shutdown
                        print(f"Failed to clean up session for {s.name}: {e}")
                
                cleanup_tasks.append(cleanup_server(server, session_id))

        # Wait for all cleanup tasks to complete
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
    print("Application shutdown complete.")

app = FastAPI(title="MCP Discovery Hub",  lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MCPListener:
    """Listens for MCP server broadcasts on the network"""
    
    def __init__(self):
        self.running = False
        self.sock = None
        
    async def start_listening(self):
        """Start listening for MCP server announcements"""
        if not ENABLE_PASSIVE_DISCOVERY:
            print("Passive discovery disabled")
            return
            
        self.running = True
        
        # Create UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to the port
        self.sock.bind(('', MCP_DISCOVERY_PORT))
        
        # Join multicast group
        mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        # Set non-blocking
        self.sock.setblocking(False)
        
        print(f"Listening for MCP broadcasts on {SSDP_ADDR}:{MCP_DISCOVERY_PORT}")
        
        while self.running:
            try:
                # Use asyncio to make it non-blocking
                await asyncio.sleep(0.1)
                
                try:
                    data, addr = self.sock.recvfrom(4096)
                    await self.process_announcement(data, addr)
                except BlockingIOError:
                    continue
                except Exception as e:
                    print(f"Error receiving broadcast: {e}")
                    
            except Exception as e:
                print(f"Listener error: {e}")
                await asyncio.sleep(1)
    
    async def process_announcement(self, data: bytes, addr: tuple):
        """Process received MCP announcement"""
        try:
            # First, try to decode as UTF-8
            try:
                decoded_data = data.decode('utf-8')
                debug_print(f"Received MCP broadcast from {addr}: {decoded_data}")
            except UnicodeDecodeError:
                # Not UTF-8, likely from other services (real UPnP/SSDP devices)
                # Silently ignore non-UTF-8 data
                return
            
            # Try to parse as JSON
            try:
                announcement = json.loads(decoded_data)
                debug_print(f"Parsed MCP announcement from {addr}: {announcement}")
            except json.JSONDecodeError:
                # Not JSON, ignore (could be SSDP text format)
                debug_print(f"Ignoring non-JSON broadcast from {addr}")
                return
            
            # Validate this is an MCP announcement
            if not isinstance(announcement, dict):
                return
                
            if announcement.get("type") != "mcp-announcement":
                # Not our announcement type, ignore
                return
            
            # Validate required fields
            required_fields = ["uuid", "name", "host", "port"]
            if not all(field in announcement for field in required_fields):
                return
            
            server_info = {
                "uuid": announcement.get("uuid"),
                "name": announcement.get("name"),
                "host": announcement.get("host"),
                "port": announcement.get("port"),
                "endpoint": announcement.get("endpoint", "/mcp"),
                "protocol": announcement.get("protocol"),
                "version": announcement.get("version")
            }
            
            print(f"✓ Discovered server via broadcast: {server_info['name']} at {server_info['host']}:{server_info['port']}")
            
            # Check if we already know about this server
            server_id = f"{server_info['host']}:{server_info['port']}"
            
            if server_id not in discovered_servers:
                # Initialize and add the server
                server = await probe_mcp_server(
                    server_info['host'],
                    server_info['port'],
                    server_info['endpoint']
                )
                
                if server:
                    server.discovery_method = "broadcast"
                    discovered_servers[server.id] = server
                    await broadcast_server_update(server)
            else:
                # Update last seen time
                discovered_servers[server_id].status = "online"
                
        except Exception as e:
            # Log unexpected errors but don't crash
            print(f"Unexpected error processing announcement: {e}")
    
    def stop_listening(self):
        """Stop listening"""
        self.running = False
        if self.sock:
            self.sock.close()

# Create listener instance
listener = MCPListener()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def get_network_range():
    local_ip = get_local_ip()
    network = local_ip + '/32'
    print(f"Local IP: {local_ip}, Network: {network}")    
    return network

def debug_print(*args, **kwargs):
    """Prints a message only if the DEBUG flag is True."""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

async def initialize_mcp_session(host: str, port: int, endpoint: str = "/mcp") -> Optional[tuple[Dict, str]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {
                        "name": "MCP Discovery Hub",
                        "version": "1.0.0"
                    },
                    "capabilities": {}
                }
            }
            
            response = await client.post(
                f"http://{host}:{port}{endpoint}",
                json=init_request,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                session_id = response.headers.get("Mcp-Session-Id")
                data = response.json()
                
                if data.get("jsonrpc") == "2.0" and "result" in data:
                    return data["result"], session_id
    except Exception as e:
        print(f"Failed to initialize {host}:{port}{endpoint}: {e}")
    return None

async def get_mcp_tools(host: str, port: int, endpoint: str, session_id: str) -> Optional[List[Dict]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            
            response = await client.post(
                f"http://{host}:{port}{endpoint}",
                json=tools_request,
                headers={
                    "Accept": "application/json",
                    "Mcp-Session-Id": session_id
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("jsonrpc") == "2.0" and "result" in data:
                    return data["result"].get("tools", [])
    except Exception as e:
        print(f"Failed to get tools from {host}:{port}: {e}")
    return None

async def probe_fastmcp_http_style(host: str, port: int) -> Optional[tuple[Dict, str, str, List[Dict]]]:
    """
    Probe FastMCP server using HTTP transport (requires JSON-RPC format with jsonrpc/id)
    Returns: (server_info, endpoint, session_id, tools)
    """
    endpoints = ["/mcp", "/messages", "/sse"]
    
    for endpoint in endpoints:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Step 1: Initialize (JSON-RPC format)
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {
                            "name": "MCP Discovery Hub",
                            "version": "1.0.0"
                        },
                        "capabilities": {}
                    }
                }
                
                response = await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=init_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )
                
                if response.status_code != 200:
                    continue
                
                session_id = response.headers.get("Mcp-Session-Id")
                if not session_id:
                    continue
                
                # Parse response (could be SSE or JSON)
                content_type = response.headers.get('content-type', '')
                if 'text/event-stream' in content_type:
                    text = response.text.strip()
                    lines = text.split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            init_data = json.loads(line[6:])
                            break
                else:
                    init_data = response.json()
                
                if "result" not in init_data:
                    continue
                
                server_info = init_data["result"]
                
                # Step 2: Send notifications/initialized
                init_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }
                
                await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=init_notification,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Mcp-Session-Id": session_id
                    }
                )
                
                # Step 3: Get tools/list (JSON-RPC format with id)
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                
                tools_response = await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=tools_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Mcp-Session-Id": session_id
                    }
                )
                
                if tools_response.status_code == 200:
                    # Parse response
                    content_type = tools_response.headers.get('content-type', '')
                    if 'text/event-stream' in content_type:
                        text = tools_response.text.strip()
                        lines = text.split("\n")
                        for line in lines:
                            if line.startswith("data: "):
                                tools_data = json.loads(line[6:])
                                break
                    else:
                        tools_data = tools_response.json()
                    
                    if "error" in tools_data:
                        continue
                    
                    if "result" in tools_data:
                        tools = tools_data["result"].get("tools", [])
                        debug_print(f"✓ FastMCP HTTP detected at {host}:{port}{endpoint}")
                        return server_info, endpoint, session_id, tools
                        
        except Exception as e:
            debug_print(f"FastMCP HTTP probe failed for {host}:{port}{endpoint}: {e}")
            continue
    
    return None


async def probe_fastmcp_streamable_http(host: str, port: int) -> Optional[tuple[Dict, str, List[Dict]]]:
    """
    Probe FastMCP server using streamable-http transport (simplified format, no jsonrpc/id)
    Returns: (server_info, endpoint, tools)
    Note: session_id is not used in streamable-http
    """
    endpoints = ["/mcp", "/messages", "/sse"]
    
    for endpoint in endpoints:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Simplified format: no jsonrpc, no id
                init_request = {
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {
                            "name": "MCP Discovery Hub",
                            "version": "1.0.0"
                        },
                        "capabilities": {}
                    }
                }
                
                response = await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=init_request,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    continue
                
                # Parse response
                init_data = response.json()
                
                if "serverInfo" not in init_data and "result" not in init_data:
                    continue
                
                server_info = init_data if "serverInfo" in init_data else init_data.get("result", {})
                
                # Get tools/list (simplified format)
                tools_request = {
                    "method": "tools/list",
                    "params": {}
                }
                
                tools_response = await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=tools_request,
                    headers={"Content-Type": "application/json"}
                )
                
                if tools_response.status_code == 200:
                    tools_data = tools_response.json()
                    
                    if "error" in tools_data:
                        continue
                    
                    tools = tools_data.get("tools", [])
                    debug_print(f"✓ FastMCP streamable-http detected at {host}:{port}{endpoint}")
                    return server_info, endpoint, tools
                        
        except Exception as e:
            debug_print(f"FastMCP streamable-http probe failed for {host}:{port}{endpoint}: {e}")
            continue
    
    return None


# REPLACE the existing probe_mcp_server function with this enhanced version:

async def probe_mcp_server(host: str, port: int, endpoint: str = None) -> Optional[MCPServer]:
    # Try FastMCP HTTP style first (JSON-RPC with session)
    fastmcp_http_result = await probe_fastmcp_http_style(host, port)
    if fastmcp_http_result:
        server_info, detected_endpoint, session_id, tools = fastmcp_http_result
        
        server = MCPServer(
            id=f"{host}:{port}",
            name=server_info.get("serverInfo", {}).get("name", f"FastMCP Server @ {host}"),
            host=host,
            port=port,
            endpoint=detected_endpoint,
            status="online",
            protocol_version=server_info.get("protocolVersion"),
            session_id=session_id,  # Keep session ID for HTTP style
            tools=[
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    inputSchema=tool.get("inputSchema", {})
                )
                for tool in tools
            ]
        )
        
        server_sessions[server.id] = session_id
        debug_print(f"✓ Detected FastMCP (HTTP) server: {server.name}")
        return server
    
    # Try FastMCP streamable-http style (simplified format, no session)
    fastmcp_streamable_result = await probe_fastmcp_streamable_http(host, port)
    if fastmcp_streamable_result:
        server_info, detected_endpoint, tools = fastmcp_streamable_result
        
        server = MCPServer(
            id=f"{host}:{port}",
            name=server_info.get("serverInfo", {}).get("name", f"FastMCP Server @ {host}"),
            host=host,
            port=port,
            endpoint=detected_endpoint,
            status="online",
            protocol_version=server_info.get("protocolVersion"),
            session_id=None,  # No session for streamable-http
            tools=[
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    inputSchema=tool.get("inputSchema", {})
                )
                for tool in tools
            ]
        )
        
        debug_print(f"✓ Detected FastMCP (streamable-http) server: {server.name}")
        return server
    
    # If not FastMCP, try traditional MCP protocol
    endpoints = [endpoint] if endpoint else ["/mcp", "/", "/v1/mcp"]
    
    for ep in endpoints:
        result = await initialize_mcp_session(host, port, ep)
        if result:
            server_info, session_id = result
            
            tools = await get_mcp_tools(host, port, ep, session_id)
            if tools is None:
                continue
            
            server = MCPServer(
                id=f"{host}:{port}",
                name=server_info.get("serverInfo", {}).get("name", f"MCP Server @ {host}"),
                host=host,
                port=port,
                endpoint=ep,
                status="online",
                protocol_version=server_info.get("protocolVersion"),
                session_id=session_id,
                tools=[
                    MCPTool(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        inputSchema=tool.get("inputSchema", {})
                    )
                    for tool in tools
                ]
            )
            
            server_sessions[server.id] = session_id
            debug_print(f"✓ Detected traditional MCP server: {server.name}")
            return server
    
    return None

async def scan_host(ip: str, ports: List[int]) -> List[MCPServer]:
    servers = []
    for port in ports:
        server = await probe_mcp_server(ip, port)
        if server:
            servers.append(server)
    return servers

async def broadcast_server_update(server: MCPServer):
    message = {
        "type": "server_discovered",
        "server": server.model_dump()
    }
    disconnected = set()
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    
    active_websockets.difference_update(disconnected)

async def discover_mcp_servers_streaming(ports: List[int] = [3000, 3001, 3002, 8080, 9000]):
    network = get_network_range()
    print(f"Scanning network: {network}")
    
    tasks = []
    
    for ip in ipaddress.IPv4Network(network, strict=False):
        ip_str = str(ip)
        tasks.append((ip_str, ports))
    
    batch_size = 20
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        batch_tasks = [scan_host(ip, ports) for ip, ports in batch]
        results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                for server in result:
                    server.discovery_method = "scan"
                    discovered_servers[server.id] = server
                    await broadcast_server_update(server)

async def ensure_session(server: MCPServer) -> str:
    if server.id in server_sessions and server_sessions[server.id]:
        return server_sessions[server.id]
    
    result = await initialize_mcp_session(server.host, server.port, server.endpoint)
    if result:
        _, session_id = result
        server_sessions[server.id] = session_id
        server.session_id = session_id
        return session_id
    
    raise HTTPException(status_code=500, detail="Failed to establish session")

@app.post("/scan", response_model=List[MCPServer])
async def scan_network(request: ScanRequest):
    ports = request.ports if request.ports else [3000, 3001, 3002, 8080, 9000]
    
    global discovered_servers, server_sessions
    discovered_servers = {}
    server_sessions = {}
    
    asyncio.create_task(discover_mcp_servers_streaming(ports))
    
    return []

@app.get("/servers", response_model=List[MCPServer])
async def get_servers():
    return list(discovered_servers.values())


@app.post("/execute-tool")
async def execute_tool(request: ToolExecutionRequest):
    print(f"Executing tool {request.tool_name} on server {request.server_id} with arguments {request.arguments}")
    server = discovered_servers.get(request.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    try:
        # Determine server type by checking session_id and endpoint pattern
        if server.session_id is None:
            # FastMCP streamable-http: no session, simplified format
            tool_request = {
                "method": "tools/call",
                "params": {
                    "name": request.tool_name,
                    "arguments": request.arguments
                }
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{server.host}:{server.port}{server.endpoint}",
                    json=tool_request,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data
                
                raise HTTPException(status_code=response.status_code, detail="Failed to execute tool")
        
        else:
            # FastMCP HTTP or traditional MCP: use session
            tool_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": request.tool_name,
                    "arguments": request.arguments
                }
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{server.host}:{server.port}{server.endpoint}",
                    json=tool_request,
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                        "Mcp-Session-Id": server.session_id
                    }
                )
                
                if response.status_code == 200:
                    # Parse response (could be SSE or JSON)
                    content_type = response.headers.get('content-type', '')
                    if 'text/event-stream' in content_type:
                        text = response.text.strip()
                        lines = text.split("\n")
                        for line in lines:
                            if line.startswith("data: "):
                                data = json.loads(line[6:])
                                break
                    else:
                        data = response.json()
                    
                    if data.get("jsonrpc") == "2.0":
                        if "result" in data:
                            return data["result"]
                        elif "error" in data:
                            raise HTTPException(
                                status_code=500,
                                detail=f"Tool execution error: {data['error'].get('message', 'Unknown error')}"
                            )
                    else:
                        return data
                
                raise HTTPException(status_code=response.status_code, detail="Failed to execute tool")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_with_tools(request: LLMRequest):
    tools_schema = []
    for tool_ref in request.selected_tools:
        server = discovered_servers.get(tool_ref["server_id"])
        if server:
            tool = next((t for t in server.tools if t.name == tool_ref["tool_name"]), None)
            if tool:
                tools_schema.append({
                    "name": f"{server.name}_{tool.name}",
                    "description": tool.description,
                    "parameters": tool.inputSchema
                })
    
    try:
        if request.provider == "ollama":
            return await chat_ollama(request, tools_schema)
        elif request.provider == "openai":
            return await chat_openai(request, tools_schema)
        elif request.provider == "claude":
            return await chat_claude(request, tools_schema)
        else:
            raise HTTPException(status_code=400, detail=f"Provider {request.provider} not supported")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_tool_from_name(tool_name: str, tool_args: Dict, selected_tools: List[Dict]) -> Dict:
    for tool_ref in selected_tools:
        server = discovered_servers.get(tool_ref["server_id"])
        if not server:
            continue
            
        tool = next((t for t in server.tools if t.name == tool_ref["tool_name"]), None)
        if not tool:
            continue
            
        expected_name = f"{server.name}_{tool.name}".replace(" ", "_")
        if expected_name == tool_name:
            try:
                result = await execute_tool(ToolExecutionRequest(
                    server_id=server.id,
                    tool_name=tool.name,
                    arguments=tool_args
                ))
                return result
            except Exception as e:
                return {"error": str(e)}
    
    return {"error": f"Tool {tool_name} not found"}

async def chat_ollama(request: LLMRequest, tools: List[Dict]):
    messages = request.messages.copy()
    
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system",
            "content": "You are a helpful assistant with access to tools."
        })
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        max_iterations = 5
        for iteration in range(max_iterations):
            response = await client.post(
                f"{request.endpoint}/api/chat",
                json={
                    "model": request.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False
                }
            )
            
            result = response.json()
            assistant_message = result.get("message", {})
            messages.append(assistant_message)
            
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                return result
            
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name")
                tool_args = tool_call.get("function", {}).get("arguments", {})
                
                tool_result = await execute_tool_from_name(tool_name, tool_args, request.selected_tools)
                
                messages.append({
                    "role": "tool",
                    "content": json.dumps(tool_result)
                })
        
        return {"message": {"role": "assistant", "content": "Max tool iterations reached"}}

async def chat_openai(request: LLMRequest, tools: List[Dict]):
    messages = request.messages.copy()
    
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system",
            "content": "You are a helpful assistant with access to tools."
        })
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        headers = {"Authorization": f"Bearer {request.endpoint}"}
        
        max_iterations = 5
        for iteration in range(max_iterations):
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": request.model,
                    "messages": messages,
                    "tools": [{"type": "function", "function": t} for t in tools]
                }
            )
            
            result = response.json()
            assistant_message = result["choices"][0]["message"]
            messages.append(assistant_message)
            
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                return result
            
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                
                tool_result = await execute_tool_from_name(tool_name, tool_args, request.selected_tools)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result)
                })
        
        return {"choices": [{"message": {"role": "assistant", "content": "Max tool iterations reached"}}]}

async def chat_claude(request: LLMRequest, tools: List[Dict]):
    messages = request.messages.copy()
    
    system_prompt = "You are a helpful assistant with access to tools."
    
    if messages and messages[0].get("role") == "system":
        system_prompt = messages[0]["content"]
        messages = messages[1:]
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        headers = {
            "x-api-key": request.endpoint,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        max_iterations = 5
        for iteration in range(max_iterations):
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": request.model,
                    "system": system_prompt,
                    "messages": messages,
                    "tools": tools,
                    "max_tokens": 4096
                }
            )
            
            result = response.json()
            assistant_message = {
                "role": "assistant",
                "content": result.get("content", [])
            }
            messages.append(assistant_message)
            
            tool_uses = [block for block in result.get("content", []) if block.get("type") == "tool_use"]
            if not tool_uses:
                return result
            
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use["name"]
                tool_args = tool_use["input"]
                
                tool_result = await execute_tool_from_name(tool_name, tool_args, request.selected_tools)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use["id"],
                    "content": json.dumps(tool_result)
                })
            
            messages.append({
                "role": "user",
                "content": tool_results
            })
        
        return {"content": [{"type": "text", "text": "Max tool iterations reached"}]}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    
    try:
        await websocket.send_json({
            "type": "initial_servers",
            "servers": [s.dict() for s in discovered_servers.values()]
        })
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "scan":
                ports = message.get("ports", [3000, 3001, 3002, 8080, 9000])
                discovered_servers.clear()
                server_sessions.clear()
                asyncio.create_task(discover_mcp_servers_streaming(ports))
                await websocket.send_json({"type": "scan_started"})
            
            elif message.get("type") == "chat":
                chat_data = message.get("data")
                async for chunk in stream_chat(chat_data):
                    await websocket.send_json(chunk)
                    
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        if websocket in active_websockets:
            active_websockets.remove(websocket)


async def build_system_prompt(tools_schema, provider: str):
    if not tools_schema:
        return "You are a helpful assistant."
    
    # For providers with native tool calling, keep it simple
    if provider in ["openai", "claude", "ollama"]:
        tools_desc = "\n".join(
            [f"- {tool['name']}: {tool['description']}" for tool in tools_schema]
        )
        return (
            "You are a helpful assistant with access to the following tools:\n\n"
            f"{tools_desc}\n\n"
            "Use these tools when appropriate to help answer the user's questions. "
            "Always explain what you're doing when calling tools and provide clear, "
            "helpful responses based on the tool results."
        )
    
    # Fallback for providers without native tool support
    tools_desc = "\n".join(
        [f"- {tool['name']}: {tool['description']}\n  Parameters: {json.dumps(tool['parameters'])}" 
         for tool in tools_schema]
    )
    return (
        "You are a helpful assistant with access to external tools.\n\n"
        f"AVAILABLE TOOLS:\n{tools_desc}\n\n"
        "When you need to use a tool, respond with ONLY a JSON object in this exact format:\n"
        '{"tool_call": "<tool_name>", "arguments": {"param1": "value1", "param2": "value2"}}\n\n'
        "After receiving tool results, provide a natural language response to the user."
    )


async def stream_chat(chat_data: Dict):
    provider = chat_data.get("provider")
    endpoint = chat_data.get("endpoint")
    model = chat_data.get("model")
    messages = chat_data.get("messages", [])
    selected_tools = chat_data.get("selected_tools", [])
    
    tools_schema = []
    for tool_ref in selected_tools:
        server = discovered_servers.get(tool_ref["server_id"])
        if server:
            tool = next((t for t in server.tools if t.name == tool_ref["tool_name"]), None)
            if tool:
                tools_schema.append({
                    "name": f"{server.name}_{tool.name}".replace(" ", "_"),
                    "description": tool.description,
                    "parameters": tool.inputSchema
                })
    
    # Build system prompt
    if not messages or messages[0].get("role") != "system":
        system_prompt = await build_system_prompt(tools_schema, provider)
        messages.insert(0, {"role": "system", "content": system_prompt})

    try:
        if provider == "ollama":
            async for chunk in stream_ollama(endpoint, model, messages, tools_schema, selected_tools):
                yield chunk
        elif provider == "openai":
            async for chunk in stream_openai(endpoint, model, messages, tools_schema, selected_tools):
                yield chunk
        elif provider == "claude":
            async for chunk in stream_claude(endpoint, model, messages, tools_schema, selected_tools):
                yield chunk
        else:
            yield {
                "type": "error",
                "error": f"Provider {provider} not supported"
            }
    except Exception as e:
        yield {
            "type": "error",
            "error": str(e)
        }

async def stream_ollama(endpoint: str, model: str, messages: list, tools_schema: list, selected_tools: list):
    """Streaming for Ollama with preserved formatting"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        max_iterations = 5
        for iteration in range(max_iterations):
            response = await client.post(
                f"{endpoint}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools_schema if tools_schema else None,
                    "stream": False
                }
            )
            
            result = response.json()
            message = result.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls")
            
            # Stream content while preserving formatting
            if content:
                # Option 1: Stream character by character (smoothest, preserves everything)
                for char in content:
                    yield {
                        "type": "chat_chunk",
                        "content": char,
                        "done": False
                    }
                    await asyncio.sleep(0.01)  # Adjust delay for speed (10ms per char)
                
                # Option 2: Stream by lines (good for code blocks and lists)
                # lines = content.split('\n')
                # for i, line in enumerate(lines):
                #     yield {
                #         "type": "chat_chunk",
                #         "content": line + ('\n' if i < len(lines) - 1 else ''),
                #         "done": False
                #     }
                #     await asyncio.sleep(0.03)  # Delay per line
                
                # Option 3: Smart chunking (balanced approach)
                # async for chunk in smart_chunk_content(content):
                #     yield {
                #         "type": "chat_chunk",
                #         "content": chunk,
                #         "done": False
                #     }
            
            messages.append(message)
            
            # Handle tool calls
            if tool_calls:
                yield {
                    "type": "chat_chunk",
                    "content": "\n\n🔧 Executing tools...\n",
                    "done": False
                }
                
                for tool_call in tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args = tool_call.get("function", {}).get("arguments", {})
                    
                    yield {
                        "type": "chat_chunk",
                        "content": f"→ Calling {tool_name}...\n",
                        "done": False
                    }
                    
                    tool_result = await execute_tool_from_name(tool_name, tool_args, selected_tools)
                    
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_result)
                    })
                
                yield {
                    "type": "chat_chunk",
                    "content": "\n",
                    "done": False
                }
                continue
            else:
                yield {
                    "type": "chat_chunk",
                    "content": "",
                    "done": True
                }
                return
        
        yield {
            "type": "chat_chunk",
            "content": "\n\n⚠️ Max tool iterations reached",
            "done": True
        }


async def stream_openai(api_key: str, model: str, messages: list, tools_schema: list, selected_tools: list):
    """Non-streaming API call but streaming response to UI"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        headers = {"Authorization": f"Bearer {api_key}"}
        
        max_iterations = 5
        for iteration in range(max_iterations):
            # Make non-streaming API call
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "tools": [{"type": "function", "function": t} for t in tools_schema] if tools_schema else None
                }
            )
            
            result = response.json()
            
            if "error" in result:
                yield {
                    "type": "error",
                    "error": result["error"].get("message", "Unknown error")
                }
                return
            
            assistant_message = result["choices"][0]["message"]
            content = assistant_message.get("content", "")
            tool_calls = assistant_message.get("tool_calls")
            
            # Stream content to UI word by word or sentence by sentence
            if content:
                # Split by words for smoother streaming effect
                words = content.split()
                for i, word in enumerate(words):
                    yield {
                        "type": "chat_chunk",
                        "content": word + (" " if i < len(words) - 1 else ""),
                        "done": False
                    }
                    await asyncio.sleep(0.02)  # Small delay for streaming effect
            
            messages.append(assistant_message)
            
            # Handle tool calls
            if tool_calls:
                yield {
                    "type": "chat_chunk",
                    "content": "\n\n🔧 Executing tools...\n",
                    "done": False
                }
                
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    
                    yield {
                        "type": "chat_chunk",
                        "content": f"→ Calling {tool_name}...\n",
                        "done": False
                    }
                    
                    tool_result = await execute_tool_from_name(tool_name, tool_args, selected_tools)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result)
                    })
                
                yield {
                    "type": "chat_chunk",
                    "content": "\n",
                    "done": False
                }
                continue
            else:
                # No more tool calls, we're done
                yield {
                    "type": "chat_chunk",
                    "content": "",
                    "done": True
                }
                return
        
        yield {
            "type": "chat_chunk",
            "content": "\n\n⚠️ Max tool iterations reached",
            "done": True
        }

async def stream_claude(api_key: str, model: str, messages: list, tools_schema: list, selected_tools: list):
    """Non-streaming API call but streaming response to UI"""
    # Extract system prompt
    system_prompt = "You are a helpful assistant."
    if messages and messages[0].get("role") == "system":
        system_prompt = messages[0]["content"]
        messages = messages[1:]
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        max_iterations = 5
        for iteration in range(max_iterations):
            # Make non-streaming API call
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": model,
                    "system": system_prompt,
                    "messages": messages,
                    "tools": tools_schema if tools_schema else None,
                    "max_tokens": 4096
                }
            )
            
            result = response.json()
            
            if "error" in result:
                yield {
                    "type": "error",
                    "error": result["error"].get("message", "Unknown error")
                }
                return
            
            content_blocks = result.get("content", [])
            
            # Stream text content to UI
            text_blocks = [block for block in content_blocks if block.get("type") == "text"]
            for block in text_blocks:
                text = block.get("text", "")
                # Split by sentences for natural streaming
                sentences = text.replace(". ", ".|").replace("? ", "?|").replace("! ", "!|").split("|")
                for sentence in sentences:
                    if sentence.strip():
                        yield {
                            "type": "chat_chunk",
                            "content": sentence,
                            "done": False
                        }
                        await asyncio.sleep(0.03)
            
            assistant_message = {
                "role": "assistant",
                "content": content_blocks
            }
            messages.append(assistant_message)
            
            # Handle tool calls
            tool_uses = [block for block in content_blocks if block.get("type") == "tool_use"]
            if tool_uses:
                yield {
                    "type": "chat_chunk",
                    "content": "\n\n🔧 Executing tools...\n",
                    "done": False
                }
                
                tool_results = []
                for tool_use in tool_uses:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    
                    yield {
                        "type": "chat_chunk",
                        "content": f"→ Calling {tool_name}...\n",
                        "done": False
                    }
                    
                    tool_result = await execute_tool_from_name(tool_name, tool_args, selected_tools)
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": json.dumps(tool_result)
                    })
                
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
                
                yield {
                    "type": "chat_chunk",
                    "content": "\n",
                    "done": False
                }
                continue
            else:
                # No more tool calls, we're done
                yield {
                    "type": "chat_chunk",
                    "content": "",
                    "done": True
                }
                return
        
        yield {
            "type": "chat_chunk",
            "content": "\n\n⚠️ Max tool iterations reached",
            "done": True
        }

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Starting MCP Discovery Hub")
    print("=" * 60)
    print("Port: 8000")
    print("WebSocket: ws://localhost:8000/ws")
    print("API: http://localhost:8000/scan")
    print(f"Passive Discovery: {'ENABLED' if ENABLE_PASSIVE_DISCOVERY else 'DISABLED'}")
    if ENABLE_PASSIVE_DISCOVERY:
        print(f"Listening on: {SSDP_ADDR}:{MCP_DISCOVERY_PORT}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)