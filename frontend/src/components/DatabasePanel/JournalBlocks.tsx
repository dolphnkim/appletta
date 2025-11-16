import { useState, useEffect } from 'react';
import { journalAPI } from '../../api/journalAPI';
import type { JournalBlock, JournalBlockCreate } from '../../types/journal';
import './JournalBlocks.css';

interface JournalBlocksProps {
  agentId: string;
}

export default function JournalBlocks({ agentId }: JournalBlocksProps) {
  const [blocks, setBlocks] = useState<JournalBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<JournalBlock | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  const loadBlocks = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await journalAPI.list(agentId);
      setBlocks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load journal blocks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBlocks();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const handleCreate = async (data: JournalBlockCreate) => {
    try {
      console.log('Creating journal block:', data);
      const newBlock = await journalAPI.create(agentId, data);
      console.log('Journal block created:', newBlock);
      setBlocks([newBlock, ...blocks]);
      setShowCreateModal(false);
      setError(null);
    } catch (err) {
      console.error('Failed to create journal block:', err);
      const errorMsg = err instanceof Error ? err.message : 'Failed to create journal block';
      setError(errorMsg);
      // Don't close modal on error so user can see what went wrong
      alert(`Error creating journal block: ${errorMsg}`);
    }
  };

  const handleUpdate = async (blockId: string, value: string) => {
    try {
      const updated = await journalAPI.update(agentId, blockId, { value });
      setBlocks(blocks.map((b) => (b.id === blockId ? updated : b)));
      setSelectedBlock(updated);
      setShowEditModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update journal block');
    }
  };

  const handleDelete = async (blockId: string) => {
    if (!confirm('Delete this journal block? This cannot be undone.')) {
      return;
    }

    try {
      await journalAPI.delete(agentId, blockId);
      setBlocks(blocks.filter((b) => b.id !== blockId));
      if (selectedBlock?.id === blockId) {
        setSelectedBlock(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete journal block');
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="journal-blocks">
        <div className="journal-loading">Loading journal blocks...</div>
      </div>
    );
  }

  return (
    <div className="journal-blocks">
      <div className="journal-header">
        <button onClick={() => setShowCreateModal(true)} className="new-block-button">
          + New Block
        </button>
      </div>

      {error && (
        <div className="journal-error">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">
            ×
          </button>
        </div>
      )}

      <div className="journal-blocks-list">
        {blocks.length === 0 ? (
          <div className="journal-empty">
            <div className="empty-icon">📔</div>
            <p>No journal blocks yet</p>
            <p className="hint">Create blocks to store thoughts and insights</p>
          </div>
        ) : (
          blocks.map((block) => (
            <div
              key={block.id}
              className={`journal-block-item ${selectedBlock?.id === block.id ? 'active' : ''}`}
              onClick={() => setSelectedBlock(block)}
            >
              <div className="block-item-header">
                <div className="block-label">{block.label}</div>
                <div className="block-badges">
                  {block.read_only && <span className="badge read-only">Read-only</span>}
                  {!block.editable_by_main_agent && (
                    <span className="badge no-main">Main: No</span>
                  )}
                  {block.editable_by_memory_agent && (
                    <span className="badge memory-yes">Memory: Yes</span>
                  )}
                </div>
              </div>
              <div className="block-item-id">{block.block_id}</div>
              {block.description && <div className="block-item-description">{block.description}</div>}
              <div className="block-item-preview">{block.value.substring(0, 100)}...</div>
              <div className="block-item-meta">
                <span>Updated: {formatDate(block.updated_at)}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {selectedBlock && (
        <BlockViewModal
          block={selectedBlock}
          onClose={() => setSelectedBlock(null)}
          onEdit={() => {
            setShowEditModal(true);
            setSelectedBlock(null);
          }}
          onDelete={() => handleDelete(selectedBlock.id)}
        />
      )}

      {showCreateModal && (
        <BlockCreateModal onClose={() => setShowCreateModal(false)} onCreate={handleCreate} />
      )}

      {showEditModal && selectedBlock && (
        <BlockEditModal
          block={selectedBlock}
          onClose={() => setShowEditModal(false)}
          onSave={(value) => handleUpdate(selectedBlock.id, value)}
        />
      )}
    </div>
  );
}

// Block View Modal
interface BlockViewModalProps {
  block: JournalBlock;
  onClose: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function BlockViewModal({ block, onClose, onEdit, onDelete }: BlockViewModalProps) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{block.label}</h2>
          <button onClick={onClose} className="modal-close">
            ×
          </button>
        </div>
        <div className="modal-body">
          <div className="block-details">
            <div className="detail-row">
              <span className="detail-label">Block ID:</span>
              <span className="detail-value monospace">{block.block_id}</span>
            </div>
            {block.description && (
              <div className="detail-row">
                <span className="detail-label">Description:</span>
                <span className="detail-value">{block.description}</span>
              </div>
            )}
            <div className="detail-row">
              <span className="detail-label">Access Control:</span>
              <div className="detail-value">
                <div className="access-flags">
                  <label>
                    <input type="checkbox" checked={block.read_only} disabled />
                    Read-only
                  </label>
                  <label>
                    <input type="checkbox" checked={block.editable_by_main_agent} disabled />
                    Main Agent
                  </label>
                  <label>
                    <input type="checkbox" checked={block.editable_by_memory_agent} disabled />
                    Memory Agent
                  </label>
                </div>
              </div>
            </div>
          </div>
          <div className="block-value-section">
            <div className="block-value-label">Content:</div>
            <div className="block-value">{block.value}</div>
          </div>
        </div>
        <div className="modal-footer">
          <button onClick={onDelete} className="button-delete">
            Delete
          </button>
          <button onClick={onEdit} className="button-primary" disabled={block.read_only}>
            Edit
          </button>
        </div>
      </div>
    </div>
  );
}

// Block Create Modal
interface BlockCreateModalProps {
  onClose: () => void;
  onCreate: (data: JournalBlockCreate) => void;
}

function BlockCreateModal({ onClose, onCreate }: BlockCreateModalProps) {
  const [label, setLabel] = useState('');
  const [value, setValue] = useState('');
  const [description, setDescription] = useState('');
  const [readOnly, setReadOnly] = useState(false);
  const [editableByMain, setEditableByMain] = useState(true);
  const [editableByMemory, setEditableByMemory] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      label,
      value,
      description: description || undefined,
      read_only: readOnly,
      editable_by_main_agent: editableByMain,
      editable_by_memory_agent: editableByMemory,
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h2>Create Journal Block</h2>
            <button type="button" onClick={onClose} className="modal-close">
              ×
            </button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label>Label *</label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g., User Preferences"
                required
              />
            </div>
            <div className="form-group">
              <label>Description</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of this block's purpose"
              />
            </div>
            <div className="form-group">
              <label>Content *</label>
              <textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Block content..."
                rows={8}
                required
              />
            </div>
            <div className="form-group">
              <label>Access Control</label>
              <div className="access-flags">
                <label>
                  <input
                    type="checkbox"
                    checked={readOnly}
                    onChange={(e) => setReadOnly(e.target.checked)}
                  />
                  Read-only
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={editableByMain}
                    onChange={(e) => setEditableByMain(e.target.checked)}
                  />
                  Editable by main agent
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={editableByMemory}
                    onChange={(e) => setEditableByMemory(e.target.checked)}
                  />
                  Editable by memory agent
                </label>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" onClick={onClose} className="button-secondary">
              Cancel
            </button>
            <button type="submit" className="button-primary">
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Block Edit Modal
interface BlockEditModalProps {
  block: JournalBlock;
  onClose: () => void;
  onSave: (value: string) => void;
}

function BlockEditModal({ block, onClose, onSave }: BlockEditModalProps) {
  const [value, setValue] = useState(block.value);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(value);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h2>Edit: {block.label}</h2>
            <button type="button" onClick={onClose} className="modal-close">
              ×
            </button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label>Content</label>
              <textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                rows={12}
                required
              />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" onClick={onClose} className="button-secondary">
              Cancel
            </button>
            <button type="submit" className="button-primary">
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
