import UserManagementCard from "./settings/UserManagementCard";
import "./settings.css";

export default function SettingsUsers() {
  return (
    <div className="settings-page">
      <h1 className="settings-title">Settings / Users</h1>
      <p className="settings-page-subtitle">
        Manage local Core accounts, roles, passwords, and access state.
      </p>
      <p className="settings-muted">
        Disabling or deleting a user revokes their active sessions and disables their enrolled devices.
      </p>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>User management</h2>
          <p>Owner, administrator, member, and guest accounts for this Core.</p>
        </div>
        <UserManagementCard />
      </section>
    </div>
  );
}
