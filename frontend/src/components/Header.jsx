import {
  Satellite,
  Search,
  Bell,
  Circle
} from "lucide-react";

export default function Header() {
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
        <button className="active">Overview</button>
        <button>Orbital Map</button>
        <button>Conjunctions</button>
        <button>Objects</button>
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