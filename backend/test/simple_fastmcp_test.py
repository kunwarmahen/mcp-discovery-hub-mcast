#!/usr/bin/env python3
"""
Test FastMCP streamable-http transport
Uses simplified format without JSON-RPC wrappers
"""
import asyncio
import httpx
import json

async def test_fastmcp_streamable_http():
    """Test FastMCP server using streamable-http format"""
    host = "192.168.1.44"
    port = 3001
    endpoint = "/mcp"
    
    print("=" * 60)
    print("Testing FastMCP Streamable-HTTP")
    print("=" * 60)
    print(f"URL: http://{host}:{port}{endpoint}")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Initialize (WITH jsonrpc and id for 'http' mode)
            print("1. Initialize")
            print("-" * 60)
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {
                        "name": "Discovery Test",
                        "version": "1.0.0"
                    },
                    "capabilities": {}
                }
            }
            
            print(f"Request: {json.dumps(init_request, indent=2)}")
            
            response = await client.post(
                f"http://{host}:{port}{endpoint}",
                json=init_request,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"  # Both headers for 'http' mode
                }
            )
            
            print(f"\nStatus: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            
            # Capture session ID
            session_id = response.headers.get("Mcp-Session-Id")
            if session_id:
                print(f"Session ID: {session_id}")
            
            if response.status_code != 200:
                print(f"❌ Failed: {response.text}")
                return False
            
            # Check response format
            content_type = response.headers.get('content-type', '')
            
            if 'text/event-stream' in content_type:
                # Parse SSE response
                print("Response format: SSE (parsing...)")
                text = response.text.strip()
                lines = text.split("\n")
                json_str = None
                for line in lines:
                    if line.startswith("data: "):
                        json_str = line[6:]
                        break
                
                if not json_str:
                    print(f"❌ No 'data:' line in SSE response")
                    return False
                
                init_data = json.loads(json_str)
            else:
                # Plain JSON response
                print("Response format: JSON")
                init_data = response.json()
            
            # Handle JSON-RPC response format
            if "result" in init_data:
                init_result = init_data["result"]
            else:
                init_result = init_data
            
            print(f"\nResponse keys: {list(init_data.keys())}")
            print(f"Server: {init_result.get('serverInfo', {}).get('name')}")
            print(f"Version: {init_result.get('serverInfo', {}).get('version')}")
            print(f"Protocol: {init_result.get('protocolVersion')}")
            print("✓ Initialize successful!\n")

            # After initialize response
            if session_id:
                # Send initialized notification
                initialized_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }
                
                await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=initialized_notification,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Mcp-Session-Id": session_id
                    }
                )                

            
            # Step 2: Tools/list (simplified format after initialization)
            print("2. Tools/list")
            print("-" * 60)
            # After initialize, use simplified format (no jsonrpc, no id)
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,  # Must be unique per request
                "method": "tools/list",
                "params": {}
            }
            
            print(f"Request: {json.dumps(tools_request, indent=2)}")
            
            # Send with session ID
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            if session_id:
                headers["Mcp-Session-Id"] = session_id
                print(f"Using session ID: {session_id}")
            
            tools_response = await client.post(
                f"http://{host}:{port}{endpoint}",
                json=tools_request,
                headers=headers
            )
            
            print(f"\nStatus: {tools_response.status_code}")
            
            if tools_response.status_code != 200:
                print(f"❌ Failed: {tools_response.text}")
                return False
            
            # Check response format
            tools_content_type = tools_response.headers.get('content-type', '')
            
            if 'text/event-stream' in tools_content_type:
                # Parse SSE response
                print("Response format: SSE (parsing...)")
                text = tools_response.text.strip()
                lines = text.split("\n")
                json_str = None
                for line in lines:
                    if line.startswith("data: "):
                        json_str = line[6:]
                        break
                
                if not json_str:
                    print(f"❌ No 'data:' line in SSE response")
                    return False
                
                tools_data = json.loads(json_str)
            else:
                # Plain JSON response
                print("Response format: JSON")
                tools_data = tools_response.json()
            
            # Handle JSON-RPC response
            if "result" in tools_data:
                tools_result = tools_data["result"]
            else:
                tools_result = tools_data
            
            if "error" in tools_data:
                print(f"❌ Error: {tools_data['error']}")
                return False
            
            tools = tools_result.get("tools", [])
            print(f"\nFound {len(tools)} tools:")
            for i, tool in enumerate(tools, 1):
                print(f"  {i}. {tool['name']}")
                print(f"     Description: {tool.get('description', 'N/A')}")
            print("✓ Tools/list successful!\n")
            
            # Step 3: Call a tool (simplified format, no jsonrpc, no id)
            if tools:
                print("3. Call tool: list_containers")
                print("-" * 60)
                tool_request = {
                    "jsonrpc": "2.0",
                    "id": 3,                    
                    "method": "tools/call",
                    "params": {
                        "name": "list_containers",
                        "arguments": {
                            "all": True
                        }
                    }
                }
                
                print(f"Request: {json.dumps(tool_request, indent=2)}")
                
                # Send with session ID
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
                if session_id:
                    headers["Mcp-Session-Id"] = session_id
                    print(f"Using session ID: {session_id}")
                
                tool_response = await client.post(
                    f"http://{host}:{port}{endpoint}",
                    json=tool_request,
                    headers=headers
                )
                
                print(f"\nStatus: {tool_response.status_code}")
                
                if tool_response.status_code != 200:
                    print(f"❌ Failed: {tool_response.text}")
                    return False
                
                # Check response format
                tool_content_type = tool_response.headers.get('content-type', '')
                
                if 'text/event-stream' in tool_content_type:
                    # Parse SSE response
                    print("Response format: SSE (parsing...)")
                    text = tool_response.text.strip()
                    lines = text.split("\n")
                    json_str = None
                    for line in lines:
                        if line.startswith("data: "):
                            json_str = line[6:]
                            break
                    
                    if not json_str:
                        print(f"❌ No 'data:' line in SSE response")
                        return False
                    
                    tool_data = json.loads(json_str)
                else:
                    # Plain JSON response
                    print("Response format: JSON")
                    tool_data = tool_response.json()
                
                # Handle JSON-RPC response
                if "result" in tool_data:
                    tool_result = tool_data["result"]
                elif "error" in tool_data:
                    print(f"❌ Error: {tool_data.get('error')}")
                    return False
                else:
                    tool_result = tool_data
                
                print(f"\nResponse keys: {list(tool_data.keys())}")
                
                if "content" in tool_result:
                    for item in tool_result["content"]:
                        if item.get("type") == "text":
                            text = item.get("text", "")
                            # Show first 500 chars
                            print(f"\nResult preview:\n{text[:500]}")
                            if len(text) > 500:
                                print("...")
                
                if "structuredContent" in tool_result:
                    print(f"\nStructured content available")
                
                print("✓ Tool execution successful!\n")
            
            print("=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_comparison():
    """Show the difference between JSON-RPC and streamable-http"""
    print("\n" + "=" * 60)
    print("Protocol Comparison")
    print("=" * 60)
    
    print("\n📝 Traditional MCP (JSON-RPC):")
    print("-" * 60)
    jsonrpc_format = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}
    }
    print(json.dumps(jsonrpc_format, indent=2))
    
    print("\n📝 FastMCP Streamable-HTTP:")
    print("-" * 60)
    streamable_format = {
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}
    }
    print(json.dumps(streamable_format, indent=2))
    
    print("\n✨ Key differences:")
    print("  - No 'jsonrpc' field")
    print("  - No 'id' field")
    print("  - Simpler, cleaner format")
    print("  - Direct responses (no wrapping)")

async def main():
    await test_comparison()
    print("\n")
    success = await test_fastmcp_streamable_http()
    
    if not success:
        print("\n💡 Troubleshooting:")
        print("  1. Make sure your FastMCP server is running:")
        print("     MCP_TRANSPORT=streamable-http MCP_PORT=3001 uv run main.py")
        print("  2. Check the server is accessible:")
        print("     curl http://192.168.1.44:3001/mcp")
        print("  3. Verify the transport is 'streamable-http' not 'http'")

if __name__ == "__main__":
    asyncio.run(main())