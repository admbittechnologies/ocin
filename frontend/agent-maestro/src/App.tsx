import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/hooks/use-theme";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/AppLayout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import VerifyEmail from "./pages/VerifyEmail";
import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import Tools from "./pages/Tools";
import Schedules from "./pages/Schedules";
import Runs from "./pages/Runs";
import Memory from "./pages/Memory";
import SettingsPage from "./pages/Settings";
import Chat from "./pages/Chat";
import NotFound from "./pages/NotFound";
import Approvals from "./pages/Approvals";

const queryClient = new QueryClient();

const ProtectedPage = ({ children }: { children: React.ReactNode }) => (
  <ProtectedRoute>
    <AppLayout>{children}</AppLayout>
  </ProtectedRoute>
);

const App = () => (
  <ThemeProvider>
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/" element={<ProtectedPage><Dashboard /></ProtectedPage>} />
          <Route path="/chat" element={<ProtectedPage><Chat /></ProtectedPage>} />
          <Route path="/agents" element={<ProtectedPage><Agents /></ProtectedPage>} />
          <Route path="/tools" element={<ProtectedPage><Tools /></ProtectedPage>} />
          <Route path="/schedules" element={<ProtectedPage><Schedules /></ProtectedPage>} />
          <Route path="/runs" element={<ProtectedPage><Runs /></ProtectedPage>} />
          <Route path="/memory" element={<ProtectedPage><Memory /></ProtectedPage>} />
          <Route path="/settings" element={<ProtectedPage><SettingsPage /></ProtectedPage>} />
          <Route path="/approvals" element={<ProtectedPage><Approvals /></ProtectedPage>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
  </ThemeProvider>
);

export default App;
