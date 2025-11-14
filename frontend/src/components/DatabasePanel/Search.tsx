import { useState } from 'react';
import { searchAPI } from '../../api/ragAPI';
import type { SearchResult } from '../../types/rag';
import './Search.css';

interface SearchProps {
  agentId: string;
}

export default function Search({ agentId }: SearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [filters, setFilters] = useState({
    semantic: true,
    fullText: true,
    sourceTypes: [] as string[],
  });

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();

    if (!query.trim()) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setSearched(true);

      const response = await searchAPI.search({
        query: query.trim(),
        agent_id: agentId,
        source_types: filters.sourceTypes.length > 0 ? filters.sourceTypes : undefined,
        limit: 20,
        semantic: filters.semantic,
        full_text: filters.fullText,
      });

      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleSourceType = (type: string) => {
    setFilters(prev => ({
      ...prev,
      sourceTypes: prev.sourceTypes.includes(type)
        ? prev.sourceTypes.filter(t => t !== type)
        : [...prev.sourceTypes, type],
    }));
  };

  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'rag_chunk':
        return '📄';
      case 'journal_block':
        return '📝';
      case 'message':
        return '💬';
      default:
        return '📋';
    }
  };

  const getSourceLabel = (type: string) => {
    switch (type) {
      case 'rag_chunk':
        return 'File';
      case 'journal_block':
        return 'Journal';
      case 'message':
        return 'Message';
      default:
        return type;
    }
  };

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="search-panel">
      <form onSubmit={handleSearch} className="search-form">
        <div className="search-input-container">
          <input
            type="text"
            className="search-input"
            placeholder="Search across files, journals, and messages..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            className="search-button"
            disabled={loading || !query.trim()}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '4px', verticalAlign: 'text-bottom' }}>
              <path d="M10.25 2a8.25 8.25 0 0 1 6.34 13.53l5.69 5.69a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215l-5.69-5.69A8.25 8.25 0 1 1 10.25 2ZM3.5 10.25a6.75 6.75 0 1 0 13.5 0 6.75 6.75 0 0 0-13.5 0Z" />
            </svg>
            Search
          </button>
        </div>

        <div className="search-filters">
          <div className="filter-group">
            <span className="filter-label">Search Type:</span>
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.semantic}
                onChange={(e) => setFilters({ ...filters, semantic: e.target.checked })}
              />
              Semantic
            </label>
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.fullText}
                onChange={(e) => setFilters({ ...filters, fullText: e.target.checked })}
              />
              Full-text
            </label>
          </div>

          <div className="filter-group">
            <span className="filter-label">Sources:</span>
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.sourceTypes.includes('rag_chunk')}
                onChange={() => toggleSourceType('rag_chunk')}
              />
              Files
            </label>
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.sourceTypes.includes('journal_block')}
                onChange={() => toggleSourceType('journal_block')}
              />
              Journals
            </label>
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.sourceTypes.includes('message')}
                onChange={() => toggleSourceType('message')}
              />
              Messages
            </label>
          </div>
        </div>
      </form>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">×</button>
        </div>
      )}

      <div className="search-results">
        {!searched && (
          <div className="search-empty-state">
            <div className="empty-icon">🔍</div>
            <p>Search across all your indexed content</p>
            <p className="hint">Files, journals, and conversation history</p>
          </div>
        )}

        {searched && !loading && results.length === 0 && (
          <div className="search-empty-state">
            <div className="empty-icon">🤷</div>
            <p>No results found for "{query}"</p>
            <p className="hint">Try different keywords or adjust your filters</p>
          </div>
        )}

        {loading && (
          <div className="search-loading">
            <div className="loading-spinner">⟳</div>
            <p>Searching...</p>
          </div>
        )}

        {searched && !loading && results.length > 0 && (
          <>
            <div className="search-results-header">
              <span>Found {results.length} result{results.length !== 1 ? 's' : ''}</span>
            </div>

            <div className="result-list">
              {results.map(result => (
                <div key={result.id} className="result-item">
                  <div className="result-header">
                    <span className="result-source">
                      {getSourceIcon(result.source_type)} {getSourceLabel(result.source_type)}
                    </span>
                    <span className="result-score">
                      {(result.score * 100).toFixed(0)}% match
                    </span>
                  </div>

                  <div className="result-title">{result.title}</div>

                  <div className="result-snippet">{result.snippet}</div>

                  <div className="result-footer">
                    <span className="result-date">{formatDate(result.created_at)}</span>
                    {result.metadata && Object.keys(result.metadata).length > 0 && (
                      <span className="result-meta">
                        {Object.entries(result.metadata)
                          .slice(0, 2)
                          .map(([key, value]) => `${key}: ${value}`)
                          .join(' • ')}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
