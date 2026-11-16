import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import { TopToolbar } from './components/TopToolbar';
import { Sidebar } from './components/Sidebar';
import { MasterChatPane } from './components/MasterChatPane';
import { InspectorPane, type InspectorTab } from './components/InspectorPane';
import { SettingsModal } from './components/SettingsModal';
import type {
  ChatMessage,
  ChecklistItem,
  DeterministicFinding,
  InspectionReport,
  OutlineSectionLite,
  ProjectDetail,
  ProjectListItem,
  TelemetrySnapshot,
  WorkspaceSample,
} from './types';

export const App: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [activeProject, setActiveProject] = useState<ProjectDetail | null>(null);
  const [samples, setSamples] = useState<WorkspaceSample[]>([]);
  const [cacheMb, setCacheMb] = useState(0);

  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('live');
  const [selectedItem, setSelectedItem] = useState<ChecklistItem | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [outline, setOutline] = useState<OutlineSectionLite[]>([]);
  const [detFindings, setDetFindings] = useState<DeterministicFinding[]>([]);

  const [uploadingRole, setUploadingRole] = useState<'tender' | 'response' | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [sendingChat, setSendingChat] = useState(false);

  const refreshProjectList = useCallback(async () => {
    const res = await api.listProjects();
    setProjects(res.projects);
    return res.projects;
  }, []);

  const loadOutline = useCallback(async (projId: string) => {
    try {
      const res = await api.getOutline(projId);
      setOutline(res.sections);
      setDetFindings(res.deterministic_findings);
    } catch {
      setOutline([]);
      setDetFindings([]);
    }
  }, []);

  const selectProject = useCallback(
    async (projId: string) => {
      const res = await api.getProject(projId);
      setActiveProject(res.project);
      setSelectedItem(null);
      setSelectedSectionId(null);
      setInspectorTab(res.project.report ? 'report' : 'live');
      if (res.project.response_doc) {
        loadOutline(projId);
      } else {
        setOutline([]);
        setDetFindings([]);
      }
    },
    [loadOutline],
  );

  // Initial bootstrap + Cmd+, keyboard shortcut for Settings
  useEffect(() => {
    (async () => {
      const [, sampleRes, settingsRes] = await Promise.all([
        Promise.resolve(),
        api.listWorkspaceSamples(),
        api.getSettings(),
      ]);
      setSamples(sampleRes.samples);
      setCacheMb(settingsRes.storage.cache_mb);

      const list = await refreshProjectList();
      if (list.length > 0) {
        await selectProject(list[0].id);
      } else {
        const created = await api.createProject();
        await refreshProjectList();
        setActiveProject(created.project);
      }
    })();

    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault();
        setSettingsOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [refreshProjectList, selectProject]);

  // Real-time SSE connection per active project
  useEffect(() => {
    const projId = activeProject?.id;
    if (!projId) return;

    const es = new EventSource(`/api/projects/${projId}/events`);

    es.addEventListener('telemetry', (ev) => {
      const tel: TelemetrySnapshot = JSON.parse((ev as MessageEvent).data);
      setActiveProject((prev) =>
        prev && prev.id === projId ? { ...prev, stage: tel.stage, telemetry: tel } : prev,
      );
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projId
            ? {
                ...p,
                stage: tel.stage,
                progress_pct: tel.progress_pct,
                total_tokens: tel.total_tokens,
              }
            : p,
        ),
      );
    });

    es.addEventListener('item_updated', (ev) => {
      const updatedItem: ChecklistItem = JSON.parse((ev as MessageEvent).data);
      setActiveProject((prev) => {
        if (!prev || prev.id !== projId) return prev;
        const exists = prev.checklist.some((i) => i.item_id === updatedItem.item_id);
        const nextList = exists
          ? prev.checklist.map((i) => (i.item_id === updatedItem.item_id ? updatedItem : i))
          : [...prev.checklist, updatedItem];
        return { ...prev, checklist: nextList };
      });
      setSelectedItem((prev) => (prev?.item_id === updatedItem.item_id ? updatedItem : prev));
    });

    es.addEventListener('checklist_replaced', (ev) => {
      const payload: { items: ChecklistItem[] } = JSON.parse((ev as MessageEvent).data);
      setActiveProject((prev) =>
        prev && prev.id === projId ? { ...prev, checklist: payload.items } : prev,
      );
      refreshProjectList();
      api.getProject(projId).then((r) => {
        setActiveProject((cur) =>
          cur && cur.id === projId
            ? { ...cur, name: r.project.name, target_lot: r.project.target_lot }
            : cur,
        );
      });
    });

    es.addEventListener('chat_message', (ev) => {
      const msg: ChatMessage = JSON.parse((ev as MessageEvent).data);
      setActiveProject((prev) => {
        if (!prev || prev.id !== projId) return prev;
        if (prev.messages.some((m) => m.id === msg.id)) return prev;
        return { ...prev, messages: [...prev.messages, msg] };
      });
    });

    es.addEventListener('report_ready', (ev) => {
      const rep: InspectionReport = JSON.parse((ev as MessageEvent).data);
      setActiveProject((prev) =>
        prev && prev.id === projId ? { ...prev, report: rep, stage: 'completed' } : prev,
      );
      setInspectorTab('report');
      refreshProjectList();
    });

    es.addEventListener('doc_mounted', () => {
      loadOutline(projId);
      refreshProjectList();
    });

    return () => {
      es.close();
    };
  }, [activeProject?.id, loadOutline, refreshProjectList]);

  const handleCreateProject = async () => {
    const res = await api.createProject();
    await refreshProjectList();
    setActiveProject(res.project);
    setOutline([]);
    setDetFindings([]);
    setSelectedItem(null);
    setInspectorTab('live');
  };

  const handleDeleteProject = async (id: string) => {
    await api.deleteProject(id);
    const list = await refreshProjectList();
    if (activeProject?.id === id) {
      if (list.length > 0) {
        await selectProject(list[0].id);
      } else {
        await handleCreateProject();
      }
    }
  };

  const handleUploadFile = async (role: 'tender' | 'response', file: File) => {
    if (!activeProject) return;
    setUploadingRole(role);
    setUploadPct(0);
    try {
      const res = await api.uploadDocument(activeProject.id, role, file, setUploadPct);
      setActiveProject(res.project);
      if (res.project.response_doc) loadOutline(activeProject.id);
      await refreshProjectList();
      const sRes = await api.getSettings();
      setCacheMb(sRes.storage.cache_mb);
    } catch (err) {
      alert(err instanceof Error ? err.message : '文档导入失败');
    } finally {
      setUploadingRole(null);
      setUploadPct(0);
    }
  };

  const handleMountSample = async (role: 'tender' | 'response', filename: string) => {
    if (!activeProject) return;
    setUploadingRole(role);
    setUploadPct(60);
    try {
      const res = await api.mountLocalSample(activeProject.id, role, filename);
      setActiveProject(res.project);
      if (res.project.response_doc) loadOutline(activeProject.id);
      await refreshProjectList();
    } catch (err) {
      alert(err instanceof Error ? err.message : '挂载失败');
    } finally {
      setUploadingRole(null);
      setUploadPct(0);
    }
  };

  const handleSendMessage = async (msg: string) => {
    if (!activeProject) return;
    setSendingChat(true);
    try {
      await api.sendChat(activeProject.id, msg);
    } catch {
      // Error bubble already pushed via backend SSE
    } finally {
      setSendingChat(false);
    }
  };

  const handleStartRun = async (recheckOnly: boolean) => {
    if (!activeProject) return;
    setInspectorTab('live');
    try {
      await api.startRun(activeProject.id, recheckOnly);
    } catch (err) {
      alert(err instanceof Error ? err.message : '启动检查失败');
    }
  };

  const handleToggleItem = async (itemId: string, enabled: boolean) => {
    if (!activeProject) return;
    await api.toggleItem(activeProject.id, itemId, enabled);
  };

  const handleInspectEvidence = (item: ChecklistItem | null, sectionId?: string) => {
    setSelectedItem(item);
    setSelectedSectionId(sectionId || item?.matched_sections[0]?.section_id || null);
    setInspectorTab('evidence');
  };

  const handleClearCache = async () => {
    const res = await api.clearCache();
    setCacheMb(res.storage.cache_mb);
  };

  const isRunning =
    activeProject?.telemetry.stage === 'inspecting' ||
    activeProject?.telemetry.stage === 'planning' ||
    activeProject?.telemetry.stage === 'assembling_report';

  return (
    <div className="w-screen h-screen flex flex-col bg-[#F5F5F7] overflow-hidden">
      <TopToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        project={activeProject}
        telemetry={activeProject?.telemetry || null}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="flex-1 flex min-h-0">
        {sidebarOpen && (
          <Sidebar
            projects={projects}
            activeId={activeProject?.id || null}
            onSelect={selectProject}
            onCreate={handleCreateProject}
            onDelete={handleDeleteProject}
            cacheMb={cacheMb}
            onClearCache={handleClearCache}
          />
        )}

        {activeProject && (
          <>
            <MasterChatPane
              project={activeProject}
              samples={samples}
              uploadingRole={uploadingRole}
              uploadPct={uploadPct}
              sendingChat={sendingChat}
              onUploadFile={handleUploadFile}
              onMountSample={handleMountSample}
              onSendMessage={handleSendMessage}
              onStartRun={handleStartRun}
              onSwitchInspectorTab={setInspectorTab}
            />

            <InspectorPane
              projectId={activeProject.id}
              activeTab={inspectorTab}
              onChangeTab={setInspectorTab}
              checklist={activeProject.checklist}
              report={activeProject.report}
              deterministicFindings={detFindings}
              outline={outline}
              isRunning={Boolean(isRunning)}
              selectedItem={selectedItem}
              selectedSectionId={selectedSectionId}
              onToggleItem={handleToggleItem}
              onInspectEvidence={handleInspectEvidence}
              onSelectSectionId={setSelectedSectionId}
            />
          </>
        )}
      </main>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
};
