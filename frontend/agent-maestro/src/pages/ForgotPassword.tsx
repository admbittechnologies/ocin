import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { ArrowLeft, Mail } from "lucide-react";
import { OcinLogo } from "@/components/OcinLogo";
import { apiForgotPassword } from "@/lib/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      toast({ title: "Error", description: "Please enter your email", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      await apiForgotPassword(email);
      setSent(true);
      toast({ title: "Email sent", description: "Check your inbox for a password reset link." });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send reset email. Please try again.";
      toast({ title: "Error", description: message, variant: "destructive" });
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
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <OcinLogo size={44} />
            <span className="text-2xl font-semibold text-foreground">OCIN</span>
          </div>
          <p className="text-muted-foreground text-sm">Reset your password</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-6 shadow-card">
          {sent ? (
            <div className="text-center py-4">
              <div className="mx-auto h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                <Mail className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-foreground font-semibold mb-2">Check your email</h3>
              <p className="text-muted-foreground text-sm mb-6">
                We sent a password reset link to <span className="text-foreground">{email}</span>
              </p>
              <Link to="/login">
                <Button variant="outline" className="border-border text-foreground">
                  <ArrowLeft className="h-4 w-4 mr-2" /> Back to sign in
                </Button>
              </Link>
            </div>
          ) : (
            <>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-foreground text-sm">Email address</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="bg-secondary border-border"
                  />
                </div>
                <Button type="submit" className="w-full gradient-primary text-primary-foreground font-medium" disabled={loading}>
                  {loading ? "Sending..." : "Send reset link"}
                </Button>
              </form>
              <p className="text-center text-sm text-muted-foreground mt-6">
                <Link to="/login" className="text-primary hover:underline inline-flex items-center gap-1">
                  <ArrowLeft className="h-3 w-3" /> Back to sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
