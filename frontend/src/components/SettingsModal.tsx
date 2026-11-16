import React, { useState, useEffect } from 'react';
import { X, Check, Loader2, Wifi, Plus, Eye, EyeOff } from 'lucide-react';
import { api } from '../api';
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
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ open, onClose }) => {
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
  }, [open]);

  if (!open || !settings) return null;

  const activeProv = settings.providers.find((p) => p.id === selectedProvId) || settings.providers[0];
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
      name: '自定义供应商',
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
      setTimeout(() => setSavedToast(false), 1800);
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
      setTestResult({ ok: true, msg: `连通正常 (${res.latency_ms}ms · ${res.model})` });
    } catch (err) {
      setTestResult({ ok: false, msg: err instanceof Error ? err.message : '连接失败' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-[2px] z-50 flex items-center justify-center p-4">
      <div className="w-[740px] max-w-full h-[520px] rounded-[14px] bg-[#F5F5F7] shadow-[0_24px_60px_rgba(0,0,0,0.22)] border border-black/[0.1] flex flex-col overflow-hidden">
        {/* macOS Sheet Titlebar */}
        <div className="h-[46px] px-4 bg-white border-b border-black/[0.08] flex items-center justify-between shrink-0">
          <span className="text-[13px] font-semibold text-[#1D1D1F]">大模型 API 与角色配置</span>

          <div className="bg-black/[0.06] p-0.5 rounded-[7px] flex items-center gap-0.5">
            <button
              onClick={() => setTab('providers')}
              className={`px-3 py-1 rounded-[5px] text-[12px] font-medium transition-all ${
                tab === 'providers' ? 'bg-white shadow-xs text-[#1D1D1F]' : 'text-[#6E6E73]'
              }`}
            >
              API 供应商密钥
            </button>
            <button
              onClick={() => setTab('routes')}
              className={`px-3 py-1 rounded-[5px] text-[12px] font-medium transition-all ${
                tab === 'routes' ? 'bg-white shadow-xs text-[#1D1D1F]' : 'text-[#6E6E73]'
              }`}
            >
              四角色路由分工
            </button>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-black/[0.06] text-[#6E6E73]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        {tab === 'providers' ? (
          <div className="flex-1 flex min-h-0">
            {/* Left Provider List */}
            <div className="w-[210px] border-r border-black/[0.08] bg-[#ECECEF]/70 p-2 flex flex-col">
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
                      className={`w-full text-left px-2.5 py-2 rounded-[7px] text-[12px] flex items-center justify-between transition-colors ${
                        active ? 'bg-[#007AFF] text-white font-medium' : 'text-[#1D1D1F] hover:bg-black/[0.05]'
                      }`}
                    >
                      <span className="truncate">{p.name}</span>
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${
                          hasKey ? (active ? 'bg-white' : 'bg-[#34C759]') : 'bg-black/[0.15]'
                        }`}
                      />
                    </button>
                  );
                })}
              </div>
              <button
                onClick={addCustomProvider}
                className="mt-2 h-[28px] rounded-[6px] bg-white border border-black/[0.1] hover:bg-black/[0.03] text-[11.5px] font-medium text-[#1D1D1F] flex items-center justify-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>新增兼容网关</span>
              </button>
            </div>

            {/* Right Provider Editor */}
            {activeProv && (
              <div className="flex-1 p-5 bg-white overflow-y-auto space-y-4">
                <div>
                  <label className="block text-[11.5px] font-medium text-[#6E6E73] mb-1">
                    供应商名称
                  </label>
                  <input
                    value={activeProv.name}
                    onChange={(e) => updateProvider({ name: e.target.value })}
                    className="w-full h-[32px] px-3 rounded-[7px] border border-black/[0.14] focus:border-[#007AFF] outline-none text-[12.5px]"
                  />
                </div>

                <div>
                  <label className="block text-[11.5px] font-medium text-[#6E6E73] mb-1">
                    OpenAI 兼容 Base URL
                  </label>
                  <input
                    value={activeProv.base_url}
                    onChange={(e) => updateProvider({ base_url: e.target.value })}
                    placeholder="https://api.deepseek.com/v1"
                    className="w-full h-[32px] px-3 rounded-[7px] border border-black/[0.14] focus:border-[#007AFF] outline-none text-[12.5px] font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[11.5px] font-medium text-[#6E6E73] mb-1">
                    API Key
                  </label>
                  <div className="relative">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={activeProv.api_key}
                      onChange={(e) => updateProvider({ api_key: e.target.value })}
                      placeholder="sk-..."
                      className="w-full h-[32px] pl-3 pr-9 rounded-[7px] border border-black/[0.14] focus:border-[#007AFF] outline-none text-[12.5px] font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((v) => !v)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8E8E93] hover:text-[#1D1D1F]"
                    >
                      {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Connectivity Quick Check */}
                <div className="pt-2 border-t border-black/[0.06] space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      value={testModel}
                      onChange={(e) => setTestModel(e.target.value)}
                      placeholder={
                        activePreset?.suggested_models[0]?.id || '输入测试模型 ID (如 qwen-plus)'
                      }
                      className="flex-1 h-[30px] px-2.5 rounded-[6px] border border-black/[0.12] text-[12px] font-mono outline-none focus:border-[#007AFF]"
                    />
                    <button
                      disabled={testing || !activeProv.api_key.trim()}
                      onClick={handleTest}
                      className="h-[30px] px-3 rounded-[6px] bg-[#F5F5F7] hover:bg-black/[0.08] disabled:opacity-45 text-[12px] font-medium text-[#1D1D1F] flex items-center gap-1.5"
                    >
                      {testing ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-[#007AFF]" />
                      ) : (
                        <Wifi className="w-3.5 h-3.5 text-[#007AFF]" />
                      )}
                      <span>连通性测试</span>
                    </button>
                  </div>

                  {testResult && (
                    <div
                      className={`text-[11.5px] px-2.5 py-1.5 rounded-[6px] ${
                        testResult.ok
                          ? 'bg-[#34C759]/10 text-[#15803D]'
                          : 'bg-[#FF3B30]/10 text-[#DC2626]'
                      }`}
                    >
                      {testResult.msg}
                    </div>
                  )}

                  {activePreset && activePreset.suggested_models.length > 0 && (
                    <div className="pt-1">
                      <div className="text-[11px] text-[#8E8E93] mb-1.5">常用模型标识（点击填入测试）</div>
                      <div className="flex flex-wrap gap-1.5">
                        {activePreset.suggested_models.map((sm) => (
                          <button
                            key={sm.id}
                            onClick={() => setTestModel(sm.id)}
                            className="px-2 py-0.5 rounded-[5px] bg-[#F5F5F7] hover:bg-black/[0.08] text-[11px] text-[#515154] font-mono"
                          >
                            {sm.id}
                          </button>
                        ))}
                      </div>
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
                <div
                  key={rDef.role}
                  className="rounded-[10px] bg-white border border-black/[0.07] p-3.5 space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-[13px] font-semibold text-[#1D1D1F]">{rDef.label}</span>
                      <span className="ml-2 text-[11.5px] text-[#8E8E93]">{rDef.desc}</span>
                    </div>
                    {rDef.role === 'vision_worker' && (
                      <label className="flex items-center gap-1.5 text-[11.5px] text-[#515154] cursor-pointer">
                        <input
                          type="checkbox"
                          checked={route.enabled}
                          onChange={(e) => updateRoute(rDef.role, { enabled: e.target.checked })}
                          className="accent-[#007AFF]"
                        />
                        <span>启用视觉核验</span>
                      </label>
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
                        className="w-full h-[30px] rounded-[6px] border border-black/[0.12] px-2 text-[12px] bg-white outline-none focus:border-[#007AFF]"
                      >
                        {settings.providers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="col-span-4">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">
                        模型名称 (支持手动输入或选预设)
                      </label>
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
                        className="w-full h-[30px] rounded-[6px] border border-black/[0.12] px-2.5 text-[12px] font-mono outline-none focus:border-[#007AFF]"
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
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">最大并发</label>
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
                        className="w-full h-[30px] rounded-[6px] border border-black/[0.12] px-2 text-[12px] tabular-nums outline-none focus:border-[#007AFF]"
                      />
                    </div>

                    <div className="col-span-2">
                      <label className="block text-[10.5px] text-[#8E8E93] mb-0.5">
                        单价(元/M入·出)
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
                          className="w-1/2 h-[30px] rounded-[6px] border border-black/[0.12] px-1.5 text-[11px] tabular-nums outline-none"
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
                          className="w-1/2 h-[30px] rounded-[6px] border border-black/[0.12] px-1.5 text-[11px] tabular-nums outline-none"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="h-[48px] px-4 bg-white border-t border-black/[0.08] flex items-center justify-end gap-2.5 shrink-0">
          {savedToast && (
            <span className="text-[12px] text-[#34C759] flex items-center gap-1 mr-auto font-medium">
              <Check className="w-3.5 h-3.5" />
              <span>已保存</span>
            </span>
          )}
          <button
            onClick={onClose}
            className="h-[30px] px-3.5 rounded-[7px] bg-black/[0.05] hover:bg-black/[0.09] text-[12.5px] font-medium text-[#1D1D1F]"
          >
            关闭
          </button>
          <button
            disabled={saving}
            onClick={handleSave}
            className="h-[30px] px-4 rounded-[7px] bg-[#007AFF] hover:bg-[#0066D6] text-[12.5px] font-medium text-white flex items-center gap-1.5"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            <span>保存配置</span>
          </button>
        </div>
      </div>
    </div>
  );
};
