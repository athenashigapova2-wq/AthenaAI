import React, { useState, useEffect, useCallback } from "react";
import { toLocalDateStr } from "@/lib/utils";
import { entities } from "@/lib/entities";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog";
import { Loader2, Scale, LogOut, Save, Trash2, AlertTriangle, ShieldAlert, Mail } from "lucide-react";
import { format } from "date-fns";
import { useLang } from "@/lib/i18n";
import WeightChart from "@/components/WeightChart";
import RecalcMacrosDialog from "@/components/RecalcMacrosDialog";
import CycleTracker from "@/components/CycleTracker";
import PersonalInfoCard from "@/components/PersonalInfoCard";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import {
  calculateGoalTargets,
} from "@/features/profile/model/profileOptions";
import ProfileGoals from "@/features/profile/components/ProfileGoals";
import ProfilePreferences from "@/features/profile/components/ProfilePreferences";

export default function Profile() {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const [profile, setProfile] = useState(null);
  const [weights, setWeights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showWeightDialog, setShowWeightDialog] = useState(false);
  const [showRecalc, setShowRecalc] = useState(false);
  const [newWeight, setNewWeight] = useState("");
  const [form, setForm] = useState({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showDeleteGuidance, setShowDeleteGuidance] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadData = useCallback(async () => {
    const [profiles, allWeights] = await Promise.all([
      entities.UserProfile.filter({ created_by_id: user?.id }),
      entities.WeightLog.filter({ created_by_id: user?.id }, "-date", 30),
    ]);
    const p = profiles[0] || null;
    setProfile(p);
    if (p) {
      setForm({
        age: p.age || "", sex: p.sex || "male", height_cm: p.height_cm || "", weight_kg: p.weight_kg || "",
        goal: p.goal || "maintain", calorie_target: p.calorie_target || "", protein_target_g: p.protein_target_g || "",
        carb_target_g: p.carb_target_g || "", fat_target_g: p.fat_target_g || "",
        budget: p.budget || "medium", cooking_skill: p.cooking_skill || "basic",
        dietary_pattern: p.dietary_pattern || "omnivore",
        dietary_restrictions: p.dietary_restrictions || [],
        allergies: (p.allergies || []).join(", "), favorite_foods: (p.favorite_foods || []).join(", "),
        disliked_foods: (p.disliked_foods || []).join(", "),
      });
    }
    setWeights(allWeights.reverse());
    setLoading(false);
  }, [user]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      age: Number(form.age) || undefined, sex: form.sex, height_cm: Number(form.height_cm) || undefined,
      weight_kg: Number(form.weight_kg) || undefined, goal: form.goal,
      calorie_target: Number(form.calorie_target), protein_target_g: Number(form.protein_target_g),
      carb_target_g: Number(form.carb_target_g), fat_target_g: Number(form.fat_target_g),
      budget: form.budget, cooking_skill: form.cooking_skill,
      dietary_pattern: form.dietary_pattern || "omnivore",
      dietary_restrictions: form.dietary_restrictions || [],
      allergies: form.allergies.split(",").map((s) => s.trim()).filter(Boolean),
      favorite_foods: form.favorite_foods.split(",").map((s) => s.trim()).filter(Boolean),
      disliked_foods: form.disliked_foods.split(",").map((s) => s.trim()).filter(Boolean),
    };
    await entities.UserProfile.update(profile.id, payload);
    setSaving(false);
  };

  const handleLogWeight = async () => {
    if (!newWeight) return;
    const entry = await entities.WeightLog.create({ weight_kg: Number(newWeight), date: toLocalDateStr() });
    setWeights((w) => [...w, entry]);
    setNewWeight("");
    setShowWeightDialog(false);
  };

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleGoalChange = (goalKey) => {
    const targets = calculateGoalTargets({
      weight: parseFloat(form.weight_kg),
      height: parseFloat(form.height_cm),
      age: parseFloat(form.age),
      sex: form.sex,
      goal: goalKey,
    });
    setForm((current) => ({ ...current, goal: goalKey, ...(targets || {}) }));
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await Promise.all([
        entities.UserProfile.deleteMany({ created_by_id: user?.id }),
        entities.MealLog.deleteMany({ created_by_id: user?.id }),
        entities.WeightLog.deleteMany({ created_by_id: user?.id }),
        entities.ShoppingItem.deleteMany({ created_by_id: user?.id }),
      ]);
    } catch { /* proceed regardless */ }
    setDeleting(false);
    setShowDeleteConfirm(false);
    setShowDeleteGuidance(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="px-4 pt-12 text-center">
        <p className="text-sm text-muted-foreground">{t("prof_completeOnboarding")}</p>
      </div>
    );
  }

  const weightData = weights.map((w) => ({ date: format(new Date(w.date), "MMM d"), val: w.weight_kg }));

  return (
    <div className="px-4 pt-6 pb-4 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold font-heading">{t("prof_title")}</h1>
        <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" onClick={() => logout()}>
          <LogOut className="w-3.5 h-3.5 mr-1" /> {t("prof_signOut")}
        </Button>
      </div>

      <PersonalInfoCard user={user} profile={profile} onUpdate={setProfile} />

      <div className="bg-card rounded-2xl border border-border p-4 flex items-center justify-between">
        <span className="text-sm font-semibold font-heading">{t("prof_language") || "Язык приложения"}</span>
        <LanguageSwitcher />
      </div>

      {(
        <div className="bg-card rounded-2xl border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold font-heading">{t("prof_weightHistory")}</span>
            <div className="flex items-center gap-1">
              {weights.length > 0 && (
                <Button
                  size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={async () => {
                    if (!window.confirm(t("prof_deleteAllWeightsConfirm"))) return;
                    await entities.WeightLog.deleteMany({ created_by_id: user.id });
                    setWeights([]);
                  }}
                  aria-label={t("prof_deleteAllWeights")}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              )}
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowWeightDialog(true)}>
                <Scale className="w-3 h-3 mr-1" /> {t("prof_log")}
              </Button>
            </div>
          </div>
          <WeightChart data={weightData} />
        </div>
      )}

      {profile?.sex === "female" && (
        <CycleTracker profile={profile} onProfileUpdate={setProfile} />
      )}

      <ProfileGoals
        form={form}
        t={t}
        onGoalChange={handleGoalChange}
        onUpdate={update}
        onRecalculate={() => setShowRecalc(true)}
      />

      <ProfilePreferences form={form} t={t} onUpdate={update} />

      <Button className="w-full h-11" onClick={handleSave} disabled={saving}>
        {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
        {saving ? t("prof_saving") : t("prof_save")}
      </Button>

      <div className="pt-2">
        <Button variant="outline" className="w-full h-11 text-destructive border-destructive/30 hover:bg-destructive/5" onClick={() => setShowDeleteConfirm(true)}>
          <Trash2 className="w-4 h-4 mr-1.5" /> {t("prof_delete")}
        </Button>
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="font-heading">{t("prof_delTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("prof_delDesc")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t("prof_cancel")}</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={handleDeleteAccount} disabled={deleting}>
              {deleting ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <AlertTriangle className="w-4 h-4 mr-1.5" />}
              {deleting ? t("prof_deleting") : t("prof_deleteEverything")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={showDeleteGuidance} onOpenChange={setShowDeleteGuidance}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-heading">{t("prof_delDoneTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex justify-center">
              <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center">
                <ShieldAlert className="w-6 h-6 text-destructive" />
              </div>
            </div>
            <p className="text-sm text-muted-foreground text-center">{t("prof_delDoneBody")}</p>
            <Button asChild variant="outline" className="w-full h-10">
              <a href={`mailto:support@TODO-your-domain.com?subject=Delete%20My%20Account&body=Please%20fully%20remove%20my%20login%20credentials%20for%20email:%20${user?.email}`}>
                <Mail className="w-4 h-4 mr-1.5" /> Request login removal
              </a>
            </Button>
            <Button className="w-full h-10" onClick={() => logout()}>
              <LogOut className="w-4 h-4 mr-1.5" /> {t("prof_signOut")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showWeightDialog} onOpenChange={setShowWeightDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-heading">{t("prof_logWeightTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("prof_weightLabel")}</Label>
              <Input type="number" step="0.1" value={newWeight} onChange={(e) => setNewWeight(e.target.value)} placeholder="75.0" autoFocus />
            </div>
            <Button className="w-full h-10" onClick={handleLogWeight} disabled={!newWeight}>{t("prof_saveBtn")}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <RecalcMacrosDialog
        open={showRecalc}
        onOpenChange={setShowRecalc}
        profile={profile}
        onApplied={(data) => {
          setForm((f) => ({
            ...f,
            weight_kg: data.weight_kg ?? f.weight_kg,
            height_cm: data.height_cm ?? f.height_cm,
            age: data.age ?? f.age,
            sex: data.sex ?? f.sex,
            calorie_target: data.calorie_target,
            protein_target_g: data.protein_target_g,
            carb_target_g: data.carb_target_g,
            fat_target_g: data.fat_target_g,
          }));
          setShowRecalc(false);
        }}
      />
    </div>
  );
}
