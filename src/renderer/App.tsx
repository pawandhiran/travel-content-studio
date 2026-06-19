import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { Dashboard } from './routes/Dashboard'
import { ProjectList } from './routes/ProjectList'
import { ProjectWorkspace } from './routes/ProjectWorkspace'
import { Settings } from './routes/Settings'
import { Setup } from './routes/Setup'
import { wsClient } from './services/websocketClient'
import { useJobStore } from './stores/jobStore'

export default function App() {
  useEffect(() => {
    wsClient.connect()

    const offProgress = wsClient.on('job.progress', (data) => {
      useJobStore.getState().updateJobFromEvent(data as { id: string })
    })
    const offCompleted = wsClient.on('job.completed', (data) => {
      useJobStore.getState().updateJobFromEvent(data as { id: string })
    })
    const offFailed = wsClient.on('job.failed', (data) => {
      useJobStore.getState().updateJobFromEvent(data as { id: string })
    })

    return () => {
      offProgress()
      offCompleted()
      offFailed()
      wsClient.disconnect()
    }
  }, [])

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects" element={<ProjectList />} />
        <Route path="/projects/:id/*" element={<ProjectWorkspace />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
