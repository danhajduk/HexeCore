import { Component, type ErrorInfo, type ReactNode } from "react";
import "./assistant.css";
import "./assistantRecovery.css";

type State = { failed: boolean };

export default class AssistantErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };
  static getDerivedStateFromError(): State { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo): void { console.error("Assistant UI failed safely", error.name, info.componentStack); }
  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return <main className="assistant-app assistant-recovery" role="alert"><section><h1>Hexe could not display this conversation</h1><p>Your session is still available. Reload to try again.</p><button onClick={() => window.location.reload()}>Reload app</button></section></main>;
  }
}
