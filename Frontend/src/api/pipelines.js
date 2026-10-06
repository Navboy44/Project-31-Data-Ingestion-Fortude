import { API_BASE } from "../data";

// Request helpers return saved data or throw an error for the caller to display.
async function requestPipeline(path = "", options = {}) {
  const response = await fetch(
    `${API_BASE}/api/config/pipelines${path}`,
    options
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Unable to complete the pipeline request. Please try again."
    );
  }
  if (response.status === 204) return;
  return response.json();
}

export function listPipelines(signal) {
  return requestPipeline("", { signal });
}

export function createPipeline(definition) {
  return requestPipeline("", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

export function updatePipeline(id, definition) {
  return requestPipeline(`/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

export function deletePipeline(id) {
  return requestPipeline(`/${id}`, { method: "DELETE" });
}
