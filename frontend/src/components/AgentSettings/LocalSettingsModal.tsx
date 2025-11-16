import { useState, useEffect } from 'react';
import { getLocalConfig, setLocalConfig } from '../../stores/localConfig';
import FilePicker from './FilePicker';
import './LocalSettingsModal.css';

interface LocalSettingsModalProps {
  onClose: () => void;
}

export default function LocalSettingsModal({ onClose }: LocalSettingsModalProps) {
  const [config, setConfig] = useState(getLocalConfig());

  useEffect(() => {
    setConfig(getLocalConfig());
  }, []);

  const handleSave = () => {
    setLocalConfig(config);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="local-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Local Settings</h2>
          <button onClick={onClose} className="modal-close">
            ×
          </button>
        </div>
        <div className="modal-body">
          <p className="settings-info">
            Configure default paths for file pickers. These settings are stored locally in your browser.
          </p>

          <FilePicker
            label="Default Model Folder"
            value={config.default_model_folder}
            onSelect={(path) => setConfig({ ...config, default_model_folder: path })}
            helpText="The folder where your MLX models are stored"
            selectFolders={true}
          />

          <FilePicker
            label="Default Adapter Folder"
            value={config.default_adapter_folder}
            onSelect={(path) => setConfig({ ...config, default_adapter_folder: path })}
            helpText="The folder where your adapters are stored (optional, defaults to model folder)"
            selectFolders={true}
            defaultPath={config.default_model_folder}
          />
        </div>
        <div className="modal-footer">
          <button onClick={onClose} className="button-secondary">
            Cancel
          </button>
          <button onClick={handleSave} className="button-primary">
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
