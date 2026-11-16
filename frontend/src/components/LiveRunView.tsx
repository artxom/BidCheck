import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Circle,
  Eye,
  ChevronRight,
  ChevronDown,
  ShieldAlert,
} from 'lucide-react';
import {
  CATEGORY_LABELS,
  type CategoryType,
  type ChecklistItem,
  type DeterministicFinding,
} from '../types';

interface LiveRunViewProps {
  checklist: ChecklistItem[];
  deterministicFindings: DeterministicFinding[];
  isRunning: boolean;
  onToggleItem: (itemId: string, enabled: boolean) => void;
  onInspectEvidence: (item: ChecklistItem | null, sectionId?: string) => void;
}

const ORDERED_CATEGORIES: CategoryType[] = [
  'qualification',
  'commercial_scoring',
  'technical_scoring',
  'procurement_req',
  'format_redline',
];

export const LiveRunView: React.FC<LiveRunViewProps> = ({
  checklist,
  deterministicFindings,
  isRunning,
  onToggleItem,
  onInspectEvidence,
}) => {
  const [showDet, setShowDet] = useState(true);

  if (checklist.length === 0 && deterministicFindings.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-[12.5px] text-[#8E8E93]">
        暂无检查项
      </div>
    );
  }

  const renderStatusIcon = (it: ChecklistItem) => {
    if (!it.enabled) return <Circle className="w-4 h-4 text-[#C7C7CC] shrink-0" />;
    if (it.run_status === 'running') {
      return <Loader2 className="w-4 h-4 text-[#007AFF] animate-spin shrink-0" />;
    }
    if (it.run_status === 'failed') {
      return <AlertTriangle className="w-4 h-4 text-[#FF3B30] shrink-0" />;
    }
    if (it.compliance_status === 'passed') {
      return <CheckCircle2 className="w-4 h-4 text-[#34C759] shrink-0" />;
    }
    if (it.compliance_status === 'partial') {
      return <AlertTriangle className="w-4 h-4 text-[#FF9500] shrink-0" />;
    }
    if (it.compliance_status === 'missing') {
      return <XCircle className="w-4 h-4 text-[#FF3B30] shrink-0" />;
    }
    return <Circle className="w-4 h-4 text-[#C7C7CC] shrink-0" />;
  };

  const renderRiskTag = (risk: ChecklistItem['risk_level']) => {
    if (risk === 'fatal') {
      return (
        <span className="px-1.5 py-0.2 rounded-[4px] bg-[#FF3B30]/10 text-[#FF3B30] text-[10.5px] font-medium shrink-0">
          红线
        </span>
      );
    }
    if (risk === 'score_loss') {
      return (
        <span className="px-1.5 py-0.2 rounded-[4px] bg-[#FF9500]/12 text-[#D97706] text-[10.5px] font-medium shrink-0">
          评分
        </span>
      );
    }
    return (
      <span className="px-1.5 py-0.2 rounded-[4px] bg-black/[0.05] text-[#6E6E73] text-[10.5px] font-medium shrink-0">
        形式
      </span>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
      {/* Deterministic Built-in Scanners Strip */}
      {deterministicFindings.length > 0 && (
        <div className="rounded-[10px] bg-white border border-black/[0.07] overflow-hidden">
          <button
            onClick={() => setShowDet((v) => !v)}
            className="w-full px-3 py-2 flex items-center justify-between bg-[#FFF9F2] border-b border-black/[0.05] text-left"
          >
            <div className="flex items-center gap-2 text-[12px] font-semibold text-[#1D1D1F]">
              <ShieldAlert className="w-3.5 h-3.5 text-[#FF9500]" />
              <span>内置固有规则扫描预警</span>
              <span className="px-1.5 py-0.2 rounded-full bg-[#FF9500]/15 text-[#B45309] text-[10.5px] tabular-nums">
                {deterministicFindings.length}
              </span>
            </div>
            {showDet ? (
              <ChevronDown className="w-3.5 h-3.5 text-[#8E8E93]" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-[#8E8E93]" />
            )}
          </button>

          {showDet && (
            <div className="divide-y divide-black/[0.05] max-h-56 overflow-y-auto">
              {deterministicFindings.map((df) => (
                <div
                  key={df.finding_id}
                  onClick={() => onInspectEvidence(null, df.section_id)}
                  className="px-3 py-2 hover:bg-black/[0.025] cursor-pointer flex items-start justify-between gap-2 transition-colors"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          df.severity === 'fatal'
                            ? 'bg-[#FF3B30]'
                            : df.severity === 'warning'
                              ? 'bg-[#FF9500]'
                              : 'bg-[#007AFF]'
                        }`}
                      />
                      <span className="text-[12px] font-medium text-[#1D1D1F] truncate">
                        {df.title}
                      </span>
                    </div>
                    <div className="text-[11px] text-[#6E6E73] truncate mt-0.5 pl-3">
                      {df.breadcrumb}
                    </div>
                  </div>
                  <span className="text-[10.5px] text-[#8E8E93] bg-[#F5F5F7] px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
                    {df.page_hint}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Categorized Checklist Items */}
      {ORDERED_CATEGORIES.map((cat) => {
        const items = checklist.filter((it) => it.category === cat);
        if (items.length === 0) return null;
        const doneCnt = items.filter((it) => it.run_status === 'completed').length;

        return (
          <div key={cat} className="space-y-1.5">
            <div className="px-1 flex items-center justify-between text-[11.5px] font-semibold text-[#6E6E73]">
              <span>{CATEGORY_LABELS[cat]}</span>
              <span className="tabular-nums text-[11px] font-normal">
                {doneCnt}/{items.length}
              </span>
            </div>

            <div className="rounded-[10px] bg-white border border-black/[0.07] divide-y divide-black/[0.05] overflow-hidden">
              {items.map((it) => (
                <div
                  key={it.item_id}
                  onClick={() => onInspectEvidence(it, it.matched_sections[0]?.section_id)}
                  className={`px-3 py-2.5 hover:bg-black/[0.02] cursor-pointer transition-colors ${
                    !it.enabled ? 'opacity-45' : ''
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    {!isRunning && it.run_status === 'pending' ? (
                      <input
                        type="checkbox"
                        checked={it.enabled}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => onToggleItem(it.item_id, e.target.checked)}
                        className="mt-0.5 accent-[#007AFF] rounded cursor-pointer"
                      />
                    ) : (
                      <div className="mt-0.5">{renderStatusIcon(it)}</div>
                    )}

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          {renderRiskTag(it.risk_level)}
                          <span className="text-[12.5px] font-medium text-[#1D1D1F] truncate">
                            {it.title}
                          </span>
                          {it.requires_vision && (
                            <span title="按需多模态验图" className="text-[#007AFF] shrink-0">
                              <Eye className="w-3.5 h-3.5" />
                            </span>
                          )}
                        </div>

                        {it.matched_sections[0] && (
                          <span className="text-[10.5px] text-[#6E6E73] bg-[#F5F5F7] px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
                            {it.matched_sections[0].page_label}
                          </span>
                        )}
                      </div>

                      <div className="text-[11.5px] text-[#6E6E73] line-clamp-2 mt-1 leading-snug">
                        {it.conclusion || it.requirement_text}
                      </div>

                      {it.vision_note && (
                        <div className="text-[11px] text-[#007AFF] mt-1 truncate">
                          图面核验：{it.vision_note}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};
