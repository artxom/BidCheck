import React, { useState, useEffect } from 'react';
import { X, Check, Loader2, Wifi, Plus, Eye, EyeOff, Sun, Moon, Monitor } from 'lucide-react';
import { api } from '../api';
import type { ThemeMode } from '../theme';
import type {
  AppSettings,
  ProviderConfig,
  ProviderPreset,
  RoleDefinition,
  RoleRouteConfig,
} from '../types';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  themeMode: ThemeMode;
  onChangeThemeMode: (mode: ThemeMode) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  onClose,
  themeMode,
  onChangeThemeMode,
}) => {
  const [tab, setTab] = useState<'providers' | 'routes'>('providers');
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [selectedProvId, setSelectedProvId] = useState<string>('dashscope');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testModel, setTestModel] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    api.getSettings().then((res) => {
      setSettings(res.settings);
      setPresets(res.presets);
      setRoles(res.roles);
      if (res.settings.providers.length > 0) {
        setSelectedProvId(res.settings.providers[0].id);
      }
    });

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open || !settings) return null;

  const activeProv =
    settings.providers.find((p) => p.id === selectedProvId) || settings.providers[0];
  const activePreset = presets.find((p) => p.id === activeProv?.id);

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

  const handleTest = async () => {
    if (!activeProv) return;
    const modelToTest =
      testModel.trim() ||
      activePreset?.suggested_models[0]?.id ||
      Object.values(settings.routes).find((r) => r.provider_id === activeProv.id)?.model ||
      'gpt-4o-mini';
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testConnection(activeProv.base_url, activeProv.api_key, modelToTest);
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
        className="w-[730px] max-w-full h-[510px] rounded-[14px] bg-[#F4F4F6] dark:bg-[#1C1C20] shadow-[0_28px_70px_rgba(0,0,0,0.28)] dark:shadow-[0_32px_80px_rgba(0,0,0,0.68)] border border-black/[0.1] dark:border-white/[0.12] flex flex-col overflow-hidden"
      >
        {/* macOS System Settings Titlebar */}
        <div className="h-[46px] px-4 macos-toolbar flex items-center justify-between shrink-0">
          <span className="text-[13px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
            设置
          </span>

          <div className="macos-segmented p-[2px] rounded-[7px] flex items-center gap-0.5">
            <button
              onClick={() => setTab('providers')}
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
                      onClick={() => {
                        setSelectedProvId(p.id);
                        setTestResult(null);
                      }}
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

                {/* Connectivity Test */}
                <div className="pt-2.5 border-t border-black/[0.06] dark:border-white/[0.07] space-y-2.5">
                  <div className="flex items-center gap-2">
                    <input
                      value={testModel}
                      onChange={(e) => setTestModel(e.target.value)}
                      placeholder={activePreset?.suggested_models[0]?.id || '模型 ID'}
                      className="flex-1 h-[30px] px-2.5 rounded-[6px] macos-input text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono outline-none"
                    />
                    <button
                      disabled={testing || !activeProv.api_key.trim()}
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

                  {activePreset && activePreset.suggested_models.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {activePreset.suggested_models.map((sm) => (
                        <button
                          key={sm.id}
                          onClick={() => setTestModel(sm.id)}
                          className="px-2 py-0.5 rounded-[5px] macos-well hover:bg-black/[0.06] dark:hover:bg-white/[0.1] text-[11px] text-[#515154] dark:text-[#AEAEB2] font-mono transition-colors"
                        >
                          {sm.id}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* 4-Role Routing Editor */
          <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
            {roles.map((rDef) => {
              const route = settings.routes[rDef.role];
              if (!route) return null;
              const presetForProv = presets.find((p) => p.id === route.provider_id);

              return (
                <div key={rDef.role} className="rounded-[10px] macos-card p-3.5 space-y-2.5">
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

                  <div className="grid grid-cols-12 gap-2.5 items-center">
                    <div className="col-span-4">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">供应商</label>
                      <select
                        value={route.provider_id}
                        onChange={(e) => {
                          const nextPid = e.target.value;
                          const nextPreset = presets.find((p) => p.id === nextPid);
                          const suggested = nextPreset?.suggested_models[0];
                          updateRoute(rDef.role, {
                            provider_id: nextPid,
                            ...(suggested
                              ? {
                                  model: suggested.id,
                                  input_price_per_m: suggested.input_price,
                                  output_price_per_m: suggested.output_price,
                                }
                              : {}),
                          });
                        }}
                        className="w-full h-[30px] rounded-[6px] macos-input px-2 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] outline-none"
                      >
                        {settings.providers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="col-span-4">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">模型</label>
                      <input
                        list={`models-${rDef.role}`}
                        value={route.model}
                        onChange={(e) => {
                          const val = e.target.value;
                          const matched = presetForProv?.suggested_models.find((m) => m.id === val);
                          updateRoute(rDef.role, {
                            model: val,
                            ...(matched
                              ? {
                                  input_price_per_m: matched.input_price,
                                  output_price_per_m: matched.output_price,
                                }
                              : {}),
                          });
                        }}
                        className="w-full h-[30px] rounded-[6px] macos-input px-2.5 text-[12px] text-[#1D1D1F] dark:text-[#F5F5F7] font-mono outline-none"
                      />
                      <datalist id={`models-${rDef.role}`}>
                        {(presetForProv?.suggested_models || []).map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.label}
                          </option>
                        ))}
                      </datalist>
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

                    <div className="col-span-2">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">
                        单价 (¥/M)
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          step="0.1"
                          value={route.input_price_per_m}
                          onChange={(e) =>
                            updateRoute(rDef.role, {
                              input_price_per_m: Math.max(0, Number(e.target.value) || 0),
                            })
                          }
                          className="w-1/2 h-[30px] rounded-[6px] macos-input px-1.5 text-[11px] text-[#1D1D1F] dark:text-[#F5F5F7] tabular-nums outline-none"
                        />
                        <input
                          type="number"
                          step="0.1"
                          value={route.output_price_per_m}
                          onChange={(e) =>
                            updateRoute(rDef.role, {
                              output_price_per_m: Math.max(0, Number(e.target.value) || 0),
                            })
                          }
                          className="w-1/2 h-[30px] rounded-[6px] macos-input px-1.5 text-[11px] text-[#1D1D1F] dark:text-[#F5F5F7] tabular-nums outline-none"
                        />
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
              完成
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
