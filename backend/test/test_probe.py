"""
MCP Discovery Test - Comprehensive Server Detection
Supports Traditional MCP, FastMCP HTTP, and FastMCP Streamable-HTTP
"""

import asyncio
import json
import httpx
from typing import Optional, Dict, List, Tuple


# ============================================================================
# FASTMCP HTTP STYLE (JSON-RPC with session management)
# ============================================================================

async def probe_fastmcp_http_style(host: str, port: int) -> Optional[Tuple[Dict, str, str, List[Dict]]]:
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
                        print(f"✓ FastMCP HTTP detected at {host}:{port}{endpoint}")
                        return server_info, endpoint, session_id, tools
                        
        except Exception as e:
            print(f"  FastMCP HTTP probe failed for {host}:{port}{endpoint}: {e}")
            continue
    
    return None


# ============================================================================
# FASTMCP STREAMABLE-HTTP STYLE (Simplified format, no jsonrpc/id)
# ============================================================================

async def probe_fastmcp_streamable_http(host: str, port: int) -> Optional[Tuple[Dict, str, List[Dict]]]:
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
                    print(f"✓ FastMCP streamable-http detected at {host}:{port}{endpoint}")
                    return server_info, endpoint, tools
                        
        except Exception as e:
            print(f"  FastMCP streamable-http probe failed for {host}:{port}{endpoint}: {e}")
            continue
    
    return None


# ============================================================================
# TRADITIONAL MCP (JSON-RPC with session management)
# ============================================================================

async def probe_traditional_mcp(host: str, port: int, endpoint: str = None) -> Optional[Tuple[Dict, str, str, List[Dict]]]:
    """
    Probe Traditional MCP server
    Returns: (server_info, endpoint, session_id, tools)
    """
    endpoints = [endpoint] if endpoint else ["/mcp", "/", "/v1/mcp"]
    
    for ep in endpoints:
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
                    f"http://{host}:{port}{ep}",
                    json=init_request,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code != 200:
                    continue
                
                session_id = response.headers.get("Mcp-Session-Id")
                if not session_id:
                    continue
                
                init_data = response.json()
                
                if "result" not in init_data:
                    continue
                
                server_info = init_data["result"]
                
                # Get tools
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                
                tools_response = await client.post(
                    f"http://{host}:{port}{ep}",
                    json=tools_request,
                    headers={
                        "Accept": "application/json",
                        "Mcp-Session-Id": session_id
                    }
                )
                
                if tools_response.status_code == 200:
                    tools_data = tools_response.json()
                    
                    if "error" in tools_data:
                        continue
                    
                    if "result" in tools_data:
                        tools = tools_data["result"].get("tools", [])
                        print(f"✓ Traditional MCP detected at {host}:{port}{ep}")
                        return server_info, ep, session_id, tools
                        
        except Exception as e:
            print(f"  Traditional MCP probe failed for {host}:{port}{ep}: {e}")
            continue
    
    return None


# ============================================================================
# UNIFIED PROBE FUNCTION
# ============================================================================

async def probe_mcp_server(host: str, port: int) -> Optional[Dict]:
    """
    Unified probing function that tries all three server types
    Returns a standardized result dictionary
    """
    print(f"\nProbing {host}:{port}")
    print("-" * 60)
    
    # Try FastMCP HTTP style first
    print("  Trying FastMCP HTTP...")
    result = await probe_fastmcp_http_style(host, port)
    if result:
        server_info, endpoint, session_id, tools = result
        return {
            "server_type": "fastmcp_http",
            "host": host,
            "port": port,
            "endpoint": endpoint,
            "server_info": server_info,
            "session_id": session_id,
            "tools": tools
        }
    
    # Try FastMCP Streamable-HTTP
    print("  Trying FastMCP Streamable-HTTP...")
    result = await probe_fastmcp_streamable_http(host, port)
    if result:
        server_info, endpoint, tools = result
        return {
            "server_type": "fastmcp_streamable",
            "host": host,
            "port": port,
            "endpoint": endpoint,
            "server_info": server_info,
            "session_id": None,
            "tools": tools
        }
    
    # Try Traditional MCP
    print("  Trying Traditional MCP...")
    result = await probe_traditional_mcp(host, port)
    if result:
        server_info, endpoint, session_id, tools = result
        return {
            "server_type": "traditional",
            "host": host,
            "port": port,
            "endpoint": endpoint,
            "server_info": server_info,
            "session_id": session_id,
            "tools": tools
        }
    
    return None


# ============================================================================
# TEST FUNCTION
# ============================================================================

async def test_probe():
    """Test probing multiple servers"""
    servers_to_test = [
        ("192.168.1.44", 3000),  # Could be any type
        ("192.168.1.44", 3001),  # Could be any type
    ]
    
    print("=" * 60)
    print("MCP Server Detection Test")
    print("=" * 60)
    
    for host, port in servers_to_test:
        result = await probe_mcp_server(host, port)
        
        if result:
            print(f"\n  Server Type: {result['server_type'].replace('_', ' ').title()}")
            print(f"  Endpoint: {result['endpoint']}")
            server_name = result['server_info'].get('serverInfo', {}).get('name', 'Unknown')
            print(f"  Name: {server_name}")
            print(f"  Tools: {len(result['tools'])}")
            
            for tool in result['tools'][:3]:  # Show first 3 tools
                desc = tool.get('description', 'N/A')[:40]
                print(f"    - {tool['name']}: {desc}")
            
            if len(result['tools']) > 3:
                print(f"    ... and {len(result['tools']) - 3} more tools")
        else:
            print(f"\n  Status: Could not detect MCP server")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_probe())