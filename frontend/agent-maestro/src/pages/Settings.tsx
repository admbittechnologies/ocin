import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { getUser } from "@/lib/auth";
import { Separator } from "@/components/ui/separator";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Eye, EyeOff, Trash2, Check, Palette, Loader2, X } from "lucide-react";
import { useTheme, type Theme } from "@/hooks/use-theme";
import {
  apiChangePassword,
  apiSaveApiKey,
  apiGetApiKeys,
  apiUpdatePlan,
  apiDeleteAccount,
} from "@/lib/api";

// LLM Providers (API keys that count toward plan limit)
const llmProviders = ["OpenAI", "Anthropic", "Google", "Mistral", "OpenRouter", "Grok", "Qwen", "DeepSeek", "Z.ai"];

// Tool Integrations (external tools - no plan limit)
// These would be returned separately from backend but for now we'll use the existing providers array
// that aren't LLM providers
const toolProviders = [];

export default function SettingsPage() {
  const user = getUser();
  const { toast } = useToast();
  const { theme, setTheme, themes, accentColors } = useTheme();

  const [email, setEmail] = useState(user?.email || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [selectedPlan, setSelectedPlan] = useState(user?.plan || "free");
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  const [changingPassword, setChangingPassword] = useState(false);
  const [savingKey, setSavingKey] = useState<Record<string, boolean>>({});
  const [updatingPlan, setUpdatingPlan] = useState(false);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [tavilyKey, setTavilyKey] = useState("");
  const [tavilyConnected, setTavilyConnected] = useState(false);
  const [deletingTavily, setDeletingTavily] = useState(false);

  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      setLoadingKeys(true);
      const data = await apiGetApiKeys();
      setApiKeys(data);
      setTavilyKey(data["Tavily"] || "");
      setTavilyConnected(!!data["Tavily"]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load API keys";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoadingKeys(false);
    }
  };

  const handleDisconnectKey = async (provider: string) => {
    try {
      setDeletingProvider(prev => ({ ...prev, [provider]: true }));
      await apiDeleteApiKey(provider.toLowerCase());
      toast({ title: "Success", description: `${provider} API key removed successfully` });
      await loadApiKeys();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to remove API key";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setDeletingProvider(prev => ({ ...prev, [provider]: false }));
    }
  };

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword) {
      toast({ title: "Error", description: "Fill in both fields", variant: "destructive" });
      return;
    }
    if (newPassword.length < 6) {
      toast({ title: "Error", description: "Password must be at least 6 characters", variant: "destructive" });
      return;
    }

    try {
      setChangingPassword(true);
      await apiChangePassword(currentPassword, newPassword);
      toast({ title: "Password changed successfully" });
      setCurrentPassword("");
      setNewPassword("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to change password";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setChangingPassword(false);
    }
  };

  const handleSaveKey = async (provider: string) => {
    try {
      setSavingKey(prev => ({ ...prev, [provider]: true }));
      await apiSaveApiKey(provider, apiKeys[provider] || "");
      toast({ title: `${provider} key saved` });
      await loadApiKeys(); // Refresh to get masked keys
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save API key";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSavingKey(prev => ({ ...prev, [provider]: false }));
    }
  };

  const handleSaveTavilyKey = async () => {
    try {
      setSavingKey(prev => ({ ...prev, "Tavily": true }));
      await apiSaveApiKey("Tavily", tavilyKey);
      toast({ title: "Tavily key saved" });
      await loadApiKeys(); // Refresh to get masked key
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save Tavily key";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSavingKey(prev => ({ ...prev, "Tavily": false }));
    }
  };

  const handleRemoveTavilyKey = async () => {
    try {
      setDeletingTavily(true);
      console.log("Attempting to remove Tavily key...");
      // Remove key by saving empty string (cleans up the key on backend)
      await apiSaveApiKey("Tavily", "");
      console.log("Tavily key removal succeeded, refreshing UI...");
      // Only show success and clear state if save succeeds
      toast({ title: "Tavily key removed" });
      setTavilyKey(""); // Clear input
      await loadApiKeys(); // Refresh to update connection status
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to remove Tavily key";
      console.error("Failed to remove Tavily key:", error);
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      console.log("Remove operation completed, resetting loading state");
      setDeletingTavily(false);
    }
  };

  const handleUpdatePlan = async (plan: "free" | "pro" | "business") => {
    if (plan === user?.plan) {
      toast({ title: "Info", description: `You're already on ${plan} plan` });
      return;
    }

    try {
      setUpdatingPlan(true);
      await apiUpdatePlan(plan);
      toast({ title: "Plan updated successfully" });
      setSelectedPlan(plan);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update plan";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setUpdatingPlan(false);
    }
  };

  const handleThemeChange = (t: Theme) => {
    setTheme(t);
    toast({ title: `Theme changed to ${t}` });
  };

  const handleDeleteAccount = async () => {
    try {
      setDeletingAccount(true);
      await apiDeleteAccount();
      toast({ title: "Account deleted", description: "You have been logged out" });
      // Clear auth and redirect to login
      localStorage.removeItem("ocin_jwt_token");
      localStorage.removeItem("ocin_user");
      window.location.href = "/login";
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete account";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setDeletingAccount(false);
      setDeleteConfirm(false);
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-8 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="text-muted-foreground text-sm mt-1">Manage your account, appearance, and API keys</p>
      </div>

      {/* Appearance */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-card space-y-4">
        <div className="flex items-center gap-2">
          <Palette className="h-4 w-4 text-primary" />
          <h2 className="text-foreground font-semibold text-sm">Appearance</h2>
        </div>
        <p className="text-xs text-muted-foreground">Choose a theme for the interface.</p>
        <div className="grid grid-cols-3 gap-3">
          {themes.map((t) => (
            <button
              key={t.value}
              onClick={() => handleThemeChange(t.value)}
              className={`relative flex flex-col items-center gap-2 rounded-lg border p-4 transition-all hover:border-primary/50 ${
                theme === t.value
                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                  : "border-border bg-secondary/50 hover:bg-secondary"
              }`}
            >
              <div className="flex gap-1.5">
                <div
                  className="h-8 w-8 rounded-md border border-border/50"
                  style={{ background: t.preview }}
                />
                <div
                  className="h-8 w-8 rounded-md border border-border/50"
                  style={{ background: accentColors[t.value] }}
                />
              </div>
              <span className="text-xs font-medium text-foreground">{t.label}</span>
              {theme === t.value && (
                <div className="absolute top-2 right-2 h-4 w-4 rounded-full bg-primary flex items-center justify-center">
                  <Check className="h-2.5 w-2.5 text-primary-foreground" />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Profile */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-card space-y-4">
        <h2 className="text-foreground font-semibold text-sm">Profile</h2>
        <div className="space-y-2">
          <Label className="text-foreground text-sm">Email</Label>
          <Input value={email} readOnly disabled className="bg-muted border-border text-muted-foreground cursor-not-allowed" />
        </div>
        <Separator className="bg-border" />
        <div className="space-y-3">
          <Label className="text-foreground text-sm">Subscription Plan</Label>
          <div className="grid grid-cols-3 gap-3">
            {([
              { id: "free", name: "Free", price: "$0/mo", features: ["1 agent", "100 runs/mo"] },
              { id: "pro", name: "Pro", price: "$29/mo", features: ["10 agents", "5,000 runs/mo", "Priority support"] },
              { id: "business", name: "Business", price: "$99/mo", features: ["Unlimited agents", "Unlimited runs", "Dedicated support", "SSO"] },
            ] as const).map((plan) => (
              <button
                key={plan.id}
                onClick={() => handleUpdatePlan(plan.id as "free" | "pro" | "business")}
                disabled={updatingPlan}
                className={`relative flex flex-col rounded-lg border p-4 text-left transition-all hover:border-primary/50 ${
                  selectedPlan === plan.id
                    ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                    : "border-border bg-secondary/50 hover:bg-secondary"
                }`}
              >
                <span className="text-sm font-semibold text-foreground">{plan.name}</span>
                <span className="text-xs font-mono text-primary mt-1">{plan.price}</span>
                <ul className="mt-2 space-y-1">
                  {plan.features.map((f) => (
                    <li key={f} className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-primary flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                {selectedPlan === plan.id && (
                  <div className="absolute top-2 right-2 h-4 w-4 rounded-full bg-primary flex items-center justify-center">
                    <Check className="h-2.5 w-2.5 text-primary-foreground" />
                  </div>
                )}
                {updatingPlan && selectedPlan === plan.id && (
                  <div className="absolute inset-0 bg-card/50 flex items-center justify-center">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Password */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-card space-y-4">
        <h2 className="text-foreground font-semibold text-sm">Change Password</h2>
        <div className="space-y-2">
          <Label className="text-foreground text-sm">Current password</Label>
          <Input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} className="bg-secondary border-border" />
        </div>
        <div className="space-y-2">
          <Label className="text-foreground text-sm">New password</Label>
          <Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} className="bg-secondary border-border" />
        </div>
        <Button onClick={handleChangePassword} variant="outline" disabled={changingPassword} className="border-border text-foreground" size="sm">
          {changingPassword ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          Update password
        </Button>
      </div>

      {/* API Keys - LLM Providers */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-card space-y-4">
        <h2 className="text-foreground font-semibold text-sm">LLM Providers</h2>
        <p className="text-xs text-muted-foreground">Manage your LLM provider API keys (Google, Anthropic, OpenAI, etc.). Keys are encrypted and stored securely.</p>
        {loadingKeys ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-3">
            {llmProviders.map(p => (
              <div key={p} className="flex items-center gap-3">
                <Label className="text-foreground text-sm w-24 flex-shrink-0">{p}</Label>
                <div className="relative flex-1">
                  <Input
                    type={visibleKeys[p] ? "text" : "password"}
                    value={apiKeys[p] || ""}
                    onChange={e => setApiKeys(prev => ({ ...prev, [p]: e.target.value }))}
                    placeholder={`${p} API key`}
                    className="bg-secondary border-border font-mono text-xs pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setVisibleKeys(prev => ({ ...prev, [p]: !prev[p] }))}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {visibleKeys[p] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <Button size="sm" variant="outline" disabled={savingKey[p]} className="border-border text-foreground" onClick={() => handleSaveKey(p)}>
                  {savingKey[p] ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search & Web */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-card space-y-4">
        <h2 className="text-foreground font-semibold text-sm">Search & Web</h2>
        <p className="text-xs text-muted-foreground">Enable web search capabilities for your agents.</p>
        {loadingKeys ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <Label className="text-foreground text-sm flex items-center gap-2">
                  <span>Tavily</span>
                  <span className="text-xs text-muted-foreground font-normal">Enables web search for your agents</span>
                </Label>
                <div className="relative mt-2">
                  <Input
                    type={visibleKeys["Tavily"] ? "text" : "password"}
                    value={tavilyKey}
                    onChange={e => setTavilyKey(e.target.value)}
                    placeholder="tvly-..."
                    className="bg-secondary border-border font-mono text-xs pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setVisibleKeys(prev => ({ ...prev, "Tavily": !prev["Tavily"] }))}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {visibleKeys["Tavily"] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className={`text-xs ${tavilyConnected ? "text-green-600 dark:text-green-400" : "text-muted-foreground"}`}>
                    {tavilyConnected ? "Connected" : "Not connected"}
                  </span>
                  <a href="https://tavily.com" target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">
                    Get your API key at tavily.com
                  </a>
                </div>
              </div>
              {tavilyConnected ? (
                <Button size="sm" variant="outline" disabled={deletingTavily} className="border-border text-foreground" onClick={handleRemoveTavilyKey}>
                  {deletingTavily ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Remove"}
                </Button>
              ) : (
                <Button size="sm" variant="outline" disabled={savingKey["Tavily"]} className="border-border text-foreground" onClick={handleSaveTavilyKey}>
                  {savingKey["Tavily"] ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      <Separator className="bg-border" />

      {/* Danger zone */}
      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-6 space-y-4">
        <h2 className="text-destructive font-semibold text-sm">Danger Zone</h2>
        <p className="text-xs text-muted-foreground">Permanently delete your account and all associated data.</p>
        <Button variant="outline" className="border-destructive/50 text-destructive hover:bg-destructive/10" size="sm" disabled={deletingAccount} onClick={() => setDeleteConfirm(true)}>
          {deletingAccount ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" /> : <Trash2 className="h-3.5 w-3.5 mr-2" />}
          Delete account
        </Button>
      </div>

      <AlertDialog open={deleteConfirm} onOpenChange={setDeleteConfirm}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Delete your account?</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">This action is permanent. All agents, runs, schedules, and data will be deleted forever.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-border text-foreground">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteAccount} disabled={deletingAccount} className="bg-destructive text-destructive-foreground">
              {deletingAccount ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Delete forever
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
