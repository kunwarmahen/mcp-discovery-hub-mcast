import axios from "axios";

const API_BASE_URL = "http://localhost:8000";

export const api = {
  scanNetwork: async (ports = [3000, 3001, 3002, 8080, 9000]) => {
    const response = await axios.post(`${API_BASE_URL}/scan`, { ports });
    return response.data;
  },

  getServers: async () => {
    const response = await axios.get(`${API_BASE_URL}/servers`);
    return response.data;
  },

  executeTool: async (serverId, toolName, toolArguments) => {
    const response = await axios.post(`${API_BASE_URL}/execute-tool`, {
      server_id: serverId,
      tool_name: toolName,
      arguments: toolArguments,
    });
    return response.data;
  },

  chat: async (provider, endpoint, model, messages, selectedTools) => {
    const response = await axios.post(`${API_BASE_URL}/chat`, {
      provider,
      endpoint,
      model,
      messages,
      selected_tools: selectedTools,
    });
    return response.data;
  },
};
