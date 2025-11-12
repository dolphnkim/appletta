import { useState, useEffect } from 'react';
import { journalAPI } from '../../api/journalAPI';
import type { JournalBlock, JournalBlockCreate } from '../../types/journal';
import './JournalBlocks.css';

interface JournalBlocksProps {
  agentId: string;
}

type EditorMode = 'none' | 'create' | 'view' | 'edit';

export default function JournalBlocks({ agentId }: JournalBlocksProps) {
  const [blocks, setBlocks] = useState<JournalBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<JournalBlock | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>('none');

  // Form state
  const [formLabel, setFormLabel] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formCharLimit, setFormCharLimit] = useState(5000);
  const [formReadOnly, setFormReadOnly] = useState(false);
  const [formEditableByMain, setFormEditableByMain] = useState(true);
  const [formEditableByMemory, setFormEditableByMemory] = useState(false);

  useEffect(() => {
    loadBlocks();
  }, [agentId]);

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

  const handleNewBlock = () => {
    setEditorMode('create');
    setSelectedBlock(null);
    // Reset form
    setFormLabel('');
    setFormValue('');
    setFormDescription('');
    setFormCharLimit(5000);
    setFormReadOnly(false);
    setFormEditableByMain(true);
    setFormEditableByMemory(false);
  };

  const handleSelectBlock = (block: JournalBlock) => {
    setSelectedBlock(block);
    setEditorMode('view');
    // Load into form for potential editing
    setFormLabel(block.label);
    setFormValue(block.value);
    setFormDescription(block.description || '');
    setFormReadOnly(block.read_only);
    setFormEditableByMain(block.editable_by_main_agent);
    setFormEditableByMemory(block.editable_by_memory_agent);
  };

  const handleEditBlock = () => {
    setEditorMode('edit');
  };

  const handleCancelEdit = () => {
    if (selectedBlock) {
      setEditorMode('view');
      // Restore original values
      setFormLabel(selectedBlock.label);
      setFormValue(selectedBlock.value);
      setFormDescription(selectedBlock.description || '');
      setFormReadOnly(selectedBlock.read_only);
      setFormEditableByMain(selectedBlock.editable_by_main_agent);
      setFormEditableByMemory(selectedBlock.editable_by_memory_agent);
    } else {
      setEditorMode('none');
    }
  };

  const handleCreate = async () => {
    if (!formLabel.trim() || !formValue.trim()) {
      setError('Label and Value are required');
      return;
    }

    try {
      const newBlock = await journalAPI.create(agentId, {
        label: formLabel,
        value: formValue,
        description: formDescription || undefined,
        read_only: formReadOnly,
        editable_by_main_agent: formEditableByMain,
        editable_by_memory_agent: formEditableByMemory,
      });
      setBlocks([newBlock, ...blocks]);
      setSelectedBlock(newBlock);
      setEditorMode('view');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create journal block');
    }
  };

  const handleUpdate = async () => {
    if (!selectedBlock) return;

    try {
      const updated = await journalAPI.update(agentId, selectedBlock.id, {
        label: formLabel,
        value: formValue,
        description: formDescription || undefined,
        read_only: formReadOnly,
        editable_by_main_agent: formEditableByMain,
        editable_by_memory_agent: formEditableByMemory,
      });
      setBlocks(blocks.map((b) => (b.id === selectedBlock.id ? updated : b)));
      setSelectedBlock(updated);
      setEditorMode('view');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update journal block');
    }
  };

  const handleDelete = async () => {
    if (!selectedBlock) return;
    if (!confirm('Delete this journal block? This cannot be undone.')) return;

    try {
      await journalAPI.delete(agentId, selectedBlock.id);
      setBlocks(blocks.filter((b) => b.id !== selectedBlock.id));
      setSelectedBlock(null);
      setEditorMode('none');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete journal block');
    }
  };

  const handleCopyBlockId = () => {
    if (selectedBlock) {
      navigator.clipboard.writeText(selectedBlock.block_id);
    }
  };

  if (loading) {
    return (
      <div className="journal-blocks-container">
        <div className="journal-loading">Loading journal blocks...</div>
      </div>
    );
  }

  return (
    <div className="journal-blocks-container">
      {/* Left side - Block list */}
      <div className="journal-blocks-list-panel">
        <div className="journal-list-header">
          <h3>Journal Block Editor</h3>
          <button onClick={handleNewBlock} className="new-block-button">
            + New block
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
              <p>No journal blocks yet</p>
              <p className="hint">Click "+ New block" to create one</p>
            </div>
          ) : (
            blocks.map((block) => (
              <div
                key={block.id}
                className={`journal-block-item ${
                  selectedBlock?.id === block.id ? 'active' : ''
                }`}
                onClick={() => handleSelectBlock(block)}
              >
                <div className="block-item-header">
                  <div className="block-label">{block.label}</div>
                  {block.read_only && <span className="badge-readonly">👁️</span>}
                </div>
                <div className="block-item-preview">
                  {block.value.substring(0, 60)}...
                </div>
                <div className="block-item-chars">{block.value.length} Chars</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right side - Editor */}
      <div className="journal-editor-panel">
        {editorMode === 'none' ? (
          <div className="journal-editor-empty">
            <p>Select a block to view or edit</p>
            <p className="hint">Or create a new block</p>
          </div>
        ) : (
          <>
            <div className="journal-editor-header">
              <h3>{editorMode === 'create' ? 'New Block' : selectedBlock?.label}</h3>
              <div className="journal-editor-actions">
                {editorMode === 'view' && (
                  <>
                    <button onClick={handleEditBlock} className="btn-edit" disabled={selectedBlock?.read_only}>
                      Edit label ✏️
                    </button>
                    <button onClick={handleCopyBlockId} className="btn-copy">
                      Copy block_id 📋
                    </button>
                    <button onClick={handleDelete} className="btn-delete">
                      🗑️
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="journal-editor-form">
              {/* Label */}
              <div className="form-field">
                <label>Label</label>
                <input
                  type="text"
                  value={formLabel}
                  onChange={(e) => setFormLabel(e.target.value)}
                  disabled={editorMode === 'view'}
                  placeholder="e.g., human"
                />
              </div>

              {/* Block ID (view only) */}
              {editorMode !== 'create' && selectedBlock && (
                <div className="form-field">
                  <label>Block ID</label>
                  <input
                    type="text"
                    value={selectedBlock.block_id}
                    disabled
                    className="monospace"
                  />
                </div>
              )}

              {/* Character Limit */}
              <div className="form-field">
                <label>Character Limit</label>
                <input
                  type="number"
                  value={formCharLimit}
                  onChange={(e) => setFormCharLimit(Number(e.target.value))}
                  disabled={editorMode === 'view'}
                />
              </div>

              {/* Description */}
              <div className="form-field">
                <label>
                  Description{' '}
                  <span className="field-hint">
                    ⓘ A short description to help you remember what this block is for
                  </span>
                </label>
                <input
                  type="text"
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  disabled={editorMode === 'view'}
                  placeholder="Brief description..."
                />
              </div>

              {/* Value */}
              <div className="form-field form-field-large">
                <label>Value</label>
                <textarea
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  disabled={editorMode === 'view'}
                  placeholder="Block content..."
                  rows={12}
                  maxLength={formCharLimit}
                />
                <div className="char-count">
                  {formValue.length} / {formCharLimit} Chars
                </div>
              </div>

              {/* Read-only checkbox */}
              <div className="form-field-checkbox">
                <label>
                  <input
                    type="checkbox"
                    checked={formReadOnly}
                    onChange={(e) => setFormReadOnly(e.target.checked)}
                    disabled={editorMode === 'view'}
                  />
                  <span>
                    Read-only{' '}
                    <span className="checkbox-hint">
                      ⓘ CLAUDE: optional read-only checkbox or toggle for blocks agents can't edit
                    </span>
                  </span>
                </label>
              </div>

              {/* Action buttons */}
              <div className="journal-editor-footer">
                {editorMode === 'create' && (
                  <>
                    <button onClick={handleCancelEdit} className="btn-secondary">
                      Cancel
                    </button>
                    <button onClick={handleCreate} className="btn-primary">
                      Create Block
                    </button>
                  </>
                )}
                {editorMode === 'edit' && (
                  <>
                    <button onClick={handleCancelEdit} className="btn-secondary">
                      Cancel
                    </button>
                    <button onClick={handleUpdate} className="btn-primary">
                      Update memory
                    </button>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
