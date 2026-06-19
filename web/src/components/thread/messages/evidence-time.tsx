export function EvidenceTime({
  sourceUpdatedAt,
  indexedAt,
}: {
  sourceUpdatedAt?: string;
  indexedAt?: string;
}) {
  if (!sourceUpdatedAt && !indexedAt) return null;

  return (
    <div className="text-muted-foreground/70 mt-0.5 text-[11px]">
      {sourceUpdatedAt && <span>源端 {sourceUpdatedAt}</span>}
      {sourceUpdatedAt && indexedAt && <span className="px-1">·</span>}
      {indexedAt && <span>索引 {indexedAt}</span>}
    </div>
  );
}
