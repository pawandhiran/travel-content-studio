import { useLocation } from 'react-router-dom'
import { ChatPanel } from '../components/chat/ChatPanel'

export function Chat() {
  const location = useLocation()
  const projectMatch = location.pathname.match(/\/projects\/([^/]+)/)
  const projectId = projectMatch?.[1] ?? undefined

  return (
    <div className="h-full">
      <ChatPanel projectId={projectId} />
    </div>
  )
}
