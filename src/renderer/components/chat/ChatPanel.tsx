import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  Send,
  Paperclip,
  Bot,
  User,
  Loader2,
  Image,
  Video,
  FileText,
  X,
  Sparkles,
  Settings,
  ThumbsUp,
  ThumbsDown,
  Trash2,
  Plus,
  Play,
  BookOpen,
  Brain,
  Zap,
  List,
  Hash,
  Copy,
  Check,
  RefreshCw,
  FolderOpen,
  Archive,
  Shield,
  Cpu
} from 'lucide-react'
import { apiClient } from '../../services/apiClient'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ActionTaken {
  tool: string
  args: Record<string, unknown>
  result: { status: string; data?: unknown; detail?: string }
}

interface ReviewResult {
  quality_score: number
  issues: string[]
  passed: boolean
  improved_reply?: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachments?: string[]
  directories?: string[]
  actions?: ActionTaken[]
  suggestions?: string[]
  timestamp: Date
  feedback?: 'up' | 'down'
  modelUsed?: string
  intent?: string
  review?: ReviewResult
}

interface ChatResponse {
  reply: string
  actions_taken: ActionTaken[]
  suggestions: string[]
  model_used?: string
  intent?: string
  review?: ReviewResult
}

interface Rule {
  id: string
  rule: string
  category: string
  created_at: string
}

interface Skill {
  id: string
  name: string
  description: string
  steps: { tool: string; args: Record<string, unknown> }[]
  built_in?: boolean
  created_at: string
}

interface HistoryStats {
  total_messages: number
  total_conversations: number
}

type SettingsTab = 'rules' | 'skills' | 'memory'

// ---------------------------------------------------------------------------
// Slash-command palette items
// ---------------------------------------------------------------------------

const SLASH_COMMANDS = [
  { command: '/rules', description: 'Show your active rules' },
  { command: '/skills', description: 'Show available skills' },
  { command: '/run ', description: 'Run a skill by name' },
  { command: '/remember ', description: 'Add a new rule' },
  { command: '/forget', description: 'Clear conversation history' }
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toolDisplayName(tool: string): string {
  return tool
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function extractReplyText(content: string): string {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) return content
  try {
    const parsed = JSON.parse(trimmed)
    if (typeof parsed.reply === 'string') return parsed.reply
    if (typeof parsed.error === 'string') return `Error: ${parsed.error}`
    if (typeof parsed.message === 'string') return parsed.message
  } catch {
    // not JSON -- check if it looks like a JSON-wrapped error string
    const match = trimmed.match(/"reply"\s*:\s*"((?:[^"\\]|\\.)*)"/);
    if (match) return match[1].replace(/\\"/g, '"').replace(/\\n/g, '\n')
  }
  return content
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AttachmentPreview({ path, onRemove, isDir }: { path: string; onRemove: () => void; isDir?: boolean }) {
  const filename = path.split('/').pop() || path
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'tiff', 'bmp'].includes(ext)
  const isVideo = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'].includes(ext)
  const isArchive = ['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)

  return (
    <div className="group flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/50 px-3 py-1.5 text-sm">
      {isDir && <FolderOpen className="h-3.5 w-3.5 text-amber-400" />}
      {!isDir && isImage && <Image className="h-3.5 w-3.5 text-emerald-400" />}
      {!isDir && isVideo && <Video className="h-3.5 w-3.5 text-blue-400" />}
      {!isDir && isArchive && <Archive className="h-3.5 w-3.5 text-purple-400" />}
      {!isDir && !isImage && !isVideo && !isArchive && <FileText className="h-3.5 w-3.5 text-gray-400" />}
      <span className="max-w-[150px] truncate text-gray-300">{isDir ? `${filename}/` : filename}</span>
      <button
        onClick={onRemove}
        className="text-gray-500 opacity-0 transition-opacity hover:text-gray-300 group-hover:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

function ActionChip({ action }: { action: ActionTaken }) {
  const [expanded, setExpanded] = useState(false)
  const chipRef = useRef<HTMLDivElement>(null)
  const success = action.result.status === 'success'

  useEffect(() => {
    if (!expanded) return
    const handler = (e: MouseEvent) => {
      if (!chipRef.current?.contains(e.target as Node)) {
        setExpanded(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [expanded])

  return (
    <div ref={chipRef} className="relative inline-block">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
          success
            ? 'bg-emerald-950/40 text-emerald-400 hover:bg-emerald-950/60'
            : 'bg-red-950/40 text-red-400 hover:bg-red-950/60'
        }`}
        title={`${toolDisplayName(action.tool)} - click for details`}
      >
        <Sparkles className="h-2.5 w-2.5" />
        {toolDisplayName(action.tool)}
        {success ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
      </button>
      {expanded && (
        <div className="absolute left-0 top-full z-20 mt-1 w-80 overflow-hidden rounded-lg border border-gray-700 bg-gray-900 shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-700 px-3 py-1.5">
            <span className={`text-xs font-medium ${success ? 'text-emerald-400' : 'text-red-400'}`}>
              {toolDisplayName(action.tool)}
            </span>
            <button onClick={() => setExpanded(false)} className="text-gray-500 hover:text-gray-300">
              <X className="h-3 w-3" />
            </button>
          </div>
          <div className="max-h-60 overflow-y-auto px-3 py-2 text-xs text-gray-400">
            <p className="font-medium text-gray-500">Arguments:</p>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(action.args, null, 2)}
            </pre>
            {action.result.data && (
              <>
                <p className="mt-2 font-medium text-gray-500">Result:</p>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(action.result.data, null, 2).slice(0, 500)}
                </pre>
              </>
            )}
            {action.result.detail && <p className="mt-2 text-red-400">{action.result.detail}</p>}
          </div>
        </div>
      )}
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="rounded p-1 text-gray-600 transition-colors hover:bg-gray-800 hover:text-gray-400"
      title="Copy text"
    >
      {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}

function FeedbackButtons({
  messageId,
  feedback,
  onFeedback
}: {
  messageId: string
  feedback?: 'up' | 'down'
  onFeedback: (id: string, rating: 'up' | 'down') => void
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onFeedback(messageId, 'up')}
        className={`rounded p-1 transition-colors ${
          feedback === 'up'
            ? 'bg-emerald-900/40 text-emerald-400'
            : 'text-gray-600 hover:bg-gray-800 hover:text-gray-400'
        }`}
        title="Good response"
      >
        <ThumbsUp className="h-3 w-3" />
      </button>
      <button
        onClick={() => onFeedback(messageId, 'down')}
        className={`rounded p-1 transition-colors ${
          feedback === 'down'
            ? 'bg-red-900/40 text-red-400'
            : 'text-gray-600 hover:bg-gray-800 hover:text-gray-400'
        }`}
        title="Bad response"
      >
        <ThumbsDown className="h-3 w-3" />
      </button>
    </div>
  )
}

function ReviewBadge({ review }: { review: ReviewResult }) {
  const passed = review.passed
  return (
    <div className={`mt-1 flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] ${
      passed ? 'bg-emerald-950/30 text-emerald-400' : 'bg-amber-950/30 text-amber-400'
    }`}>
      <Shield className="h-3 w-3" />
      <span>Quality: {review.quality_score}/10</span>
      {review.issues.length > 0 && (
        <span className="text-gray-500">- {review.issues[0]}</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Settings side-panel
// ---------------------------------------------------------------------------

function SettingsPanel({
  onClose,
  projectId
}: {
  onClose: () => void
  projectId?: string
}) {
  const [tab, setTab] = useState<SettingsTab>('rules')
  const [rules, setRules] = useState<Rule[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [stats, setStats] = useState<HistoryStats>({ total_messages: 0, total_conversations: 0 })
  const [newRule, setNewRule] = useState('')
  const [newRuleCategory, setNewRuleCategory] = useState('general')
  const [loading, setLoading] = useState(false)

  const loadRules = useCallback(async () => {
    try {
      const data = await apiClient.get<Rule[]>('/chat/rules')
      setRules(data)
    } catch {
      /* empty */
    }
  }, [])

  const loadSkills = useCallback(async () => {
    try {
      const data = await apiClient.get<Skill[]>('/chat/skills')
      setSkills(data)
    } catch {
      /* empty */
    }
  }, [])

  const loadStats = useCallback(async () => {
    try {
      const data = await apiClient.get<{ stats: HistoryStats }>('/chat/history')
      setStats(data.stats)
    } catch {
      /* empty */
    }
  }, [])

  useEffect(() => {
    loadRules()
    loadSkills()
    loadStats()
  }, [loadRules, loadSkills, loadStats])

  const handleAddRule = async () => {
    if (!newRule.trim()) return
    setLoading(true)
    try {
      await apiClient.post('/chat/rules', { rule: newRule, category: newRuleCategory })
      setNewRule('')
      await loadRules()
    } catch {
      /* empty */
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteRule = async (id: string) => {
    try {
      await apiClient.delete(`/chat/rules/${id}`)
      await loadRules()
    } catch {
      /* empty */
    }
  }

  const handleDeleteSkill = async (id: string) => {
    try {
      await apiClient.delete(`/chat/skills/${id}`)
      await loadSkills()
    } catch {
      /* empty */
    }
  }

  const handleRunSkill = async (id: string) => {
    try {
      await apiClient.post(`/chat/skills/${id}/run`, { project_id: projectId || null })
    } catch {
      /* empty */
    }
  }

  const handleClearHistory = async () => {
    try {
      await apiClient.delete('/chat/history')
      await loadStats()
    } catch {
      /* empty */
    }
  }

  const tabs: { key: SettingsTab; label: string; icon: typeof BookOpen }[] = [
    { key: 'rules', label: 'Rules', icon: BookOpen },
    { key: 'skills', label: 'Skills', icon: Zap },
    { key: 'memory', label: 'Memory', icon: Brain }
  ]

  return (
    <div className="flex h-full w-80 flex-col border-l border-gray-800 bg-gray-900/80">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
        <h3 className="text-sm font-semibold text-white">Chat Settings</h3>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-colors ${
              tab === t.key
                ? 'border-b-2 border-brand-500 text-brand-400'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'rules' && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              Rules are persistent instructions the AI follows in every conversation.
            </p>

            {/* Add rule form */}
            <div className="space-y-2">
              <textarea
                value={newRule}
                onChange={(e) => setNewRule(e.target.value)}
                placeholder='e.g., "Always use casual tone" or "My channel is TravelWithPawan"'
                rows={2}
                className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-600/50 focus:outline-none"
              />
              <div className="flex gap-2">
                <select
                  value={newRuleCategory}
                  onChange={(e) => setNewRuleCategory(e.target.value)}
                  className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:outline-none"
                >
                  <option value="general">General</option>
                  <option value="tone">Tone</option>
                  <option value="content">Content</option>
                  <option value="branding">Branding</option>
                  <option value="format">Format</option>
                </select>
                <button
                  onClick={handleAddRule}
                  disabled={!newRule.trim() || loading}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-brand-500 disabled:opacity-40"
                >
                  <Plus className="h-3 w-3" />
                  Add
                </button>
              </div>
            </div>

            {/* Rules list */}
            <div className="space-y-2">
              {rules.length === 0 && (
                <p className="text-center text-xs text-gray-600">No rules yet</p>
              )}
              {rules.map((r) => (
                <div
                  key={r.id}
                  className="group flex items-start gap-2 rounded-lg border border-gray-800 bg-gray-800/30 p-2.5"
                >
                  <Hash className="mt-0.5 h-3 w-3 shrink-0 text-brand-500" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-gray-300">{r.rule}</p>
                    <p className="mt-0.5 text-[10px] text-gray-600">{r.category}</p>
                  </div>
                  <button
                    onClick={() => handleDeleteRule(r.id)}
                    className="shrink-0 text-gray-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'skills' && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              Skills are reusable multi-step workflows. Run them on any project.
            </p>

            <div className="space-y-2">
              {skills.length === 0 && (
                <p className="text-center text-xs text-gray-600">No skills available</p>
              )}
              {skills.map((s) => (
                <div
                  key={s.id}
                  className="group rounded-lg border border-gray-800 bg-gray-800/30 p-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Zap className="h-3.5 w-3.5 text-amber-400" />
                      <span className="text-xs font-medium text-white">{s.name}</span>
                      {s.built_in && (
                        <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                          built-in
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={() => handleRunSkill(s.id)}
                        className="rounded p-1 text-gray-500 hover:bg-gray-700 hover:text-emerald-400"
                        title="Run this skill"
                      >
                        <Play className="h-3 w-3" />
                      </button>
                      {!s.built_in && (
                        <button
                          onClick={() => handleDeleteSkill(s.id)}
                          className="rounded p-1 text-gray-500 hover:bg-gray-700 hover:text-red-400"
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 text-[11px] text-gray-500">{s.description}</p>
                  <p className="mt-1 text-[10px] text-gray-600">
                    {s.steps.length} step{s.steps.length !== 1 ? 's' : ''}:{' '}
                    {s.steps.map((st) => toolDisplayName(st.tool)).join(' → ')}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'memory' && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              The AI remembers your past conversations to provide better context.
            </p>

            <div className="rounded-lg border border-gray-800 bg-gray-800/30 p-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-gray-600">Messages</p>
                  <p className="mt-0.5 text-lg font-semibold text-white">{stats.total_messages}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-gray-600">
                    Conversations
                  </p>
                  <p className="mt-0.5 text-lg font-semibold text-white">
                    {stats.total_conversations}
                  </p>
                </div>
              </div>
            </div>

            <button
              onClick={handleClearHistory}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-2 text-xs font-medium text-red-400 transition-colors hover:bg-red-950/40"
            >
              <Trash2 className="h-3 w-3" />
              Clear All History
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Slash command palette dropdown
// ---------------------------------------------------------------------------

function CommandPalette({
  filter,
  onSelect
}: {
  filter: string
  onSelect: (cmd: string) => void
}) {
  const filtered = useMemo(() => {
    const q = filter.slice(1).toLowerCase()
    return SLASH_COMMANDS.filter(
      (c) => c.command.slice(1).startsWith(q) || c.description.toLowerCase().includes(q)
    )
  }, [filter])

  if (filtered.length === 0) return null

  return (
    <div className="absolute bottom-full left-0 mb-1 w-72 overflow-hidden rounded-lg border border-gray-700 bg-gray-800 shadow-xl">
      {filtered.map((c) => (
        <button
          key={c.command}
          onClick={() => onSelect(c.command)}
          className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-gray-700"
        >
          <List className="h-3.5 w-3.5 shrink-0 text-brand-400" />
          <div>
            <span className="font-mono text-xs text-brand-300">{c.command}</span>
            <p className="text-[11px] text-gray-500">{c.description}</p>
          </div>
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ChatPanel
// ---------------------------------------------------------------------------

export function ChatPanel({ projectId }: { projectId?: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<string[]>([])
  const [directories, setDirectories] = useState<string[]>([])
  const [sending, setSending] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [showPalette, setShowPalette] = useState(false)
  const [activeModel, setActiveModel] = useState<string>('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [thinkingMessage, setThinkingMessage] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // Load chat history on mount or when projectId changes
  useEffect(() => {
    setMessages([])
    const loadHistory = async () => {
      setHistoryLoading(true)
      try {
        const url = projectId ? `/chat/history?project_id=${projectId}` : '/chat/history'
        const data = await apiClient.get<{ messages: Array<{ role: string; content: string; timestamp: string; metadata?: Record<string, unknown> }> }>(url)
        if (data.messages && data.messages.length > 0) {
          const loaded: ChatMessage[] = data.messages.map((m, i) => ({
            id: `history-${i}`,
            role: m.role as 'user' | 'assistant',
            content: m.role === 'assistant' ? extractReplyText(m.content) : m.content,
            timestamp: new Date(m.timestamp),
          }))
          setMessages(loaded)
        }
      } catch { /* history load is optional */ }
      finally { setHistoryLoading(false) }
    }
    loadHistory()
  }, [projectId])

  // Fetch active model for display
  useEffect(() => {
    apiClient.get<{ active_model: string | null }>('/system/models')
      .then(data => setActiveModel(data.active_model || 'qwen3:14b'))
      .catch(() => {})
  }, [])

  // Show / hide slash command palette
  useEffect(() => {
    setShowPalette(input.startsWith('/') && !input.includes(' '))
  }, [input])

  // Elapsed timer while AI is thinking
  useEffect(() => {
    if (!sending) {
      setElapsedSeconds(0)
      return
    }
    setElapsedSeconds(0)
    const interval = setInterval(() => setElapsedSeconds((s) => s + 1), 1000)
    return () => clearInterval(interval)
  }, [sending])

  const handleFeedback = useCallback(
    async (messageId: string, rating: 'up' | 'down') => {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedback: rating } : m))
      )
      try {
        await apiClient.post('/chat/feedback', {
          message_id: messageId,
          rating,
          project_id: projectId || null
        })
      } catch {
        /* best-effort */
      }
    },
    [projectId]
  )

  const sendMessage = useCallback(async (text: string, files: string[] = [], dirs: string[] = []) => {
    const trimmed = text.trim()
    if (!trimmed && files.length === 0 && dirs.length === 0) return

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      attachments: files.length > 0 ? files : undefined,
      directories: dirs.length > 0 ? dirs : undefined,
      timestamp: new Date()
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    setAttachments([])
    setDirectories([])
    const totalFiles = files.length + dirs.length
    setThinkingMessage(
      totalFiles > 0
        ? `Processing ${totalFiles} file${totalFiles !== 1 ? 's' : ''} with ${activeModel || 'AI'}...`
        : `Thinking with ${activeModel || 'AI'}...`
    )
    setSending(true)

    try {
      const response = await apiClient.post<ChatResponse>('/chat/message', {
        message: trimmed,
        project_id: projectId || null,
        attachments: files,
        directories: dirs,
      })

      const aiMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: extractReplyText(response.reply),
        actions: response.actions_taken.length > 0 ? response.actions_taken : undefined,
        suggestions: response.suggestions.length > 0 ? response.suggestions : undefined,
        modelUsed: response.model_used,
        intent: response.intent,
        review: response.review || undefined,
        timestamp: new Date()
      }

      setMessages((prev) => {
        const updated = [...prev, aiMessage]
        if (trimmed.toLowerCase() === '/forget') {
          return updated.slice(-2)
        }
        return updated
      })
    } catch (err) {
      const aiMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Sorry, I encountered an error: ${(err as Error).message}`,
        timestamp: new Date()
      }
      setMessages((prev) => [...prev, aiMessage])
    } finally {
      setSending(false)
      setThinkingMessage('')
    }
  }, [projectId, activeModel])

  const handleSend = () => {
    sendMessage(input, attachments, directories)
  }

  const handleResend = (msg: ChatMessage) => {
    sendMessage(msg.content, msg.attachments || [], msg.directories || [])
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (sending) return
      handleSend()
    }
  }

  const handleFileSelect = async () => {
    try {
      const paths = await window.api.selectFiles({ multiSelections: true })
      if (paths && paths.length > 0) {
        setAttachments((prev) => [...prev, ...paths])
      }
    } catch { /* user cancelled */ }
  }

  const handleFolderSelect = async () => {
    try {
      const dir = await window.api.selectDirectory()
      if (dir) {
        setDirectories((prev) => [...prev, dir])
      }
    } catch { /* user cancelled */ }
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
  }

  const handleCommandSelect = (cmd: string) => {
    setInput(cmd)
    setShowPalette(false)
  }

  return (
    <div className="flex h-full">
      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Chat header */}
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-brand-400" />
            <span className="text-sm font-medium text-white">AI Assistant</span>
            {activeModel && (
              <span className="text-xs text-gray-500">using {activeModel}</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                setMessages([])
                setInput('')
                setAttachments([])
                setDirectories([])
                setShowPalette(false)
                const url = projectId ? `/chat/history?project_id=${projectId}` : '/chat/history'
                apiClient.delete(url).catch(() => {})
              }}
              className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
              title="New chat"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={() => setSettingsOpen(!settingsOpen)}
              className={`rounded-lg p-1.5 transition-colors ${
                settingsOpen
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
              }`}
              title="Chat settings"
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-4 scroll-smooth">
          {historyLoading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-gray-500" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 animate-fade-in">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-brand-600/20 animate-pulse-subtle">
                <Bot className="h-10 w-10 text-brand-400" />
              </div>
              <h3 className="text-xl font-semibold text-white">AI Assistant</h3>
              <p className="max-w-md text-center text-sm text-gray-400">
                I can help you create travel content, edit videos, generate blogs, transcribe
                audio, and more. Ask me anything or drop files to get started.
              </p>
              <div className="mt-2 rounded-xl border border-gray-800/50 bg-gray-800/30 p-4 backdrop-blur-sm">
                <p className="mb-2.5 text-center text-xs font-medium text-gray-500">
                  Slash commands
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {SLASH_COMMANDS.map((c) => (
                    <button
                      key={c.command}
                      onClick={() => setInput(c.command)}
                      className="rounded-md bg-gray-800 px-2.5 py-1 font-mono text-[11px] text-gray-400 transition-all duration-200 hover:bg-gray-700 hover:text-gray-200 hover:scale-105"
                    >
                      {c.command.trim()}
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                {[
                  'Generate a travel blog post',
                  'Help me edit my latest video',
                  'Create captions for my reel',
                  'Suggest a thumbnail idea'
                ].map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSuggestionClick(s)}
                    className="rounded-full border border-gray-700/80 bg-gray-800/50 px-4 py-2 text-sm text-gray-300 transition-all duration-200 hover:border-brand-600/50 hover:bg-gray-800 hover:text-white hover:scale-105"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`group/msg flex gap-3 animate-fade-in-up ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800/80 ring-1 ring-gray-700/50">
                      <Bot className="h-4 w-4 text-brand-400" />
                    </div>
                  )}
                  <div
                    className={`max-w-[75%] min-w-0 space-y-2 ${
                      msg.role === 'user' ? 'items-end' : 'items-start'
                    }`}
                  >
                    <div
                      className={`px-4 py-2.5 text-sm shadow-sm ${
                        msg.role === 'user'
                          ? 'rounded-3xl bg-gradient-to-r from-brand-600 to-brand-500 text-white'
                          : 'rounded-2xl border-l-2 border-brand-500/30 bg-gray-800/80 text-gray-200'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    </div>

                    {msg.attachments && msg.attachments.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {msg.attachments.map((a, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-1.5 rounded-md bg-gray-800/50 px-2 py-1 text-xs text-gray-400"
                          >
                            <Paperclip className="h-3 w-3" />
                            {a.split('/').pop()}
                          </div>
                        ))}
                      </div>
                    )}

                    {msg.actions && msg.actions.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {msg.actions.map((action, i) => (
                          <ActionChip key={i} action={action} />
                        ))}
                      </div>
                    )}

                    {msg.review && <ReviewBadge review={msg.review} />}

                    {msg.suggestions && msg.suggestions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {msg.suggestions.map((s, i) => (
                          <button
                            key={i}
                            onClick={() => handleSuggestionClick(s)}
                            className="rounded-full border border-gray-700/80 bg-gray-800/50 px-3 py-1 text-xs text-gray-300 transition-all duration-200 hover:border-brand-600/50 hover:text-white hover:scale-105"
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Timestamp + model + feedback + copy + resend */}
                    <div className="flex items-center gap-2">
                      <p className="text-[10px] text-gray-600">
                        {msg.timestamp.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                      {msg.role === 'assistant' && msg.modelUsed && (
                        <span className="flex items-center gap-1 rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                          <Cpu className="h-2.5 w-2.5" />
                          {msg.modelUsed}
                        </span>
                      )}
                      {msg.role === 'assistant' && msg.intent && msg.intent !== 'chat' && (
                        <span className="rounded bg-brand-900/30 px-1.5 py-0.5 text-[10px] text-brand-400">
                          {msg.intent}
                        </span>
                      )}
                      <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover/msg:opacity-100">
                        <CopyButton text={msg.content} />
                        {msg.role === 'user' && (
                          <button
                            onClick={() => handleResend(msg)}
                            className="rounded p-1 text-gray-600 transition-colors hover:bg-gray-800 hover:text-gray-400"
                            title="Resend this message"
                            disabled={sending}
                          >
                            <RefreshCw className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                      {msg.role === 'assistant' && (
                        <FeedbackButtons
                          messageId={msg.id}
                          feedback={msg.feedback}
                          onFeedback={handleFeedback}
                        />
                      )}
                    </div>
                  </div>
                  {msg.role === 'user' && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600/20">
                      <User className="h-4 w-4 text-brand-400" />
                    </div>
                  )}
                </div>
              ))}

              {sending && (
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800">
                    <Bot className="h-4 w-4 text-brand-400" />
                  </div>
                  <div className="flex items-center gap-2 rounded-2xl bg-gray-800 px-4 py-3">
                    <Loader2 className="h-4 w-4 animate-spin text-brand-400" />
                    <span className="text-sm text-gray-400">
                      {thinkingMessage || 'Thinking...'}
                      {elapsedSeconds > 0 && (
                        <span className="ml-1 text-gray-500">({elapsedSeconds}s)</span>
                      )}
                    </span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-gray-800/50 p-4">
          <div className="mx-auto max-w-3xl">
            {(attachments.length > 0 || directories.length > 0) && (
              <div className="mb-2 flex flex-wrap gap-2 animate-fade-in">
                {attachments.map((a, i) => (
                  <AttachmentPreview
                    key={`file-${i}`}
                    path={a}
                    onRemove={() => setAttachments((prev) => prev.filter((_, idx) => idx !== i))}
                  />
                ))}
                {directories.map((d, i) => (
                  <AttachmentPreview
                    key={`dir-${i}`}
                    path={d}
                    isDir
                    onRemove={() => setDirectories((prev) => prev.filter((_, idx) => idx !== i))}
                  />
                ))}
              </div>
            )}

            <div className="relative">
              {showPalette && <CommandPalette filter={input} onSelect={handleCommandSelect} />}

              <div className="flex items-end gap-2 rounded-xl border border-gray-700/80 bg-gray-800/50 p-2 transition-all duration-200 focus-within:border-brand-500/40 focus-within:ring-2 focus-within:ring-brand-500/10 focus-within:shadow-lg focus-within:shadow-brand-500/5">
                <button
                  onClick={handleFileSelect}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-all duration-200 hover:bg-gray-700 hover:text-gray-200"
                  title="Attach files (photos, videos, zip, any file)"
                >
                  <Paperclip className="h-4 w-4" />
                </button>
                <button
                  onClick={handleFolderSelect}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-all duration-200 hover:bg-gray-700 hover:text-gray-200"
                  title="Attach a folder (all files inside will be included)"
                >
                  <FolderOpen className="h-4 w-4" />
                </button>
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement
                    target.style.height = 'auto'
                    target.style.height = target.scrollHeight + 'px'
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask anything... or type / for commands"
                  rows={1}
                  className="max-h-32 min-w-0 flex-1 resize-none bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
                  style={{ minHeight: '36px' }}
                />
                <button
                  onClick={handleSend}
                  disabled={sending || (!input.trim() && attachments.length === 0 && directories.length === 0)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-r from-brand-600 to-brand-500 text-white transition-all duration-200 hover:shadow-md hover:shadow-brand-500/25 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {sending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <p className="mt-2 text-center text-[10px] text-gray-600">
              AI responses are generated by your local Ollama models
            </p>
          </div>
        </div>
      </div>

      {/* Settings side panel */}
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} projectId={projectId} />}
    </div>
  )
}
