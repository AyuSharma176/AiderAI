import { Navigate, Route, Routes } from "react-router-dom";

import { AuthPage } from "./auth/AuthPage";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ChatPage } from "./chat/ChatPage";
import { ConversationList } from "./conversations/ConversationList";
import { DocumentsPage } from "./documents/DocumentsPage";
import { DashboardLayout } from "./layout/DashboardLayout";
import { OrderDetailPage } from "./orders/OrderDetailPage";
import { OrdersPage } from "./orders/OrdersPage";

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
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/conversations" element={<ConversationList />} />
          <Route path="/knowledge" element={<DocumentsPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
