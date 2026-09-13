import { BrowserRouter, Routes, Route } from "react-router-dom";

import Header from "./components/Header";

import Overview from "./pages/Overview";
import OrbitalMap from "./pages/OrbitalMap";
import Conjunctions from "./pages/Conjunctions";
import Objects from "./pages/Objects";
import ObjectDetails from "./pages/ObjectDetails";
import ConjunctionAnalysis from "./pages/ConjunctionAnalysis";

import "./App.css";

function App() {
  return (
    <BrowserRouter>

      <div className="app">

        <Header />

        <Routes>
          <Route
            path="/conjunctions/:object1Id/:object2Id"
            element={<ConjunctionAnalysis />}
          />

          <Route path="/" element={<Overview />} />

          <Route path="/orbital-map" element={<OrbitalMap />} />

          <Route path="/conjunctions" element={<Conjunctions />} />

          <Route path="/objects" element={<Objects />} />

          <Route
            path="/objects/:noradId"
            element={<ObjectDetails />}
          />

        </Routes>

      </div>

    </BrowserRouter>
  );
}

export default App;