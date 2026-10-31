import clsx from "clsx";
import { Activity, BarChart3, Gauge, Handshake, SlidersHorizontal } from "lucide-react";
import { NavLink, Route, Routes } from "react-router-dom";
import HeaderBanner from "./components/HeaderBanner";
import SidebarControls from "./components/SidebarControls";
import TickerFooter from "./components/TickerFooter";
import { WarningBanner } from "./components/ui";
import { useExperiment } from "./context/ExperimentContext";
import BenchmarksReportsPage from "./pages/BenchmarksReportsPage";
import CommandCenterPage from "./pages/CommandCenterPage";
import HandshakeInspectorPage from "./pages/HandshakeInspectorPage";
import PolicyCalibrationPage from "./pages/PolicyCalibrationPage";
import WorkloadsDatasetsPage from "./pages/WorkloadsDatasetsPage";

const TABS = [
  { to: "/", label: "Command Center", icon: Gauge },
  { to: "/policy", label: "Policy Calibration", icon: SlidersHorizontal },
  { to: "/handshake", label: "Handshake Inspector", icon: Handshake },
  { to: "/workloads", label: "Workloads & Datasets", icon: Activity },
  { to: "/reports", label: "Benchmarks & Reports", icon: BarChart3 },
];

export default function App() {
  const { healthError, health } = useExperiment();
  return (
    <div className="flex h-full flex-col">
      <HeaderBanner />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <SidebarControls />
        <div className="flex min-w-0 shrink-0 flex-col lg:min-h-0 lg:flex-1 lg:shrink">
          <nav className="flex gap-1 overflow-x-auto border-b border-acid-muted px-3 pt-2" aria-label="Main">
            {TABS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-2 whitespace-nowrap rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors",
                    isActive ? "border-acid text-ink" : "border-transparent text-ink-muted hover:text-ink",
                  )
                }
              >
                <Icon size={15} aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
          <main className="min-h-0 flex-1 space-y-4 p-4 lg:overflow-y-auto">
            {healthError && <WarningBanner>{healthError}</WarningBanner>}
            {health && !health.benchmarks_loaded && (
              <WarningBanner>
                No benchmark profile exists yet, so decisions cannot be computed. Run one on the Benchmarks &amp; Reports tab.
              </WarningBanner>
            )}
            <Routes>
              <Route path="/" element={<CommandCenterPage />} />
              <Route path="/policy" element={<PolicyCalibrationPage />} />
              <Route path="/handshake" element={<HandshakeInspectorPage />} />
              <Route path="/workloads" element={<WorkloadsDatasetsPage />} />
              <Route path="/reports" element={<BenchmarksReportsPage />} />
            </Routes>
          </main>
        </div>
      </div>
      <TickerFooter />
    </div>
  );
}
