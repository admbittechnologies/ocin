import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { register } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { Eye, EyeOff, Check } from "lucide-react";
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
  const [showPassword, setShowPassword] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<User['plan']>('free');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast({ title: "Error", description: "Please fill in all fields", variant: "destructive" });
      return;
    }
    if (password.length < 6) {
      toast({ title: "Error", description: "Password must be at least 6 characters", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      await register(email, password, selectedPlan);
      toast({ title: "Account created!", description: `Welcome to OCIN on the ${selectedPlan} plan.` });
      navigate("/");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Registration failed. Please try again.";
      toast({ title: "Registration failed", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              <div className="space-y-2">
                <Label htmlFor="password" className="text-foreground text-sm">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Min 6 characters"
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

            <Button type="submit" className="w-full gradient-primary text-primary-foreground font-medium" disabled={loading}>
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
