export function StorageDetails({ rows }: { rows: [string, string][] }) {
  return (
    <section className="space-y-4 border-t pt-6" aria-label="Thông tin lưu trữ">
      <h3 className="text-sm font-semibold">Lưu trữ</h3>
      <dl className="space-y-4 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="space-y-1">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="break-all select-text">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
