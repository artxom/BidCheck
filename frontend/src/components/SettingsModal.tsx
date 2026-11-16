import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  Check,
  Loader2,
  Wifi,
  Plus,
  Eye,
  EyeOff,
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  ChevronsUpDown,
  Search,
} from 'lucide-react';
import { api } from '../api';
import type { ThemeMode } from '../theme';
import type {
  AppSettings,
  ProviderConfig,
  RemoteModelInfo,
  RoleDefinition,
  RoleRouteConfig,
} from '../types';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  themeMode: ThemeMode;
  onChangeThemeMode: (mode: ThemeMode) => void;
}

interface ModelPickerProps {
  roleIndex: number;
  provider: ProviderConfig | undefined;
  currentModel: string;
  models: RemoteModelInfo[];
  loading: boolean;
  error: string;
  isVisionRole: boolean;
  isOpen: boolean;
  onToggleOpen: () => void;
  onClosePopover: () => void;
  onRefresh: () => void;
  onSelectModel: (modelId: string, remoteInfo?: RemoteModelInfo) => void;
  onGoConfigureKey: () => void;
}

const ModelPicker: React.FC<ModelPickerProps> = ({
  roleIndex,
  provider,
  currentModel,
  models,
  loading,
  error,
  isVisionRole,
  isOpen,
  onToggleOpen,
  onClosePopover,
  onRefresh,
  onSelectModel,
  onGoConfigureKey,
}) => {
  const [query, setQuery] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      return;
    }
    const timer = setTimeout(() => searchRef.current?.focus(), 20);
    const handleOutside = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        onClosePopover();
      }
    };
    window.addEventListener('mousedown', handleOutside);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('mousedown', handleOutside);
    };
  }, [isOpen, onClosePopover]);

  const hasKey = Boolean(provider?.api_key.trim() && provider?.base_url.trim());
  const matchedRemote = models.find((m) => m.id === currentModel);

  const q = query.trim().toLowerCase();
  const ordered = isVisionRole
    ? [...models].sort((a, b) => Number(b.vision) - Number(a.vision) || a.id.localeCompare(b.id))
    : models;
  const filtered = q ? ordered.filter((m) => m.id.toLowerCase().includes(q)) : ordered;
  const exactMatch = q ? models.some((m) => m.id.toLowerCase() === q) : true;
  const openUpward = roleIndex >= 2;

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center justify-between mb-0.5">
        <label className="text-[10.5px] text-[#8E8E93]">模型</label>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || !hasKey}
          title="从 API 刷新模型列表"
          className="text-[10px] text-[#8E8E93] hover:text-[#007AFF] dark:hover:text-[#409CFF] disabled:opacity-40 flex items-center gap-0.5 transition-colors"
        >
          <RefreshCw className={`w-2.5 h-2.5 ${loading ? 'animate-spin' : ''}`} />
          <span>刷新</span>
        </button>
      </div>

      <button
        type="button"
        onClick={onToggleOpen}
        className="w-full h-[30px] rounded-[6px] macos-input px-2 text-left flex items-center justify-between gap-1.5 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] outline-none"
      >
        <span className="flex items-center gap-1 min-w-0 flex-1">
          <span className="truncate font-mono">{currentModel || '选择模型'}</span>
          {matchedRemote?.vision && (
            <span className="px-1 py-[0.5px] rounded-[3px] bg-[#007AFF]/12 dark:bg-[#0A84FF]/20 text-[#007AFF] dark:text-[#409CFF] text-[9.5px] font-semibold shrink-0">
              VL
            </span>
          )}
        </span>
        <ChevronsUpDown className="w-3 h-3 text-[#8E8E93] shrink-0" />
      </button>

      {isOpen && (
        <div
          className={`absolute left-0 ${
            openUpward ? 'bottom-full mb-1' : 'top-full mt-1'
          } w-[310px] max-w-[80vw] rounded-[10px] macos-popover p-1.5 z-50`}
        >
          <div className="flex items-center gap-1.5 px-2 h-[28px] rounded-[6px] macos-input mb-1.5">
            <Search className="w-3 h-3 text-[#8E8E93] shrink-0" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && query.trim()) {
                  e.preventDefault();
                  const first = filtered[0];
                  if (first && exactMatch) {
                    onSelectModel(first.id, first);
                  } else if (first && filtered.length === 1) {
                    onSelectModel(first.id, first);
                  } else {
                    onSelectModel(query.trim());
                  }
                  onClosePopover();
                } else if (e.key === 'Escape') {
                  e.stopPropagation();
                  onClosePopover();
                }
              }}
              placeholder="搜索模型或输入接入点…"
              className="flex-1 min-w-0 bg-transparent text-[11.5px] text-[#1D1D1F] dark:text-[#F5F5F7] placeholder:text-[#8E8E93] outline-none font-mono"
            />
          </div>

          {!hasKey ? (
            <div className="py-3 px-2 text-center space-y-2">
              <div className="text-[11.5px] text-[#8E8E93]">未配置供应商密钥</div>
              <button
                type="button"
                onClick={() => {
                  onClosePopover();
                  onGoConfigureKey();
                }}
                className="h-[26px] px-3 rounded-[6px] macos-btn-primary text-[11.5px] font-medium"
              >
                先去配置 API Key
              </button>
            </div>
          ) : loading && models.length === 0 ? (
            <div className="py-4 flex items-center justify-center gap-1.5 text-[11.5px] text-[#8E8E93]">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
              <span>拉取模型列表…</span>
            </div>
          ) : error && models.length === 0 ? (
            <div className="py-2.5 px-2 space-y-2 text-center">
              <div className="text-[11px] text-[#DC2626] dark:text-[#FF6961] break-words">
                {error}
              </div>
              <button
                type="button"
                onClick={onRefresh}
                className="h-[24px] px-2.5 rounded-[5px] macos-btn-secondary text-[11px] text-[#1D1D1F] dark:text-[#F5F5F7]"
              >
                重试
              </button>
            </div>
          ) : (
            <div className="max-h-[168px] overflow-y-auto space-y-0.5">
              {filtered.map((m) => {
                const selected = m.id === currentModel;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      onSelectModel(m.id, m);
                      onClosePopover();
                    }}
                    className={`w-full text-left px-2 py-1.5 rounded-[6px] text-[11.5px] flex items-center justify-between gap-2 transition-colors ${
                      selected
                        ? 'bg-[#007AFF] dark:bg-[#0A84FF] text-white'
                        : 'text-[#1D1D1F] dark:text-[#F5F5F7] hover:bg-black/[0.05] dark:hover:bg-white/[0.08]'
                    }`}
                  >
                    <span className="flex items-center gap-1.5 min-w-0 flex-1">
                      <Check
                        className={`w-3 h-3 shrink-0 ${
                          selected ? 'opacity-100' : 'opacity-0'
                        }`}
                      />
                      <span className="truncate font-mono">{m.id}</span>
                    </span>

                    <span className="flex items-center gap-1 shrink-0">
                      {m.vision && (
                        <span
                          className={`px-1 py-[0.5px] rounded-[3px] text-[9.5px] font-semibold ${
                            selected
                              ? 'bg-white/20 text-white'
                              : 'bg-[#007AFF]/12 dark:bg-[#0A84FF]/20 text-[#007AFF] dark:text-[#409CFF]'
                          }`}
                        >
                          VL
                        </span>
                      )}
                      {m.input_price !== null && m.output_price !== null && (
                        <span
                          className={`text-[10px] tabular-nums ${
                            selected ? 'text-white/80' : 'text-[#8E8E93]'
                          }`}
                        >
                          ¥{m.input_price}/{m.output_price}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}

              {!exactMatch && query.trim() && (
                <button
                  type="button"
                  onClick={() => {
                    onSelectModel(query.trim());
                    onClosePopover();
                  }}
                  className="w-full text-left px-2 py-1.5 rounded-[6px] text-[11.5px] text-[#007AFF] dark:text-[#409CFF] hover:bg-[#007AFF]/10 dark:hover:bg-[#0A84FF]/15 font-mono truncate"
                >
                  使用 &ldquo;{query.trim()}&rdquo;
                </button>
              )}

              {filtered.length === 0 && !query.trim() && (
                <div className="py-3 text-center text-[11.5px] text-[#8E8E93]">暂无可用模型</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  onClose,
  themeMode,
  onChangeThemeMode,
}) => {
  const [tab, setTab] = useState<'providers' | 'routes'>('providers');
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [selectedProvId, setSelectedProvId] = useState<string>('dashscope');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testModel, setTestModel] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const [modelsByProv, setModelsByProv] = useState<Record<string, RemoteModelInfo[]>>({});
  const [loadingProv, setLoadingProv] = useState<Record<string, boolean>>({});
  const [provModelErr, setProvModelErr] = useState<Record<string, string>>({});
  const [openPickerRole, setOpenPickerRole] = useState<string | null>(null);

  const loadModelsForProvider = useCallback(
    async (prov: ProviderConfig, forceRefresh = false) => {
      const base = prov.base_url.trim();
      const key = prov.api_key.trim();
      if (!base || !key) return;

      setLoadingProv((prev) => ({ ...prev, [prov.id]: true }));
      setProvModelErr((prev) => ({ ...prev, [prov.id]: '' }));
      try {
        const res = await api.fetchModels({
          provider_id: prov.id,
          base_url: base,
          api_key: key,
          force_refresh: forceRefresh,
        });
        setModelsByProv((prev) => ({ ...prev, [prov.id]: res.models }));
      } catch (err) {
        setProvModelErr((prev) => ({
          ...prev,
          [prov.id]: err instanceof Error ? err.message : '拉取失败',
        }));
      } finally {
        setLoadingProv((prev) => ({ ...prev, [prov.id]: false }));
      }
    },
    [],
  );

  useEffect(() => {
    if (!open) {
      setOpenPickerRole(null);
      return;
    }
    api.getSettings().then((res) => {
      setSettings(res.settings);
      setRoles(res.roles);
      if (res.settings.providers.length > 0) {
        const firstProv = res.settings.providers[0];
        setSelectedProvId(firstProv.id);
        if (firstProv.api_key.trim() && firstProv.base_url.trim()) {
          loadModelsForProvider(firstProv);
        }
      }
    });

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, loadModelsForProvider]);

  // Auto-fetch model lists for configured providers when switching to routes tab
  useEffect(() => {
    if (!open || !settings || tab !== 'routes') return;
    for (const p of settings.providers) {
      if (
        p.api_key.trim() &&
        p.base_url.trim() &&
        !modelsByProv[p.id] &&
        !loadingProv[p.id] &&
        !provModelErr[p.id]
      ) {
        loadModelsForProvider(p);
      }
    }
  }, [open, tab, settings, modelsByProv, loadingProv, provModelErr, loadModelsForProvider]);

  if (!open || !settings) return null;

  const activeProv =
    settings.providers.find((p) => p.id === selectedProvId) || settings.providers[0];
  const activeModels = activeProv ? modelsByProv[activeProv.id] || [] : [];
  const activeModelLoading = activeProv ? Boolean(loadingProv[activeProv.id]) : false;
  const activeModelErr = activeProv ? provModelErr[activeProv.id] || '' : '';

  const updateProvider = (patch: Partial<ProviderConfig>) => {
    if (!activeProv) return;
    setSettings({
      ...settings,
      providers: settings.providers.map((p) =>
        p.id === activeProv.id ? { ...p, ...patch } : p,
      ),
    });
    setTestResult(null);
  };

  const handleSelectProvider = (prov: ProviderConfig) => {
    setSelectedProvId(prov.id);
    setTestResult(null);
    setTestModel('');
    if (
      prov.api_key.trim() &&
      prov.base_url.trim() &&
      !modelsByProv[prov.id] &&
      !loadingProv[prov.id]
    ) {
      loadModelsForProvider(prov);
    }
  };

  const addCustomProvider = () => {
    const newId = `custom_${Date.now().toString(36).slice(-4)}`;
    const newProv: ProviderConfig = {
      id: newId,
      name: '自定义网关',
      base_url: 'https://api.openai.com/v1',
      api_key: '',
      currency: 'CNY',
      enabled: true,
    };
    setSettings({ ...settings, providers: [...settings.providers, newProv] });
    setSelectedProvId(newId);
    setTestModel('');
    setTestResult(null);
  };

  const updateRoute = (roleKey: string, patch: Partial<RoleRouteConfig>) => {
    const current = settings.routes[roleKey];
    if (!current) return;
    setSettings({
      ...settings,
      routes: {
        ...settings.routes,
        [roleKey]: { ...current, ...patch },
      },
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.saveSettings(settings);
      setSettings(res.settings);
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 1600);
    } finally {
      setSaving(false);
    }
  };

  const effectiveTestModel =
    (activeModels.length > 0 && activeModels.some((m) => m.id === testModel)
      ? testModel
      : activeModels[0]?.id) ||
    testModel.trim() ||
    Object.values(settings.routes).find((r) => r.provider_id === activeProv?.id)?.model ||
    '';

  const handleTest = async () => {
    if (!activeProv || !effectiveTestModel) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testConnection(
        activeProv.base_url,
        activeProv.api_key,
        effectiveTestModel,
      );
      setTestResult({ ok: true, msg: `正常 · ${res.latency_ms}ms (${res.model})` });
    } catch (err) {
      setTestResult({ ok: false, msg: err instanceof Error ? err.message : '连接失败' });
    } finally {
      setTesting(false);
    }
  };

  const appearanceOptions: { mode: ThemeMode; label: string; icon: React.ReactNode }[] = [
    { mode: 'light', label: '浅色', icon: <Sun className="w-3 h-3" /> },
    { mode: 'dark', label: '深色', icon: <Moon className="w-3 h-3" /> },
    { mode: 'system', label: '自动', icon: <Monitor className="w-3 h-3" /> },
  ];

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 bg-black/35 dark:bg-black/60 backdrop-blur-[3px] z-50 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[740px] max-w-full h-[560px] max-h-[90vh] rounded-[14px] bg-[#F4F4F6] dark:bg-[#1C1C20] shadow-[0_28px_70px_rgba(0,0,0,0.28)] dark:shadow-[0_32px_80px_rgba(0,0,0,0.68)] border border-black/[0.1] dark:border-white/[0.12] flex flex-col overflow-hidden"
      >
        {/* macOS System Settings Titlebar */}
        <div className="h-[46px] px-4 macos-toolbar flex items-center justify-between shrink-0">
          <span className="text-[13px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
            设置
          </span>

          <div className="macos-segmented p-[2px] rounded-[7px] flex items-center gap-0.5">
            <button
              onClick={() => {
                setTab('providers');
                setOpenPickerRole(null);
              }}
              className={`px-3 py-1 rounded-[5px] text-[12px] font-medium transition-all ${
                tab === 'providers'
                  ? 'macos-segmented-active text-[#1D1D1F] dark:text-[#F5F5F7]'
                  : 'text-[#6E6E73] dark:text-[#98989D]'
              }`}
            >
              供应商
            </button>
            <button
              onClick={() => setTab('routes')}
              className={`px-3 py-1 rounded-[5px] text-[12px] font-medium transition-all ${
                tab === 'routes'
                  ? 'macos-segmented-active text-[#1D1D1F] dark:text-[#F5F5F7]'
                  : 'text-[#6E6E73] dark:text-[#98989D]'
              }`}
            >
              模型路由
            </button>
          </div>

          <button
            onClick={onClose}
            className="w-6 h-6 rounded-full hover:bg-black/[0.06] dark:hover:bg-white/[0.1] text-[#6E6E73] dark:text-[#98989D] flex items-center justify-center transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Body */}
        {tab === 'providers' ? (
          <div className="flex-1 flex min-h-0">
            {/* Left Provider Source List */}
            <div className="w-[205px] macos-sidebar p-2 flex flex-col">
              <div className="flex-1 overflow-y-auto space-y-0.5">
                {settings.providers.map((p) => {
                  const active = p.id === activeProv?.id;
                  const hasKey = Boolean(p.api_key.trim());
                  return (
                    <button
                      key={p.id}
                      onClick={() => handleSelectProvider(p)}
                      className={`w-full text-left px-2.5 py-[7px] rounded-[7px] text-[12px] flex items-center justify-between transition-all ${
                        active
                          ? 'macos-sidebar-active font-medium'
                          : 'text-[#1D1D1F] dark:text-[#E5E5EA] hover:bg-black/[0.045] dark:hover:bg-white/[0.06]'
                      }`}
                    >
                      <span className="truncate">{p.name}</span>
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${
                          hasKey
                            ? active
                              ? 'bg-white'
                              : 'bg-[#34C759] dark:bg-[#30D158]'
                            : 'bg-black/[0.14] dark:bg-white/[0.16]'
                        }`}
                      />
                    </button>
                  );
                })}
              </div>
              <button
                onClick={addCustomProvider}
                className="mt-2 h-[28px] rounded-[6px] macos-btn-secondary text-[11.5px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7] flex items-center justify-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>添加网关</span>
              </button>
            </div>

            {/* Right Provider Form */}
            {activeProv && (
              <div className="flex-1 p-5 bg-white dark:bg-[#1E1E22] overflow-y-auto space-y-4">
                <div>
                  <label className="block text-[11px] font-medium text-[#8E8E93] mb-1">
                    名称
                  </label>
                  <input
                    value={activeProv.name}
                    onChange={(e) => updateProvider({ name: e.target.value })}
                    className="w-full h-[32px] px-3 rounded-[7px] macos-input outline-none text-[12.5px] text-[#1D1D1F] dark:text-[#F5F5F7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-[#8E8E93] mb-1">
                    Base URL
                  </label>
                  <input
                    value={activeProv.base_url}
                    onChange={(e) => updateProvider({ base_url: e.target.value })}
                    onBlur={() => {
                      if (activeProv.base_url.trim() && activeProv.api_key.trim()) {
                        loadModelsForProvider(activeProv, true);
                      }
                    }}
                    placeholder="https://api.deepseek.com/v1"
                    className="w-full h-[32px] px-3 rounded-[7px] macos-input outline-none text-[12.5px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-[#8E8E93] mb-1">
                    API Key
                  </label>
                  <div className="relative">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={activeProv.api_key}
                      onChange={(e) => updateProvider({ api_key: e.target.value })}
                      onBlur={() => {
                        if (activeProv.base_url.trim() && activeProv.api_key.trim()) {
                          loadModelsForProvider(activeProv, true);
                        }
                      }}
                      placeholder="sk-..."
                      className="w-full h-[32px] pl-3 pr-9 rounded-[7px] macos-input outline-none text-[12.5px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((v) => !v)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8E8E93] hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]"
                    >
                      {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Live Models & Connectivity Test */}
                <div className="pt-2.5 border-t border-black/[0.06] dark:border-white/[0.07] space-y-2.5">
                  <div className="flex items-center gap-2">
                    {activeModels.length > 0 ? (
                      <select
                        value={effectiveTestModel}
                        onChange={(e) => setTestModel(e.target.value)}
                        className="flex-1 min-w-0 h-[30px] px-2.5 rounded-[6px] macos-input macos-select text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono outline-none"
                      >
                        {activeModels.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.id}
                            {m.vision ? ' [VL]' : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={testModel}
                        onChange={(e) => setTestModel(e.target.value)}
                        placeholder="模型 ID"
                        className="flex-1 h-[30px] px-2.5 rounded-[6px] macos-input text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono outline-none"
                      />
                    )}

                    <button
                      type="button"
                      disabled={
                        activeModelLoading ||
                        !activeProv.api_key.trim() ||
                        !activeProv.base_url.trim()
                      }
                      onClick={() => loadModelsForProvider(activeProv, true)}
                      title="拉取模型列表"
                      className="h-[30px] px-2.5 rounded-[6px] macos-btn-secondary disabled:opacity-45 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] flex items-center gap-1"
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 text-[#515154] dark:text-[#AEAEB2] ${
                          activeModelLoading ? 'animate-spin' : ''
                        }`}
                      />
                    </button>

                    <button
                      disabled={testing || !activeProv.api_key.trim() || !effectiveTestModel}
                      onClick={handleTest}
                      className="h-[30px] px-3 rounded-[6px] macos-btn-secondary disabled:opacity-45 text-[12px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7] flex items-center gap-1.5"
                    >
                      {testing ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
                      ) : (
                        <Wifi className="w-3.5 h-3.5 text-[#007AFF] dark:text-[#409CFF]" />
                      )}
                      <span>测试</span>
                    </button>
                  </div>

                  {activeModelLoading && (
                    <div className="text-[11px] text-[#8E8E93]">正在从 API 拉取模型列表…</div>
                  )}
                  {!activeModelLoading && activeModelErr && (
                    <div className="text-[11px] text-[#DC2626] dark:text-[#FF6961] break-words">
                      模型列表：{activeModelErr}
                    </div>
                  )}
                  {!activeModelLoading && !activeModelErr && activeModels.length > 0 && (
                    <div className="text-[11px] text-[#8E8E93] tabular-nums">
                      已从 API 同步 {activeModels.length} 个可用模型
                    </div>
                  )}

                  {testResult && (
                    <div
                      className={`text-[11.5px] px-2.5 py-1.5 rounded-[6px] ${
                        testResult.ok
                          ? 'bg-[#34C759]/12 dark:bg-[#30D158]/18 text-[#15803D] dark:text-[#30D158]'
                          : 'bg-[#FF3B30]/12 dark:bg-[#FF453A]/18 text-[#DC2626] dark:text-[#FF6961]'
                      }`}
                    >
                      {testResult.msg}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* 4-Role Routing Editor */
          <div className="flex-1 overflow-y-auto p-3.5 space-y-2">
            {roles.map((rDef, roleIdx) => {
              const route = settings.routes[rDef.role];
              if (!route) return null;
              const prov = settings.providers.find((p) => p.id === route.provider_id);
              const provModels = modelsByProv[route.provider_id] || [];
              const isPickerOpen = openPickerRole === rDef.role;

              return (
                <div
                  key={rDef.role}
                  className={`relative rounded-[10px] macos-card px-3.5 py-2.5 space-y-2 ${
                    isPickerOpen ? 'z-30' : 'z-0'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[12.5px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
                      {rDef.label}
                    </span>

                    {rDef.role === 'vision_worker' && (
                      <button
                        type="button"
                        onClick={() => updateRoute(rDef.role, { enabled: !route.enabled })}
                        className="flex items-center gap-2 text-[11.5px] text-[#6E6E73] dark:text-[#98989D]"
                      >
                        <span>启用</span>
                        <span
                          className={`w-[30px] h-[17px] rounded-full p-[2px] transition-colors flex items-center ${
                            route.enabled
                              ? 'bg-[#34C759] dark:bg-[#30D158] justify-end'
                              : 'bg-black/[0.15] dark:bg-white/[0.18] justify-start'
                          }`}
                        >
                          <span className="w-[13px] h-[13px] rounded-full bg-white shadow-xs" />
                        </span>
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-12 gap-2 items-center">
                    <div className="col-span-3">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">供应商</label>
                      <select
                        value={route.provider_id}
                        onChange={(e) => {
                          const nextPid = e.target.value;
                          const nextProv = settings.providers.find((p) => p.id === nextPid);
                          const nextModels = modelsByProv[nextPid] || [];
                          const picked =
                            rDef.role === 'vision_worker'
                              ? nextModels.find((m) => m.vision) || nextModels[0]
                              : nextModels[0];

                          updateRoute(rDef.role, {
                            provider_id: nextPid,
                            ...(picked
                              ? {
                                  model: picked.id,
                                  ...(picked.input_price !== null && picked.output_price !== null
                                    ? {
                                        input_price_per_m: picked.input_price,
                                        output_price_per_m: picked.output_price,
                                      }
                                    : {}),
                                }
                              : {}),
                          });

                          if (
                            nextProv &&
                            nextProv.api_key.trim() &&
                            nextProv.base_url.trim() &&
                            !modelsByProv[nextPid] &&
                            !loadingProv[nextPid]
                          ) {
                            loadModelsForProvider(nextProv);
                          }
                        }}
                        className="w-full min-w-0 h-[30px] rounded-[6px] macos-input macos-select pl-2 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] outline-none"
                      >
                        {settings.providers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="col-span-4">
                      <ModelPicker
                        roleIndex={roleIdx}
                        provider={prov}
                        currentModel={route.model}
                        models={provModels}
                        loading={Boolean(loadingProv[route.provider_id])}
                        error={provModelErr[route.provider_id] || ''}
                        isVisionRole={rDef.role === 'vision_worker'}
                        isOpen={isPickerOpen}
                        onToggleOpen={() =>
                          setOpenPickerRole((cur) => (cur === rDef.role ? null : rDef.role))
                        }
                        onClosePopover={() =>
                          setOpenPickerRole((cur) => (cur === rDef.role ? null : cur))
                        }
                        onRefresh={() => prov && loadModelsForProvider(prov, true)}
                        onSelectModel={(modelId, remoteInfo) => {
                          updateRoute(rDef.role, {
                            model: modelId,
                            ...(remoteInfo &&
                            remoteInfo.input_price !== null &&
                            remoteInfo.output_price !== null
                              ? {
                                  input_price_per_m: remoteInfo.input_price,
                                  output_price_per_m: remoteInfo.output_price,
                                }
                              : {}),
                          });
                        }}
                        onGoConfigureKey={() => {
                          setTab('providers');
                          if (prov) handleSelectProvider(prov);
                        }}
                      />
                    </div>

                    <div className="col-span-2">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">并发</label>
                      <input
                        type="number"
                        min={1}
                        max={20}
                        value={route.concurrency}
                        onChange={(e) =>
                          updateRoute(rDef.role, {
                            concurrency: Math.max(1, Number(e.target.value) || 1),
                          })
                        }
                        className="w-full h-[30px] rounded-[6px] macos-input px-2 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] tabular-nums outline-none"
                      />
                    </div>

                    <div className="col-span-3">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">
                        单价 (¥/M)
                      </label>
                      <div className="flex items-center gap-1.5">
                        <div className="flex-1 h-[30px] rounded-[6px] macos-input px-1.5 flex items-center gap-1">
                          <span className="text-[10px] text-[#8E8E93] shrink-0">入</span>
                          <input
                            type="number"
                            step="0.1"
                            value={route.input_price_per_m}
                            onChange={(e) =>
                              updateRoute(rDef.role, {
                                input_price_per_m: Math.max(0, Number(e.target.value) || 0),
                              })
                            }
                            className="w-full min-w-0 bg-transparent text-[11.5px] text-[#1D1D1F] dark:text-[#F5F5F7] tabular-nums outline-none"
                          />
                        </div>
                        <div className="flex-1 h-[30px] rounded-[6px] macos-input px-1.5 flex items-center gap-1">
                          <span className="text-[10px] text-[#8E8E93] shrink-0">出</span>
                          <input
                            type="number"
                            step="0.1"
                            value={route.output_price_per_m}
                            onChange={(e) =>
                              updateRoute(rDef.role, {
                                output_price_per_m: Math.max(0, Number(e.target.value) || 0),
                              })
                            }
                            className="w-full min-w-0 bg-transparent text-[11.5px] text-[#1D1D1F] dark:text-[#F5F5F7] tabular-nums outline-none"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer: Appearance Switcher on Left + Save Actions on Right */}
        <div className="h-[48px] px-4 bg-white/85 dark:bg-[#1E1E22]/85 backdrop-blur-md border-t border-black/[0.08] dark:border-white/[0.08] flex items-center justify-between gap-2.5 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-[11.5px] text-[#8E8E93]">外观</span>
            <div className="macos-segmented p-[2px] rounded-[7px] flex items-center gap-0.5">
              {appearanceOptions.map((opt) => {
                const active = themeMode === opt.mode;
                return (
                  <button
                    key={opt.mode}
                    type="button"
                    onClick={() => onChangeThemeMode(opt.mode)}
                    className={`h-[24px] px-2.5 rounded-[5px] text-[11.5px] font-medium flex items-center gap-1 transition-all ${
                      active
                        ? 'macos-segmented-active text-[#1D1D1F] dark:text-[#F5F5F7]'
                        : 'text-[#6E6E73] dark:text-[#98989D]'
                    }`}
                  >
                    {opt.icon}
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {savedToast && (
              <span className="text-[12px] text-[#34C759] dark:text-[#30D158] flex items-center gap-1 mr-1 font-medium">
                <Check className="w-3.5 h-3.5" />
                <span>已保存</span>
              </span>
            )}
            <button
              onClick={onClose}
              className="h-[29px] px-3.5 rounded-[7px] macos-btn-secondary text-[12px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7]"
            >
              取消
            </button>
            <button
              disabled={saving}
              onClick={handleSave}
              className="h-[29px] px-4 rounded-[7px] macos-btn-primary text-[12px] font-medium flex items-center gap-1.5"
            >
              {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>保存</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
