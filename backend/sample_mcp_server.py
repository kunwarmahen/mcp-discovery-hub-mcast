"""
MCP Server with UPnP/SSDP Broadcasting Support
Broadcasts server presence on local network for automatic discovery
"""

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, AsyncGenerator
import json
import asyncio
from dataclasses import dataclass
import os
import uuid
from dotenv import load_dotenv
import socket
import struct

load_dotenv()

app = FastAPI(title="MCP File System Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@dataclass
class Tool:
    name: str
    description: str
    inputSchema: Dict[str, Any]

# Configuration
REQUIRE_AUTH = os.getenv("MCP_REQUIRE_AUTH", "false").lower() == "true"
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
ENABLE_BROADCAST = os.getenv("MCP_ENABLE_BROADCAST", "true").lower() == "true"
BROADCAST_INTERVAL = int(os.getenv("MCP_BROADCAST_INTERVAL", "30"))
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "3000"))
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "File System MCP Server")

DEBUG = os.getenv("DEBUG_LOGGING", "false").lower() == "true"

# SSDP/Multicast settings
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
MCP_DISCOVERY_PORT = 5353  # Custom port for MCP discovery

def debug_print(*args, **kwargs):
    """Prints a message only if the DEBUG flag is True."""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

def verify_auth(authorization: Optional[str] = None) -> bool:
    if not REQUIRE_AUTH:
        return True
    if not authorization:
        return False
    token = authorization.replace("Bearer ", "").strip()
    return token == AUTH_TOKEN

class JSONRPCRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[Dict[str, Any]] = {}
    id: Optional[Any] = None

class MCPBroadcaster:
    """Handles SSDP-style broadcasting for MCP server discovery"""
    
    def __init__(self, server_name: str, port: int):
        self.server_name = server_name
        self.port = port
        self.uuid = str(uuid.uuid4())
        self.running = False
        self.sock = None
        
    def get_local_ip(self):
        """Get the local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            debug_print(f"Local IP address determined: {ip}")
            return ip
        except:
            return '127.0.0.1'
    
    def create_announcement(self):
        """Create MCP discovery announcement message"""
        local_ip = self.get_local_ip()
        announcement = {
            "type": "mcp-announcement",
            "protocol": "MCP-DISCOVERY-v1",  # Magic identifier
            "uuid": self.uuid,
            "name": self.server_name,
            "host": local_ip,
            "port": self.port,
            "endpoint": "/mcp",
            "protocol_type": "MCP-HTTP",
            "version": "1.0.0",
            "timestamp": asyncio.get_event_loop().time()
        }
        return json.dumps(announcement).encode('utf-8')
    
    async def start_broadcasting(self):
        """Start broadcasting server presence"""
        if not ENABLE_BROADCAST:
            print("Broadcasting disabled via MCP_ENABLE_BROADCAST=false")
            return
            
        self.running = True
        
        # Create UDP socket for multicast
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        print(f"Starting MCP broadcaster on {SSDP_ADDR}:{MCP_DISCOVERY_PORT}")
        print(f"Broadcasting every {BROADCAST_INTERVAL} seconds")
        
        while self.running:
            try:
                message = self.create_announcement()
                debug_print(f"Broadcasting MCP announcement: {message.decode('utf-8')}")
                self.sock.sendto(message, (SSDP_ADDR, MCP_DISCOVERY_PORT))
                await asyncio.sleep(BROADCAST_INTERVAL)
            except Exception as e:
                print(f"Broadcast error: {e}")
                await asyncio.sleep(5)
    
    def stop_broadcasting(self):
        """Stop broadcasting"""
        self.running = False
        if self.sock:
            self.sock.close()

class MCPServer:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self.tools: List[Tool] = []
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.message_queues: Dict[str, asyncio.Queue] = {}
        
    def add_tool(self, tool: Tool):
        self.tools.append(tool)
    
    async def handle_message(self, message: Dict[str, Any], session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        jsonrpc = message.get("jsonrpc")
        if jsonrpc != "2.0":
            return self.error_response(None, -32600, "Invalid Request")
        
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")
        
        if method == "initialize":
            return await self.handle_initialize(msg_id, params, session_id)
        elif method == "tools/list":
            return await self.handle_tools_list(msg_id)
        elif method == "tools/call":
            return await self.handle_tools_call(msg_id, params)
        elif method == "ping":
            return self.success_response(msg_id, {})
        elif method == "notifications/initialized":
            return None
        else:
            return self.error_response(msg_id, -32601, f"Method not found: {method}")
    
    async def handle_initialize(self, msg_id: Any, params: Dict[str, Any], session_id: Optional[str]) -> Dict[str, Any]:
        if not session_id:
            session_id = str(uuid.uuid4())
        
        self.sessions[session_id] = {
            "initialized": True,
            "client_info": params.get("clientInfo", {})
        }
        
        self.message_queues[session_id] = asyncio.Queue()
        
        return self.success_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version
            },
            "capabilities": {
                "tools": {}
            }
        }), session_id
    
    async def handle_tools_list(self, msg_id: Any) -> Dict[str, Any]:
        tools_list = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            }
            for tool in self.tools
        ]
        
        return self.success_response(msg_id, {
            "tools": tools_list
        })
    
    async def handle_tools_call(self, msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        tool_func = None
        if tool_name == "read_file":
            tool_func = self.read_file
        elif tool_name == "write_file":
            tool_func = self.write_file
        elif tool_name == "list_directory":
            tool_func = self.list_directory
        elif tool_name == "get_file_info":
            tool_func = self.get_file_info
        
        if not tool_func:
            return self.error_response(msg_id, -32602, f"Unknown tool: {tool_name}")
        
        try:
            result = await tool_func(arguments)
            return self.success_response(msg_id, {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            })
        except Exception as e:
            return self.error_response(msg_id, -32603, f"Tool execution error: {str(e)}")
    
    async def read_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("file_path")
        if not path:
            raise ValueError("Missing 'file_path' argument")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "path": path,
                "content": content,
                "size": len(content)
            }
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")
    
    async def write_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path")
        content = args.get("content")
        
        if not path or content is None:
            raise ValueError("Missing 'path' or 'content' argument")
        
        if ".." in path or path.startswith("/"):
            raise ValueError("Invalid path")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "path": path,
            "bytes_written": len(content)
        }
    
    async def list_directory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path", ".")
        
        if ".." in path:
            raise ValueError("Invalid path")
        
        entries = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            is_dir = os.path.isdir(full_path)
            entries.append({
                "name": entry,
                "type": "directory" if is_dir else "file",
                "path": full_path
            })
        
        return {
            "success": True,
            "path": path,
            "entries": entries,
            "count": len(entries)
        }
    
    async def get_file_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path")
        if not path:
            raise ValueError("Missing 'path' argument")
        
        if ".." in path or path.startswith("/"):
            raise ValueError("Invalid path")
        
        stat_info = os.stat(path)
        
        return {
            "success": True,
            "path": path,
            "size": stat_info.st_size,
            "modified": stat_info.st_mtime,
            "created": stat_info.st_ctime,
            "is_file": os.path.isfile(path),
            "is_directory": os.path.isdir(path)
        }
    
    def success_response(self, msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result
        }
    
    def error_response(self, msg_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": message
            }
        }
    
    def cleanup_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.message_queues:
            del self.message_queues[session_id]

# Create instances
mcp_server = MCPServer(SERVER_NAME, "1.0.0")
broadcaster = MCPBroadcaster(SERVER_NAME, SERVER_PORT)

# Register tools
mcp_server.add_tool(Tool(
    name="read_file",
    description="Read the contents of a file",
    inputSchema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read"
            }
        },
        "required": ["file_path"]
    }
))

mcp_server.add_tool(Tool(
    name="write_file",
    description="Write content to a file",
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        },
        "required": ["path", "content"]
    }
))

mcp_server.add_tool(Tool(
    name="list_directory",
    description="List all files and directories in a given path",
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory to list",
                "default": "."
            }
        }
    }
))

mcp_server.add_tool(Tool(
    name="get_file_info",
    description="Get information about a file (size, modified time, etc.)",
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file"
            }
        },
        "required": ["path"]
    }
))

@app.on_event("startup")
async def startup_event():
    """Start broadcaster on server startup"""
    if ENABLE_BROADCAST:
        asyncio.create_task(broadcaster.start_broadcasting())

@app.on_event("shutdown")
async def shutdown_event():
    """Stop broadcaster on shutdown"""
    broadcaster.stop_broadcasting()

@app.get("/")
async def root():
    return {
        "name": mcp_server.name,
        "version": mcp_server.version,
        "protocol": "MCP Streamable HTTP",
        "endpoint": "/mcp",
        "broadcasting": ENABLE_BROADCAST,
        "broadcast_interval": BROADCAST_INTERVAL if ENABLE_BROADCAST else None
    }

@app.post("/mcp")
@app.get("/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id")
):
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    accept_header = request.headers.get("accept", "")
    wants_sse = "text/event-stream" in accept_header
    wants_json = "application/json" in accept_header
    
    if request.method == "GET":
        if not wants_sse:
            raise HTTPException(status_code=405, detail="GET requires text/event-stream")
        
        if not mcp_session_id or mcp_session_id not in mcp_server.sessions:
            raise HTTPException(status_code=400, detail="Invalid session")
        
        async def sse_generator() -> AsyncGenerator[str, None]:
            queue = mcp_server.message_queues.get(mcp_session_id)
            if not queue:
                return
            
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(message)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                mcp_server.cleanup_session(mcp_session_id)
        
        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    try:
        body = await request.json()
    except json.JSONDecodeError:
        error_response = mcp_server.error_response(None, -32700, "Parse error")
        return JSONResponse(content=error_response, status_code=400)
    
    is_initialize = body.get("method") == "initialize"
    
    if not is_initialize:
        if not mcp_session_id or mcp_session_id not in mcp_server.sessions:
            raise HTTPException(status_code=400, detail="Invalid session")
    
    result = await mcp_server.handle_message(body, mcp_session_id)
    
    if is_initialize and isinstance(result, tuple):
        response, new_session_id = result
        
        if wants_sse and not wants_json:
            async def init_sse_generator() -> AsyncGenerator[str, None]:
                yield f"data: {json.dumps(response)}\n\n"
                
                queue = mcp_server.message_queues.get(new_session_id)
                if queue:
                    try:
                        while True:
                            if await request.is_disconnected():
                                break
                            
                            try:
                                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                                yield f"data: {json.dumps(message)}\n\n"
                            except asyncio.TimeoutError:
                                yield ": keepalive\n\n"
                    finally:
                        mcp_server.cleanup_session(new_session_id)
            
            return StreamingResponse(
                init_sse_generator(),
                media_type="text/event-stream",
                headers={
                    "Mcp-Session-Id": new_session_id,
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            return JSONResponse(
                content=response,
                headers={"Mcp-Session-Id": new_session_id}
            )
    
    if result is None:
        return JSONResponse(content={"status": "ok"})
    
    if mcp_session_id and mcp_session_id in mcp_server.message_queues:
        await mcp_server.message_queues[mcp_session_id].put(result)
    
    return JSONResponse(content=result)

@app.delete("/mcp")
async def mcp_delete(
    authorization: Optional[str] = Header(None),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id")
):
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if mcp_session_id:
        mcp_server.cleanup_session(mcp_session_id)
    
    return JSONResponse(content={"status": "ok"})

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Starting MCP File System Server with Broadcasting")
    print("=" * 60)
    print(f"Port: {SERVER_PORT}")
    print(f"Endpoint: http://localhost:{SERVER_PORT}/mcp")
    print(f"Broadcasting: {'ENABLED' if ENABLE_BROADCAST else 'DISABLED'}")
    if ENABLE_BROADCAST:
        print(f"Broadcast Interval: {BROADCAST_INTERVAL}s")
        print(f"Multicast: {SSDP_ADDR}:{MCP_DISCOVERY_PORT}")
    print(f"Auth: {'ENABLED' if REQUIRE_AUTH else 'DISABLED'}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)