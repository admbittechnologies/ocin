import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiRegister } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { Eye, EyeOff, Check, Mail } from "lucide-react";
import { OcinLogo } from "@/components/OcinLogo";
import type { User } from "@/lib/auth";

const plans: { id: User['plan']; name: string; price: string; features: string[] }[] = [
  { id: 'free', name: 'Free', price: '$0/mo', features: ['3 agents', '100 runs/mo', 'Community support'] },
  { id: 'pro', name: 'Pro', price: '$29/mo', features: ['Unlimited agents', '5,000 runs/mo', 'Priority support', 'Webhooks'] },
  { id: 'business', name: 'Business', price: '$99/mo', features: ['Everything in Pro', 'Unlimited runs', 'Dedicated support', 'SSO', 'Custom tools'] },
];

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<User['plan']>('free');
  const [loading, setLoading] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !confirmPassword) {
      toast({ title: "Error", description: "Please fill in all fields", variant: "destructive" });
      return;
    }
    if (password.length < 8) {
      toast({ title: "Error", description: "Password must be at least 8 characters", variant: "destructive" });
      return;
    }
    if (password !== confirmPassword) {
      toast({ title: "Error", description: "Passwords do not match", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      await apiRegister(email, password, selectedPlan);
      setSentTo(email);
      toast({ title: "Check your inbox", description: `Verification email sent to ${email}` });
    } catch (error: any) {
      const message = error?.message || "Registration failed. Please try again.";
      toast({ title: "Registration failed", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  // Verification email sent state
  if (sentTo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-md text-center"
        >
          <div className="inline-flex items-center gap-2 mb-4">
            <OcinLogo size={44} />
            <span className="text-2xl font-semibold text-foreground">OCIN</span>
          </div>
          <div className="rounded-xl border border-border bg-card p-8 shadow-card">
            <div className="mx-auto w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
              <Mail className="h-7 w-7 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Check your email</h2>
            <p className="text-muted-foreground text-sm mb-6">
              We sent a verification link to <strong className="text-foreground">{sentTo}</strong>.<br />
              Click the link to activate your account.
            </p>
            <p className="text-xs text-muted-foreground">
              Didn't receive it?{" "}
              <button
                onClick={async () => {
                  try {
                    const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
                    const res = await fetch(`${API_BASE}/auth/resend-verification`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ email: sentTo }),
                    });
                    if (res.ok) toast({ title: "Sent!", description: "Check your inbox again." });
                  } catch {}
                }}
                className="text-primary hover:underline"
              >
                Resend verification email
              </button>
            </p>
          </div>
          <p className="text-sm text-muted-foreground mt-4">
            <Link to="/login" className="text-primary hover:underline">Back to sign in</Link>
          </p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-2xl"
      >
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <OcinLogo size={44} />
            <span className="text-2xl font-semibold text-foreground">OCIN</span>
          </div>
          <p className="text-muted-foreground text-sm">Create your account</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-6 shadow-card">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-foreground text-sm">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-secondary border-border"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="password" className="text-foreground text-sm">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Min 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="bg-secondary border-border pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-foreground text-sm">Confirm Password</Label>
                <div className="relative">
                  <Input
                    id="confirmPassword"
                    type={showPassword ? "text" : "password"}
                    placeholder="Repeat password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className={`bg-secondary border-border pr-10 ${confirmPassword && confirmPassword !== password ? 'border-red-500' : ''}`}
                  />
                  {confirmPassword && confirmPassword === password && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 text-green-500">
                      <Check className="h-4 w-4" />
                    </div>
                  )}
                </div>
                {confirmPassword && confirmPassword !== password && (
                  <p className="text-xs text-red-500">Passwords do not match</p>
                )}
              </div>
            </div>

            <div className="space-y-3">
              <Label className="text-foreground text-sm">Select a plan</Label>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {plans.map((plan) => (
                  <button
                    key={plan.id}
                    type="button"
                    onClick={() => setSelectedPlan(plan.id)}
                    className={`rounded-lg border p-4 text-left transition-all ${
                      selectedPlan === plan.id
                        ? 'border-primary bg-primary/5 shadow-glow'
                        : 'border-border bg-secondary hover:border-muted-foreground/30'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-foreground text-sm">{plan.name}</span>
                      {selectedPlan === plan.id && (
                        <div className="h-5 w-5 rounded-full gradient-primary flex items-center justify-center">
                          <Check className="h-3 w-3 text-primary-foreground" />
                        </div>
                      )}
                    </div>
                    <p className="text-primary font-mono text-lg mb-3">{plan.price}</p>
                    <ul className="space-y-1">
                      {plan.features.map((f) => (
                        <li key={f} className="text-xs text-muted-foreground flex items-center gap-1.5">
                          <Check className="h-3 w-3 text-primary" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  </button>
                ))}
              </div>
            </div>

            <Button type="submit" className="w-full gradient-primary text-primary-foreground font-medium" disabled={loading || (password !== confirmPassword && confirmPassword.length > 0)}>
              {loading ? "Creating account..." : "Create account"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-6">
            Already have an account?{" "}
            <Link to="/login" className="text-primary hover:underline">Sign in</Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
