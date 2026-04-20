import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Brain, Plus, Pencil, Trash2, Save, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/use-toast";
import { apiGetMemoryFacts, apiCreateMemoryFact, apiUpdateMemoryFact, apiDeleteMemoryFact } from "@/lib/api";

interface Fact {
  id: string;
  key: string;
  value: string;
}

export default function Memory() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    loadFacts();
  }, []);

  const loadFacts = async () => {
    try {
      setLoading(true);
      const data = await apiGetMemoryFacts();
      setFacts(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load memory facts";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) {
      toast({ title: "Error", description: "Key and value are required", variant: "destructive" });
      return;
    }

    try {
      setSaving(true);
      await apiCreateMemoryFact(newKey, newValue);
      setNewKey("");
      setNewValue("");
      setShowAdd(false);
      toast({ title: "Fact added" });
      await loadFacts();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to add fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveEdit = async (id: string) => {
    try {
      setSaving(true);
      await apiUpdateMemoryFact(id, editValue);
      setEditing(null);
      toast({ title: "Fact updated" });
      await loadFacts();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDeleteMemoryFact(id);
      toast({ title: "Fact deleted" });
      await loadFacts();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete fact";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  if (loading) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 lg:p-8">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-6 p-6 lg:p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Memory</h1>
          <p className="text-muted-foreground text-sm mt-1">Agent memory — key/value facts</p>
        </div>
        <Button className="gradient-primary text-primary-foreground" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4 mr-2" /> Add fact
        </Button>
      </div>

      {showAdd && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-primary/30 bg-card p-4 flex items-end gap-3">
          <div className="flex-1 space-y-1">
            <label className="text-xs text-muted-foreground">Key</label>
            <Input value={newKey} onChange={e => setNewKey(e.target.value)} className="bg-secondary border-border font-mono text-sm" placeholder="my_key" />
          </div>
          <div className="flex-1 space-y-1">
            <label className="text-xs text-muted-foreground">Value</label>
            <Input value={newValue} onChange={e => setNewValue(e.target.value)} className="bg-secondary border-border text-sm" placeholder="Value" />
          </div>
          <Button size="sm" onClick={handleAdd} disabled={saving} className="gradient-primary text-primary-foreground">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)} className="text-muted-foreground"><X className="h-4 w-4" /></Button>
        </motion.div>
      )}

      {facts.length === 0 ? (
        <EmptyState icon={Brain} title="No memory facts" description="Add key-value facts for your agents to remember." actionLabel="Add fact" onAction={() => setShowAdd(true)} />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="text-left px-5 py-3 font-medium">Key</th>
                <th className="text-left px-5 py-3 font-medium">Value</th>
                <th className="px-5 py-3 w-20"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {facts.map(fact => (
                <tr key={fact.id} className="hover:bg-accent/30 transition-colors">
                  <td className="px-5 py-3 text-sm font-mono text-primary">{fact.key}</td>
                  <td className="px-5 py-3 text-sm text-foreground">
                    {editing === fact.id ? (
                      <Input
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        className="bg-secondary border-border text-sm h-8"
                        autoFocus
                        onKeyDown={e => { if (e.key === "Enter") handleSaveEdit(fact.id); }}
                      />
                    ) : fact.value}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex gap-1">
                      {editing === fact.id ? (
                        <>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-primary" onClick={() => handleSaveEdit(fact.id)}>
                            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground" onClick={() => setEditing(null)}><X className="h-3.5 w-3.5" /></Button>
                        </>
                      ) : (
                        <>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground" onClick={() => { setEditing(fact.id); setEditValue(fact.value); }}><Pencil className="h-3.5 w-3.5" /></Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => handleDelete(fact.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
