import { useParams } from "react-router-dom";

import { useMembership } from "../auth/session";

/**
 * Which flat's books are on screen, and where its sub-pages live.
 *  - My own flat (any role that lives in one):  /s/:id/statement, /s/:id/receipt/:entryId
 *  - Another flat (office-bearers only):          /s/:id/flat/:flatId/statement, .../receipt/:entryId
 * It is decided by the URL, not by role: a treasurer who lives in a flat opens their own
 * statement exactly like a resident does. The server enforces who may see which flat.
 */
export function useStatementTarget() {
  const membership = useMembership();
  const { flatId } = useParams();
  const viewingAnotherFlat = flatId !== undefined;
  const id = viewingAnotherFlat ? Number(flatId) : membership.flat_id;
  const prefix = `/s/${membership.society_id}`;
  return {
    membership,
    societyId: membership.society_id,
    flatId: id !== null && Number.isFinite(id) ? id : null,
    /** True when looking at someone else's flat (shows the "All flats" way back). */
    staff: viewingAnotherFlat,
    statementPath: viewingAnotherFlat ? `${prefix}/flat/${id}/statement` : `${prefix}/statement`,
    receiptPath: (entryId: number) =>
      viewingAnotherFlat
        ? `${prefix}/flat/${id}/receipt/${entryId}`
        : `${prefix}/receipt/${entryId}`,
    backPath: viewingAnotherFlat ? `${prefix}/dues` : `${prefix}/home`,
  };
}
