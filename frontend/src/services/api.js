const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')
  : '';

export const getApiUrl = (endpoint) => {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE_URL}${cleanEndpoint}`;
};
const TOKEN_KEY = 'codegraph_token';

// FastAPI returns `detail` as a string (HTTPException) or a list (422 validation errors).
const formatDetail = (detail) => {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  return JSON.stringify(detail);
};

// Single entry point: attaches the token, picks the body encoding, handles cold-start retries, and throws on any failure.
async function request(path, { method = 'GET', json, form, retries = 2 } = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  let body;
  if (form) {
    body = form; // browser sets the multipart boundary itself
  } else if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  let res;
  let lastNetworkError = false;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      res = await fetch(getApiUrl(path), { method, headers, body });
      // If Render is waking up (502 or 503 from edge proxy during spin-up), retry after delay
      if ((res.status === 502 || res.status === 503) && attempt < retries) {
        await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
        continue;
      }
      lastNetworkError = false;
      break;
    } catch {
      lastNetworkError = true;
      if (attempt < retries) {
        // Wait and retry in case Render free tier is waking up
        await new Promise((r) => setTimeout(r, 2500 * (attempt + 1)));
      }
    }
  }

  if (lastNetworkError || !res) {
    throw new Error(`Cannot reach backend at ${API_BASE_URL || 'local server'}. If the server was sleeping (Render free tier), it takes ~35s to spin up. Please retry in a moment.`);
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(formatDetail(data?.detail) || `Request failed (${res.status})`);
  }
  return data;
}

const storeToken = (data) => {
  if (data?.access_token) localStorage.setItem(TOKEN_KEY, data.access_token);
  return data;
};

// Provider-aware key attacher: ensures keys are tagged to their matching provider
const withKey = (payload, key, provider) => {
  const targetProvider = (provider || payload?.provider || 'gemini').toLowerCase();
  if (key && typeof key === 'string' && key.trim() && !key.includes('...') && key !== 'CONFIGURED') {
    const trimmed = key.trim();
    // Guardrail: Never pass a Google Gemini key (starts with AIzaSy) to OpenAI/Anthropic/DeepSeek/Groq
    if (targetProvider !== 'gemini' && trimmed.startsWith('AIzaSy')) {
      return payload;
    }
    if (targetProvider === 'gemini') {
      return { ...payload, gemini_api_key: trimmed, api_key: trimmed };
    }
    return { ...payload, api_key: trimmed };
  }
  return payload;
};

export const getKeyStatus = async () => {
  try {
    const data = await request('/api/keys/status');
    return data?.status || data || {};
  } catch (err) {
    console.error("Key status check failed:", err);
    return { gemini: true, openai: false, anthropic: false, deepseek: false, groq: false };
  }
};

export const getDiscoveredModels = async () => {
  try {
    const data = await request('/api/keys/models', { method: 'GET' });
    if (Array.isArray(data)) return data;
    if (data?.models && Array.isArray(data.models)) return data.models;
    return [];
  } catch (err) {
    console.warn("Dynamic model discovery notice:", err.message || err);
    return [];
  }
};

export const api = {
  getApiUrl,
  checkHealth: () => request('/health'),
  // Multi-Provider Key Vault Operations
  saveApiKey: (provider, key) =>
    request('/api/keys/save', { method: 'POST', json: { provider, api_key: key } }),

  getKeysStatus: () => request('/api/keys/status'),
  getKeyStatus,
  getDiscoveredModels,
  getAvailableModels: () => request('/api/keys/models'),

  deleteApiKey: (provider) =>
    request(`/api/keys/${provider}`, { method: 'DELETE' }),

  testApiKey: (provider, key) =>
    request('/api/keys/test', { method: 'POST', json: { provider, api_key: key } }),

  // Legacy Gemini Key Compatibility
  saveGeminiKey: (geminiApiKey) =>
    request('/api/keys/save', { method: 'POST', json: { provider: 'gemini', api_key: geminiApiKey } }),

  getGeminiKey: () => request('/api/auth/gemini-key'),

  deleteGeminiKey: () => request('/api/keys/gemini', { method: 'DELETE' }),

  // Authentication & Session
  loginDemo: async () => storeToken(await request('/api/auth/demo', { method: 'POST' })),

  register: async (email, password) =>
    storeToken(await request('/api/auth/register', { method: 'POST', json: { email, password } })),

  login: async (email, password) =>
    storeToken(await request('/api/auth/login', { method: 'POST', json: { email, password } })),

  // Workspace Operations
  listWorkspaces: () => request('/api/workspace/list'),
  getWorkspace: (workspaceId) => request(`/api/workspace/${workspaceId}`),
  listWorkspaceSymbols: (workspaceId) => request(`/api/workspace/${workspaceId}/symbols`),
  deleteWorkspace: (workspaceId) => request(`/api/workspace/${workspaceId}`, { method: 'DELETE' }),

  // payload: { repo_url, type, branch } for git, or { type: 'zip', file: File } for an upload
  ingestWorkspace: (payload) => {
    if (payload.type === 'zip') {
      if (!(payload.file instanceof File)) {
        return Promise.reject(new Error('Select a .zip file to upload.'));
      }
      const form = new FormData();
      form.append('type', 'zip');
      form.append('file', payload.file);
      return request('/api/workspace/ingest', { method: 'POST', form });
    }
    return request('/api/workspace/ingest', { method: 'POST', json: payload });
  },

  // RAG & Graph Operations
  getSymbolImpact: (workspaceId, symbolKey) =>
    request('/api/rag/impact', { method: 'POST', json: { workspace_id: workspaceId, symbol: symbolKey } }),

  getWorkspaceArchitectureGraph: (workspaceId) =>
    request('/api/rag/architecture-graph', { method: 'POST', json: { workspace_id: workspaceId } }),

  queryRag: (workspaceId, queryText, key, history, modelMetadata = {}) => {
    const prov = (modelMetadata?.provider || 'gemini').toLowerCase();
    const payload = {
      workspace_id: workspaceId,
      query: queryText,
      history: history || [],
      model_id: modelMetadata?.model_id,
      provider: prov,
      thinking_level: modelMetadata?.thinking_level,
    };
    return request('/api/rag/query', {
      method: 'POST',
      json: withKey(payload, key, prov),
    });
  },

  searchRag: (payload) =>
    request('/api/rag/search', {
      method: 'POST',
      json: payload,
    }),

  generateRefactor: (workspaceId, promptText, geminiKey, previousDiffs) =>
    request('/api/rag/refactor', {
      method: 'POST',
      json: withKey({
        workspace_id: workspaceId,
        prompt: promptText,
        previous_diffs: previousDiffs || []
      }, geminiKey),
    }),
};
