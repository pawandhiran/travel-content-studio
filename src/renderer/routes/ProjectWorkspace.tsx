import { useEffect } from 'react'
import { useParams, useNavigate, Routes, Route, Navigate } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { VideoPanel } from '../components/video/VideoPanel'
import { VideoEditingPanel } from '../components/video/VideoEditingPanel'
import { TranscriptPanel } from '../components/transcription/TranscriptPanel'
import { ContentPanel } from '../components/content/ContentPanel'
import { ThumbnailPanel } from '../components/thumbnail/ThumbnailPanel'
import { VoiceoverPanel } from '../components/voiceover/VoiceoverPanel'
import { BlogPanel } from '../components/blog/BlogPanel'
import { ReelPanel } from '../components/reels/ReelPanel'
import { AgentPanel } from '../components/agents/AgentPanel'
import { StockPhotoPanel } from '../components/photos/StockPhotoPanel'

export function ProjectWorkspace() {
  const { id } = useParams<{ id: string }>()
  const { currentProject, fetchProject, loading, error } = useProjectStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (id) fetchProject(id)
  }, [id])

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 animate-fade-in">
        <div className="rounded-xl border border-red-900/40 bg-red-950/20 px-6 py-5 text-center backdrop-blur-sm">
          <p className="font-medium text-red-400">Failed to load project</p>
          <p className="mt-1.5 max-w-md text-sm text-red-300/70">
            {error === 'Failed to fetch'
              ? 'The backend server is not responding. It may have crashed or is still processing a previous request.'
              : error}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => {
              if (id) fetchProject(id)
            }}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:bg-brand-700 hover:-translate-y-0.5"
          >
            Retry
          </button>
          <button
            onClick={() => navigate('/projects')}
            className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 transition-all duration-200 hover:bg-gray-700 hover:-translate-y-0.5"
          >
            Back to Projects
          </button>
        </div>
      </div>
    )
  }

  if (loading || !currentProject) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading project...</p>
      </div>
    )
  }

  return (
    <div className="h-full">
      <Routes>
        <Route index element={<ProjectOverview project={currentProject} />} />
        <Route path="videos" element={<VideoPanel projectId={currentProject.id} />} />
        <Route path="editing" element={<VideoEditingPanel projectId={currentProject.id} />} />
        <Route path="transcripts" element={<TranscriptPanel key={currentProject.id} projectId={currentProject.id} />} />
        <Route path="content" element={<ContentPanel projectId={currentProject.id} />} />
        <Route path="insta360" element={<ContentPanel projectId={currentProject.id} />} />
        <Route path="stories" element={<ContentPanel projectId={currentProject.id} />} />
        <Route path="reels" element={<ReelPanel projectId={currentProject.id} />} />
        <Route path="youtube" element={<ContentPanel projectId={currentProject.id} />} />
        <Route path="thumbnails" element={<ThumbnailPanel projectId={currentProject.id} />} />
        <Route path="voiceover" element={<VoiceoverPanel projectId={currentProject.id} />} />
        <Route path="blog" element={<BlogPanel projectId={currentProject.id} />} />
        <Route path="agents" element={<AgentPanel key={currentProject.id} projectId={currentProject.id} />} />
        <Route path="stock-photos" element={<StockPhotoPanel key={currentProject.id} projectId={currentProject.id} />} />
        <Route path="*" element={<Navigate to="" replace />} />
      </Routes>
    </div>
  )
}

function ProjectOverview({ project }: { project: { id: string; name: string; description: string; created_at: string } }) {
  const navigate = useNavigate()

  return (
    <div className="mx-auto max-w-4xl animate-fade-in">
      <h2 className="text-2xl font-bold tracking-tight text-white">{project.name}</h2>
      <p className="mt-2 text-gray-400">{project.description}</p>
      <p className="mt-1 text-sm text-gray-500">
        Created {new Date(project.created_at).toLocaleDateString()}
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          { label: 'Import Videos', desc: 'Add travel footage to your project', path: 'videos' },
          { label: 'Video Editing', desc: 'Color grade, captions, reframe, stitch, and more', path: 'editing' },
          { label: 'Stock Photos', desc: 'Enhance photos for Shutterstock', path: 'stock-photos' },
          { label: 'Transcribe', desc: 'Generate transcripts from video audio', path: 'transcripts' },
          { label: 'AI Content', desc: 'Generate titles, scripts, and stories', path: 'content' },
          { label: 'Thumbnails', desc: 'Create AI-generated thumbnails', path: 'thumbnails' },
          { label: 'Voiceover', desc: 'Generate narration audio', path: 'voiceover' },
          { label: 'Blog Studio', desc: 'Write travel blogs and guides', path: 'blog' },
          { label: 'Reel Generator', desc: 'Create short-form content plans', path: 'reels' },
          { label: 'Travel Agents', desc: 'Run AI agent pipeline', path: 'agents' }
        ].map((item, idx) => (
          <button
            key={item.path}
            onClick={() => navigate(`/projects/${project.id}/${item.path}`)}
            className="group rounded-xl border border-gray-800/80 bg-gray-900/60 p-5 text-left transition-all duration-300 hover:border-brand-600/40 hover:bg-gray-900 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/20 animate-fade-in-up"
            style={{ animationDelay: `${idx * 50}ms`, animationFillMode: 'backwards' }}
          >
            <h3 className="font-medium text-white group-hover:text-brand-300 transition-colors duration-200">{item.label}</h3>
            <p className="mt-1 text-sm text-gray-400">{item.desc}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
