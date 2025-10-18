import React, { useState, useEffect, useRef } from "react";
import {
  Search,
  Server,
  CheckCircle,
  Circle,
  RefreshCw,
  Settings,
  Wrench,
  Send,
  MessageSquare,
  Loader,
  Globe,
  Zap,
  Clock,
  ChevronDown,
  ChevronUp,
  X,
} from "lucide-react";
import "./App.css";

const MCPDiscoveryManager = () => {
  const [servers, setServers] = useState([]);
  const [selectedTools, setSelectedTools] = useState({});
  const [scanning, setScanning] = useState(false);
  const [activeTab, setActiveTab] = useState("discover");
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [searchQuery, setSearchQuery] = useState("");
  const [collapsedServers, setCollapsedServers] = useState({});
  const [llmConfig, setLlmConfig] = useState({
    provider: "ollama",
    endpoint: "http://localhost:11434",
    model: "qwen2.5:14b",
  });

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Update current time every minute for timestamp refresh
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  // Format timestamp helper
  const formatTimestamp = (isoString) => {
    if (!isoString) return "Unknown";

    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) {
      return "Just now";
    } else if (diffMins < 60) {
      return `${diffMins} min${diffMins !== 1 ? "s" : ""} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
    } else if (diffDays < 7) {
      return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  const formatAbsoluteTime = (isoString) => {
    if (!isoString) return "Unknown";

    const date = new Date(isoString);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = () => {
    const ws = new WebSocket("ws://localhost:8000/ws");

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("WebSocket message received:", data);

      if (data.type === "server_discovered") {
        setServers((prev) => {
          const existing = prev.find((s) => s.id === data.server.id);
          if (existing) return prev;

          const serverWithTimestamp = {
            ...data.server,
            discovered_at: new Date().toISOString(),
          };

          return [...prev, serverWithTimestamp];
        });
      } else if (data.type === "initial_servers") {
        const serversWithTimestamps = data.servers.map((server) => ({
          ...server,
          discovered_at: server.discovered_at || new Date().toISOString(),
        }));
        setServers(serversWithTimestamps);
      } else if (data.type === "scan_started") {
        setServers([]);
      } else if (data.type === "chat_chunk") {
        if (data.content) {
          // Only process if there's actual content
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === "assistant" && lastMsg.streaming) {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...lastMsg,
                content: lastMsg.content + data.content,
                streaming: !data.done,
              };
              return updated;
            }
            return [
              ...prev,
              {
                role: "assistant",
                content: data.content,
                streaming: !data.done,
              },
            ];
          });
        } else if (data.done) {
          // If done with no content, just mark the last message as complete
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === "assistant" && lastMsg.streaming) {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...lastMsg,
                streaming: false,
              };
              return updated;
            }
            return prev;
          });
        }

        if (data.done) setIsSending(false);
      } else if (data.type === "error") {
        setMessages((prev) => [
          ...prev,
          { role: "error", content: `Error: ${data.error}` },
        ]);
        setIsSending(false);
      }
    };

    ws.onerror = (error) => console.error("WebSocket error:", error);
    ws.onclose = () => {
      console.log("WebSocket disconnected, reconnecting...");
      setTimeout(connectWebSocket, 3000);
    };

    wsRef.current = ws;
  };

  const scanNetwork = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setScanning(true);
      setServers([]);
      wsRef.current.send(
        JSON.stringify({ type: "scan", ports: [3000, 3001, 3002, 8080, 9000] })
      );
      setTimeout(() => setScanning(false), 30000);
    } else {
      alert("WebSocket connection not established. Please refresh the page.");
    }
  };

  const toggleTool = (serverId, toolName) => {
    setSelectedTools((prev) => {
      const key = `${serverId}:${toolName}`;
      const newSelected = { ...prev };
      if (newSelected[key]) {
        delete newSelected[key];
      } else {
        newSelected[key] = { serverId, toolName };
      }
      return newSelected;
    });
  };

  const getSelectedCount = () => Object.keys(selectedTools).length;

  const getToolParameters = (inputSchema) => {
    if (!inputSchema || !inputSchema.properties) return [];
    return Object.keys(inputSchema.properties);
  };

  const toggleServerCollapse = (serverId) => {
    setCollapsedServers((prev) => ({
      ...prev,
      [serverId]: !prev[serverId],
    }));
  };

  const filterTools = (tools) => {
    if (!searchQuery.trim()) return tools;
    const query = searchQuery.toLowerCase();
    return tools.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        tool.description.toLowerCase().includes(query)
    );
  };

  const getFilteredServers = () => {
    if (!searchQuery.trim()) return servers;
    return servers.filter((server) => {
      const filteredTools = filterTools(server.tools);
      return (
        filteredTools.length > 0 ||
        server.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
    });
  };

  const exportConfig = () => {
    const config = {
      llm: llmConfig,
      selectedTools: Object.values(selectedTools).map((tool) => {
        const server = servers.find((s) => s.id === tool.serverId);
        const toolInfo = server.tools.find((t) => t.name === tool.toolName);
        return {
          server: server.name,
          host: server.host,
          port: server.port,
          endpoint: server.endpoint,
          protocol_version: server.protocol_version,
          tool: toolInfo,
        };
      }),
    };
    const blob = new Blob([JSON.stringify(config, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "mcp-config.json";
    a.click();
  };

  const sendMessage = () => {
    if (!inputMessage.trim() || isSending) return;

    const userMessage = { role: "user", content: inputMessage };
    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");
    setIsSending(true);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const selectedToolsList = Object.values(selectedTools).map((tool) => ({
        server_id: tool.serverId,
        tool_name: tool.toolName,
      }));

      wsRef.current.send(
        JSON.stringify({
          type: "chat",
          data: {
            provider: llmConfig.provider,
            endpoint: llmConfig.endpoint,
            model: llmConfig.model,
            messages: [...messages, userMessage],
            selected_tools: selectedToolsList,
          },
        })
      );
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="container mx-auto p-6">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-purple-600 p-3 rounded-lg">
              <Globe className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-4xl font-bold text-white">MCP Discovery Hub</h1>
          </div>
          <p className="text-purple-300">
            Discover and integrate MCP servers across your network using the
            Model Context Protocol
          </p>
        </div>

        <div className="flex gap-4 mb-6">
          <button
            onClick={() => setActiveTab("discover")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              activeTab === "discover"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-500/50"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <Search className="inline mr-2 w-5 h-5" />
            Discover Servers
          </button>
          <button
            onClick={() => setActiveTab("chat")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              activeTab === "chat"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-500/50"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <MessageSquare className="inline mr-2 w-5 h-5" />
            Chat Portal
            {getSelectedCount() > 0 && (
              <span className="ml-2 px-2 py-1 bg-purple-500 text-white text-xs rounded-full">
                {getSelectedCount()}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("config")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              activeTab === "config"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-500/50"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <Settings className="inline mr-2 w-5 h-5" />
            LLM Configuration
          </button>
        </div>

        {activeTab === "discover" && (
          <>
            <div className="bg-slate-800 rounded-lg p-6 mb-6 border border-slate-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white text-lg font-semibold">
                    Found {servers.length} MCP server
                    {servers.length !== 1 ? "s" : ""}
                  </p>
                  <p className="text-slate-400 text-sm">
                    {getSelectedCount()} tool
                    {getSelectedCount() !== 1 ? "s" : ""} selected
                  </p>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={scanNetwork}
                    disabled={scanning}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all"
                  >
                    <RefreshCw
                      className={`w-4 h-4 ${scanning ? "animate-spin" : ""}`}
                    />
                    {scanning ? "Scanning..." : "Scan Network"}
                  </button>
                  <button
                    onClick={exportConfig}
                    disabled={getSelectedCount() === 0}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    Export Config
                  </button>
                </div>
              </div>
              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search servers and tools..."
                  className="w-full bg-slate-700 text-white pl-10 pr-10 py-3 rounded-lg border border-slate-600 focus:outline-none focus:border-purple-500"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                )}
              </div>
            </div>

            {scanning && servers.length === 0 && (
              <div className="bg-slate-800 rounded-lg p-12 text-center border border-slate-700">
                <Loader className="w-12 h-12 text-purple-400 animate-spin mx-auto mb-4" />
                <p className="text-slate-300 text-lg animate-pulse">
                  Scanning network for MCP servers...
                </p>
                <p className="text-slate-400 text-sm mt-2">
                  This may take up to 30 seconds
                </p>
              </div>
            )}

            {!scanning && servers.length === 0 && (
              <div className="bg-slate-800 rounded-lg p-12 text-center border border-slate-700">
                <Server className="w-16 h-16 text-slate-600 mx-auto mb-4" />
                <p className="text-slate-300 text-lg mb-2">
                  No MCP servers discovered
                </p>
                <p className="text-slate-400 text-sm mb-1">
                  Servers with broadcasting enabled will appear automatically
                </p>
                <p className="text-slate-500 text-xs">
                  or click "Scan Network" to actively search for servers
                </p>
              </div>
            )}

            <div className="grid gap-6">
              {getFilteredServers().map((server, index) => {
                const isCollapsed = collapsedServers[server.id];
                const filteredTools = filterTools(server.tools);

                return (
                  <div
                    key={server.id}
                    className="bg-slate-800 rounded-lg border border-slate-700 hover:border-purple-500 transition-all"
                    style={{
                      animation: `fadeIn 1.5s ease-in ${index * 0.1}s both`,
                    }}
                  >
                    {/* Server Header - Always Visible */}
                    <div
                      className="p-6 cursor-pointer"
                      onClick={() => toggleServerCollapse(server.id)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3 flex-1">
                          <div className="bg-purple-600 p-3 rounded-lg">
                            <Server className="w-6 h-6 text-white" />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <h3 className="text-xl font-bold text-white">
                                {server.name}
                              </h3>
                              {isCollapsed ? (
                                <ChevronDown className="w-5 h-5 text-slate-400" />
                              ) : (
                                <ChevronUp className="w-5 h-5 text-slate-400" />
                              )}
                            </div>
                            <p className="text-slate-400 text-sm">
                              {server.host}:{server.port}
                              {server.endpoint || ""}
                            </p>
                            {server.protocol_version && (
                              <p className="text-slate-500 text-xs mt-1">
                                Protocol: {server.protocol_version}
                              </p>
                            )}
                            {server.discovered_at && (
                              <p className="text-slate-500 text-xs mt-1 flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Discovered{" "}
                                {formatTimestamp(server.discovered_at)}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap justify-end">
                          {server.discovery_method && (
                            <span
                              className={`px-3 py-1 text-xs rounded-full flex items-center gap-1 animate-fade-in ${
                                server.discovery_method === "broadcast"
                                  ? "bg-emerald-600 text-white"
                                  : "bg-blue-600 text-white"
                              }`}
                              title={`Discovered ${
                                server.discovered_at
                                  ? formatAbsoluteTime(server.discovered_at)
                                  : "recently"
                              } via ${server.discovery_method}`}
                            >
                              {server.discovery_method === "broadcast" ? (
                                <>
                                  <Globe className="w-3 h-3" />
                                  Auto-discovered
                                </>
                              ) : (
                                <>
                                  <Search className="w-3 h-3" />
                                  Scanned
                                </>
                              )}
                            </span>
                          )}
                          {server.session_id && (
                            <span className="px-3 py-1 bg-blue-600 text-white text-xs rounded-full flex items-center gap-1">
                              <Zap className="w-3 h-3" />
                              Connected
                            </span>
                          )}
                          <span className="px-3 py-1 bg-green-600 text-white text-sm rounded-full">
                            {server.status}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Collapsible Tools Section */}
                    {!isCollapsed && (
                      <div className="px-6 pb-6 space-y-2 border-t border-slate-700 pt-4">
                        <p className="text-slate-300 font-semibold mb-3 flex items-center gap-2">
                          <Wrench className="w-4 h-4" />
                          Available Tools ({filteredTools.length}
                          {searchQuery && ` of ${server.tools.length}`})
                        </p>
                        {filteredTools.length === 0 ? (
                          <p className="text-slate-500 text-sm py-4 text-center">
                            No tools match your search
                          </p>
                        ) : (
                          filteredTools.map((tool) => {
                            const isSelected =
                              selectedTools[`${server.id}:${tool.name}`];
                            const params = getToolParameters(tool.inputSchema);
                            const requiredParams =
                              tool.inputSchema?.required || [];

                            return (
                              <div
                                key={tool.name}
                                onClick={() => toggleTool(server.id, tool.name)}
                                className={`p-4 rounded-lg cursor-pointer transition-all ${
                                  isSelected
                                    ? "bg-purple-600 border-2 border-purple-400 shadow-lg"
                                    : "bg-slate-700 border-2 border-slate-600 hover:border-purple-500"
                                }`}
                              >
                                <div className="flex items-start gap-3">
                                  {isSelected ? (
                                    <CheckCircle className="w-5 h-5 text-white mt-0.5 flex-shrink-0" />
                                  ) : (
                                    <Circle className="w-5 h-5 text-slate-400 mt-0.5 flex-shrink-0" />
                                  )}
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                      <Wrench className="w-4 h-4 text-purple-300 flex-shrink-0" />
                                      <span className="font-mono text-white font-semibold truncate">
                                        {tool.name}
                                      </span>
                                    </div>
                                    <p className="text-slate-300 text-sm mb-2">
                                      {tool.description}
                                    </p>
                                    {params.length > 0 && (
                                      <div className="flex gap-2 flex-wrap">
                                        {params.map((param) => (
                                          <span
                                            key={param}
                                            className={`px-2 py-1 text-xs rounded ${
                                              isSelected
                                                ? "bg-purple-700 text-purple-100"
                                                : "bg-slate-800 text-slate-300"
                                            }`}
                                          >
                                            {param}
                                            {requiredParams.includes(param) && (
                                              <span className="text-red-400 ml-1">
                                                *
                                              </span>
                                            )}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {activeTab === "chat" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div
              className="lg:col-span-2 bg-slate-800 rounded-lg flex flex-col border border-slate-700"
              style={{ height: "70vh" }}
            >
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {messages.length === 0 ? (
                  <div className="h-full flex items-center justify-center">
                    <div className="text-center">
                      <MessageSquare className="w-16 h-16 text-slate-600 mx-auto mb-4" />
                      <p className="text-slate-400 text-lg">
                        Start a conversation with your MCP tools
                      </p>
                      <p className="text-slate-500 text-sm mt-2">
                        {getSelectedCount() > 0
                          ? `${getSelectedCount()} tool${
                              getSelectedCount() !== 1 ? "s" : ""
                            } available`
                          : "Select tools from the Discovery tab first"}
                      </p>
                    </div>
                  </div>
                ) : (
                  messages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex ${
                        msg.role === "user" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg p-4 ${
                          msg.role === "user"
                            ? "bg-purple-600 text-white"
                            : msg.role === "error"
                            ? "bg-red-600 text-white"
                            : "bg-slate-700 text-slate-200"
                        }`}
                      >
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                        {msg.streaming && msg.role === "assistant" && (
                          <Loader className="w-4 h-4 animate-spin mt-2" />
                        )}
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="p-4 border-t border-slate-700">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Type your message..."
                    disabled={isSending || getSelectedCount() === 0}
                    className="flex-1 bg-slate-700 text-white p-3 rounded-lg border border-slate-600 focus:outline-none focus:border-purple-500 disabled:opacity-50"
                  />
                  <button
                    onClick={sendMessage}
                    disabled={
                      isSending ||
                      !inputMessage.trim() ||
                      getSelectedCount() === 0
                    }
                    className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all"
                  >
                    {isSending ? (
                      <Loader className="w-5 h-5 animate-spin" />
                    ) : (
                      <Send className="w-5 h-5" />
                    )}
                  </button>
                </div>
                {getSelectedCount() === 0 && (
                  <p className="text-yellow-400 text-sm mt-2">
                    Please select at least one tool from the Discovery tab
                  </p>
                )}
              </div>
            </div>

            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-bold text-white mb-4">
                Active Tools
              </h3>
              {getSelectedCount() === 0 ? (
                <div className="text-center py-8">
                  <Wrench className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400">No tools selected</p>
                  <p className="text-slate-500 text-sm mt-1">
                    Go to Discovery tab to select tools
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {Object.values(selectedTools).map((tool) => {
                    const server = servers.find((s) => s.id === tool.serverId);
                    const toolInfo = server?.tools.find(
                      (t) => t.name === tool.toolName
                    );
                    return (
                      <div
                        key={`${tool.serverId}:${tool.toolName}`}
                        className="bg-slate-700 rounded-lg p-3 border border-slate-600 hover:border-purple-500 transition-all"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Wrench className="w-4 h-4 text-purple-400" />
                            <span className="text-white font-semibold text-sm">
                              {tool.toolName}
                            </span>
                          </div>
                          <button
                            onClick={() =>
                              toggleTool(tool.serverId, tool.toolName)
                            }
                            className="text-slate-400 hover:text-red-400 transition-colors"
                          >
                            ×
                          </button>
                        </div>
                        <p className="text-slate-400 text-xs mb-1">
                          {toolInfo?.description}
                        </p>
                        <p className="text-slate-500 text-xs">{server?.name}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-6 pt-6 border-t border-slate-700">
                <h4 className="text-white font-semibold mb-3">Current LLM</h4>
                <div className="bg-slate-700 rounded-lg p-3 space-y-2">
                  <div>
                    <span className="text-slate-400 text-xs">Provider:</span>
                    <p className="text-white font-mono text-sm">
                      {llmConfig.provider}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs">Model:</span>
                    <p className="text-white font-mono text-sm">
                      {llmConfig.model}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "config" && (
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h2 className="text-2xl font-bold text-white mb-6">
              LLM Provider Configuration
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-slate-300 font-semibold mb-2">
                  Provider
                </label>
                <select
                  value={llmConfig.provider}
                  onChange={(e) =>
                    setLlmConfig((prev) => ({
                      ...prev,
                      provider: e.target.value,
                    }))
                  }
                  className="w-full bg-slate-700 text-white p-3 rounded-lg border border-slate-600 focus:outline-none focus:border-purple-500"
                >
                  <option value="ollama">Ollama</option>
                  <option value="vllm">vLLM</option>
                  <option value="openai">OpenAI</option>
                  <option value="claude">Claude (Anthropic)</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-2">
                  Endpoint URL{" "}
                  {llmConfig.provider === "openai" ||
                  llmConfig.provider === "claude"
                    ? "(API Key)"
                    : ""}
                </label>
                <input
                  type="text"
                  value={llmConfig.endpoint}
                  onChange={(e) =>
                    setLlmConfig((prev) => ({
                      ...prev,
                      endpoint: e.target.value,
                    }))
                  }
                  className="w-full bg-slate-700 text-white p-3 rounded-lg border border-slate-600 focus:outline-none focus:border-purple-500"
                  placeholder={
                    llmConfig.provider === "openai"
                      ? "sk-..."
                      : llmConfig.provider === "claude"
                      ? "sk-ant-..."
                      : "http://localhost:11434"
                  }
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-2">
                  Model Name
                </label>
                <input
                  type="text"
                  value={llmConfig.model}
                  onChange={(e) =>
                    setLlmConfig((prev) => ({ ...prev, model: e.target.value }))
                  }
                  className="w-full bg-slate-700 text-white p-3 rounded-lg border border-slate-600 focus:outline-none focus:border-purple-500"
                  placeholder="llama2"
                />
                <p className="text-slate-400 text-sm mt-1">
                  Examples: llama2, gpt-4, claude-3-5-sonnet-20241022,
                  gemini-pro
                </p>
              </div>

              <div className="mt-6 p-4 bg-slate-700 rounded-lg border border-slate-600">
                <h3 className="text-white font-semibold mb-2">
                  Current Configuration
                </h3>
                <pre className="text-slate-300 text-sm overflow-x-auto">
                  {JSON.stringify(llmConfig, null, 2)}
                </pre>
              </div>

              <div className="mt-6 p-4 bg-blue-900 bg-opacity-30 border border-blue-700 rounded-lg">
                <h4 className="text-blue-300 font-semibold mb-2">
                  💡 Quick Setup Tips
                </h4>
                <ul className="text-blue-200 text-sm space-y-1 list-disc list-inside">
                  <li>
                    <strong>Ollama:</strong> Make sure Ollama is running with{" "}
                    <code className="bg-slate-800 px-1 rounded">
                      ollama serve
                    </code>
                  </li>
                  <li>
                    <strong>OpenAI/Claude:</strong> Enter your API key in the
                    Endpoint field
                  </li>
                  <li>
                    <strong>vLLM:</strong> Use the OpenAI-compatible endpoint
                    URL
                  </li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MCPDiscoveryManager;
