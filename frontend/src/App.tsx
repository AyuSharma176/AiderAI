import { Navigate, Route, Routes } from "react-router-dom";

import { AuthPage } from "./auth/AuthPage";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { DashboardLayout } from "./layout/DashboardLayout";

function Placeholder({ title, description }: { title: string; description: string }) {
  return <section className="page"><p className="eyebrow">Workspace</p><h1>{title}</h1><p className="muted">{description}</p></section>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/chat" element={<Placeholder title="Support chat" description="Ask a question or take action for a customer." />} />
          <Route path="/conversations" element={<Placeholder title="Conversations" description="Return to a previous support thread." />} />
          <Route path="/knowledge" element={<Placeholder title="Knowledge base" description="Manage the documents that ground AI answers." />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
