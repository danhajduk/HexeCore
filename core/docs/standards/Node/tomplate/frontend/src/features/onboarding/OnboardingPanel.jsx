export function OnboardingPanel({ status }) {
  return (
    <section className="panel">
      <h2>Onboarding</h2>
      <p>Current stage: <strong>{status?.lifecycle_state || "unconfigured"}</strong></p>
    </section>
  );
}
