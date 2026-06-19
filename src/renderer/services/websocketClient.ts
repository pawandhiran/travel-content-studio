type EventHandler = (data: Record<string, unknown>) => void

class WebSocketClient {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private url: string

  constructor(url: string) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return

    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      console.log('[WS] Connected')
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
        this.reconnectTimer = null
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        const { type, data } = message
        const handlers = this.handlers.get(type)
        if (handlers) {
          handlers.forEach((handler) => handler(data))
        }
        const wildcardHandlers = this.handlers.get('*')
        if (wildcardHandlers) {
          wildcardHandlers.forEach((handler) => handler(message))
        }
      } catch {
        console.warn('[WS] Failed to parse message:', event.data)
      }
    }

    this.ws.onclose = () => {
      console.log('[WS] Disconnected, reconnecting in 3s...')
      this.scheduleReconnect()
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  on(eventType: string, handler: EventHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set())
    }
    this.handlers.get(eventType)!.add(handler)

    return () => {
      this.handlers.get(eventType)?.delete(handler)
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, 3000)
  }
}

export const wsClient = new WebSocketClient('ws://127.0.0.1:8420/ws/events')
