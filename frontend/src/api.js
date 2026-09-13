const API_BASE = "http://127.0.0.1:8000";

export async function getObjects(group = "stations", limit = 100) {
  const response = await fetch(
    `${API_BASE}/objects?group=${group}&limit=${limit}`
  );

  if (!response.ok) {
    throw new Error("Failed to fetch orbital objects");
  }

  return response.json();
}

export async function getObject(noradId) {
  const response = await fetch(`${API_BASE}/objects/${noradId}`);

  if (!response.ok) {
    throw new Error("Failed to fetch object");
  }

  return response.json();
}

export async function getTrajectory(noradId) {
  const response = await fetch(
    `${API_BASE}/trajectory/${noradId}`
  );

  if (!response.ok) {
    throw new Error("Failed to fetch trajectory");
  }

  return response.json();
}

export async function getConjunctions(
  group = "stations",
  limit = 100,
  threshold = 5
) {
  const response = await fetch(
    `${API_BASE}/conjunctions?group=${group}&limit=${limit}&threshold_km=${threshold}`
  );

  if (!response.ok) {
    throw new Error("Failed to fetch conjunctions");
  }

  return response.json();
}
export async function getWhatIf(
  noradId,
  otherNoradId,
  altitudeDeltaKm = 10
) {
  const response = await fetch(
    `${API_BASE}/what-if?norad_id=${noradId}&other_norad_id=${otherNoradId}&altitude_delta_km=${altitudeDeltaKm}`
  );

  if (!response.ok) {
    throw new Error("Failed to run maneuver analysis");
  }

  return response.json();
}