import type { RagFolder, RagFolderCreate, RagFolderUpdate, RagFile, SearchQuery, SearchResponse } from '../types/rag';

const API_BASE = '/api/v1';

async function fetchAPI<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const ragAPI = {
  // Folder management
  attachFolder: (data: RagFolderCreate): Promise<RagFolder> =>
    fetchAPI('/rag/folders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listFolders: (agentId: string): Promise<RagFolder[]> =>
    fetchAPI(`/rag/folders?agent_id=${agentId}`),

  getFolder: (folderId: string): Promise<RagFolder> =>
    fetchAPI(`/rag/folders/${folderId}`),

  updateFolder: (folderId: string, data: RagFolderUpdate): Promise<RagFolder> =>
    fetchAPI(`/rag/folders/${folderId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  detachFolder: (folderId: string): Promise<{ message: string }> =>
    fetchAPI(`/rag/folders/${folderId}`, {
      method: 'DELETE',
    }),

  // File management
  listFiles: (folderId: string): Promise<RagFile[]> =>
    fetchAPI(`/rag/folders/${folderId}/files`),

  scanFolder: (folderId: string): Promise<any> =>
    fetchAPI(`/rag/folders/${folderId}/scan`, {
      method: 'POST',
    }),

  deleteFile: (fileId: string): Promise<{ message: string }> =>
    fetchAPI(`/rag/files/${fileId}`, {
      method: 'DELETE',
    }),
};

export const searchAPI = {
  search: (query: SearchQuery): Promise<SearchResponse> =>
    fetchAPI('/search', {
      method: 'POST',
      body: JSON.stringify(query),
    }),
};
