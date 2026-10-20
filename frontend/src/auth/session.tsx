import { createContext, useContext } from "react";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";

import { useMe } from "../api/hooks";
import type { Membership, Me, Role } from "../api/types";
import { PageLoader } from "../components/common";

interface SessionValue {
  me: Me;
  membership: Membership | null; // the membership for the society in the URL, if any
}

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <RequireAuth>");
  return value;
}

/** The role-specific landing page for a membership. */
export function homePath(m: Membership): string {
  const base = `/s/${m.society_id}`;
  return m.role === "resident" ? `${base}/home` : `${base}/overview`;
}

/** Blocks the whole app behind a login. */
export function RequireAuth() {
  const { data: me, isPending } = useMe();
  const location = useLocation();

  if (isPending) return <PageLoader />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // The server refuses every other request anyway; this just sends the person where they can act.
  if (me.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  return (
    <SessionContext.Provider value={{ me, membership: null }}>
      <Outlet />
    </SessionContext.Provider>
  );
}

/**
 * Guards a /s/:societyId/... route. The URL is only a hint: the server checks membership on
 * every request. This guard exists so the UI shows "not found" instead of broken pages.
 */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { me } = useSession();
  const { societyId } = useParams();
  const membership = me.memberships.find((m) => String(m.society_id) === societyId) ?? null;

  if (!membership) return <Navigate to="/" replace />;
  if (!roles.includes(membership.role)) return <Navigate to={homePath(membership)} replace />;
  return (
    <SessionContext.Provider value={{ me, membership }}>
      <Outlet />
    </SessionContext.Provider>
  );
}

/**
 * For pages about the person's OWN flat (home, statement, receipts). Any role qualifies, as
 * long as they live in a flat: an office-bearer is also a resident who pays dues.
 */
export function RequireFlat() {
  const { membership } = useSession();
  if (!membership) return <Navigate to="/" replace />;
  if (membership.flat_id === null) return <Navigate to={homePath(membership)} replace />;
  return <Outlet />;
}

/** For pages under RequireRole: the membership is guaranteed non-null there. */
export function useMembership(): Membership {
  const { membership } = useSession();
  if (!membership) throw new Error("useMembership must be used under <RequireRole>");
  return membership;
}
