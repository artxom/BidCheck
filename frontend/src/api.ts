import type {
  AppSettings,
  ChecklistItem,
  ChatMessage,
  DeterministicFinding,
  OutlineSectionLite,
  ProjectDetail,
  ProjectListItem,
  ProviderPreset,
  RoleDefinition,
  SectionDetail,
  WorkspaceSample,
} from './types';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.detail) detail = String(errBody.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: () => requestJson<{ projects: ProjectListItem[] }>('/api/projects'),

  createProject: (name = '新建项目') =>
    requestJson<{ project: ProjectDetail }>('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),

  getProject: (id: string) => requestJson<{ project: ProjectDetail }>(`/api/projects/${id}`),

  deleteProject: (id: string) =>
    requestJson<{ deleted: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),

  listWorkspaceSamples: () => requestJson<{ samples: WorkspaceSample[] }>('/api/workspace-samples'),

  uploadDocument: (
    projectId: string,
    docRole: 'tender' | 'response',
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<{ project: ProjectDetail }> =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/projects/${projectId}/documents/upload`);
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable && onProgress) {
          onProgress(Math.round((ev.loaded / ev.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || `上传失败 (${xhr.status})`));
          } catch {
            reject(new Error(`上传失败 (${xhr.status})`));
          }
        }
      };
      xhr.onerror = () => reject(new Error('网络异常，上传中断'));
      const fd = new FormData();
      fd.append('doc_role', docRole);
      fd.append('file', file);
      xhr.send(fd);
    }),

  mountLocalSample: (projectId: string, docRole: 'tender' | 'response', filename: string) =>
    requestJson<{ project: ProjectDetail }>(`/api/projects/${projectId}/documents/mount-local`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_role: docRole, filename }),
    }),

  sendChat: (projectId: string, message: string) =>
    requestJson<{ message: ChatMessage; project: ProjectDetail }>(`/api/projects/${projectId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }),

  triggerPlan: (projectId: string, targetLot?: string) =>
    requestJson<{ message: ChatMessage; project: ProjectDetail }>(`/api/projects/${projectId}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_lot: targetLot || null }),
    }),

  startRun: (projectId: string, recheckOnly = false) =>
    requestJson<{ started: boolean }>(`/api/projects/${projectId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recheck_only: recheckOnly }),
    }),

  toggleItem: (projectId: string, itemId: string, enabled: boolean) =>
    requestJson<{ item: ChecklistItem }>(`/api/projects/${projectId}/checklist/${itemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }),

  getOutline: (projectId: string) =>
    requestJson<{ sections: OutlineSectionLite[]; deterministic_findings: DeterministicFinding[] }>(
      `/api/projects/${projectId}/outline`,
    ),

  getSection: (projectId: string, sectionId: string) =>
    requestJson<{ section: SectionDetail }>(`/api/projects/${projectId}/sections/${sectionId}`),

  getSettings: () =>
    requestJson<{
      settings: AppSettings;
      presets: ProviderPreset[];
      roles: RoleDefinition[];
      storage: { cache_bytes: number; cache_mb: number };
    }>('/api/settings'),

  saveSettings: (settings: AppSettings) =>
    requestJson<{ settings: AppSettings }>('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),

  testConnection: (baseUrl: string, apiKey: string, model: string) =>
    requestJson<{ ok: boolean; latency_ms: number; reply: string; model: string }>(
      '/api/settings/test',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model }),
      },
    ),

  clearCache: () =>
    requestJson<{ freed_mb: number; storage: { cache_bytes: number; cache_mb: number } }>(
      '/api/settings/clear-cache',
      { method: 'POST' },
    ),
};
