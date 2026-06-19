import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderOpen,
  MessageSquare,
  Settings,
  Video,
  FileText,
  Image,
  Mic,
  BookOpen,
  Film,
  Youtube,
  Bot,
  Camera,
  Wand2,
  Power,
  Check,
  Loader2
} from 'lucide-react'

const navItems = [
  { icon: MessageSquare, label: 'AI Assistant', path: '/chat' },
  { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
  { icon: FolderOpen, label: 'Projects', path: '/projects' }
]

const studioItems = [
  { icon: Video, label: 'Videos', path: 'videos' },
  { icon: Wand2, label: 'Video Editing', path: 'editing' },
  { icon: FileText, label: 'Transcripts', path: 'transcripts' },
  { icon: Bot, label: 'AI Content', path: 'content' },
  { icon: Camera, label: 'Insta360', path: 'insta360' },
  { icon: BookOpen, label: 'Stories', path: 'stories' },
  { icon: Film, label: 'Reels', path: 'reels' },
  { icon: Youtube, label: 'YouTube', path: 'youtube' },
  { icon: Image, label: 'Thumbnails', path: 'thumbnails' },
  { icon: Mic, label: 'Voiceover', path: 'voiceover' },
  { icon: BookOpen, label: 'Blog', path: 'blog' },
  { icon: Bot, label: 'Travel Agents', path: 'agents' },
  { icon: Camera, label: 'Stock Photos', path: 'stock-photos' }
]

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const isProjectOpen = location.pathname.startsWith('/projects/')
  const projectId = isProjectOpen ? location.pathname.split('/')[2] : null

  const [showConfirm, setShowConfirm] = useState(false)
  const [shutdownState, setShutdownState] = useState<
    null | { phase: 'saving' | 'ai' | 'backend' | 'done' }
  >(null)

  useEffect(() => {
    const api = (window as any).api
    if (!api?.onAppClosing) return
    api.onAppClosing(() => {
      setShowConfirm(true)
    })
  }, [])

  async function handleStopApp() {
    setShowConfirm(false)
    setShutdownState({ phase: 'saving' })

    await new Promise((r) => setTimeout(r, 400))
    setShutdownState({ phase: 'backend' })

    await new Promise((r) => setTimeout(r, 300))
    setShutdownState({ phase: 'ai' })

    const api = (window as any).api
    if (api?.stopApp) {
      await api.stopApp()
    }

    setShutdownState({ phase: 'done' })
  }

  return (
    <>
      <aside className="flex w-60 flex-col border-r border-gray-800 bg-gray-900/50">
        <div className="flex h-14 items-center gap-2 border-b border-gray-800 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
            <Video className="h-4 w-4 text-white" />
          </div>
          <span className="text-sm font-semibold text-white">Travel Studio</span>
        </div>

        <nav className="flex-1 overflow-y-auto p-3">
          <div className="space-y-1">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? 'bg-brand-600/20 text-brand-400'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </button>
              )
            })}
          </div>

          {isProjectOpen && projectId && (
            <>
              <div className="my-4 border-t border-gray-800" />
              <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                Workspace
              </p>
              <div className="space-y-1">
                {studioItems.map((item) => {
                  const fullPath = `/projects/${projectId}/${item.path}`
                  const isActive = location.pathname === fullPath
                  return (
                    <button
                      key={item.path}
                      onClick={() => navigate(fullPath)}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-brand-600/20 text-brand-400'
                          : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                      }`}
                    >
                      <item.icon className="h-4 w-4" />
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </nav>

        <div className="border-t border-gray-800 p-3 space-y-1">
          <button
            onClick={() => navigate('/logs')}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              location.pathname === '/logs'
                ? 'bg-brand-600/20 text-brand-400'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            <FileText className="h-4 w-4" />
            Logs
          </button>
          <button
            onClick={() => navigate('/settings')}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              location.pathname === '/settings'
                ? 'bg-brand-600/20 text-brand-400'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>
          <button
            onClick={() => setShowConfirm(true)}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-red-400 hover:bg-red-900/20 transition-colors"
          >
            <Power className="h-4 w-4" />
            Stop App
          </button>
        </div>
      </aside>

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-80 rounded-xl bg-gray-900 border border-gray-700 p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white mb-2">Stop Travel Content Studio?</h3>
            <p className="text-sm text-gray-400 mb-5">
              This will shut down all services including the AI engine and backend.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowConfirm(false)}
                className="rounded-lg px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStopApp}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
              >
                Stop
              </button>
            </div>
          </div>
        </div>
      )}

      {shutdownState && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="w-72 rounded-xl bg-gray-900 border border-gray-700 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-4">Shutting down...</h3>
            <ul className="space-y-2 text-sm">
              <ShutdownStep
                label="Saving work..."
                done={shutdownState.phase !== 'saving'}
                active={shutdownState.phase === 'saving'}
              />
              <ShutdownStep
                label="Stopping backend..."
                done={shutdownState.phase === 'ai' || shutdownState.phase === 'done'}
                active={shutdownState.phase === 'backend'}
              />
              <ShutdownStep
                label="Stopping AI engine..."
                done={shutdownState.phase === 'done'}
                active={shutdownState.phase === 'ai'}
              />
              <ShutdownStep
                label="Done. App will close."
                done={shutdownState.phase === 'done'}
                active={false}
              />
            </ul>
          </div>
        </div>
      )}
    </>
  )
}

function ShutdownStep({ label, done, active }: { label: string; done: boolean; active: boolean }) {
  return (
    <li className={`flex items-center gap-2 ${done ? 'text-green-400' : active ? 'text-gray-200' : 'text-gray-500'}`}>
      {done ? (
        <Check className="h-4 w-4 text-green-400" />
      ) : active ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <div className="h-4 w-4" />
      )}
      {label}
    </li>
  )
}
