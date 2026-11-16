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
  Check,
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
  readOnly?: boolean;
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
  readOnly = false,
  onToggleItem,
  onInspectEvidence,
}) => {
  const [showDet, setShowDet] = useState(true);

  if (checklist.length === 0 && deterministicFindings.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-[12px] text-[#8E8E93]">
        待生成清单
      </div>
    );
  }

  const renderStatusIcon = (it: ChecklistItem) => {
    if (!it.enabled) {
      return <Circle className="w-[15px] h-[15px] text-[#C7C7CC] dark:text-[#48484A] shrink-0" />;
    }
    if (it.run_status === 'running') {
      return (
        <Loader2 className="w-[15px] h-[15px] text-[#007AFF] dark:text-[#0A84FF] animate-spin shrink-0" />
      );
    }
    if (it.run_status === 'failed') {
      return (
        <AlertTriangle className="w-[15px] h-[15px] text-[#FF3B30] dark:text-[#FF453A] shrink-0" />
      );
    }
    if (it.compliance_status === 'passed') {
      return (
        <CheckCircle2 className="w-[15px] h-[15px] text-[#34C759] dark:text-[#30D158] shrink-0" />
      );
    }
    if (it.compliance_status === 'partial') {
      return (
        <AlertTriangle className="w-[15px] h-[15px] text-[#FF9500] dark:text-[#FF9F0A] shrink-0" />
      );
    }
    if (it.compliance_status === 'missing') {
      return <XCircle className="w-[15px] h-[15px] text-[#FF3B30] dark:text-[#FF453A] shrink-0" />;
    }
    return <Circle className="w-[15px] h-[15px] text-[#C7C7CC] dark:text-[#48484A] shrink-0" />;
  };

  const renderRiskTag = (risk: ChecklistItem['risk_level']) => {
    if (risk === 'fatal') {
      return (
        <span className="px-1.5 py-[0.5px] rounded-[4px] bg-[#FF3B30]/10 dark:bg-[#FF453A]/18 text-[#FF3B30] dark:text-[#FF6961] text-[10px] font-semibold shrink-0">
          红线
        </span>
      );
    }
    if (risk === 'score_loss') {
      return (
        <span className="px-1.5 py-[0.5px] rounded-[4px] bg-[#FF9500]/12 dark:bg-[#FF9F0A]/18 text-[#D97706] dark:text-[#FFB340] text-[10px] font-semibold shrink-0">
          评分
        </span>
      );
    }
    return (
      <span className="px-1.5 py-[0.5px] rounded-[4px] bg-black/[0.05] dark:bg-white/[0.08] text-[#6E6E73] dark:text-[#98989D] text-[10px] font-medium shrink-0">
        形式
      </span>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
      {/* Deterministic Scanners Collapsible Card */}
      {deterministicFindings.length > 0 && (
        <div className="rounded-[10px] macos-card overflow-hidden">
          <button
            onClick={() => setShowDet((v) => !v)}
            className="w-full px-3 py-2 flex items-center justify-between bg-[#FF9500]/[0.06] dark:bg-[#FF9F0A]/[0.08] border-b border-black/[0.05] dark:border-white/[0.06] text-left"
          >
            <div className="flex items-center gap-2 text-[12px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
              <ShieldAlert className="w-3.5 h-3.5 text-[#FF9500] dark:text-[#FF9F0A]" />
              <span>形式预警</span>
              <span className="px-1.5 py-[0.5px] rounded-full bg-[#FF9500]/15 dark:bg-[#FF9F0A]/20 text-[#B45309] dark:text-[#FFB340] text-[10px] tabular-nums">
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
            <div className="divide-y divide-black/[0.05] dark:divide-white/[0.06] max-h-52 overflow-y-auto">
              {deterministicFindings.map((df) => (
                <div
                  key={df.finding_id}
                  onClick={() => onInspectEvidence(null, df.section_id)}
                  className="px-3 py-2 hover:bg-black/[0.025] dark:hover:bg-white/[0.035] cursor-pointer flex items-center justify-between gap-2 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        df.severity === 'fatal'
                          ? 'bg-[#FF3B30] dark:bg-[#FF453A]'
                          : df.severity === 'warning'
                            ? 'bg-[#FF9500] dark:bg-[#FF9F0A]'
                            : 'bg-[#007AFF] dark:bg-[#0A84FF]'
                      }`}
                    />
                    <span className="text-[12px] font-medium text-[#1D1D1F] dark:text-[#EAEAEF] truncate">
                      {df.title}
                    </span>
                  </div>
                  <span className="text-[10.5px] text-[#8E8E93] macos-well px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
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
            <div className="px-1 flex items-center justify-between text-[11px] font-semibold text-[#6E6E73] dark:text-[#98989D]">
              <span>{CATEGORY_LABELS[cat]}</span>
              <span className="tabular-nums font-normal text-[#8E8E93]">
                {doneCnt}/{items.length}
              </span>
            </div>

            <div className="rounded-[10px] macos-card divide-y divide-black/[0.05] dark:divide-white/[0.06] overflow-hidden">
              {items.map((it) => {
                const canToggle = !isRunning && !readOnly && it.run_status === 'pending';
                return (
                  <div
                    key={it.item_id}
                    title={it.requirement_text}
                    onClick={() => onInspectEvidence(it, it.matched_sections[0]?.section_id)}
                    className={`px-3 py-2 hover:bg-black/[0.022] dark:hover:bg-white/[0.03] cursor-pointer transition-colors ${
                      !it.enabled ? 'opacity-45' : ''
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      {canToggle ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onToggleItem(it.item_id, !it.enabled);
                          }}
                          className={`mt-[2px] w-[15px] h-[15px] rounded-[4px] flex items-center justify-center shrink-0 transition-all ${
                            it.enabled
                              ? 'macos-btn-primary'
                              : 'macos-well border border-black/[0.16] dark:border-white/[0.18]'
                          }`}
                        >
                          {it.enabled && <Check className="w-2.5 h-2.5 stroke-[3] text-white" />}
                        </button>
                      ) : (
                        <div className="mt-[2px]">{renderStatusIcon(it)}</div>
                      )}

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-1.5 min-w-0">
                            {renderRiskTag(it.risk_level)}
                            <span className="text-[12.5px] font-medium text-[#1D1D1F] dark:text-[#F5F5F7] truncate">
                              {it.title}
                            </span>
                            {it.requires_vision && (
                              <Eye className="w-3.5 h-3.5 text-[#007AFF] dark:text-[#409CFF] shrink-0" />
                            )}
                          </div>

                          {it.matched_sections[0] ? (
                            <span className="text-[10.5px] text-[#6E6E73] dark:text-[#98989D] macos-well px-1.5 py-0.5 rounded-[4px] shrink-0 tabular-nums">
                              {it.matched_sections[0].page_label}
                            </span>
                          ) : (
                            it.tender_source && (
                              <span className="text-[10.5px] text-[#8E8E93] truncate max-w-[96px] shrink-0">
                                {it.tender_source}
                              </span>
                            )
                          )}
                        </div>

                        {it.conclusion && (
                          <div className="text-[11.5px] text-[#6E6E73] dark:text-[#98989D] line-clamp-1 mt-0.5 leading-snug">
                            {it.conclusion}
                          </div>
                        )}

                        {it.vision_note && (
                          <div className="text-[11px] text-[#007AFF] dark:text-[#409CFF] mt-0.5 truncate">
                            {it.vision_note}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};
