const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000/api";

function makeUrl(path) {
  const cleanBase = API_BASE_URL.replace(/\/$/, "");
  const cleanPath = path.replace(/^\//, "");
  return `${cleanBase}/${cleanPath}`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(makeUrl(path), {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (networkError) {
    throw new Error(
      "Unable to connect to the backend server. Please verify the Flask server is running at " +
        API_BASE_URL,
    );
  }

  const responseText = await response.text();
  let json;

  if (responseText) {
    try {
      json = JSON.parse(responseText);
    } catch {
      throw new Error("The backend server returned an invalid response.");
    }
  }

  if (!response.ok || (json && json.success === false)) {
    const errorMsg =
      json?.error?.message ||
      json?.message ||
      `Server returned status ${response.status}.`;
    const err = new Error(errorMsg);
    err.code = json?.error?.code;
    err.status = response.status;
    throw err;
  }

  if (json === undefined) {
    throw new Error("The backend server returned an empty response.");
  }

  return json.data;
}

// System health check
export function checkHealth() {
  return request("/health");
}

// Fetch all active departments
export function getDepartments() {
  return request("/departments");
}

// Fetch active services, optionally filtered by department
export function getServices(departmentId) {
  const query = departmentId ? `?department_id=${encodeURIComponent(departmentId)}` : "";
  return request(`/services${query}`);
}

// Fetch active counters, optionally filtered by department
export function getCounters(departmentId) {
  const query = departmentId ? `?department_id=${encodeURIComponent(departmentId)}` : "";
  return request(`/counters${query}`);
}

// Register a new student
export function registerStudent({ full_name, email, password }) {
  return request("/users", {
    method: "POST",
    body: JSON.stringify({ full_name, email, password }),
  });
}

// Generate a new queue token for a user and service
export function createToken({ user_id, service_id }) {
  return request("/tokens", {
    method: "POST",
    body: JSON.stringify({ user_id, service_id }),
  });
}

// Fetch token tracking details by token ID or 32-character token code
export function getToken(tokenReference) {
  return request(`/tokens/${encodeURIComponent(tokenReference)}`);
}

// Admin: Fetch active queues and status summary
export function getAdminQueues({ department_id, counter_id } = {}) {
  const params = new URLSearchParams();
  if (department_id) params.append("department_id", department_id);
  if (counter_id) params.append("counter_id", counter_id);
  const query = params.toString() ? `?${params.toString()}` : "";
  return request(`/admin/queues${query}`);
}

// Admin: Call next token for a counter
export function callNextToken(counter_id) {
  return request("/admin/call-next", {
    method: "POST",
    body: JSON.stringify({ counter_id }),
  });
}

// Admin: Complete a token
export function completeToken(token_id, counter_id) {
  return request("/admin/complete", {
    method: "POST",
    body: JSON.stringify({ token_id, counter_id }),
  });
}

// Admin: Skip a token
export function skipToken(token_id, counter_id) {
  return request("/admin/skip", {
    method: "POST",
    body: JSON.stringify({ token_id, counter_id }),
  });
}
