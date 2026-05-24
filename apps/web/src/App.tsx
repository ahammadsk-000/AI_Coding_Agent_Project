import { Navigate, Route, Routes } from "react-router-dom";

import { LoginPage } from "@/routes/login";
import { RegisterPage } from "@/routes/register";
import { DashboardPage } from "@/routes/dashboard";
import { RepositoriesPage } from "@/routes/repositories";
import { RepositoryDetailPage } from "@/routes/repository-detail";
import { SearchPage } from "@/routes/search";
import { ChatPage } from "@/routes/chat";
import { MemoryPage } from "@/routes/memory";
import { SandboxPage } from "@/routes/sandbox";
import { GitHubPage } from "@/routes/github";
import { RequireAuth } from "@/components/layout/require-auth";
import { AppShell } from "@/components/layout/shell";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/repositories" element={<RepositoriesPage />} />
        <Route path="/repositories/:id" element={<RepositoryDetailPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:id" element={<ChatPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/sandbox" element={<SandboxPage />} />
        <Route path="/github" element={<GitHubPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
