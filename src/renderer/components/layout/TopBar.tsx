import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useSystemStore } from '../../stores/systemStore'
import { Circle } from 'lucide-react'

const routeTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/projects': 'Projects',
  '/settings': 'Settings'
}

export function TopBar() {
  const location = useLocation()
  const { backendStatus, ollamaStatus, checkHealth } = useSystemStore()

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const title = routeTitles[location.pathname] || 'Project Workspace'

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-800 bg-gray-900/30 px-6">
      <h1 className="text-lg font-semibold text-white">{title}</h1>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-xs">
          <StatusDot active={backendStatus === 'connected'} />
          <span className="text-gray-400">Backend</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <StatusDot active={ollamaStatus === 'connected'} />
          <span className="text-gray-400">Ollama</span>
        </div>
      </div>
    </header>
  )
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <Circle
      className={`h-2 w-2 ${active ? 'fill-emerald-500 text-emerald-500' : 'fill-red-500 text-red-500'}`}
    />
  )
}
