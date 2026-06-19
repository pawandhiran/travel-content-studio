import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Send,
  Paperclip,
  Bot,
  User,
  ChevronDown,
  ChevronUp,
  Loader2,
  Image,
  Video,
  FileText,
  X,
  Sparkles
} from 'lucide-react'
import { apiClient } from '../../services/apiClient'

interface ActionTaken {
  tool: string
  args: Record<string, unknown>
  result: { status: string; data?: unknown; detail?: string }
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachments?: string[]
  actions?: ActionTaken[]
  suggestions?: string[]
  timestamp: Date
}

interface ChatResponse {
  reply: string
  actions_taken: ActionTaken[]
  suggestions: string[]
}

const TOOL_ICONS: Record<string, string> = {
  create_project: 'FolderOpen',
  import_video: 'Video',
  transcribe: 'FileText',
  generate_content: 'Sparkles',
  color_grade: 'Palette',
  auto_reframe: 'Crop',
  add_captions: 'Subtitles',
  enhance_audio: 'Volume2',
  smart_stitch: 'Scissors',
  generate_thumbnail: 'Image',
  generate_voiceover: 'Mic',
  generate_blog: 'BookOpen',
  enhance_photos: 'Camera',
  quality_check: 'CheckCircle',
  run_agents: 'Bot'
}

function toolDisplayName(tool: string): string {
  return tool
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function AttachmentPreview({
  path,
  onRemove
}: {
  path: string
  onRemove: () => void
}) {
  const filename = path.split('/').pop() || path
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
  const isVideo = ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)

  return (
    <div className="group flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/50 px-3 py-1.5 text-sm">
      {isImage && <Image className="h-3.5 w-3.5 text-emerald-400" />}
      {isVideo && <Video className="h-3.5 w-3.5 text-blue-400" />}
      {!isImage && !isVideo && <FileText className="h-3.5 w-3.5 text-gray-400" />}
      <span className="max-w-[120px] truncate text-gray-300">{filename}</span>
      <button
        onClick={onRemove}
        className="text-gray-500 opacity-0 transition-opacity hover:text-gray-300 group-hover:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

function ActionCard({ action }: { action: ActionTaken }) {
  const [expanded, setExpanded] = useState(false)
  const success = action.result.status === 'success'

  return (
    <div
      className={`rounded-lg border ${
        success ? 'border-emerald-800/50 bg-emerald-950/30' : 'border-red-800/50 bg-red-950/30'
      } overflow-hidden`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
      >
        <Sparkles
          className={`h-3.5 w-3.5 ${success ? 'text-emerald-400' : 'text-red-400'}`}
        />
        <span className={success ? 'text-emerald-300' : 'text-red-300'}>
          {toolDisplayName(action.tool)}
        </span>
        <span className="ml-auto text-gray-500">
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-gray-800 px-3 py-2 text-xs text-gray-400">
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
          {action.result.detail && (
            <p className="mt-2 text-red-400">{action.result.detail}</p>
          )}
        </div>
      )}
    </div>
  )
}

export function ChatPanel({ projectId }: { projectId?: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<string[]>([])
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed && attachments.length === 0) return

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      attachments: attachments.length > 0 ? [...attachments] : undefined,
      timestamp: new Date()
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setAttachments([])
    setSending(true)

    try {
      const response = await apiClient.post<ChatResponse>('/chat/message', {
        message: trimmed,
        project_id: projectId || null,
        attachments: userMessage.attachments || []
      })

      const aiMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.reply,
        actions:
          response.actions_taken.length > 0 ? response.actions_taken : undefined,
        suggestions:
          response.suggestions.length > 0 ? response.suggestions : undefined,
        timestamp: new Date()
      }

      setMessages((prev) => [...prev, aiMessage])
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
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    const paths = Array.from(files).map((f) => (f as any).path || f.name)
    setAttachments((prev) => [...prev, ...paths])
    e.target.value = ''
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600/20">
              <Bot className="h-8 w-8 text-brand-400" />
            </div>
            <h3 className="text-lg font-medium text-white">AI Assistant</h3>
            <p className="max-w-md text-center text-sm text-gray-400">
              I can help you create travel content, edit videos, generate blogs,
              transcribe audio, and more. Ask me anything or drop files to get started.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {[
                'Generate a travel blog post',
                'Help me edit my latest video',
                'Create captions for my reel',
                'Suggest a thumbnail idea'
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => handleSuggestionClick(s)}
                  className="rounded-full border border-gray-700 bg-gray-800/50 px-4 py-2 text-sm text-gray-300 transition-colors hover:border-brand-600/50 hover:bg-gray-800 hover:text-white"
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
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800">
                    <Bot className="h-4 w-4 text-brand-400" />
                  </div>
                )}
                <div
                  className={`max-w-[75%] space-y-2 ${
                    msg.role === 'user' ? 'items-end' : 'items-start'
                  }`}
                >
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-sm ${
                      msg.role === 'user'
                        ? 'bg-brand-600 text-white'
                        : 'bg-gray-800 text-gray-200'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>

                  {/* Attachment previews for user messages */}
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

                  {/* Action cards */}
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="space-y-2">
                      {msg.actions.map((action, i) => (
                        <ActionCard key={i} action={action} />
                      ))}
                    </div>
                  )}

                  {/* Suggestion chips */}
                  {msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {msg.suggestions.map((s, i) => (
                        <button
                          key={i}
                          onClick={() => handleSuggestionClick(s)}
                          className="rounded-full border border-gray-700 bg-gray-800/50 px-3 py-1 text-xs text-gray-300 transition-colors hover:border-brand-600/50 hover:text-white"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}

                  <p className="text-[10px] text-gray-600">
                    {msg.timestamp.toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </p>
                </div>
                {msg.role === 'user' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600/20">
                    <User className="h-4 w-4 text-brand-400" />
                  </div>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800">
                  <Bot className="h-4 w-4 text-brand-400" />
                </div>
                <div className="flex items-center gap-2 rounded-2xl bg-gray-800 px-4 py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-brand-400" />
                  <span className="text-sm text-gray-400">Thinking...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-gray-800 p-4">
        <div className="mx-auto max-w-3xl">
          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {attachments.map((a, i) => (
                <AttachmentPreview
                  key={i}
                  path={a}
                  onRemove={() =>
                    setAttachments((prev) => prev.filter((_, idx) => idx !== i))
                  }
                />
              ))}
            </div>
          )}

          <div className="flex items-end gap-2 rounded-xl border border-gray-700 bg-gray-800/50 p-2 focus-within:border-brand-600/50">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-700 hover:text-gray-200"
              title="Attach files"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,video/*"
              className="hidden"
              onChange={handleFileSelect}
            />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask me anything about your travel content..."
              rows={1}
              className="max-h-32 flex-1 resize-none bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
              style={{ minHeight: '36px' }}
            />
            <button
              onClick={handleSend}
              disabled={sending || (!input.trim() && attachments.length === 0)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white transition-colors hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>

          <p className="mt-2 text-center text-[10px] text-gray-600">
            AI responses are generated by your local Ollama models
          </p>
        </div>
      </div>
    </div>
  )
}
