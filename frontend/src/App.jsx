import React from "react";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  getDepartments,
  getServices,
  getCounters,
  registerStudent,
  createToken,
  getToken,
  getAdminQueues,
  callNextToken,
  completeToken,
  skipToken,
} from "./api";

const VALID_STATUSES = ["Waiting", "Called", "Serving", "Completed", "Skipped", "Cancelled"];

function getErrorMessage(error) {
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

export default function App() {
  const [page, setPage] = useState("home"); // home, register, departments, services, tracking, admin
  const [departments, setDepartments] = useState([]);
  const [departmentsLoading, setDepartmentsLoading] = useState(true);
  const [selectedDepartment, setSelectedDepartment] = useState(null);
  const [services, setServices] = useState([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [selectedService, setSelectedService] = useState(null);

  // Student authentication / session state
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem("queueflow_user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [registerForm, setRegisterForm] = useState({
    full_name: "",
    email: "",
    password: "",
  });

  // Token tracking state
  const [token, setToken] = useState(null);
  const [trackingLookup, setTrackingLookup] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  // Admin state
  const [counters, setCounters] = useState([]);
  const [selectedCounterId, setSelectedCounterId] = useState(() => {
    try {
      const saved = localStorage.getItem("queueflow_counter_id");
      return saved ? parseInt(saved, 10) : null;
    } catch {
      return null;
    }
  });
  const [adminDeptFilter, setAdminDeptFilter] = useState("all");
  const [adminQueueData, setAdminQueueData] = useState(null);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminAutoRefresh, setAdminAutoRefresh] = useState(true);

  // Save student to localStorage
  const saveUserSession = (user) => {
    setCurrentUser(user);
    try {
      if (user) {
        localStorage.setItem("queueflow_user", JSON.stringify(user));
      } else {
        localStorage.removeItem("queueflow_user");
      }
    } catch {
      // Ignore storage errors
    }
  };

  // Save selected counter
  const handleSelectCounter = (counterId) => {
    setSelectedCounterId(counterId);
    try {
      if (counterId) {
        localStorage.setItem("queueflow_counter_id", counterId.toString());
      } else {
        localStorage.removeItem("queueflow_counter_id");
      }
    } catch {
      // Ignore storage errors
    }
  };

  // Load departments once
  useEffect(() => {
    let isMounted = true;
    async function loadInitial() {
      try {
        const deptList = await getDepartments();
        if (isMounted) {
          setDepartments(Array.isArray(deptList) ? deptList : []);
          setError("");
        }
      } catch (err) {
        if (isMounted) setError(getErrorMessage(err));
      } finally {
        if (isMounted) setDepartmentsLoading(false);
      }
    }
    loadInitial();
    return () => {
      isMounted = false;
    };
  }, []);

  // When selected department changes, load its services
  useEffect(() => {
    if (!selectedDepartment) {
      setServices([]);
      setSelectedService(null);
      return;
    }

    let isMounted = true;
    setServicesLoading(true);

    async function loadServices() {
      try {
        const sList = await getServices(selectedDepartment.id);
        if (isMounted) {
          setServices(Array.isArray(sList) ? sList : []);
          setSelectedService(null);
        }
      } catch (err) {
        if (isMounted) setError(getErrorMessage(err));
      } finally {
        if (isMounted) setServicesLoading(false);
      }
    }
    loadServices();
    return () => {
      isMounted = false;
    };
  }, [selectedDepartment]);

  // Load counters whenever admin view is opened or department filter changes
  const loadCounters = useCallback(async () => {
    try {
      const deptId = adminDeptFilter !== "all" ? adminDeptFilter : undefined;
      const cList = await getCounters(deptId);
      setCounters(Array.isArray(cList) ? cList : []);
    } catch (err) {
      console.error("Failed to load counters:", err);
    }
  }, [adminDeptFilter]);

  useEffect(() => {
    if (page === "admin") {
      loadCounters();
    }
  }, [page, loadCounters]);

  // Fetch admin queue data
  const fetchAdminQueues = useCallback(async () => {
    try {
      const params = {};
      if (adminDeptFilter !== "all") params.department_id = adminDeptFilter;
      if (selectedCounterId) params.counter_id = selectedCounterId;
      const data = await getAdminQueues(params);
      setAdminQueueData(data);
    } catch (err) {
      console.error("Failed to fetch admin queues:", err);
    }
  }, [adminDeptFilter, selectedCounterId]);

  useEffect(() => {
    if (page === "admin") {
      fetchAdminQueues();
      if (!adminAutoRefresh) return;
      const interval = setInterval(fetchAdminQueues, 5000);
      return () => clearInterval(interval);
    }
  }, [page, fetchAdminQueues, adminAutoRefresh]);

  // Student tracking polling: poll while token is active (Waiting, Called, Serving)
  useEffect(() => {
    if (page === "tracking" && token?.token_id) {
      const isQueueActive = ["Waiting", "Called", "Serving"].includes(token.status);
      if (!isQueueActive) return;

      const interval = setInterval(async () => {
        try {
          const updated = await getToken(token.token_id);
          if (updated && updated.token_id) {
            setToken((prev) => ({ ...prev, ...updated }));
          }
        } catch {
          // Silent polling failure to avoid jarring UI
        }
      }, 5000);

      return () => clearInterval(interval);
    }
  }, [page, token?.token_id, token?.status]);

  // Handle student registration
  async function handleRegisterSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!registerForm.full_name.trim()) {
      setError("Please enter your full name.");
      return;
    }
    if (!registerForm.email.trim()) {
      setError("Please enter a valid email address.");
      return;
    }
    if (registerForm.password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);
    try {
      const res = await registerStudent(registerForm);
      const user = {
        id: res.user_id,
        full_name: registerForm.full_name.trim(),
        email: registerForm.email.trim().toLowerCase(),
      };
      saveUserSession(user);
      setSuccessMessage("Registration successful! Now select your department.");
      setRegisterForm({ full_name: "", email: "", password: "" });
      setPage("departments");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Start token generation flow
  function handleStartTokenFlow() {
    setError("");
    setSuccessMessage("");
    if (!currentUser) {
      setPage("register");
    } else {
      setPage("departments");
    }
  }

  // Handle department selection
  function handleSelectDepartment(dept) {
    setSelectedDepartment(dept);
    setError("");
    setPage("services");
  }

  // Handle token generation
  async function handleGenerateToken() {
    if (!currentUser?.id) {
      setError("Student session not found. Please register first.");
      setPage("register");
      return;
    }
    if (!selectedService?.id) {
      setError("Please select a service before generating a token.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const newToken = await createToken({
        user_id: currentUser.id,
        service_id: selectedService.id,
      });

      // Augment with department & service names for immediate display
      const fullToken = {
        ...newToken,
        token_number: newToken.queue_number,
        service_name: selectedService.name,
        department_name: selectedDepartment?.name || "",
        queue_position: 1,
        people_ahead: 0,
        estimated_wait_minutes: selectedService.estimated_duration_minutes || 10,
      };

      setToken(fullToken);
      setSuccessMessage(`Token #${newToken.queue_number} generated successfully!`);
      setPage("tracking");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Refresh token tracking
  async function refreshQueue() {
    if (!token?.token_id) return;
    setLoading(true);
    setError("");
    try {
      const updated = await getToken(token.token_id);
      setToken(updated);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Lookup token by reference (ID or 32-character code)
  async function handleLookupToken(e) {
    e.preventDefault();
    if (!trackingLookup.trim()) return;

    setLoading(true);
    setError("");
    try {
      const found = await getToken(trackingLookup.trim());
      setToken(found);
      setTrackingLookup("");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Admin action: Call next token
  async function handleAdminCallNext() {
    if (!selectedCounterId) {
      setError("Please select an active service counter first.");
      return;
    }
    setAdminLoading(true);
    setError("");
    setSuccessMessage("");
    try {
      const result = await callNextToken(selectedCounterId);
      setSuccessMessage(
        `Called Token #${result.queue_number} (${result.service_name}) to this counter!`,
      );
      await fetchAdminQueues();
    } catch (err) {
      if (err.code === "queue_empty") {
        setSuccessMessage("Queue is empty: No students are currently waiting for this department.");
      } else {
        setError(getErrorMessage(err));
      }
    } finally {
      setAdminLoading(false);
    }
  }

  // Admin action: Complete token
  async function handleAdminComplete(tokenId) {
    if (!selectedCounterId) {
      setError("Please select an active service counter first.");
      return;
    }
    setAdminLoading(true);
    setError("");
    setSuccessMessage("");
    try {
      await completeToken(tokenId, selectedCounterId);
      setSuccessMessage(`Token completed successfully! Service history recorded.`);
      await fetchAdminQueues();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setAdminLoading(false);
    }
  }

  // Admin action: Skip token
  async function handleAdminSkip(tokenId) {
    if (!selectedCounterId) {
      setError("Please select an active service counter first.");
      return;
    }
    setAdminLoading(true);
    setError("");
    setSuccessMessage("");
    try {
      await skipToken(tokenId, selectedCounterId);
      setSuccessMessage(`Token marked as Skipped.`);
      await fetchAdminQueues();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setAdminLoading(false);
    }
  }

  function goHome() {
    setPage("home");
    setError("");
    setSuccessMessage("");
  }

  const selectedCounterObj = counters.find((c) => c.id === selectedCounterId);

  return (
    <div className="app-shell">
      {/* Topbar navigation */}
      <header className="topbar">
        <button className="brand" onClick={goHome} aria-label="QueueFlow AI home">
          <span className="brand-icon">Q</span>
          <span>
            QueueFlow <strong>AI</strong>
          </span>
        </button>

        <nav className="navigation" aria-label="Main navigation">
          <button className={page === "home" ? "nav-active" : ""} onClick={goHome}>
            Home
          </button>
          <button
            className={page === "departments" || page === "services" ? "nav-active" : ""}
            onClick={handleStartTokenFlow}
          >
            Get a Token
          </button>
          <button
            className={page === "tracking" ? "nav-active" : ""}
            onClick={() => setPage("tracking")}
          >
            Track Queue
          </button>
          <button
            className={`admin-nav-button ${page === "admin" ? "nav-active" : ""}`}
            onClick={() => {
              setPage("admin");
              setError("");
              setSuccessMessage("");
            }}
          >
            Admin Dashboard
          </button>
        </nav>
      </header>

      {/* Student session indicator bar */}
      {currentUser && (
        <aside className="user-session-bar" aria-label="Current student session">
          <div className="user-session-inner">
            <span>
              Student: <strong>{currentUser.full_name}</strong> ({currentUser.email})
            </span>
            <div className="user-session-actions">
              <button
                className="text-btn"
                onClick={() => {
                  saveUserSession(null);
                  setPage("register");
                }}
              >
                Switch Student
              </button>
            </div>
          </div>
        </aside>
      )}

      <main>
        {/* Global Notifications */}
        {error && (
          <div className="system-banner error-banner" role="alert">
            <span>{error}</span>
            <button className="close-banner" onClick={() => setError("")}>
              ✕
            </button>
          </div>
        )}
        {successMessage && (
          <div className="system-banner success-banner" role="status">
            <span>{successMessage}</span>
            <button className="close-banner" onClick={() => setSuccessMessage("")}>
              ✕
            </button>
          </div>
        )}

        {/* 1. HOME SCREEN */}
        {page === "home" && (
          <>
            <section className="hero">
              <div>
                <p className="eyebrow">YOUR CAMPUS, WITHOUT THE WAIT</p>
                <h1>
                  Make time for
                  <br />
                  <span>what matters.</span>
                </h1>
                <p className="hero-copy">
                  Join your college service queue online, receive a digital token with QR code, and
                  track your real-time place in line from anywhere.
                </p>
                <div className="hero-actions">
                  <button className="primary-button" onClick={handleStartTokenFlow}>
                    Get a token <span aria-hidden="true">→</span>
                  </button>
                  <button
                    className="secondary-button hero-secondary"
                    onClick={() => setPage(token ? "tracking" : "departments")}
                  >
                    Track your status
                  </button>
                </div>
              </div>

              <div className="hero-card" aria-label="Queue tracking preview">
                <div className="preview-top">
                  <span>QUEUEFLOW AI</span>
                  <span className="preview-dot" />
                </div>
                <p className="preview-label">LIVE CAMPUS QUEUE SYSTEM</p>
                <div className="preview-line">
                  <span>Digital Token</span>
                  <span>Instant QR Code</span>
                </div>
                <div className="preview-line">
                  <span>Queue Position</span>
                  <span>Live Wait Time</span>
                </div>
                <div className="preview-line">
                  <span>Multiple Counters</span>
                  <span>Direct Notification</span>
                </div>
                <p className="preview-note">Fast, transparent service across all university departments.</p>
              </div>
            </section>

            <section className="departments-section">
              <p className="eyebrow">CAMPUS SERVICES</p>
              <h2>Select a Department to Begin</h2>
              {departmentsLoading && (
                <p className="message">Loading available campus departments…</p>
              )}
              {!departmentsLoading && departments.length === 0 && (
                <p className="message">No active departments found.</p>
              )}
              <div className="department-grid">
                {departments.map((dept) => (
                  <button
                    className="department-card"
                    key={dept.id}
                    onClick={() => {
                      if (!currentUser) {
                        setSelectedDepartment(dept);
                        setPage("register");
                      } else {
                        handleSelectDepartment(dept);
                      }
                    }}
                  >
                    <span className="department-symbol" aria-hidden="true">
                      ▦
                    </span>
                    <strong>{dept.name}</strong>
                    <span>{dept.description || "Campus service department"}</span>
                    <span className="card-link">Select department →</span>
                  </button>
                ))}
              </div>
            </section>
          </>
        )}

        {/* 2. STUDENT REGISTRATION SCREEN */}
        {page === "register" && (
          <section className="flow-section auth-section">
            <button className="back-button" onClick={goHome}>
              ← Back home
            </button>
            <p className="eyebrow">STEP 1 OF 3</p>
            <h1>Student Registration</h1>
            <p className="section-copy">
              Please register your student details. Your token and queue history will be linked to
              your record.
            </p>

            <div className="auth-card">
              <form onSubmit={handleRegisterSubmit}>
                <div className="form-group">
                  <label className="form-label" htmlFor="student-full-name">
                    Full Name *
                  </label>
                  <input
                    id="student-full-name"
                    className="form-input"
                    type="text"
                    required
                    placeholder="e.g. Asha Student"
                    maxLength={120}
                    value={registerForm.full_name}
                    onChange={(e) =>
                      setRegisterForm({ ...registerForm, full_name: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="student-email">
                    Student Email Address *
                  </label>
                  <input
                    id="student-email"
                    className="form-input"
                    type="email"
                    required
                    placeholder="e.g. asha@college.edu"
                    maxLength={254}
                    value={registerForm.email}
                    onChange={(e) =>
                      setRegisterForm({ ...registerForm, email: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="student-password">
                    Password * (8-128 characters)
                  </label>
                  <input
                    id="student-password"
                    className="form-input"
                    type="password"
                    required
                    minLength={8}
                    maxLength={128}
                    placeholder="Enter password"
                    value={registerForm.password}
                    onChange={(e) =>
                      setRegisterForm({ ...registerForm, password: e.target.value })
                    }
                  />
                </div>

                <button
                  type="submit"
                  className="primary-button full-width"
                  disabled={loading}
                >
                  {loading ? "Registering…" : "Complete Registration & Continue"} →
                </button>
              </form>
            </div>
          </section>
        )}

        {/* 3. DEPARTMENT SELECTION SCREEN */}
        {page === "departments" && (
          <section className="flow-section">
            <button className="back-button" onClick={goHome}>
              ← Back home
            </button>
            <p className="eyebrow">STEP 2 OF 3</p>
            <h1>Choose Department</h1>
            <p className="section-copy">
              Select which campus department you need assistance with.
            </p>

            <div className="department-grid selection-grid">
              {departments.map((dept) => (
                <button
                  className={`department-card ${
                    selectedDepartment?.id === dept.id ? "selected" : ""
                  }`}
                  key={dept.id}
                  onClick={() => handleSelectDepartment(dept)}
                >
                  <span className="department-symbol" aria-hidden="true">
                    ▦
                  </span>
                  <strong>{dept.name}</strong>
                  <span>{dept.description || "Campus service department"}</span>
                  <span className="card-link">
                    {selectedDepartment?.id === dept.id ? "Selected ✓" : "Choose Service →"}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* 4. SERVICE SELECTION SCREEN */}
        {page === "services" && (
          <section className="flow-section">
            <button className="back-button" onClick={() => setPage("departments")}>
              ← Back to departments
            </button>
            <p className="eyebrow">STEP 3 OF 3</p>
            <h1>Select Service – {selectedDepartment?.name}</h1>
            <p className="section-copy">
              Choose the specific service you need. Duration estimates help calculate queue wait
              times.
            </p>

            {servicesLoading && <p className="message">Loading services…</p>}
            {!servicesLoading && services.length === 0 && (
              <p className="message">No active services currently listed for this department.</p>
            )}

            <div className="services-grid">
              {services.map((svc) => (
                <button
                  className={`service-card ${selectedService?.id === svc.id ? "selected" : ""}`}
                  key={svc.id}
                  onClick={() => setSelectedService(svc)}
                >
                  <div className="service-header">
                    <strong>{svc.name}</strong>
                    <span className="duration-tag">
                      ~{svc.estimated_duration_minutes} min
                    </span>
                  </div>
                  <p className="service-desc">{svc.description}</p>
                  <div className="service-footer">
                    <span className="card-link">
                      {selectedService?.id === svc.id ? "Selected ✓" : "Select Service →"}
                    </span>
                  </div>
                </button>
              ))}
            </div>

            <div className="service-action-bar">
              <button
                className="primary-button"
                onClick={handleGenerateToken}
                disabled={!selectedService || loading}
              >
                {loading ? "Generating Token…" : "Generate Digital Token"} →
              </button>
            </div>
          </section>
        )}

        {/* 5. STUDENT TOKEN TRACKING SCREEN */}
        {page === "tracking" && (
          <section className="flow-section tracking-section">
            <div className="tracking-top-bar">
              <button className="back-button" onClick={goHome}>
                ← Back home
              </button>

              {/* Quick lookup form */}
              <form className="quick-lookup-form" onSubmit={handleLookupToken}>
                <input
                  type="text"
                  placeholder="Lookup Token ID or Code"
                  value={trackingLookup}
                  onChange={(e) => setTrackingLookup(e.target.value)}
                  className="form-input lookup-input"
                />
                <button type="submit" className="secondary-button btn-sm" disabled={loading}>
                  Find
                </button>
              </form>
            </div>

            <p className="eyebrow">LIVE QUEUE TRACKING</p>
            <h1>Your Digital Token</h1>

            {token ? (
              <div className="tracking-card">
                {/* Status banner if CALLED */}
                {token.status === "Called" && (
                  <div className="called-banner" role="alert">
                    <div className="called-icon">📢</div>
                    <div>
                      <strong>Your Token Has Been Called!</strong>
                      <p>
                        Please proceed immediately to{" "}
                        <strong>{token.counter_name || `Counter ${token.counter_id}`}</strong>
                        {token.counter_location ? ` (${token.counter_location})` : ""}.
                      </p>
                    </div>
                  </div>
                )}

                <div className="tracking-heading">
                  <span>QUEUE TOKEN</span>
                  <span className={`status-badge status-${token.status.toLowerCase()}`}>
                    {token.status}
                  </span>
                </div>

                <div className="token-hero-row">
                  <div>
                    <div className="token-number">#{token.token_number}</div>
                    <div className="token-code-tag">
                      Code: <code>{token.token_code}</code>
                    </div>
                    <p className="tracking-meta">
                      <strong>{token.service_name}</strong> •{" "}
                      <span>{token.department_name}</span>
                    </p>
                  </div>

                  {/* QR Code display */}
                  {token.qr_code_base64 && (
                    <div className="qr-box" aria-label="Digital Token QR Code">
                      <img
                        src={`data:${token.qr_code_mime_type || "image/png"};base64,${
                          token.qr_code_base64
                        }`}
                        alt={`QR code for token ${token.token_number}`}
                        className="qr-image"
                      />
                      <span className="qr-caption">Scan at counter</span>
                    </div>
                  )}
                </div>

                <div className="queue-details">
                  <div>
                    <span>Queue position</span>
                    <strong>{token.queue_position ?? "—"}</strong>
                  </div>
                  <div>
                    <span>People ahead</span>
                    <strong>{token.people_ahead ?? 0}</strong>
                  </div>
                  <div>
                    <span>Estimated wait</span>
                    <strong>
                      {token.estimated_wait_minutes ?? 0}{" "}
                      <small style={{ fontSize: "14px" }}>min</small>
                    </strong>
                  </div>
                  <div>
                    <span>Assigned counter</span>
                    <strong>{token.counter_name || (token.counter_id ? `Counter ${token.counter_id}` : "Unassigned")}</strong>
                  </div>
                </div>

                <div className="tracking-footer">
                  <p className="token-date-text">
                    Issued: {new Date(token.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} • Date: {token.queue_date}
                  </p>

                  <button
                    className="secondary-button"
                    onClick={refreshQueue}
                    disabled={loading}
                  >
                    {loading ? "Refreshing…" : "Refresh Queue"} ↻
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-card">
                <h2>No active token selected</h2>
                <p>
                  You haven't requested a token yet, or you can search for an existing token by ID
                  using the lookup box above.
                </p>
                <button className="primary-button" onClick={handleStartTokenFlow}>
                  Get a Token Now →
                </button>
              </div>
            )}
          </section>
        )}

        {/* 6. ADMIN DASHBOARD SCREEN */}
        {page === "admin" && (
          <section className="flow-section admin-section">
            <div className="admin-header-row">
              <div>
                <p className="eyebrow">ADMINISTRATION & COUNTER CONTROL</p>
                <h1>Counter Operations & Live Queues</h1>
              </div>

              <div className="admin-controls-group">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={adminAutoRefresh}
                    onChange={(e) => setAdminAutoRefresh(e.target.checked)}
                  />
                  Auto-refresh (5s)
                </label>
                <button
                  className="secondary-button btn-sm"
                  onClick={fetchAdminQueues}
                  disabled={adminLoading}
                >
                  Refresh Now ↻
                </button>
              </div>
            </div>

            {/* Counter Selection Bar */}
            <div className="counter-selector-panel">
              <div className="counter-selector-fields">
                <div className="form-group-inline">
                  <label htmlFor="admin-dept-select">Department Filter:</label>
                  <select
                    id="admin-dept-select"
                    className="form-select"
                    value={adminDeptFilter}
                    onChange={(e) => {
                      setAdminDeptFilter(e.target.value);
                      setSelectedCounterId(null);
                    }}
                  >
                    <option value="all">All Departments</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group-inline">
                  <label htmlFor="admin-counter-select">Operating Counter:</label>
                  <select
                    id="admin-counter-select"
                    className="form-select"
                    value={selectedCounterId || ""}
                    onChange={(e) => handleSelectCounter(e.target.value ? parseInt(e.target.value, 10) : null)}
                  >
                    <option value="">-- Select a Counter to Operate --</option>
                    {counters.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.counter_name} ({c.department_name})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {selectedCounterObj ? (
                <div className="selected-counter-summary">
                  <div>
                    <span className="pill-badge">Active Counter</span>
                    <strong>{selectedCounterObj.counter_name}</strong>
                    <span className="counter-loc">({selectedCounterObj.location})</span>
                  </div>
                  <div>
                    Department: <strong>{selectedCounterObj.department_name}</strong>
                  </div>
                </div>
              ) : (
                <p className="counter-hint-note">
                  Select a counter above to call next tokens, complete services, or skip students.
                </p>
              )}
            </div>

            {/* Active Counter Action Station */}
            {selectedCounterObj && (
              <div className="counter-action-card">
                <div className="counter-station-header">
                  <h3>Counter Station: {selectedCounterObj.counter_name}</h3>
                  <span className="status-badge status-called">Ready to Serve</span>
                </div>

                <div className="counter-action-body">
                  {adminQueueData?.current_token ? (
                    <div className="current-serving-box">
                      <div className="serving-label">CURRENTLY SERVING TOKEN:</div>
                      <div className="serving-details">
                        <div className="serving-num">#{adminQueueData.current_token.queue_number}</div>
                        <div>
                          <strong>{adminQueueData.current_token.service_name}</strong>
                          <p>
                            Student: {adminQueueData.current_token.student_name || "Unregistered"} (
                            {adminQueueData.current_token.student_email || "N/A"})
                          </p>
                          <p className="token-code-tag">
                            Code: <code>{adminQueueData.current_token.token_code}</code>
                          </p>
                        </div>
                      </div>

                      <div className="serving-buttons">
                        <button
                          className="primary-button btn-complete"
                          onClick={() => handleAdminComplete(adminQueueData.current_token.token_id)}
                          disabled={adminLoading}
                        >
                          Complete Service ✓
                        </button>
                        <button
                          className="secondary-button btn-skip"
                          onClick={() => handleAdminSkip(adminQueueData.current_token.token_id)}
                          disabled={adminLoading}
                        >
                          Skip Token ✕
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="no-serving-box">
                      <p>Counter is currently idle. Click below to call the next waiting student.</p>
                      <button
                        className="primary-button"
                        onClick={handleAdminCallNext}
                        disabled={adminLoading}
                      >
                        {adminLoading ? "Calling…" : "Call Next Token"} 📢
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Queue Metrics Dashboard */}
            {adminQueueData?.summary && (
              <div className="metrics-grid">
                <div className="metric-card">
                  <span className="metric-label">Waiting in Queue</span>
                  <strong className="metric-value metric-waiting">
                    {adminQueueData.summary.waiting_count}
                  </strong>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Currently Called / Serving</span>
                  <strong className="metric-value metric-called">
                    {adminQueueData.summary.called_count}
                  </strong>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Completed Today</span>
                  <strong className="metric-value metric-completed">
                    {adminQueueData.summary.completed_count}
                  </strong>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Skipped Today</span>
                  <strong className="metric-value metric-skipped">
                    {adminQueueData.summary.skipped_count}
                  </strong>
                </div>
              </div>
            )}

            {/* Active Queue Table */}
            <div className="queue-table-section">
              <div className="section-title-row">
                <h2>Today's Queue List ({adminQueueData?.tokens?.length || 0} Total)</h2>
                {selectedCounterObj && (
                  <button
                    className="primary-button btn-sm"
                    onClick={handleAdminCallNext}
                    disabled={adminLoading}
                  >
                    Call Next Token 📢
                  </button>
                )}
              </div>

              {!adminQueueData?.tokens || adminQueueData.tokens.length === 0 ? (
                <div className="empty-card">
                  <p>No tokens have been issued today for this department.</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="queue-table">
                    <thead>
                      <tr>
                        <th>Token #</th>
                        <th>Status</th>
                        <th>Service</th>
                        <th>Department</th>
                        <th>Student</th>
                        <th>Assigned Counter</th>
                        <th>Issued At</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adminQueueData.tokens.map((tok) => (
                        <tr key={tok.token_id} className={`tr-${tok.status.toLowerCase()}`}>
                          <td>
                            <strong>#{tok.queue_number}</strong>
                          </td>
                          <td>
                            <span className={`status-badge status-${tok.status.toLowerCase()}`}>
                              {tok.status}
                            </span>
                          </td>
                          <td>{tok.service_name}</td>
                          <td>{tok.department_name}</td>
                          <td>
                            {tok.student_name ? (
                              <span>
                                {tok.student_name}
                                <br />
                                <small style={{ color: "#778399" }}>{tok.student_email}</small>
                              </span>
                            ) : (
                              <span style={{ color: "#8c9ba5" }}>Guest</span>
                            )}
                          </td>
                          <td>{tok.counter_name || "—"}</td>
                          <td>
                            {new Date(tok.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </td>
                          <td>
                            <div className="action-button-cell">
                              {tok.status === "Waiting" && selectedCounterObj && (
                                <button
                                  className="text-action-btn btn-danger-text"
                                  onClick={() => handleAdminSkip(tok.token_id)}
                                  disabled={adminLoading}
                                  title="Skip waiting token"
                                >
                                  Skip
                                </button>
                              )}
                              {(tok.status === "Called" || tok.status === "Serving") &&
                                selectedCounterId === tok.counter_id && (
                                  <>
                                    <button
                                      className="text-action-btn btn-success-text"
                                      onClick={() => handleAdminComplete(tok.token_id)}
                                      disabled={adminLoading}
                                    >
                                      Complete
                                    </button>
                                    <button
                                      className="text-action-btn btn-danger-text"
                                      onClick={() => handleAdminSkip(tok.token_id)}
                                      disabled={adminLoading}
                                    >
                                      Skip
                                    </button>
                                  </>
                                )}
                              {tok.status === "Completed" && (
                                <span className="status-finished">Done</span>
                              )}
                              {tok.status === "Skipped" && (
                                <span className="status-finished">Skipped</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        <div>
          <strong>QueueFlow AI</strong> — Campus Queue Management System
        </div>
        <span>Department of Campus Operations & Student Services</span>
      </footer>
    </div>
  );
}
