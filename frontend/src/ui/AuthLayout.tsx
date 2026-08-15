import { Link } from "react-router-dom";
import type { ReactNode } from "react";

type AuthLayoutProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export function AuthLayout({ title, description, children }: AuthLayoutProps) {
  return (
    <div className="auth-shell">
      <div className="auth-card stack-lg">
        <div className="stack">
          <Link to="/ingresar" className="brand">
            NEXUS CRM
          </Link>
          <h1>{title}</h1>
          {description ? <p className="muted">{description}</p> : null}
        </div>
        {children}
      </div>
    </div>
  );
}
