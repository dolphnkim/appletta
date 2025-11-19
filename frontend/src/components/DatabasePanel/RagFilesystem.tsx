import { useState, useEffect, useRef } from 'react';
import { ragAPI } from '../../api/ragAPI';
import type { RagFolder, RagFile } from '../../types/rag';
import SourceInstructionsModal from './SourceInstructionsModal';
import FilePicker from '../AgentSettings/FilePicker';
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
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

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

  const handleAttachFolder = () => {
    setShowFolderPicker(true);
  };

  const handleFolderSelected = async (path: string) => {
    try {
      setError(null);
      const newFolder = await ragAPI.attachFolder({
        agent_id: agentId,
        path,
        max_files_open: 5,
        per_file_char_limit: 15000,
      });
      setFolders([newFolder, ...folders]);
      setShowFolderPicker(false);
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

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;

    // Check if files/folders were dropped
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      // Note: Browsers don't give us full folder paths for security reasons
      // We'll open the folder picker as a fallback
      setShowFolderPicker(true);
    }
  };

  if (loading) {
    return <div className="rag-filesystem loading">Loading folders...</div>;
  }

  return (
    <div
      className={`rag-filesystem ${isDragging ? 'dragging' : ''}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">×</button>
        </div>
      )}

      {isDragging && (
        <div className="drag-overlay">
          <div className="drag-message">
            <div className="drag-icon">📁</div>
            <p>Drop folder here to attach</p>
          </div>
        </div>
      )}

      <div className="rag-content">
        {/* Folder List */}
        <div className="folder-list-section">
          <div className="section-header">
            <span>Attached Folders</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="count">{folders.length}</span>
              <button
                onClick={handleAttachFolder}
                className="attach-button-icon"
                title="Attach folder"
                style={{
                  padding: '4px 8px',
                  background: 'transparent',
                  border: '1px solid #444',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  color: '#ccc',
                  fontSize: '12px'
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 8.25a.75.75 0 0 1 .75.75v2.25H15a.75.75 0 0 1 0 1.5h-2.25V15a.75.75 0 0 1-1.5 0v-2.25H9a.75.75 0 0 1 0-1.5h2.25V9a.75.75 0 0 1 .75-.75Z" />
                  <path d="M3 3a2 2 0 0 1 2-2h9.982a2 2 0 0 1 1.414.586l4.018 4.018A2 2 0 0 1 21 7.018V21a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3Zm2-.5a.5.5 0 0 0-.5.5v18a.5.5 0 0 0 .5.5h14a.5.5 0 0 0 .5-.5V7.018a.5.5 0 0 0-.146-.354l-4.018-4.018a.5.5 0 0 0-.354-.146H5Z" />
                </svg>
                Attach
              </button>
            </div>
          </div>

          {folders.length === 0 ? (
            <div className="empty-state">
              <p>No folders attached yet</p>
              <p className="hint">Click "Attach" button above to add a directory for RAG</p>
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
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '4px', verticalAlign: 'text-bottom' }}>
                        <path d="M12 1.25c2.487 0 4.773.402 6.466 1.079.844.337 1.577.758 2.112 1.264.536.507.922 1.151.922 1.907v12.987l-.026.013h.026c0 .756-.386 1.4-.922 1.907-.535.506-1.268.927-2.112 1.264-1.693.677-3.979 1.079-6.466 1.079s-4.774-.402-6.466-1.079c-.844-.337-1.577-.758-2.112-1.264C2.886 19.9 2.5 19.256 2.5 18.5h.026l-.026-.013V5.5c0-.756.386-1.4.922-1.907.535-.506 1.268-.927 2.112-1.264C7.226 1.652 9.513 1.25 12 1.25ZM4 14.371v4.116l-.013.013H4c0 .211.103.487.453.817.351.332.898.666 1.638.962 1.475.589 3.564.971 5.909.971 2.345 0 4.434-.381 5.909-.971.739-.296 1.288-.63 1.638-.962.349-.33.453-.607.453-.817h.013L20 18.487v-4.116a7.85 7.85 0 0 1-1.534.8c-1.693.677-3.979 1.079-6.466 1.079s-4.774-.402-6.466-1.079a7.843 7.843 0 0 1-1.534-.8ZM20 12V7.871a7.85 7.85 0 0 1-1.534.8C16.773 9.348 14.487 9.75 12 9.75s-4.774-.402-6.466-1.079A7.85 7.85 0 0 1 4 7.871V12c0 .21.104.487.453.817.35.332.899.666 1.638.961 1.475.59 3.564.972 5.909.972 2.345 0 4.434-.382 5.909-.972.74-.295 1.287-.629 1.638-.96.35-.33.453-.607.453-.818ZM4 5.5c0 .211.103.487.453.817.351.332.898.666 1.638.962 1.475.589 3.564.971 5.909.971 2.345 0 4.434-.381 5.909-.971.739-.296 1.288-.63 1.638-.962.349-.33.453-.607.453-.817 0-.211-.103-.487-.453-.817-.351-.332-.898-.666-1.638-.962-1.475-.589-3.564-.971-5.909-.971-2.345 0-4.434.381-5.909.971-.739.296-1.288.63-1.638.962C4.104 5.013 4 5.29 4 5.5Z" />
                      </svg>
                      Scan
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDetachFolder(folder.id);
                      }}
                      className="detach-button"
                      title="Detach folder"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20.347 3.653a3.936 3.936 0 0 0-5.567 0l-1.75 1.75a.75.75 0 0 1-1.06-1.06l1.75-1.75a5.436 5.436 0 0 1 7.688 7.687l-1.564 1.564a.75.75 0 0 1-1.06-1.06l1.563-1.564a3.936 3.936 0 0 0 0-5.567ZM9.786 12.369a.75.75 0 0 1 1.053.125c.096.122.2.24.314.353 1.348 1.348 3.386 1.587 4.89.658l-3.922-2.858a.745.745 0 0 1-.057-.037c-1.419-1.013-3.454-.787-4.784.543L3.653 14.78a3.936 3.936 0 0 0 5.567 5.567l3-3a.75.75 0 1 1 1.06 1.06l-3 3a5.436 5.436 0 1 1-7.688-7.687l3.628-3.628a5.517 5.517 0 0 1 3.014-1.547l-7.05-5.136a.75.75 0 0 1 .883-1.213l20.25 14.75a.75.75 0 0 1-.884 1.213l-5.109-3.722c-2.155 1.709-5.278 1.425-7.232-.53a5.491 5.491 0 0 1-.431-.485.75.75 0 0 1 .125-1.053Z" />
                      </svg>
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

      {showFolderPicker && (
        <div className="modal-overlay" onClick={() => setShowFolderPicker(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Select Folder to Attach</h2>
              <button onClick={() => setShowFolderPicker(false)} className="modal-close">
                ×
              </button>
            </div>
            <div className="modal-body">
              <p style={{ marginTop: 0, fontSize: '13px', color: '#888', marginBottom: '16px' }}>
                Navigate to the folder you want to attach and click "✓ Select"
              </p>
              <FilePicker
                label="Folder Browser"
                value=""
                onSelect={handleFolderSelected}
                selectFolders={true}
                helpText="Browse to your desired folder, then click '✓ Select' to attach it"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
