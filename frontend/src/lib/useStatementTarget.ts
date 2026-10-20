import { useParams } from "react-router-dom";

import { useMembership } from "../auth/session";

/**
 * Which flat's books are on screen, and where its sub-pages live.
 *  - A resident always sees their OWN flat:   /s/:id/statement, /s/:id/receipt/:entryId
 *  - Admin and treasurer pick any flat:        /s/:id/flat/:flatId/statement, .../receipt/:entryId
 * The server enforces the same rule (a resident asking for another flat gets a 404); this just
 * decides which URL to build.
 */
export function useStatementTarget() {
  const membership = useMembership();
  const { flatId } = useParams();
  const staff = membership.role !== "resident";
  const id = staff ? Number(flatId) : membership.flat_id;
  const prefix = `/s/${membership.society_id}`;
  return {
    membership,
    societyId: membership.society_id,
    flatId: id !== null && Number.isFinite(id) ? id : null,
    staff,
    statementPath: staff ? `${prefix}/flat/${id}/statement` : `${prefix}/statement`,
    receiptPath: (entryId: number) =>
      staff ? `${prefix}/flat/${id}/receipt/${entryId}` : `${prefix}/receipt/${entryId}`,
    backPath: staff ? `${prefix}/dues` : `${prefix}/home`,
  };
}
