import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './VSCodeIntegrationView.css';

interface VSCodeStatus {
  mlx_available: boolean;
  model_loaded: boolean;
  model_path: string | null;
  is_moe: boolean;
  endpoint: string;
  provider_config: {
    name: string;
    api_base_url: string;
    api_key: string;
    models: string[];
  };
}

interface BrowseItem {
  name: string;
  path: string;
  is_dir: boolean;
  is_model?: boolean;
  is_adapter?: boolean;
}

export default function VSCodeIntegrationView() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<VSCodeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Model loading
  const [modelPath, setModelPath] = useState('');
  const [adapterPath, setAdapterPath] = useState('');
  const [loadingModel, setLoadingModel] = useState(false);

  // File browser
  const [showFileBrowser, setShowFileBrowser] = useState(false);
  const [fileBrowserMode, setFileBrowserMode] = useState<'model' | 'adapter'>('model');
  const [currentBrowsePath, setCurrentBrowsePath] = useState<string>('~');
  const [browseItems, setBrowseItems] = useState<BrowseItem[]>([]);
  const [browseParent, setBrowseParent] = useState<string | null>(null);

  // Config display
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await fetch('http://localhost:8000/v1/status');
      if (!response.ok) throw new Error('Failed to fetch status');
      const data = await response.json();
      setStatus(data);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadModel = async () => {
    if (!modelPath) {
      setError('Please provide a model path');
      return;
    }

    setLoadingModel(true);
    setError(null);

    try {
      const params = new URLSearchParams({ model_path: modelPath });
      if (adapterPath) {
        params.append('adapter_path', adapterPath);
      }

      const response = await fetch(`http://localhost:8000/v1/load-model?${params}`, {
        method: 'POST',
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to load model');
      }

      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoadingModel(false);
    }
  };

  const browseDirectory = async (path: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/v1/router-lens/browse/directory?path=${encodeURIComponent(path)}`);
      if (!response.ok) throw new Error('Failed to browse directory');
      const data = await response.json();
      setCurrentBrowsePath(data.path);
      setBrowseItems(data.items);
      setBrowseParent(data.parent);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const openFileBrowser = async (mode: 'model' | 'adapter') => {
    setFileBrowserMode(mode);
    setShowFileBrowser(true);

    // Start in appropriate directory
    const startPath = mode === 'model'
      ? '~/.cache/huggingface/hub'
      : '~/appletta/adapters';
    await browseDirectory(startPath);
  };

  const selectPath = (item: BrowseItem) => {
    if (fileBrowserMode === 'model') {
      setModelPath(item.path);
    } else {
      setAdapterPath(item.path);
    }
    setShowFileBrowser(false);
  };

  const generateRouterConfig = () => {
    if (!status?.provider_config) return '';

    const config = {
      name: "appletta",
      api_base_url: "http://localhost:8000/v1/chat/completions",
      api_key: "appletta",
      models: status.model_path ? [status.model_path] : ["mlx-model"]
    };

    return JSON.stringify(config, null, 2);
  };

  const generateFullConfig = () => {
    const providerConfig = {
      name: "appletta",
      api_base_url: "http://localhost:8000/v1/chat/completions",
      api_key: "appletta",
      models: status?.model_path ? [status.model_path] : ["mlx-model"]
    };

    const routerConfig = {
      default: `appletta,${status?.model_path || 'mlx-model'}`,
      background: `appletta,${status?.model_path || 'mlx-model'}`,
      think: `appletta,${status?.model_path || 'mlx-model'}`,
      longContext: `appletta,${status?.model_path || 'mlx-model'}`,
      webSearch: `appletta,${status?.model_path || 'mlx-model'}`
    };

    return `// Add to Providers array in ~/.claude-code-router/config.json:
${JSON.stringify(providerConfig, null, 2)}

// Update Router config to use Appletta:
${JSON.stringify(routerConfig, null, 2)}`;
  };

  const copyConfig = async () => {
    await navigator.clipboard.writeText(generateFullConfig());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="vscode-view">
        <div className="loading">Loading VS Code Integration status...</div>
      </div>
    );
  }

  return (
    <div className="vscode-view">
      <header className="vscode-header">
        <button className="back-button" onClick={() => navigate('/')}>
          ← Dashboard
        </button>
        <h1>VS Code Integration</h1>
        <p>Use local MLX models with Claude Code via claude-code-router</p>
      </header>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="vscode-content">
        {/* Status Section */}
        <section className="status-section">
          <h2>Status</h2>
          <div className="status-grid">
            <div className={`status-item ${status?.mlx_available ? 'online' : 'offline'}`}>
              <span className="status-label">MLX</span>
              <span className="status-value">
                {status?.mlx_available ? 'Available' : 'Not Installed'}
              </span>
            </div>
            <div className={`status-item ${status?.model_loaded ? 'online' : 'offline'}`}>
              <span className="status-label">Model</span>
              <span className="status-value">
                {status?.model_loaded ? 'Loaded' : 'Not Loaded'}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Endpoint</span>
              <span className="status-value endpoint">
                {status?.endpoint || 'http://localhost:8000/v1/chat/completions'}
              </span>
            </div>
            {status?.is_moe && (
              <div className="status-item moe">
                <span className="status-label">MoE</span>
                <span className="status-value">Active</span>
              </div>
            )}
          </div>
        </section>

        {/* Model Loading Section */}
        <section className="load-model-section">
          <h2>Load Model</h2>
          <p className="section-description">
            Load an MLX model to serve through the OpenAI-compatible API.
          </p>

          <div className="model-form">
            <div className="form-group">
              <label>Model Path</label>
              <div className="input-with-browse">
                <input
                  type="text"
                  value={modelPath}
                  onChange={(e) => setModelPath(e.target.value)}
                  placeholder="~/.cache/huggingface/hub/model-name"
                />
                <button onClick={() => openFileBrowser('model')}>Browse</button>
              </div>
            </div>

            <div className="form-group">
              <label>Adapter Path (Optional)</label>
              <div className="input-with-browse">
                <input
                  type="text"
                  value={adapterPath}
                  onChange={(e) => setAdapterPath(e.target.value)}
                  placeholder="~/appletta/adapters/adapter-name"
                />
                <button onClick={() => openFileBrowser('adapter')}>Browse</button>
              </div>
            </div>

            <button
              className="load-button"
              onClick={loadModel}
              disabled={loadingModel || !modelPath}
            >
              {loadingModel ? 'Loading...' : 'Load Model'}
            </button>
          </div>

          {status?.model_loaded && status?.model_path && (
            <div className="current-model">
              <strong>Currently Loaded:</strong> {status.model_path}
              {status.is_moe && <span className="moe-badge">MoE</span>}
            </div>
          )}
        </section>

        {/* Configuration Section */}
        <section className="config-section">
          <h2>Claude Code Router Configuration</h2>
          <p className="section-description">
            Add this provider configuration to your <code>~/.claude-code-router/config.json</code> file
            to route Claude Code requests to your local MLX model.
          </p>

          <div className="config-display">
            <div className="config-header">
              <span>Configuration</span>
              <button onClick={copyConfig} className="copy-button">
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <pre>{generateFullConfig()}</pre>
          </div>

          <div className="setup-steps">
            <h3>Setup Steps</h3>
            <ol>
              <li>Install claude-code-router: <code>npm install -g @musistudio/claude-code-router</code></li>
              <li>Initialize config: <code>ccr init</code></li>
              <li>Add the Appletta provider config above to your <code>config.json</code></li>
              <li>Start the router: <code>ccr start</code></li>
              <li>Launch Claude Code with the router proxy</li>
            </ol>
          </div>
        </section>

        {/* API Testing Section */}
        <section className="api-test-section">
          <h2>API Endpoints</h2>
          <div className="api-endpoints">
            <div className="endpoint-item">
              <code>POST /v1/chat/completions</code>
              <span>OpenAI-compatible chat endpoint</span>
            </div>
            <div className="endpoint-item">
              <code>GET /v1/models</code>
              <span>List available models</span>
            </div>
            <div className="endpoint-item">
              <code>POST /v1/load-model</code>
              <span>Load/switch models</span>
            </div>
            <div className="endpoint-item">
              <code>GET /v1/status</code>
              <span>Integration status</span>
            </div>
          </div>
        </section>
      </div>

      {/* File Browser Modal */}
      {showFileBrowser && (
        <div className="modal-overlay" onClick={() => setShowFileBrowser(false)}>
          <div className="file-browser-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Select {fileBrowserMode === 'model' ? 'Model' : 'Adapter'} Directory</h3>
              <button onClick={() => setShowFileBrowser(false)}>×</button>
            </div>

            <div className="current-path">
              <strong>Path:</strong> {currentBrowsePath}
            </div>

            <div className="browser-content">
              {browseParent && (
                <div
                  className="browser-item parent-dir"
                  onClick={() => browseDirectory(browseParent)}
                >
                  <span className="item-icon">📁</span>
                  <span className="item-name">..</span>
                </div>
              )}

              {browseItems.map((item) => (
                <div
                  key={item.path}
                  className={`browser-item ${item.is_dir ? 'directory' : 'file'} ${
                    item.is_model ? 'is-model' : ''
                  } ${item.is_adapter ? 'is-adapter' : ''}`}
                  onClick={() => {
                    if (item.is_dir) {
                      if (item.is_model || item.is_adapter) {
                        selectPath(item);
                      } else {
                        browseDirectory(item.path);
                      }
                    }
                  }}
                >
                  <span className="item-icon">
                    {item.is_model ? '🤖' : item.is_adapter ? '🔧' : item.is_dir ? '📁' : '📄'}
                  </span>
                  <span className="item-name">{item.name}</span>
                  {item.is_model && <span className="item-badge model">Model</span>}
                  {item.is_adapter && <span className="item-badge adapter">Adapter</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
