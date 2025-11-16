/**
 * Local configuration store using localStorage
 * For user preferences that persist across sessions
 */

export interface LocalConfig {
  default_model_folder: string;
  default_adapter_folder: string;
  // Add more local settings as needed
}

const DEFAULT_CONFIG: LocalConfig = {
  default_model_folder: '',
  default_adapter_folder: '',
};

const STORAGE_KEY = 'appletta_local_config';

export function getLocalConfig(): LocalConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
    }
  } catch (err) {
    console.error('Failed to load local config:', err);
  }
  return DEFAULT_CONFIG;
}

export function setLocalConfig(updates: Partial<LocalConfig>): LocalConfig {
  const current = getLocalConfig();
  const updated = { ...current, ...updates };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function getConfigValue<K extends keyof LocalConfig>(key: K): LocalConfig[K] {
  return getLocalConfig()[key];
}

export function setConfigValue<K extends keyof LocalConfig>(key: K, value: LocalConfig[K]): void {
  setLocalConfig({ [key]: value });
}
