import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireFlat, RequireRole } from "./auth/session";
import { AppLayout } from "./layout/AppLayout";
import { ActivityPage } from "./pages/ActivityPage";
import { PeoplePage } from "./pages/admin/PeoplePage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { DuesPage } from "./pages/DuesPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { ReceiptPage } from "./pages/ReceiptPage";
import { ResidentDashboard } from "./pages/ResidentDashboard";
import { StatementPage } from "./pages/StatementPage";
import { ExpensesPage } from "./pages/treasurer/ExpensesPage";
import { OverviewPage } from "./pages/treasurer/OverviewPage";
import { PaymentsPage } from "./pages/treasurer/PaymentsPage";

const EVERYONE = ["president", "secretary", "treasurer", "resident"] as const;
const OFFICE_BEARERS = ["president", "secretary", "treasurer"] as const;
const MANAGERS = ["president", "secretary"] as const;

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        {/* The society in the URL mirrors the API (/api/societies/<id>/...). The server still
            checks every request; these guards only keep the UI from showing broken pages. */}
        <Route path="/s/:societyId" element={<RequireRole roles={[...EVERYONE]} />}>
          <Route element={<AppLayout />}>
            {/* My own flat: any role, as long as the person lives in one. */}
            <Route element={<RequireFlat />}>
              <Route path="home" element={<ResidentDashboard />} />
              <Route path="statement" element={<StatementPage />} />
              <Route path="receipt/:entryId" element={<ReceiptPage />} />
            </Route>

            {/* The society's books: the office-bearers. */}
            <Route element={<RequireRole roles={[...OFFICE_BEARERS]} />}>
              <Route path="overview" element={<OverviewPage />} />
              <Route path="dues" element={<DuesPage />} />
              <Route path="payments" element={<PaymentsPage />} />
              <Route path="expenses" element={<ExpensesPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="flat/:flatId/statement" element={<StatementPage />} />
              <Route path="flat/:flatId/receipt/:entryId" element={<ReceiptPage />} />
            </Route>

            {/* Flats and people: president and secretary. */}
            <Route element={<RequireRole roles={[...MANAGERS]} />}>
              <Route path="people" element={<PeoplePage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
