export function OperationalPanel({ status }) {
  return (
    <section className="panel">
      <h2>Operational</h2>
      <p>Readiness: <strong>{String(status?.operational_ready ?? false)}</strong></p>
    </section>
  );
}
