const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const TOKEN_KEY = 'codegraph_token';

// FastAPI returns `detail` as a string (HTTPException) or a list (422 validation errors).
const formatDetail = (detail) => {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  return JSON.stringify(detail);
};

// Single entry point: attaches the token, picks the body encoding, and throws on any failure.
async function request(path, { method = 'GET', json, form } = {}) {
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
  try {
    res = await fetch(`${BASE_URL}${path}`, { method, headers, body });
  } catch {
    throw new Error(`Cannot reach the backend at ${BASE_URL}. Is it running?`);
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

// Only send the BYOK Gemini key when the user actually entered one.
const withKey = (payload, geminiKey) =>
  geminiKey && geminiKey.trim() ? { ...payload, gemini_api_key: geminiKey.trim() } : payload;

export const api = {
  // Authentication
  loginDemo: async () => storeToken(await request('/api/auth/demo', { method: 'POST' })),

  register: async (email, password) =>
    storeToken(await request('/api/auth/register', { method: 'POST', json: { email, password } })),

  login: async (email, password) =>
    storeToken(await request('/api/auth/login', { method: 'POST', json: { email, password } })),

  // Workspace Operations
  listWorkspaces: () => request('/api/workspace/list'),

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

  queryRag: (workspaceId, queryText, geminiKey) =>
    request('/api/rag/query', {
      method: 'POST',
      json: withKey({ workspace_id: workspaceId, query: queryText }, geminiKey),
    }),

  generateRefactor: (workspaceId, promptText, geminiKey) =>
    request('/api/rag/refactor', {
      method: 'POST',
      json: withKey({ workspace_id: workspaceId, prompt: promptText }, geminiKey),
    }),
};
