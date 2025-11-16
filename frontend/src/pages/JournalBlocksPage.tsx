import { useState, useEffect } from 'react';

interface JournalBlock {
  id: string;
  label: string;
  block_id: string;
  description: string | null;
  value: string;
  read_only: boolean;
  always_in_context: boolean;
  created_at: string;
  updated_at: string;
}

const JournalBlocksPage = () => {
  const [blocks, setBlocks] = useState<JournalBlock[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchBlocks();
  }, []);

  const fetchBlocks = async () => {
    try {
      // TODO: Update to global blocks endpoint
      const response = await fetch('http://localhost:8000/api/v1/journal-blocks/');
      if (response.ok) {
        const data = await response.json();
        setBlocks(data.blocks || []);
      }
    } catch (error) {
      console.error('Failed to fetch journal blocks:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div>
        <h1 style={{ color: '#fff', marginBottom: '20px' }}>Journal Blocks</h1>
        <p style={{ color: '#888' }}>Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ color: '#fff', margin: 0 }}>Journal Blocks</h1>
        <button
          style={{
            background: '#4a9eff',
            color: '#fff',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          + New Block
        </button>
      </div>

      {blocks.length === 0 ? (
        <p style={{ color: '#888' }}>No journal blocks yet. Create one to get started.</p>
      ) : (
        <div style={{ display: 'grid', gap: '16px' }}>
          {blocks.map((block) => (
            <div
              key={block.id}
              style={{
                background: '#2a2a2a',
                borderRadius: '8px',
                padding: '16px',
                border: '1px solid #3a3a3a',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h3 style={{ color: '#fff', margin: 0 }}>{block.label}</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {block.read_only && (
                    <span style={{ color: '#888', fontSize: '0.8rem' }}>Read-only</span>
                  )}
                  {block.always_in_context && (
                    <span style={{ color: '#4a9eff', fontSize: '0.8rem' }}>Always in context</span>
                  )}
                </div>
              </div>
              {block.description && (
                <p style={{ color: '#888', fontSize: '0.9rem', marginBottom: '8px' }}>{block.description}</p>
              )}
              <div
                style={{
                  background: '#1e1e1e',
                  padding: '12px',
                  borderRadius: '4px',
                  maxHeight: '200px',
                  overflow: 'auto',
                }}
              >
                <pre style={{ color: '#e0e0e0', margin: 0, whiteSpace: 'pre-wrap', fontSize: '0.9rem' }}>
                  {block.value}
                </pre>
              </div>
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <button
                  style={{
                    background: '#3a3a3a',
                    color: '#e0e0e0',
                    border: 'none',
                    padding: '6px 12px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                  }}
                >
                  Edit
                </button>
                <button
                  style={{
                    background: '#3a3a3a',
                    color: '#e0e0e0',
                    border: 'none',
                    padding: '6px 12px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default JournalBlocksPage;
