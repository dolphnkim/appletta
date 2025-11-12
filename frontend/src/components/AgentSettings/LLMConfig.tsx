import { useState } from 'react';
import type { LLMConfig as LLMConfigType } from '../../types/agent';
import FilePicker from './FilePicker';
import SystemInstructionsField from './SystemInstructionsField';
import './LLMConfig.css';

interface LLMConfigProps {
  config: LLMConfigType;
  onUpdate: (updates: Partial<LLMConfigType>) => void;
  modelPath: string;
  adapterPath: string;
  systemInstructions: string;
  onModelPathUpdate: (path: string) => void;
  onAdapterPathUpdate: (path: string) => void;
  onSystemInstructionsClick: () => void;
}

export default function LLMConfig({
  config,
  onUpdate,
  modelPath,
  adapterPath,
  systemInstructions,
  onModelPathUpdate,
  onAdapterPathUpdate,
  onSystemInstructionsClick
}: LLMConfigProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleTemperatureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({ temperature: parseFloat(e.target.value) });
  };

  const handleTopPChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({ top_p: parseFloat(e.target.value) });
  };

  const handleTopKChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({ top_k: parseInt(e.target.value, 10) });
  };

  const handleSeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    onUpdate({ seed: value ? parseInt(value, 10) : undefined });
  };

  const handleMaxTokensChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({ max_output_tokens: parseInt(e.target.value, 10) });
  };

  return (
    <div className="config-section">
      <button
        className="config-section-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="config-section-title">LLM CONFIG</span>
        <svg
          className={`expand-icon ${isExpanded ? 'expanded' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z" />
        </svg>
      </button>

      {isExpanded && (
        <div className="config-section-content">
          {/* Model Path */}
          <FilePicker
            label="Model"
            value={modelPath}
            onSelect={onModelPathUpdate}
            helpText="choose model from filepath"
            required
          />

          {/* Adapter Path */}
          <FilePicker
            label="Adapter"
            value={adapterPath}
            onSelect={onAdapterPathUpdate}
            helpText="choose adapter folder"
            selectFolders={true}
          />

          {/* System Instructions */}
          <SystemInstructionsField
            value={systemInstructions}
            onClick={onSystemInstructionsClick}
          />

          {/* Reasoning Toggle */}
          <div className="config-item">
            <div className="config-label">
              Reasoning
              <span className="help-icon" title="Enable reasoning mode with <think> tags">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={config.reasoning_enabled}
                onChange={(e) => onUpdate({ reasoning_enabled: e.target.checked })}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-label">{config.reasoning_enabled ? 'On' : 'Off'}</span>
            </label>
          </div>

          {/* Temperature Slider */}
          <div className="config-item">
            <div className="config-label">
              Temperature
              <span className="help-icon" title="Controls randomness (0.0 = deterministic, 2.0 = very random)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <div className="slider-container">
              <input
                type="range"
                className="slider"
                min="0"
                max="2"
                step="0.1"
                value={config.temperature}
                onChange={handleTemperatureChange}
              />
              <span className="slider-value">{config.temperature.toFixed(1)}</span>
            </div>
          </div>

          {/* Top P Slider */}
          <div className="config-item">
            <div className="config-label">
              Top P
              <span className="help-icon" title="Nucleus sampling: only sample from top tokens with cumulative probability P (0.0-1.0)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <div className="slider-container">
              <input
                type="range"
                className="slider"
                min="0"
                max="1"
                step="0.05"
                value={config.top_p}
                onChange={handleTopPChange}
              />
              <span className="slider-value">{config.top_p.toFixed(2)}</span>
            </div>
          </div>

          {/* Top K Slider */}
          <div className="config-item">
            <div className="config-label">
              Top K
              <span className="help-icon" title="Sample from top K tokens (0 = disabled, higher = more diversity)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <div className="slider-container">
              <input
                type="range"
                className="slider"
                min="0"
                max="100"
                step="1"
                value={config.top_k}
                onChange={handleTopKChange}
              />
              <span className="slider-value">{config.top_k}</span>
            </div>
          </div>

          {/* Seed Input */}
          <div className="config-item">
            <div className="config-label">
              Seed
              <span className="help-icon" title="Random seed for reproducible outputs">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <input
              type="number"
              className="number-input"
              value={config.seed ?? ''}
              onChange={handleSeedChange}
              placeholder="Optional"
            />
          </div>

          {/* Max Output Tokens Toggle */}
          <div className="config-item">
            <div className="config-label">
              Enable max output tokens
              <span className="help-icon" title="Limit the maximum number of tokens generated">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={config.max_output_tokens_enabled}
                onChange={(e) => onUpdate({ max_output_tokens_enabled: e.target.checked })}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-label">{config.max_output_tokens_enabled ? 'On' : 'Off'}</span>
            </label>
          </div>

          {/* Max Output Tokens Slider */}
          {config.max_output_tokens_enabled && (
            <div className="config-item">
              <div className="config-label">
                Max output tokens
                <span className="help-icon" title="Maximum number of tokens to generate">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                  </svg>
                </span>
              </div>
              <div className="slider-container">
                <input
                  type="range"
                  className="slider"
                  min="256"
                  max="32768"
                  step="256"
                  value={config.max_output_tokens}
                  onChange={handleMaxTokensChange}
                />
                <span className="slider-value">{config.max_output_tokens}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
