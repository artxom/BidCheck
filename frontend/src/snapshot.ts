import type { OfflineReportSnapshot, SectionDetail } from './types';

let cachedSnapshot: OfflineReportSnapshot | null | undefined;

const FALLBACK_MEDIA_SVG =
  'data:image/svg+xml;charset=utf-8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180"><rect width="320" height="180" fill="#f4f4f7"/><text x="160" y="94" font-family="-apple-system,PingFang SC,Microsoft YaHei,sans-serif" font-size="13" fill="#8e8e93" text-anchor="middle">原图未嵌入</text></svg>`,
  );

export function getOfflineSnapshot(): OfflineReportSnapshot | null {
  if (cachedSnapshot !== undefined) {
    return cachedSnapshot;
  }
  if (typeof document === 'undefined') {
    cachedSnapshot = null;
    return null;
  }
  const el = document.getElementById('bidguard-report-snapshot');
  const raw = el?.textContent?.trim();
  if (!raw) {
    cachedSnapshot = null;
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as OfflineReportSnapshot;
    if (parsed && parsed.format === 'bidguard-static-report-v1' && parsed.project) {
      cachedSnapshot = parsed;
      return cachedSnapshot;
    }
  } catch {
    // ignore malformed snapshot JSON
  }
  cachedSnapshot = null;
  return null;
}

export function isOfflineSnapshotMode(): boolean {
  return Boolean(getOfflineSnapshot());
}

export function getSnapshotSection(sectionId: string): SectionDetail | null {
  const snap = getOfflineSnapshot();
  if (!snap) return null;
  return snap.sections?.[sectionId] ?? null;
}

export function getSnapshotMediaUrl(mediaId: string): string {
  const snap = getOfflineSnapshot();
  if (!snap) return FALLBACK_MEDIA_SVG;
  const blobKey = snap.media_map?.[mediaId];
  if (blobKey && snap.media_blobs?.[blobKey]) {
    return snap.media_blobs[blobKey];
  }
  if (snap.media_blobs?.[mediaId]) {
    return snap.media_blobs[mediaId];
  }
  return FALLBACK_MEDIA_SVG;
}
