const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const getHeaders = () => {
  const token = localStorage.getItem('codegraph_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
};

export const api = {
  // Authentication
  loginDemo: async () => {
    const res = await fetch(`${BASE_URL}/api/auth/demo`, { method: 'POST', headers: getHeaders() });
    if (!res.ok) throw new Error('Demo login failed');
    const data = await res.json();
    if (data.access_token) localStorage.setItem('codegraph_token', data.access_token);
    return data;
  },

  register: async (email, password) => {
    const res = await fetch(`${BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email, password })
    });
    return res.json();
  },

  login: async (email, password) => {
    const res = await fetch(`${BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (data.access_token) localStorage.setItem('codegraph_token', data.access_token);
    return data;
  },

  // Workspace Operations
  listWorkspaces: async () => {
    const res = await fetch(`${BASE_URL}/api/workspace/list`, { headers: getHeaders() });
    return res.json();
  },

  ingestWorkspace: async (payload) => {
    // payload: { repo_url, type, branch }
    const res = await fetch(`${BASE_URL}/api/workspace/ingest`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
    return res.json();
  },

  // RAG & Graph Operations
  getSymbolImpact: async (workspaceId, symbolKey) => {
    const res = await fetch(`${BASE_URL}/api/rag/impact`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ workspace_id: workspaceId, symbol: symbolKey })
    });
    return res.json();
  },

  queryRag: async (workspaceId, queryText) => {
    const res = await fetch(`${BASE_URL}/api/rag/query`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ workspace_id: workspaceId, query: queryText })
    });
    return res.json();
  },

  generateRefactor: async (workspaceId, promptText) => {
    const res = await fetch(`${BASE_URL}/api/rag/refactor`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ workspace_id: workspaceId, prompt: promptText })
    });
    return res.json();
  }
};
