import { useEffect } from 'react'
import { useSystemStore } from '../stores/systemStore'

export function Settings() {
  const { hardware, activeModel, availableModels, fetchHardware, fetchModels, switchModel } =
    useSystemStore()

  useEffect(() => {
    fetchHardware()
    fetchModels()
  }, [])

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <h2 className="text-2xl font-bold text-white">Settings</h2>

      {/* Hardware Info */}
      <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">Hardware</h3>
        {hardware ? (
          <div className="grid grid-cols-2 gap-4">
            <InfoRow label="GPU" value={hardware.gpuName} />
            <InfoRow
              label={hardware.gpuType === 'apple_silicon' ? 'Unified Memory' : 'VRAM'}
              value={
                hardware.gpuType === 'apple_silicon'
                  ? `${hardware.ramGb} GB (shared)`
                  : `${hardware.vramGb} GB`
              }
            />
            <InfoRow label="System RAM" value={`${hardware.ramGb} GB`} />
            <InfoRow
              label="GPU Acceleration"
              value={
                hardware.cudaAvailable
                  ? 'CUDA Available'
                  : hardware.metalAvailable
                    ? 'Metal / MPS Available'
                    : 'CPU Only'
              }
            />
          </div>
        ) : (
          <p className="text-sm text-gray-500">Detecting hardware...</p>
        )}
      </section>

      {/* AI Model Selection */}
      <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">AI Model</h3>
        <p className="mb-4 text-sm text-gray-400">
          Select the AI model for content generation. Larger models produce better results but
          require more resources.
        </p>
        <div className="space-y-2">
          {(availableModels.length > 0
            ? availableModels
            : ['qwen3:8b', 'qwen3:14b', 'qwen3:32b']
          ).map((model) => (
            <button
              key={model}
              onClick={() => switchModel(model)}
              className={`flex w-full items-center justify-between rounded-lg border px-4 py-3 text-sm transition-colors ${
                activeModel === model
                  ? 'border-brand-500 bg-brand-600/10 text-brand-400'
                  : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'
              }`}
            >
              <span>{model}</span>
              {activeModel === model && (
                <span className="rounded-full bg-brand-600/20 px-2 py-0.5 text-xs text-brand-400">
                  Active
                </span>
              )}
            </button>
          ))}
        </div>
      </section>

      {/* About */}
      <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">About</h3>
        <div className="space-y-2">
          <InfoRow label="Version" value="0.1.0" />
          <InfoRow label="License" value="MIT" />
        </div>
      </section>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm text-white">{value}</p>
    </div>
  )
}
