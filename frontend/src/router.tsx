import { createBrowserRouter, Navigate } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import Market from "./pages/Market";
import Strategies from "./pages/Strategies";
import Trading from "./pages/Trading";
import Positions from "./pages/Positions";
import History from "./pages/History";
import AiReports from "./pages/AiReports";
import RiskSettings from "./pages/RiskSettings";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import NotFound from "./pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "market", element: <Market /> },
      { path: "strategies", element: <Strategies /> },
      { path: "trading", element: <Trading /> },
      { path: "positions", element: <Positions /> },
      { path: "history", element: <History /> },
      { path: "ai-reports", element: <AiReports /> },
      { path: "risk-settings", element: <RiskSettings /> },
      { path: "settings", element: <Settings /> },
      { path: "logs", element: <Logs /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
