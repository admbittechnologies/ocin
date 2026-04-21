import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, X, Loader2 } from "lucide-react";
import { OcinLogo } from "@/components/OcinLogo";
import { apiGetCurrentUser } from "@/lib/api";
import { login } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";

type VerifyStatus = "loading" | "success" | "error" | "already_verified";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<VerifyStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMsg("No verification token provided.");
      return;
    }

    const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

    fetch(`${API_BASE}/auth/verify-email?token=${token}`)
      .then(async (res) => {
        const data = await res.json();
        if (res.ok && data.access_token) {
          // Store token
          localStorage.setItem("ocin_jwt_token", data.access_token);
          localStorage.setItem("ocin_user", JSON.stringify(data.user));
          setStatus("success");
          toast({ title: "Email verified!", description: "Welcome to OCIN." });
          // Redirect after short delay
          setTimeout(() => navigate("/"), 2000);
        } else {
          setStatus("error");
          setErrorMsg(data.detail?.error || data.detail || "Invalid or expired link.");
        }
      })
      .catch(() => {
        setStatus("error");
        setErrorMsg("Something went wrong. Please try again.");
      });
  }, [token, navigate, toast]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md text-center"
      >
        <div className="inline-flex items-center gap-2 mb-6">
          <OcinLogo size={44} />
          <span className="text-2xl font-semibold text-foreground">OCIN</span>
        </div>

        <div className="rounded-xl border border-border bg-card p-8 shadow-card">
          {status === "loading" && (
            <>
              <div className="mx-auto w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                <Loader2 className="h-7 w-7 text-primary animate-spin" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">Verifying...</h2>
              <p className="text-muted-foreground text-sm">Please wait while we verify your email.</p>
            </>
          )}

          {status === "success" && (
            <>
              <div className="mx-auto w-14 h-14 rounded-full bg-green-500/10 flex items-center justify-center mb-4">
                <Check className="h-7 w-7 text-green-500" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">Email verified!</h2>
              <p className="text-muted-foreground text-sm">Redirecting you to the dashboard...</p>
            </>
          )}

          {status === "error" && (
            <>
              <div className="mx-auto w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
                <X className="h-7 w-7 text-red-500" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">Verification failed</h2>
              <p className="text-muted-foreground text-sm mb-4">{errorMsg}</p>
              <button
                onClick={() => navigate("/register")}
                className="text-sm text-primary hover:underline"
              >
                Try registering again
              </button>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
