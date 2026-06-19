import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderOpen,
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
  Wand2
} from 'lucide-react'

const navItems = [
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

  return (
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

      <div className="border-t border-gray-800 p-3">
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
      </div>
    </aside>
  )
}
