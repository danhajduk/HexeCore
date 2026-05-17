export function StatusCard({ status, error }) {
  return (
    <section className="panel">
      <h2>Status</h2>
      {error ? <p className="error">{error}</p> : null}
      <pre>{JSON.stringify(status || { status: "loading" }, null, 2)}</pre>
    </section>
  );
}
