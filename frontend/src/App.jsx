
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
} from "react-router-dom";

import Header from "./components/Header";
import Overview from "./pages/Overview";
import OrbitalMap from "./pages/OrbitalMap";
import Conjunctions from "./pages/Conjunctions";
import Objects from "./pages/Objects";
import ObjectDetails from "./pages/ObjectDetails";
import ConjunctionAnalysis from "./pages/ConjunctionAnalysis";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Learn from "./pages/Learn";
import Lesson from "./pages/Lesson";
import Landing from "./pages/Landing";

import {
  getCurrentUser,
  isLoggedIn,
  logoutUser,
} from "./api";

import "./App.css";

function DashboardLayout() {
  return (
    <div className="app">
      <Header />
      <Outlet />
    </div>
  );
}

function AppRoutes({ user, setUser, checkingSession }) {
  if (checkingSession) {
    return (
      <div className="app-loading">
        <div className="app-loading-orbit" />
        <p>Initializing OrbitGuard...</p>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={
          user ? (
            <Navigate to="/" replace />
          ) : (
            <Login onAuthSuccess={setUser} />
          )
        }
      />

      <Route
        path="/register"
        element={
          user ? (
            <Navigate to="/" replace />
          ) : (
            <Register onAuthSuccess={setUser} />
          )
        }
      />

      <Route
        element={
          user ? (
            <DashboardLayout />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      >
        <Route path="/" element={<Overview />} />
        <Route path="/orbital-map" element={<OrbitalMap />} />
        <Route path="/conjunctions" element={<Conjunctions />} />
        <Route
          path="/conjunctions/:object1Id/:object2Id"
          element={<ConjunctionAnalysis />}
        />
        <Route path="/objects" element={<Objects />} />
        <Route path="/objects/:noradId" element={<ObjectDetails />} />
        <Route path="/learn" element={<Learn />} />
        <Route path="/learn/:lessonId" element={<Lesson />} />
      </Route>

      {/* Public landing page */}
      <Route path="/landing" element={<Landing />} />

      <Route
        path="*"
        element={<Navigate to={user ? "/" : "/login"} replace />}
      />
    </Routes>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let active = true;

    async function restoreSession() {
      if (!isLoggedIn()) {
        if (active) setCheckingSession(false);
        return;
      }

      try {
        const currentUser = await getCurrentUser();
        if (active) setUser(currentUser);
      } catch {
        logoutUser();
        if (active) setUser(null);
      } finally {
        if (active) setCheckingSession(false);
      }
    }

    restoreSession();

    return () => {
      active = false;
    };
  }, []);

  return (
    <BrowserRouter>
      <AppRoutes
        user={user}
        setUser={setUser}
        checkingSession={checkingSession}
      />
    </BrowserRouter>
  );
}

export default App;
