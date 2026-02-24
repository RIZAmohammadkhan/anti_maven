const API_BASE = '/api';

function getToken() {
  return localStorage.getItem('maven_token');
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body.detail || body.message || `Request failed (${res.status})`;
    throw new Error(msg);
  }

  return res.json();
}

// Auth
export async function signup(name, email, password) {
  return request('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ name, email, password }),
  });
}

export async function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe() {
  return request('/auth/me');
}

// History
export async function getHistory() {
  return request('/history');
}

export async function deleteHistoryItem(id) {
  return request(`/history/${id}`, { method: 'DELETE' });
}

// Personalization
export async function initPersonalization(query) {
  return request('/personalization/init', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export async function submitPersonalizationAnswers(sessionId, answers) {
  return request('/personalization/answers', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, answers }),
  });
}

// Research stream (returns EventSource)
export function createResearchStream({ query, sessionId, userId }) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (query && !sessionId) params.set('query', query);
  if (userId) params.set('user_id', userId);
  return new EventSource(`${API_BASE}/research/stream?${params.toString()}`);
}
