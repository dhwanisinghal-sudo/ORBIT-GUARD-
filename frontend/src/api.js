
const API_BASE = "http://127.0.0.1:8000";

const TOKEN_KEY = "orbitguard_access_token";
const USER_KEY = "orbitguard_user";

// Shared API helper
async function apiRequest(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);

  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(", ")
      : typeof detail === "string"
        ? detail
        : "Something went wrong. Please try again.";

    throw new Error(message);
  }

  return data;
}

// Authentication
export async function registerUser({ name, email, password }) {
  const data = await apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });

  saveSession(data);
  return data;
}

export async function loginUser({ email, password }) {
  const data = await apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  saveSession(data);
  return data;
}

function saveSession(data) {
  if (!data.access_token || !data.user) {
    throw new Error("The server returned an invalid login response.");
  }

  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export async function getCurrentUser() {
  return apiRequest("/auth/me");
}

export function getSavedUser() {
  try {
    const saved = localStorage.getItem(USER_KEY);
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
}

export function logoutUser() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLoggedIn() {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}

// Existing orbital API functions
export async function getObjects(group = "stations", limit = 100) {
  return apiRequest(
    `/objects?group=${encodeURIComponent(group)}&limit=${limit}`
  );
}

export async function getObject(noradId) {
  return apiRequest(`/objects/${encodeURIComponent(noradId)}`);
}

export async function getTrajectory(noradId, hours = null) {
  const query = hours ? `?hours=${encodeURIComponent(hours)}` : "";
  return apiRequest(`/trajectory/${encodeURIComponent(noradId)}${query}`);
}

export async function getConjunctions(
  group = "stations",
  limit = 100,
  threshold = 5
) {
  return apiRequest(
    `/conjunctions?group=${encodeURIComponent(group)}&limit=${limit}&threshold_km=${threshold}`
  );
}

export async function getWhatIf(
  noradId,
  otherNoradId,
  altitudeDeltaKm = 10
) {
  return apiRequest(
    `/what-if?norad_id=${encodeURIComponent(noradId)}&other_norad_id=${encodeURIComponent(otherNoradId)}&altitude_delta_km=${encodeURIComponent(altitudeDeltaKm)}`
  );
}

// ML risk scoring
export async function getModelInfo() {
  return apiRequest("/model-info");
}

export async function getRiskScore({
  distance_km,
  relative_velocity_km_s,
  altitude_km,
}) {
  const params = new URLSearchParams({
    distance_km: String(distance_km),
    relative_velocity_km_s: String(relative_velocity_km_s),
    altitude_km: String(altitude_km),
  });

  return apiRequest(`/risk-score?${params.toString()}`);
}
