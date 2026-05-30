import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import Login from './pages/Login.jsx';
import Register from './pages/Register.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Cameras from './pages/Cameras.jsx';
import CameraDetail from './pages/CameraDetail.jsx';
import Alerts from './pages/Alerts.jsx';
import AlertRules from './pages/AlertRules.jsx';
import Reports from './pages/Reports.jsx';
import Settings from './pages/Settings.jsx';
import AISettings from './pages/AISettings.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/cameras" element={<Cameras />} />
        <Route path="/cameras/:id" element={<CameraDetail />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/alerts/rules" element={<AlertRules />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/ai" element={<AISettings />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
