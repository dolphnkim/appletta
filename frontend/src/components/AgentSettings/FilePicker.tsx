import { useState, useRef, useEffect } from 'react';
import { filesAPI } from '../../api/agentAPI';
import type { FileItem } from '../../types/agent';
import './FilePicker.css';

interface FilePickerProps {
  label: string;
  value: string;
  onSelect: (path: string) => void;
  helpText?: string;
  required?: boolean;
  selectFolders?: boolean;  // If true, can select folders; if false, only files
}

export default function FilePicker({
  label,
  value,
  onSelect,
  helpText,
  required = false,
  selectFolders = false,
}: FilePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState('');
  const [items, setItems] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const loadPath = async (path?: string) => {
    try {
      setLoading(true);
      setError(null);
      const response = await filesAPI.browse(path);
      setCurrentPath(response.current_path);
      setItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    setIsOpen(true);
    if (items.length === 0) {
      // Load home directory or suggested paths
      loadPath();
    }
  };

  const handleItemClick = (item: FileItem) => {
    if (item.is_directory) {
      if (selectFolders) {
        // For folder selection, allow selecting the folder
        loadPath(item.path);
      } else {
        // For file selection, navigate into the folder
        loadPath(item.path);
      }
    } else {
      // Always allow selecting files when not in folder-only mode
      if (!selectFolders) {
        onSelect(item.path);
        setIsOpen(false);
      }
    }
  };

  const handleSelectCurrentFolder = () => {
    // Select the current folder when in folder selection mode
    if (selectFolders && currentPath) {
      onSelect(currentPath);
      setIsOpen(false);
    }
  };

  const handleParentClick = () => {
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/';
    loadPath(parentPath);
  };

  return (
    <div className="file-picker">
      <div className="field-label">
        {label}
        {required && <span className="required-mark">*</span>}
        {helpText && (
          <span className="help-icon" title={helpText}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.92 6.085h.001a.75.75 0 1 1-1.342-.67c.169-.339.436-.701.849-.977C6.845 4.16 7.369 4 8 4a2.756 2.756 0 0 1 1.638.525c.503.377.862.965.862 1.725 0 .448-.115.83-.329 1.15-.205.307-.47.513-.692.662-.109.072-.22.138-.313.195l-.006.004a6.24 6.24 0 0 0-.26.16.952.952 0 0 0-.216.16.577.577 0 0 0-.119.1.334.334 0 0 0-.049.07l-.007.012-.004.006-.001.003v.001a.75.75 0 0 1-1.442-.412l.001-.003.004-.007.013-.024a1.334 1.334 0 0 1 .184-.213c.096-.096.223-.196.371-.297a4.88 4.88 0 0 1 .195-.122c.172-.106.353-.213.516-.334.316-.235.484-.505.484-.78 0-.336-.17-.59-.431-.772A1.25 1.25 0 0 0 8 5.5c-.444 0-.736.095-.95.214-.214.119-.377.27-.483.437ZM7.25 11a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z" />
            </svg>
          </span>
        )}
      </div>
      {helpText && <div className="field-help-text">{helpText}</div>}

      <div className="file-picker-dropdown" ref={dropdownRef}>
        <div className="file-picker-button-group">
          <button
            className="file-picker-button"
            onClick={handleOpen}
          >
            {value || (selectFolders ? 'Choose folder...' : 'Choose file...')}
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z" />
            </svg>
          </button>
          {!required && value && (
            <button
              className="file-picker-clear-button"
              onClick={() => onSelect('')}
              title="Clear selection"
            >
              ×
            </button>
          )}
        </div>

        {isOpen && (
          <div className="file-picker-menu">
            {loading ? (
              <div className="file-picker-loading">Loading...</div>
            ) : error ? (
              <div className="file-picker-error">{error}</div>
            ) : (
              <>
                <div className="file-picker-path">
                  {currentPath}
                  <div className="path-actions">
                    {selectFolders && (
                      <button
                        className="select-folder-button"
                        onClick={handleSelectCurrentFolder}
                        title="Select this folder"
                      >
                        ✓ Select
                      </button>
                    )}
                    {currentPath !== '/' && (
                      <button
                        className="path-up-button"
                        onClick={handleParentClick}
                        title="Go up one directory"
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M7.78 12.53a.75.75 0 01-1.06 0L2.47 8.28a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 1.06L4.81 7h7.44a.75.75 0 010 1.5H4.81l2.97 2.97a.75.75 0 010 1.06z" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
                <div className="file-picker-items">
                  {items.map((item) => (
                    <button
                      key={item.path}
                      className={`file-picker-item ${item.is_directory ? 'directory' : 'file'}`}
                      onClick={() => handleItemClick(item)}
                    >
                      {item.is_directory ? (
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
                        </svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0113.25 16h-9.5A1.75 1.75 0 012 14.25V1.75z" />
                        </svg>
                      )}
                      <span className="item-name">{item.name}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
