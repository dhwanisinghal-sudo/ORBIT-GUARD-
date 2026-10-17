import {
  Satellite,
  Search,
  Bell,
  Circle
} from "lucide-react";

import { NavLink } from "react-router-dom";

export default function Header() {
  return (
    <header className="header">

      <div className="brand">

        <div className="brand-icon">
          <Satellite size={20} />
        </div>

        <div>
          <h1>OrbitGuard</h1>
          <span>
            ORBITAL COLLISION RISK MONITORING
          </span>
        </div>

      </div>

      <nav className="navigation">

        <NavLink
          to="/"
          className={({ isActive }) =>
            isActive ? "active" : ""
          }
        >
          Overview
        </NavLink>

        <NavLink
          to="/orbital-map"
          className={({ isActive }) =>
            isActive ? "active" : ""
          }
        >
          Orbital Map
        </NavLink>

        <NavLink
          to="/conjunctions"
          className={({ isActive }) =>
            isActive ? "active" : ""
          }
        >
          Conjunctions
        </NavLink>

        <NavLink
          to="/objects"
          className={({ isActive }) =>
            isActive ? "active" : ""
          }
        >
          Objects
        </NavLink>

      </nav>

      <div className="header-actions">

        <button className="icon-button">
          <Search size={18} />
        </button>

        <button className="icon-button notification">
          <Bell size={18} />
          <span></span>
        </button>

        <div className="system-status">
          <Circle size={8} fill="currentColor" />
          SYSTEM ONLINE
        </div>

      </div>

    </header>
  );
}