import { NavLink } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

const links = [
  { to: "/chat", label: "Chat", icon: "✦" },
  { to: "/conversations", label: "Conversations", icon: "◫" },
  { to: "/knowledge", label: "Knowledge base", icon: "▤" },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  return (
    <aside className="sidebar">
      <div>
        <div className="sidebar-brand"><span>◇</span> SupportAI</div>
        <nav aria-label="Main navigation">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <span aria-hidden="true">{link.icon}</span>{link.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="account-block">
        <div className="avatar">{user?.name?.slice(0, 1).toUpperCase() ?? "U"}</div>
        <div><strong>{user?.name ?? "Support user"}</strong><small>{user?.email}</small></div>
        <button className="text-button" onClick={logout} type="button">Sign out</button>
      </div>
    </aside>
  );
}
