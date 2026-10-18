import { useState, useEffect, useRef } from "react";
import {
  Satellite,
  Search,
  Bell,
  Circle,
  LogOut,
  X,
  BookOpen,
  User,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { getObjects, getConjunctions, logoutUser } from "../api";

export default function Header() {
  const navigate = useNavigate();

  // Search state
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [allObjects, setAllObjects] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef(null);

  // Notification state
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const notifRef = useRef(null);

  // Load objects for search when panel opens
  useEffect(() => {
    if (!searchOpen || allObjects.length > 0) return;
    setSearchLoading(true);
    getObjects("stations", 50)
      .then((data) => setAllObjects(data.objects || []))
      .catch(() => {})
      .finally(() => setSearchLoading(false));
  }, [searchOpen, allObjects.length]);

  // Filter results
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const q = searchQuery.toLowerCase();
    setSearchResults(
      allObjects
        .filter(
          (o) =>
            o.name.toLowerCase().includes(q) ||
            String(o.norad_id).includes(q)
        )
        .slice(0, 8)
    );
  }, [searchQuery, allObjects]);

  // Load notifications (top conjunctions)
  useEffect(() => {
    if (!notifOpen || notifications.length > 0) return;
    getConjunctions("stations", 30, 5)
      .then((data) => {
        const items = (data.conjunctions || []).slice(0, 5).map((c) => ({
          title: `${c.object_1.name} ↔ ${c.object_2.name}`,
          detail: `${c.distance_km} km miss · ${c.risk_level} risk`,
          link: `/conjunctions/${c.object_1.norad_id}/${c.object_2.norad_id}`,
          risk: c.risk_level,
        }));
        setNotifications(
          items.length > 0
            ? items
            : [{ title: "No active conjunctions", detail: "All clear within 5 km threshold", link: "/conjunctions" }]
        );
      })
      .catch(() =>
        setNotifications([
          {
            title: "Conjunction data unavailable",
            detail: "Backend unreachable",
            link: "/conjunctions",
          },
        ])
      );
  }, [notifOpen, notifications.length]);

  // Close panels on outside click
  useEffect(() => {
    function handler(e) {
      if (searchRef.current && !searchRef.current.contains(e.target))
        setSearchOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target))
        setNotifOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleSearchKey(e) {
    if (e.key === "Escape") {
      setSearchOpen(false);
      setSearchQuery("");
    }
  }

  function handleLogout() {
    logoutUser();
    navigate("/login", { replace: true });
  }

  function selectResult(obj) {
    setSearchOpen(false);
    setSearchQuery("");
    navigate(`/objects/${obj.norad_id}`);
  }

  return (
    <header className="header">
      <div className="brand">
        <div className="brand-icon">
          <Satellite size={20} />
        </div>
        <div>
          <h1>OrbitGuard</h1>
          <span>ORBITAL COLLISION RISK MONITORING</span>
        </div>
      </div>

      <nav className="navigation">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Overview
        </NavLink>
        <NavLink to="/orbital-map" className={({ isActive }) => (isActive ? "active" : "")}>
          Orbital Map
        </NavLink>
        <NavLink to="/conjunctions" className={({ isActive }) => (isActive ? "active" : "")}>
          Conjunctions
        </NavLink>
        <NavLink to="/objects" className={({ isActive }) => (isActive ? "active" : "")}>
          Objects
        </NavLink>
        <NavLink to="/learn" className={({ isActive }) => (isActive ? "active" : "")}>
          <BookOpen size={13} style={{ verticalAlign: "middle", marginRight: 4 }} />
          Academy
        </NavLink>
      </nav>

      <div className="header-actions">
        {/* SEARCH */}
        <div className="header-panel-wrap" ref={searchRef}>
          <button
            className="icon-button"
            onClick={() => { setSearchOpen((v) => !v); setNotifOpen(false); }}
            aria-label="Search satellites"
          >
            <Search size={18} />
          </button>

          {searchOpen && (
            <div className="header-panel search-panel">
              <div className="search-input-row">
                <Search size={15} />
                <input
                  autoFocus
                  placeholder="Search by name or NORAD ID…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleSearchKey}
                />
                <button onClick={() => { setSearchOpen(false); setSearchQuery(""); }}>
                  <X size={14} />
                </button>
              </div>
              {searchLoading && <p className="panel-hint">Loading objects…</p>}
              {!searchLoading && searchQuery && searchResults.length === 0 && (
                <p className="panel-hint">No results for "{searchQuery}"</p>
              )}
              {searchResults.map((obj) => (
                <button
                  key={obj.norad_id}
                  className="search-result"
                  onClick={() => selectResult(obj)}
                >
                  <span className="sr-name">{obj.name}</span>
                  <span className="sr-id">NORAD {obj.norad_id}</span>
                </button>
              ))}
              {!searchQuery && !searchLoading && (
                <p className="panel-hint">Type a satellite name or NORAD ID</p>
              )}
            </div>
          )}
        </div>

        {/* NOTIFICATIONS */}
        <div className="header-panel-wrap" ref={notifRef}>
          <button
            className="icon-button notification"
            onClick={() => { setNotifOpen((v) => !v); setSearchOpen(false); }}
            aria-label="Conjunction notifications"
          >
            <Bell size={18} />
            <span />
          </button>

          {notifOpen && (
            <div className="header-panel notif-panel">
              <div className="panel-header">
                <strong>CONJUNCTION ALERTS</strong>
                <span className="panel-sub">Within 5 km threshold</span>
              </div>
              {notifications.map((n, i) => (
                <NavLink
                  key={i}
                  to={n.link}
                  className={`notif-item risk-${(n.risk || "low").toLowerCase()}`}
                  onClick={() => setNotifOpen(false)}
                >
                  <span className="notif-title">{n.title}</span>
                  <span className="notif-detail">{n.detail}</span>
                </NavLink>
              ))}
            </div>
          )}
        </div>

        <div className="system-status">
          <Circle size={8} fill="currentColor" />
          SYSTEM ONLINE
        </div>

        {/* LOGOUT */}
        <button
          className="icon-button logout-btn"
          onClick={handleLogout}
          aria-label="Log out"
          title="Log out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  );
}