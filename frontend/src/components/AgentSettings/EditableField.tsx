import { useState } from 'react';
import './EditableField.css';

interface EditableFieldProps {
  label: string;
  value: string;
  onSave: (value: string) => void;
  helpText?: string;
  multiline?: boolean;
  required?: boolean;
}

export default function EditableField({
  label,
  value,
  onSave,
  helpText,
  multiline = false,
  required = false,
}: EditableFieldProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedValue, setEditedValue] = useState(value);

  const handleSave = () => {
    if (required && !editedValue.trim()) {
      return;
    }
    if (editedValue !== value) {
      onSave(editedValue);
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditedValue(value);
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !multiline) {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  return (
    <div className="editable-field">
      <div className="field-label">
        {label}
        {helpText && (
          <span className="help-icon" title={helpText}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
            </svg>
          </span>
        )}
      </div>
      {helpText && <div className="field-help-text">{helpText}</div>}
      <div className="field-value">
        {isEditing ? (
          multiline ? (
            <textarea
              className="field-input"
              value={editedValue}
              onChange={(e) => setEditedValue(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyDown}
              autoFocus
              rows={3}
            />
          ) : (
            <input
              type="text"
              className="field-input"
              value={editedValue}
              onChange={(e) => setEditedValue(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          )
        ) : (
          <div className="field-display" onClick={() => setIsEditing(true)}>
            {value || <span className="field-placeholder">Click to edit</span>}
          </div>
        )}
      </div>
    </div>
  );
}
