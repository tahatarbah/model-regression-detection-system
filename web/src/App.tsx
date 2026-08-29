import { NavLink, Route, Routes } from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import RunsPage from "./pages/RunsPage";
import RunDetailPage from "./pages/RunDetailPage";
import ComparePage from "./pages/ComparePage";
import SuitesPage from "./pages/SuitesPage";

export default function App() {
  return (
    <div className="shell">
      <nav className="nav">
        <NavLink to="/" className="brand" end>
          MRDS
        </NavLink>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Overview
        </NavLink>
        <NavLink to="/runs" className={({ isActive }) => (isActive ? "active" : "")}>
          Runs
        </NavLink>
        <NavLink to="/compare" className={({ isActive }) => (isActive ? "active" : "")}>
          Compare
        </NavLink>
        <NavLink to="/suites" className={({ isActive }) => (isActive ? "active" : "")}>
          Suites
        </NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/suites" element={<SuitesPage />} />
      </Routes>
    </div>
  );
}
