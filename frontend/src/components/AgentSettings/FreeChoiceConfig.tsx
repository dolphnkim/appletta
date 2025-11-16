import { useState } from 'react';
import type { FreeChoiceConfig as FreeChoiceConfigType } from '../../types/agent';
import './LLMConfig.css'; // Reuse the same styles

interface FreeChoiceConfigProps {
  config: FreeChoiceConfigType;
  onUpdate: (updates: Partial<FreeChoiceConfigType>) => void;
}

export default function FreeChoiceConfig({
  config,
  onUpdate,
}: FreeChoiceConfigProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleIntervalChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({ interval_minutes: parseInt(e.target.value, 10) });
  };

  const formatLastSession = () => {
    if (!config.last_session_at) return 'Never';
    const date = new Date(config.last_session_at);
    return date.toLocaleString();
  };

  return (
    <div className="config-section">
      <button
        className="config-section-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="config-section-title">
          FREE CHOICE MODE
          {config.enabled && <span className="config-status-badge enabled">ON</span>}
        </span>
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
          {/* Enable Toggle */}
          <div className="config-item">
            <div className="config-label">
              Enable Free Choice
              <span className="help-icon" title="Allow agent to explore, research, and learn autonomously">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={(e) => onUpdate({ enabled: e.target.checked })}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-label">{config.enabled ? 'On' : 'Off'}</span>
            </label>
          </div>

          {/* Interval Slider */}
          <div className="config-item">
            <div className="config-label">
              Session Interval (minutes)
              <span className="help-icon" title="How often the agent gets free choice time">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
                </svg>
              </span>
            </div>
            <div className="slider-container">
              <input
                type="range"
                className="slider"
                min="1"
                max="120"
                step="1"
                value={config.interval_minutes}
                onChange={handleIntervalChange}
              />
              <span className="slider-value">{config.interval_minutes} min</span>
            </div>
          </div>

          {/* Last Session Info */}
          <div className="config-item">
            <div className="config-label">Last Session</div>
            <div className="config-value-display">{formatLastSession()}</div>
          </div>

          {/* Info Box */}
          <div className="config-info-box">
            <p>
              When enabled, the agent will have free choice sessions where they can:
            </p>
            <ul>
              <li>Search the web for interesting topics</li>
              <li>Review and organize their journal blocks</li>
              <li>Search through past conversations</li>
              <li>Chat with attached agents</li>
            </ul>
            <p className="info-note">
              Sessions are triggered by the app polling - only runs when the app is open.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
