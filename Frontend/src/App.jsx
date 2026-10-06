import React, { useState, useRef, useEffect } from "react";
import {
  COLORS,
  FONTS,
  GOOGLE_FONTS_IMPORT,
  LIGHT_THEME,
  DARK_THEME,
} from "./theme";
import { INITIAL_HISTORY, API_BASE } from "./data";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import Toast from "./components/Toast";
import Dashboard from "./pages/Dashboard";
import NewIngestion from "./pages/NewIngestion";
import Configure from "./pages/Configuration";
import History from "./pages/History";
import EntryDetail from "./pages/EntryDetail";
import Login from "./pages/Login";
import Settings from "./pages/Settings";
import ChangeUsername from "./pages/ChangeUsername";
import * as pipelineApi from "./api/pipelines";

// Empty config shape used while the backend data is loading.
const EMPTY_CONFIG = { connectors: [], rules: [], outputs: [] };

// The root app component controls navigation, shared state, and the main layout.
export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [themeMode, setThemeMode] = useState("light");

  // Tracks which page is currently visible in the main content area.
  const [page, setPage] = useState("dashboard");
  const contentRef = useRef(null);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 });
  }, [page]);
  // Controls whether the left-hand navigation panel is visible.
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Ingestion history loaded from the backend.
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  // Configuration loaded from the backend.  Each item is { id, name, created_at }.
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [configLoading, setConfigLoading] = useState(true);
  const [pipelines, setPipelines] = useState([]);
  const [pipelinesLoading, setPipelinesLoading] = useState(true);
  const [pipelinesError, setPipelinesError] = useState("");
  const pipelineRequest = useRef(null);

  // Shared pipeline data stays available when switching between pages.
  async function fetchPipelines() {
    pipelineRequest.current?.abort();
    const controller = new AbortController();
    pipelineRequest.current = controller;
    setPipelinesLoading(true);
    setPipelinesError("");
    try {
      const data = await pipelineApi.listPipelines(controller.signal);
      if (!controller.signal.aborted) setPipelines(data);
    } catch (error) {
      if (!controller.signal.aborted)
        setPipelinesError(error.message || "Unable to load pipelines.");
    } finally {
      if (!controller.signal.aborted) setPipelinesLoading(false);
    }
  }

  useEffect(() => {
    fetchPipelines();
    return () => pipelineRequest.current?.abort();
  }, []);

  async function createPipeline(definition) {
    const pipeline = await pipelineApi.createPipeline(definition);
    setPipelines((items) => [...items, pipeline]);
    return pipeline;
  }

  async function updatePipeline(id, definition) {
    const pipeline = await pipelineApi.updatePipeline(id, definition);
    setPipelines((items) =>
      items.map((item) => (item.id === id ? pipeline : item))
    );
    return pipeline;
  }

  async function deletePipeline(id) {
    await pipelineApi.deletePipeline(id);
    setPipelines((items) => items.filter((item) => item.id !== id));
  }

  const [nextId, setNextId] = useState(7);
  const [activeEntryId, setActiveEntryId] = useState(1);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);

  // Form state for the ingestion creation page.
  const [form, setForm] = useState({ connector: "", mapper: "", rules: "", outputs: "", order_type: "", order_number: "" });

  // Displays a brief success or status message near the bottom of the screen.
  const showToast = (msg) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2200);
  };

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  useEffect(() => {
    const storedTheme = localStorage.getItem("theme");
    if (storedTheme === "dark" || storedTheme === "light") {
      setThemeMode(storedTheme);
    }
  }, []);

  useEffect(() => {
    const theme = themeMode === "dark" ? DARK_THEME : LIGHT_THEME;
    Object.entries(theme).forEach(([key, value]) => {
      document.documentElement.style.setProperty(`--${key}`, value);
    });
    localStorage.setItem("theme", themeMode);
  }, [themeMode]);

  // Auth initialization
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      fetch(`${API_BASE}/api/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      })
        .then((r) => {
          if (!r.ok) throw new Error("invalid token");
          return r.json();
        })
        .then((data) => {
          setAuthenticated(true);
          setCurrentUser(data.username);
        })
        .catch(() => {
          localStorage.removeItem("auth_token");
          setAuthenticated(false);
          setCurrentUser(null);
        });
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Load configuration from the backend on mount.
  // ---------------------------------------------------------------------------
  const fetchConfig = async () => {
    setConfigLoading(true);
    try {
      const [connRes, rulesRes, outputsRes] = await Promise.all([
        fetch(`${API_BASE}/api/config/connectors`),
        fetch(`${API_BASE}/api/config/rules`),
        fetch(`${API_BASE}/api/config/outputs`),
      ]);
      const [connectors, rules, outputs] = await Promise.all([
        connRes.json(),
        rulesRes.json(),
        outputsRes.json(),
      ]);
      setConfig({ connectors, rules, outputs });
    } catch {
      showToast("Unable to load configuration from the backend.");
    } finally {
      setConfigLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // ---------------------------------------------------------------------------
  // Load history from the backend on mount.
  // ---------------------------------------------------------------------------
  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch {
      // silently fail - history just stays empty
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  // ---------------------------------------------------------------------------
  // Navigation helpers
  // ---------------------------------------------------------------------------

  const toggleSidebar = () => setIsSidebarOpen((prev) => !prev);
  const closeSidebar = () => setIsSidebarOpen(false);

  const signOut = () => {
    setAuthenticated(false);
    setCurrentUser(null);
    localStorage.removeItem("auth_token");
    goTo("dashboard");
  };

  const goTo = (p) => {
    setPage(p);
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  const openEntry = (id) => {
    setActiveEntryId(id);
    goTo("entry");
  };

  const deleteEntry = async (id) => {
    try {
      await fetch(`${API_BASE}/api/history/${id}`, { method: "DELETE" });
    } catch {
      // best-effort - remove from UI regardless
    }
    setHistory((h) => h.filter((e) => e.id !== id));
    showToast(`Entry ${id} deleted`);
  };

  // ---------------------------------------------------------------------------
  // Config mutation helpers - talk to the backend, then refresh local state.
  // ---------------------------------------------------------------------------

  const KEY_TO_PATH = {
    connectors: "connectors",
    rules: "rules",
    outputs: "outputs",
  };

  const addRow = async (key, name) => {
    try {
      const res = await fetch(`${API_BASE}/api/config/${KEY_TO_PATH[key]}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showToast(body.detail || "Failed to add item.");
        return;
      }
      const newItem = await res.json();
      setConfig((c) => ({ ...c, [key]: [...c[key], newItem] }));
      showToast(`"${newItem.name}" added.`);
    } catch {
      showToast("Network error - could not add item.");
    }
  };

  const removeConfigRow = async (key, id, name) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/config/${KEY_TO_PATH[key]}/${id}`,
        {
          method: "DELETE",
        }
      );
      if (!res.ok && res.status !== 404) {
        showToast("Failed to delete item.");
        return;
      }
      setConfig((c) => ({
        ...c,
        [key]: c[key].filter((item) => item.id !== id),
      }));
      showToast(`"${name}" deleted.`);
    } catch {
      showToast("Network error - could not delete item.");
    }
  };

  // ---------------------------------------------------------------------------
  // Ingestion submission
  // ---------------------------------------------------------------------------

  const startIngestion = async (options = {}) => {
    try {
      const response = await fetch(`${API_BASE}/api/ingest/local-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connector: form.connector,
          rule: form.rules,
          mapper: form.mapper,
          outputs: form.outputs,
          ...(form.connector.toLowerCase().includes("infor") ? {
            order_type: form.order_type,
            order_number: form.order_number.trim(),
          } : {}),
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(Array.isArray(errData.detail)
          ? errData.detail.map((error) => error.msg).join("; ")
          : errData.detail || "Ingestion request failed");
      }

      const data = await response.json();

      // Refresh history from the backend so it persists across reloads
      await fetchHistory();

      if (data.message) {
        showToast(data.message);
      } else {
        showToast(
          `Ingestion complete - ${data.processed} document(s) processed`
        );
      }

      setForm({ connector: "", mapper: "", rules: "", outputs: "", order_type: "", order_number: "" });
      goTo("dashboard");
    } catch (error) {
      if (options.onError) {
        options.onError(error.message);
      } else {
        showToast(error.message || "Ingestion failed. Please try again.");
      }
      throw error;
    }
  };

  const activeEntry = history.find((e) => e.id === activeEntryId) || history[0];

  if (!authenticated) {
    return (
      <Login
        onLogin={(username) => {
          setAuthenticated(true);
          setCurrentUser(username);
        }}
      />
    );
  }

  return (
    <div
      style={{
        background: COLORS.bg,
        fontFamily: FONTS.body,
        height: "100dvh",
        overflow: "hidden",
      }}
    >
      <style>{`
        ${GOOGLE_FONTS_IMPORT}
        body { margin: 0; }
        select:focus { outline: none; border-color: ${COLORS.blue} !important; }
      `}</style>

      <div
        className="flex h-full overflow-hidden relative"
        style={{ background: COLORS.bg }}
      >
        {isSidebarOpen && (
          <div
            className="fixed inset-0 z-20 bg-black/30 transition-opacity duration-200 md:hidden"
            onClick={closeSidebar}
          />
        )}

        <div className="fixed inset-y-0 left-0 z-30 md:static md:shrink-0 h-full">
          {isSidebarOpen ? (
            <Sidebar
              page={page}
              goTo={goTo}
              user={currentUser}
              onSignOut={signOut}
              onClose={closeSidebar}
            />
          ) : null}
        </div>

        <div className="flex flex-col flex-1 min-w-0 min-h-0">
          <Header
            notificationCount={3}
            onToggleSidebar={toggleSidebar}
            onOpenSettings={() => goTo("settings")}
            themeMode={themeMode}
            onToggleTheme={() =>
              setThemeMode((prev) => (prev === "dark" ? "light" : "dark"))
            }
          />

          <div
            ref={contentRef}
            role="main"
            aria-label="Page content"
            className="flex-1 min-h-0 overflow-y-auto p-4 md:p-6"
          >
            {page === "dashboard" && (
              <Dashboard
                history={history}
                config={config}
                goTo={goTo}
                openEntry={openEntry}
              />
            )}
            {page === "ingest" && (
              <NewIngestion
                form={form}
                setForm={setForm}
                config={config}
                onStart={startIngestion}
              />
            )}
            {page === "configure" && (
              <Configure
                config={config}
                configLoading={configLoading}
                addRow={addRow}
                removeConfigRow={removeConfigRow}
                pipelines={pipelines}
                pipelinesLoading={pipelinesLoading}
                pipelinesError={pipelinesError}
                onRetryPipelines={fetchPipelines}
                onCreatePipeline={createPipeline}
                onUpdatePipeline={updatePipeline}
                onDeletePipeline={deletePipeline}
              />
            )}
            {page === "settings" && (
              <Settings
                token={localStorage.getItem("auth_token")}
                currentUser={currentUser}
                onSaved={(username) => setCurrentUser(username)}
                goTo={goTo}
              />
            )}
            {page === "change-username" && (
              <ChangeUsername
                token={localStorage.getItem("auth_token")}
                currentUser={currentUser}
                onSaved={(username) => setCurrentUser(username)}
                goTo={goTo}
              />
            )}
            {page === "history" && (
              <History
                history={history}
                openEntry={openEntry}
                deleteEntry={deleteEntry}
              />
            )}
            {page === "entry" && (
              <EntryDetail entry={activeEntry} goTo={goTo} />
            )}
          </div>
        </div>
      </div>

      <Toast message={toast} />
    </div>
  );
}
