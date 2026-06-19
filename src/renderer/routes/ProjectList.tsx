import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { Plus, Search, FolderOpen, Trash2 } from 'lucide-react'

export function ProjectList() {
  const navigate = useNavigate()
  const { projects, loading, fetchProjects, createProject, deleteProject } = useProjectStore()
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  useEffect(() => {
    fetchProjects(search || undefined)
  }, [search])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const project = await createProject(newName.trim(), newDesc.trim())
      setShowCreate(false)
      setNewName('')
      setNewDesc('')
      navigate(`/projects/${project.id}`)
    } catch {
      // Show error
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Projects</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>

      {/* Create Dialog */}
      {showCreate && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-6">
          <h3 className="mb-4 text-lg font-semibold text-white">Create New Project</h3>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-gray-400">Project Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="My Travel Vlog"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">Description</label>
              <textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Describe your travel project..."
                rows={3}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-lg px-4 py-2 text-sm text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newName.trim()}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                Create Project
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Project List */}
      {loading ? (
        <div className="py-20 text-center text-gray-500">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-20">
          <FolderOpen className="mb-4 h-16 w-16 text-gray-600" />
          <p className="text-lg text-gray-400">No projects found</p>
          <p className="mt-1 text-sm text-gray-500">Create a project to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="flex items-center justify-between rounded-xl border border-gray-800 bg-gray-900/50 p-4 transition-colors hover:border-gray-700"
            >
              <button
                onClick={() => navigate(`/projects/${project.id}`)}
                className="flex-1 text-left"
              >
                <h4 className="font-medium text-white">{project.name}</h4>
                <p className="mt-0.5 text-sm text-gray-400">{project.description}</p>
                <p className="mt-1 text-xs text-gray-500">
                  Created {new Date(project.created_at).toLocaleDateString()}
                </p>
              </button>
              <button
                onClick={() => deleteProject(project.id)}
                className="ml-4 rounded-lg p-2 text-gray-500 hover:bg-gray-800 hover:text-red-400"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
