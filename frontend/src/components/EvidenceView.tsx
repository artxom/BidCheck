import React, { useState, useEffect } from 'react';
import { Loader2, Image as ImageIcon, X, FileSearch } from 'lucide-react';
import { api } from '../api';
import type { ChecklistItem, OutlineSectionLite, SectionDetail } from '../types';

interface EvidenceViewProps {
  projectId: string;
  selectedItem: ChecklistItem | null;
  selectedSectionId: string | null;
  outline: OutlineSectionLite[];
  onSelectSectionId: (secId: string) => void;
}

export const EvidenceView: React.FC<EvidenceViewProps> = ({
  projectId,
  selectedItem,
  selectedSectionId,
  outline,
  onSelectSectionId,
}) => {
  const [section, setSection] = useState<SectionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [lightboxMediaId, setLightboxMediaId] = useState<string | null>(null);

  useEffect(() => {
    if (!lightboxMediaId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxMediaId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightboxMediaId]);

  useEffect(() => {
    const targetId =
      selectedSectionId ||
      selectedItem?.matched_sections[0]?.section_id ||
      outline[0]?.section_id ||
      null;
    if (!targetId) {
      setSection(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    api
      .getSection(projectId, targetId)
      .then((res) => {
        if (!cancelled) setSection(res.section);
      })
      .catch(() => {
        if (!cancelled) setSection(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, selectedSectionId, selectedItem, outline]);

  if (!selectedItem && outline.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-[12px] text-[#8E8E93]">
        选择条目或章节预览原文
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden p-3.5 space-y-3">
      {/* Clause Summary Card */}
      {selectedItem && (
        <div className="rounded-[10px] macos-card p-3 space-y-1.5 selectable-text">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] truncate">
              {selectedItem.item_id} · {selectedItem.title}
            </span>
            {selectedItem.tender_source && (
              <span className="text-[10.5px] text-[#8E8E93] macos-well px-1.5 py-0.5 rounded-[4px] shrink-0">
                {selectedItem.tender_source}
              </span>
            )}
          </div>
          <div className="text-[11.5px] text-[#6E6E73] dark:text-[#98989D] leading-relaxed">
            {selectedItem.requirement_text}
          </div>
          {selectedItem.conclusion && (
            <div className="text-[11.5px] font-medium text-[#007AFF] dark:text-[#409CFF] pt-1.5 border-t border-black/[0.05] dark:border-white/[0.06]">
              {selectedItem.conclusion}
            </div>
          )}

          {selectedItem.matched_sections.length > 1 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {selectedItem.matched_sections.map((ms) => (
                <button
                  key={ms.section_id}
                  onClick={() => onSelectSectionId(ms.section_id)}
                  className={`px-2 py-0.5 rounded-[5px] text-[11px] transition-colors ${
                    section?.section_id === ms.section_id
                      ? 'macos-btn-primary'
                      : 'macos-well text-[#515154] dark:text-[#AEAEB2] hover:bg-black/[0.07] dark:hover:bg-white/[0.1]'
                  }`}
                >
                  {ms.page_label} · {ms.breadcrumb.split(' > ').pop()}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Outline Quick Selector */}
      {outline.length > 0 && (
        <div className="flex items-center gap-2 min-w-0">
          <FileSearch className="w-3.5 h-3.5 text-[#8E8E93] shrink-0" />
          <select
            value={section?.section_id || ''}
            onChange={(e) => onSelectSectionId(e.target.value)}
            className="flex-1 min-w-0 w-full h-[29px] rounded-[7px] macos-input macos-select pl-2.5 text-[11.5px] text-[#1D1D1F] dark:text-[#F5F5F7] outline-none"
          >
            {outline.map((s) => (
              <option key={s.section_id} value={s.section_id}>
                {'　'.repeat(Math.max(0, s.level - 1))}
                [{s.page_label}] {s.title}
                {s.image_count > 0 ? ` (${s.image_count}图)` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Section Content Body */}
      {loading ? (
        <div className="py-12 flex items-center justify-center text-[#8E8E93] gap-2 text-[12px]">
          <Loader2 className="w-4 h-4 animate-spin text-[#007AFF] dark:text-[#0A84FF]" />
          <span>加载中…</span>
        </div>
      ) : section ? (
        <div className="rounded-[10px] macos-card p-3.5 space-y-3 selectable-text">
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-black/[0.06] dark:border-white/[0.07]">
            <div className="text-[12px] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7] leading-snug">
              {section.breadcrumb}
            </div>
            <span className="px-2 py-0.5 rounded-[5px] bg-[#007AFF]/10 dark:bg-[#0A84FF]/18 text-[#007AFF] dark:text-[#409CFF] text-[11px] font-semibold shrink-0 tabular-nums">
              {section.page_label}
            </span>
          </div>

          {section.deterministic_findings.length > 0 && (
            <div className="space-y-1">
              {section.deterministic_findings.map((d) => (
                <div
                  key={d.finding_id}
                  className="px-2.5 py-1.5 rounded-[6px] bg-[#FF9500]/[0.08] dark:bg-[#FF9F0A]/[0.12] border border-[#FF9500]/20 dark:border-[#FF9F0A]/25 text-[11.5px] text-[#92400E] dark:text-[#FFB340]"
                >
                  {d.title}：{d.detail}
                </div>
              ))}
            </div>
          )}

          {/* Paragraphs */}
          {section.paragraphs.length > 0 && (
            <div className="space-y-1.5 text-[12.5px] text-[#2C2C2E] dark:text-[#D1D1D6] leading-relaxed">
              {section.paragraphs.map((p, idx) => (
                <p key={idx}>{p}</p>
              ))}
            </div>
          )}

          {/* Tables */}
          {section.tables.map((tbl) => (
            <div
              key={tbl.table_id}
              className="overflow-x-auto border border-black/[0.08] dark:border-white/[0.09] rounded-[7px]"
            >
              <table className="w-full text-[11.5px] border-collapse">
                <tbody>
                  {tbl.rows.slice(0, 35).map((row, rIdx) => (
                    <tr
                      key={rIdx}
                      className={
                        rIdx === 0
                          ? 'bg-black/[0.035] dark:bg-white/[0.055] font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]'
                          : 'border-t border-black/[0.06] dark:border-white/[0.07] text-[#2C2C2E] dark:text-[#D1D1D6]'
                      }
                    >
                      {row.map((cell, cIdx) => (
                        <td
                          key={cIdx}
                          className="px-2 py-1.5 border-r last:border-r-0 border-black/[0.05] dark:border-white/[0.06] align-top"
                        >
                          {cell || (
                            <span className="text-[#FF3B30]/70 dark:text-[#FF6961]/80 italic">
                              空
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {/* Embedded Scanned Images Gallery */}
          {section.media_ids.length > 0 && (
            <div className="space-y-2 pt-1">
              <div className="text-[11px] font-semibold text-[#8E8E93] flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-[#007AFF] dark:text-[#409CFF]" />
                <span>扫描件 ({section.media_ids.length})</span>
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                {section.media_ids.map((mid) => (
                  <div
                    key={mid}
                    onClick={() => setLightboxMediaId(mid)}
                    className="group rounded-[8px] macos-well overflow-hidden cursor-zoom-in p-1.5"
                  >
                    <div className="rounded-[5px] overflow-hidden bg-white">
                      <img
                        src={`/api/projects/${projectId}/media/${mid}`}
                        alt={mid}
                        loading="lazy"
                        className="w-full h-36 object-contain group-hover:scale-[1.02] transition-transform"
                      />
                    </div>
                    <div className="pt-1 px-0.5 text-[10px] text-[#8E8E93] font-mono tabular-nums truncate">
                      {mid}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {section.paragraphs.length === 0 &&
            section.tables.length === 0 &&
            section.media_ids.length === 0 && (
              <div className="py-6 text-center text-[12px] text-[#8E8E93]">无直接正文</div>
            )}
        </div>
      ) : null}

      {/* Quick Look Lightbox */}
      {lightboxMediaId && (
        <div
          onClick={() => setLightboxMediaId(null)}
          className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-6"
        >
          <button
            onClick={() => setLightboxMediaId(null)}
            className="absolute top-5 right-5 w-8 h-8 rounded-full bg-white/15 hover:bg-white/25 text-white flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
          <img
            src={`/api/projects/${projectId}/media/${lightboxMediaId}`}
            alt={lightboxMediaId}
            onClick={(e) => e.stopPropagation()}
            className="max-w-full max-h-full rounded-[10px] shadow-2xl bg-white"
          />
        </div>
      )}
    </div>
  );
};
