import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "./auth/session";
import { AppLayout } from "./layout/AppLayout";
import { ActivityPage } from "./pages/ActivityPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { FlatsPage } from "./pages/admin/FlatsPage";
import { ResidentsPage } from "./pages/admin/ResidentsPage";
import { DuesPage } from "./pages/DuesPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { ReceiptPage } from "./pages/ReceiptPage";
import { ResidentDashboard } from "./pages/ResidentDashboard";
import { StatementPage } from "./pages/StatementPage";
import { ExpensesPage } from "./pages/treasurer/ExpensesPage";
import { OverviewPage } from "./pages/treasurer/OverviewPage";
import { PaymentsPage } from "./pages/treasurer/PaymentsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        {/* The society in the URL mirrors the API (/api/societies/<id>/...). The server still
            checks every request; these guards only keep the UI from showing broken pages. */}
        <Route path="/s/:societyId" element={<RequireRole roles={["admin", "treasurer", "resident"]} />}>
          <Route element={<AppLayout />}>
            {/* Residents: their own flat only. */}
            <Route element={<RequireRole roles={["resident"]} />}>
              <Route path="home" element={<ResidentDashboard />} />
              <Route path="statement" element={<StatementPage />} />
              <Route path="receipt/:entryId" element={<ReceiptPage />} />
            </Route>

            {/* Admin and treasurer: the society's books. */}
            <Route element={<RequireRole roles={["admin", "treasurer"]} />}>
              <Route path="overview" element={<OverviewPage />} />
              <Route path="dues" element={<DuesPage />} />
              <Route path="expenses" element={<ExpensesPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="flat/:flatId/statement" element={<StatementPage />} />
              <Route path="flat/:flatId/receipt/:entryId" element={<ReceiptPage />} />
            </Route>

            <Route element={<RequireRole roles={["treasurer"]} />}>
              <Route path="payments" element={<PaymentsPage />} />
            </Route>
            <Route element={<RequireRole roles={["admin"]} />}>
              <Route path="flats" element={<FlatsPage />} />
              <Route path="residents" element={<ResidentsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
