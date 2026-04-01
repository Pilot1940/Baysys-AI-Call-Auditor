import { BrowserRouter, Routes, Route } from "react-router-dom";
import { MockAuthProvider } from "./mock/MockAuthContext";
import DashboardPage from "./pages/audit/DashboardPage";
import CallDetailPage from "./pages/audit/CallDetailPage";

function App() {
  return (
    <MockAuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/audit" element={<DashboardPage />} />
          <Route path="/audit/call/:id" element={<CallDetailPage />} />
        </Routes>
      </BrowserRouter>
    </MockAuthProvider>
  );
}

export default App;
