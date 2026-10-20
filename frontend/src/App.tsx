import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "./auth/session";
import { AppLayout } from "./layout/AppLayout";
import { FlatsPage } from "./pages/admin/FlatsPage";
import { ResidentsPage } from "./pages/admin/ResidentsPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { ResidentDashboard } from "./pages/ResidentDashboard";
import { ExpensesPage } from "./pages/treasurer/ExpensesPage";
import { OverviewPage } from "./pages/treasurer/OverviewPage";
import { PaymentsPage } from "./pages/treasurer/PaymentsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomeRedirect />} />

        {/* The society in the URL mirrors the API (/api/societies/<id>/...). The server still
            checks every request; these guards only keep the UI from showing broken pages. */}
        <Route path="/s/:societyId" element={<RequireRole roles={["admin", "treasurer", "resident"]} />}>
          <Route element={<AppLayout />}>
            <Route element={<RequireRole roles={["resident"]} />}>
              <Route path="home" element={<ResidentDashboard />} />
            </Route>
            <Route element={<RequireRole roles={["admin", "treasurer"]} />}>
              <Route path="overview" element={<OverviewPage />} />
              <Route path="expenses" element={<ExpensesPage />} />
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
