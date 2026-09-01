import { Route, Routes } from 'react-router-dom'
import { AppShell } from './app-shell/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { EpisodeStudioPage } from './pages/EpisodeStudioPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { AssetGenerationPage } from './pages/AssetGenerationPage'
import { SettingsPage } from './pages/SettingsPage'
import { VideoEntryPage } from './pages/VideoEntryPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<ProjectsPage />} />
        <Route path="projects/:projectName" element={<DashboardPage />} />
        <Route path="projects/:projectName/assets" element={<AssetGenerationPage />} />
        <Route path="projects/:projectName/video" element={<VideoEntryPage />} />
        <Route path="projects/:projectName/settings" element={<SettingsPage />} />
        <Route path="projects/:projectName/episodes/:episodeId" element={<EpisodeStudioPage />} />
      </Route>
    </Routes>
  )
}
