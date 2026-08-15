import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  LogOut,
  Menu,
  Settings,
  Shield,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuthStore } from "../stores/auth-store";
import { Button } from "../ui/Button";

const ADMIN_LINKS = [
  { to: "/app/configuracion", label: "Configuración", icon: Settings },
  { to: "/app/usuarios", label: "Usuarios", icon: Users },
  { to: "/app/arco", label: "ARCO", icon: Shield },
  { to: "/app/auditoria", label: "Auditoría", icon: FileText },
] as const;

export function AppShell() {
  const principal = useAuthStore((state) => state.principal);
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const setMfaChallengeId = useAuthStore((state) => state.setMfaChallengeId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const isAdmin = principal?.role === "administrador";

  const logout = useMutation({
    mutationFn: () => api<void>("/sessions/current", { method: "DELETE" }),
    onSettled: () => {
      setPrincipal(null);
      setMfaChallengeId(null);
      queryClient.clear();
      navigate("/ingresar", { replace: true });
    },
  });

  const links = [
    { to: "/app/perfil", label: "Perfil", icon: UserRound },
    ...(isAdmin ? ADMIN_LINKS : []),
  ];

  function navList(id?: string) {
    return (
      <nav id={id} aria-label="Principal" className="stack">
        {links.map((link) => {
          const Icon = link.icon;
          return (
            <NavLink
              key={link.to}
              to={link.to}
              className="nav-link"
              onClick={() => setMenuOpen(false)}
            >
              {({ isActive }) => (
                <>
                  <Icon size={24} aria-hidden="true" />
                  <span>{link.label}</span>
                  {isActive ? <span className="sr-only">(página actual)</span> : null}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <aside className="sidebar">
        <p className="brand">NEXUS CRM</p>
        {navList()}
        <Button variant="ghost" onClick={() => logout.mutate()} loading={logout.isPending}>
          <LogOut size={24} aria-hidden="true" />
          Cerrar sesión
        </Button>
      </aside>
      <div className="shell-main">
        <header className="topbar">
          <p className="brand">NEXUS CRM</p>
          <Button
            variant="ghost"
            aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={menuOpen}
            aria-controls="menu-movil"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={24} aria-hidden="true" /> : <Menu size={24} aria-hidden="true" />}
          </Button>
        </header>
        {menuOpen ? (
          <div className="mobile-menu" id="menu-movil">
            {navList("menu-movil-nav")}
            <Button variant="ghost" onClick={() => logout.mutate()} loading={logout.isPending}>
              <LogOut size={24} aria-hidden="true" />
              Cerrar sesión
            </Button>
          </div>
        ) : null}
        <main id="contenido" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
