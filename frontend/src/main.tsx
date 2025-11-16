import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import DashboardLayout from './components/Dashboard/DashboardLayout.tsx'
import ProjectsPage from './pages/ProjectsPage.tsx'
import AgentsPage from './pages/AgentsPage.tsx'
import JournalBlocksPage from './pages/JournalBlocksPage.tsx'
import ToolsPage from './pages/ToolsPage.tsx'
import TerminalPage from './pages/TerminalPage.tsx'
import CodingPage from './pages/CodingPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Chat view (original 3-panel layout) */}
        <Route path="/chat" element={<App />} />

        {/* Dashboard with sidebar */}
        <Route path="/" element={<DashboardLayout />}>
          <Route index element={<Navigate to="/projects" replace />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="journal-blocks" element={<JournalBlocksPage />} />
          <Route path="tools" element={<ToolsPage />} />
          <Route path="terminal" element={<TerminalPage />} />
          <Route path="coding" element={<CodingPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
