import React from 'react';
import { Plus, Trash2, FolderCheck, HardDrive } from 'lucide-react';
import type { ProjectListItem } from '../types';

interface SidebarProps {
  projects: ProjectListItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  cacheMb: number;
  onClearCache: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  projects,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  cacheMb,
  onClearCache,
}) => {
  return (
    <aside className="w-[216px] shrink-0 macos-sidebar flex flex-col h-full max-[920px]:absolute max-[920px]:inset-y-0 max-[920px]:left-0 max-[920px]:z-30 max-[920px]:shadow-2xl">
      <div className="px-3 pt-3 pb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-wide text-[#8E8E93] dark:text-[#8E8E93]">
          项目
        </span>
        <button
          onClick={onCreate}
          title="新建项目"
          className="w-6 h-6 rounded-[5px] text-[#515154] dark:text-[#AEAEB2] hover:bg-black/[0.06] dark:hover:bg-white/[0.08] active:scale-[0.95] flex items-center justify-center transition-all"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {projects.map((p) => {
          const isActive = p.id === activeId;
          const dot =
            p.stage === 'completed'
              ? 'bg-[#34C759] dark:bg-[#30D158]'
              : p.stage === 'inspecting' || p.stage === 'planning'
                ? 'bg-[#007AFF] dark:bg-[#0A84FF]'
                : p.stage === 'awaiting_confirm'
                  ? 'bg-[#FF9500] dark:bg-[#FF9F0A]'
                  : 'bg-[#C7C7CC] dark:bg-[#48484A]';

          const subText = p.target_lot
            ? `${p.target_lot}标段${p.progress_pct > 0 ? ` · ${p.progress_pct.toFixed(0)}%` : ''}`
            : p.stage === 'completed'
              ? '已完成'
              : p.progress_pct > 0
                ? `${p.progress_pct.toFixed(0)}%`
                : '就绪';

          return (
            <div
              key={p.id}
              onClick={() => onSelect(p.id)}
              className={`group flex items-center justify-between px-2.5 py-[7px] rounded-[7px] cursor-pointer transition-all ${
                isActive
                  ? 'macos-sidebar-active'
                  : 'text-[#1D1D1F] dark:text-[#E5E5EA] hover:bg-black/[0.045] dark:hover:bg-white/[0.055]'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <FolderCheck
                  className={`w-[15px] h-[15px] shrink-0 ${
                    isActive ? 'text-white/95' : 'text-[#007AFF] dark:text-[#0A84FF]'
                  }`}
                />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate leading-tight">{p.name}</div>
                  <div
                    className={`text-[10.5px] flex items-center gap-1.5 mt-0.5 tabular-nums ${
                      isActive ? 'text-white/80' : 'text-[#8E8E93]'
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white' : dot}`} />
                    <span className="truncate">{subText}</span>
                  </div>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(p.id);
                }}
                title="删除"
                className={`opacity-0 group-hover:opacity-100 p-1 rounded-[5px] transition-opacity ${
                  isActive
                    ? 'text-white/80 hover:bg-white/20 hover:text-white'
                    : 'text-[#8E8E93] hover:bg-black/[0.08] dark:hover:bg-white/[0.1] hover:text-[#FF3B30] dark:hover:text-[#FF453A]'
                }`}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="px-3 py-2 border-t border-black/[0.06] dark:border-white/[0.07] flex items-center justify-between text-[11px] text-[#8E8E93] tabular-nums">
        <span className="flex items-center gap-1.5">
          <HardDrive className="w-3 h-3" />
          <span>{cacheMb.toFixed(1)} MB</span>
        </span>
        {cacheMb > 0.1 && (
          <button
            onClick={onClearCache}
            className="text-[#007AFF] dark:text-[#409CFF] hover:underline font-medium"
          >
            清理
          </button>
        )}
      </div>
    </aside>
  );
};
