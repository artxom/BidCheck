import React from 'react';
import { LiveRunView } from './LiveRunView';
import { ReportView } from './ReportView';
import { EvidenceView } from './EvidenceView';
import type {
  ChecklistItem,
  DeterministicFinding,
  InspectionReport,
  OutlineSectionLite,
} from '../types';

export type InspectorTab = 'live' | 'report' | 'evidence';

interface InspectorPaneProps {
  projectId: string;
  activeTab: InspectorTab;
  onChangeTab: (t: InspectorTab) => void;
  checklist: ChecklistItem[];
  report: InspectionReport | null;
  deterministicFindings: DeterministicFinding[];
  outline: OutlineSectionLite[];
  isRunning: boolean;
  selectedItem: ChecklistItem | null;
  selectedSectionId: string | null;
  onToggleItem: (itemId: string, enabled: boolean) => void;
  onInspectEvidence: (item: ChecklistItem | null, sectionId?: string) => void;
  onSelectSectionId: (secId: string) => void;
}

export const InspectorPane: React.FC<InspectorPaneProps> = ({
  projectId,
  activeTab,
  onChangeTab,
  checklist,
  report,
  deterministicFindings,
  outline,
  isRunning,
  selectedItem,
  selectedSectionId,
  onToggleItem,
  onInspectEvidence,
  onSelectSectionId,
}) => {
  const tabs: { key: InspectorTab; label: string; badge?: number }[] = [
    { key: 'live', label: '检查实况', badge: checklist.length || undefined },
    {
      key: 'report',
      label: '核查报告',
      badge: report ? report.partial_count + report.missing_count : undefined,
    },
    { key: 'evidence', label: '原文证据' },
  ];

  return (
    <aside className="w-[45%] max-w-[660px] min-w-[390px] bg-[#FAFAFC] flex flex-col h-full">
      {/* macOS Segmented Control Header */}
      <div className="px-3.5 py-2.5 border-b border-black/[0.06] flex items-center justify-center bg-white/70 backdrop-blur-md">
        <div className="w-full max-w-[360px] bg-black/[0.06] p-0.5 rounded-[8px] grid grid-cols-3 gap-0.5">
          {tabs.map((t) => {
            const active = activeTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => onChangeTab(t.key)}
                className={`h-[26px] rounded-[6px] text-[12px] font-medium flex items-center justify-center gap-1.5 transition-all tabular-nums ${
                  active
                    ? 'bg-white text-[#1D1D1F] shadow-[0_1px_2px_rgba(0,0,0,0.1)]'
                    : 'text-[#6E6E73] hover:text-[#1D1D1F]'
                }`}
              >
                <span>{t.label}</span>
                {t.badge !== undefined && t.badge > 0 && (
                  <span
                    className={`px-1.5 py-0.1 rounded-full text-[10px] ${
                      t.key === 'report'
                        ? 'bg-[#FF9500]/15 text-[#B45309]'
                        : 'bg-black/[0.06] text-[#515154]'
                    }`}
                  >
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === 'live' && (
        <LiveRunView
          checklist={checklist}
          deterministicFindings={deterministicFindings}
          isRunning={isRunning}
          onToggleItem={onToggleItem}
          onInspectEvidence={onInspectEvidence}
        />
      )}

      {activeTab === 'report' && (
        <ReportView
          report={report}
          checklist={checklist}
          onInspectEvidence={onInspectEvidence}
        />
      )}

      {activeTab === 'evidence' && (
        <EvidenceView
          projectId={projectId}
          selectedItem={selectedItem}
          selectedSectionId={selectedSectionId}
          outline={outline}
          onSelectSectionId={onSelectSectionId}
        />
      )}
    </aside>
  );
};
