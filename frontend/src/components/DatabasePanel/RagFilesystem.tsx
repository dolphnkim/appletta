import { useState, useEffect, useRef } from 'react';
import { ragAPI } from '../../api/ragAPI';
import type { RagFolder, RagFile } from '../../types/rag';
import SourceInstructionsModal from './SourceInstructionsModal';
import './RagFilesystem.css';

interface RagFilesystemProps {
  agentId: string;
}

export default function RagFilesystem({ agentId }: RagFilesystemProps) {
  const [folders, setFolders] = useState<RagFolder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<RagFolder | null>(null);
  const [files, setFiles] = useState<RagFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInstructionsModal, setShowInstructionsModal] = useState(false);
  const [scanning, setScanning] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadFolders();
  }, [agentId]);

  const loadFolders = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await ragAPI.listFolders(agentId);
      setFolders(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load folders');
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async (folderId: string) => {
    try {
      const data = await ragAPI.listFiles(folderId);
      setFiles(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    }
  };

  const handleFolderSelect = (folder: RagFolder) => {
    setSelectedFolder(folder);
    loadFiles(folder.id);
  };

  const handleAttachFolder = async () => {
    // For now, use a simple prompt. In production, use native file dialog
    const path = prompt('Enter folder path:');
    if (!path) return;

    try {
      setError(null);
      const newFolder = await ragAPI.attachFolder({
        agent_id: agentId,
        path,
        max_files_open: 5,
        per_file_char_limit: 15000,
      });
      setFolders([newFolder, ...folders]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to attach folder');
    }
  };

  const handleDetachFolder = async (folderId: string) => {
    if (!confirm('Are you sure you want to detach this folder? This will remove all indexed files.')) {
      return;
    }

    try {
      setError(null);
      await ragAPI.detachFolder(folderId);
      setFolders(folders.filter(f => f.id !== folderId));
      if (selectedFolder?.id === folderId) {
        setSelectedFolder(null);
        setFiles([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to detach folder');
    }
  };

  const handleScanFolder = async (folderId: string) => {
    try {
      setScanning(true);
      setError(null);
      const result = await ragAPI.scanFolder(folderId);
      alert(`Scanned folder: ${result.message}`);

      // Reload folders to update file counts
      await loadFolders();

      // Reload files if this folder is selected
      if (selectedFolder?.id === folderId) {
        await loadFiles(folderId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to scan folder');
    } finally {
      setScanning(false);
    }
  };

  const handleUpdateSettings = async (folderId: string, updates: { max_files_open?: number; per_file_char_limit?: number }) => {
    try {
      setError(null);
      const updated = await ragAPI.updateFolder(folderId, updates);
      setFolders(folders.map(f => f.id === folderId ? updated : f));
      if (selectedFolder?.id === folderId) {
        setSelectedFolder(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update settings');
    }
  };

  const handleUpdateInstructions = async (instructions: string) => {
    if (!selectedFolder) return;

    try {
      setError(null);
      const updated = await ragAPI.updateFolder(selectedFolder.id, {
        source_instructions: instructions,
      });
      setFolders(folders.map(f => f.id === selectedFolder.id ? updated : f));
      setSelectedFolder(updated);
      setShowInstructionsModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update instructions');
    }
  };

  const handleDeleteFile = async (fileId: string) => {
    if (!confirm('Remove this file from the database?')) return;

    try {
      setError(null);
      await ragAPI.deleteFile(fileId);
      setFiles(files.filter(f => f.id !== fileId));

      // Update folder file count
      if (selectedFolder) {
        await loadFolders();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete file');
    }
  };

  if (loading) {
    return <div className="rag-filesystem loading">Loading folders...</div>;
  }

  return (
    <div className="rag-filesystem">
      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">×</button>
        </div>
      )}

      <div className="rag-toolbar">
        <button onClick={handleAttachFolder} className="attach-button">
          + Attach Folder
        </button>
      </div>

      <div className="rag-content">
        {/* Folder List */}
        <div className="folder-list-section">
          <div className="section-header">
            <span>Attached Folders</span>
            <span className="count">{folders.length}</span>
          </div>

          {folders.length === 0 ? (
            <div className="empty-state">
              <p>No folders attached yet</p>
              <p className="hint">Click "Attach Folder" to add a directory for RAG</p>
            </div>
          ) : (
            <div className="folder-list">
              {folders.map(folder => (
                <div
                  key={folder.id}
                  className={`folder-item ${selectedFolder?.id === folder.id ? 'selected' : ''}`}
                  onClick={() => handleFolderSelect(folder)}
                >
                  <div className="folder-header">
                    <span className="folder-icon">📁</span>
                    <span className="folder-name">{folder.name}</span>
                    <span className="file-count">{folder.file_count}</span>
                  </div>
                  <div className="folder-path">{folder.path}</div>
                  <div className="folder-actions">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleScanFolder(folder.id);
                      }}
                      className="scan-button"
                      disabled={scanning}
                    >
                      {scanning ? '⟳' : '🔄'} Scan
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDetachFolder(folder.id);
                      }}
                      className="detach-button"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Folder Details */}
        {selectedFolder && (
          <div className="folder-details-section">
            <div className="section-header">
              <span>{selectedFolder.name}</span>
            </div>

            {/* Settings */}
            <div className="folder-settings">
              <div className="setting-row">
                <label>Max Files Open</label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={selectedFolder.max_files_open}
                  onChange={(e) => handleUpdateSettings(selectedFolder.id, {
                    max_files_open: parseInt(e.target.value)
                  })}
                  className="setting-input"
                />
              </div>
              <div className="setting-row">
                <label>Per File Char Limit</label>
                <input
                  type="number"
                  min="100"
                  max="1000000"
                  step="1000"
                  value={selectedFolder.per_file_char_limit}
                  onChange={(e) => handleUpdateSettings(selectedFolder.id, {
                    per_file_char_limit: parseInt(e.target.value)
                  })}
                  className="setting-input"
                />
              </div>
              <div className="setting-row">
                <label>Source Instructions</label>
                <button
                  onClick={() => setShowInstructionsModal(true)}
                  className="edit-instructions-button"
                >
                  {selectedFolder.source_instructions ? 'Edit' : 'Add'} Instructions
                </button>
              </div>
            </div>

            {/* File List */}
            <div className="file-list-header">
              <span>Files</span>
              <span className="count">{files.length}</span>
            </div>

            {files.length === 0 ? (
              <div className="empty-state">
                <p>No files indexed yet</p>
                <p className="hint">Click "Scan" to discover files in this folder</p>
              </div>
            ) : (
              <div className="file-list">
                {files.map(file => (
                  <div key={file.id} className="file-item">
                    <div className="file-header">
                      <span className="file-icon">📄</span>
                      <span className="file-name">{file.filename}</span>
                      <button
                        onClick={() => handleDeleteFile(file.id)}
                        className="delete-file-button"
                      >
                        ✕
                      </button>
                    </div>
                    <div className="file-meta">
                      <span>{(file.size_bytes || 0) / 1024 | 0} KB</span>
                      <span>•</span>
                      <span>{file.chunk_count} chunks</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {showInstructionsModal && selectedFolder && (
        <SourceInstructionsModal
          value={selectedFolder.source_instructions || ''}
          folderName={selectedFolder.name}
          onSave={handleUpdateInstructions}
          onClose={() => setShowInstructionsModal(false)}
        />
      )}
    </div>
  );
}
