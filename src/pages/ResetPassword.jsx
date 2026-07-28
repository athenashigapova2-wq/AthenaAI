import React, { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Lock, Loader2 } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";
import { useLang } from "@/lib/i18n";

// Примечание: с Supabase Auth не нужен token из URL вручную —
// клиент (detectSessionInUrl: true в supabaseClient.js) сам поднимает
// временную сессию из ссылки в письме сброса пароля. Здесь просто
// вызываем updateUser с новым паролем поверх этой сессии.
export default function ResetPassword() {
  const { t } = useLang();
  const { resetPassword } = useAuth();

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) { setError(t("auth_passwordsNoMatch")); return; }
    setLoading(true);
    try {
      await resetPassword(newPassword);
      window.location.href = "/login";
    } catch (err) {
      setError(err.message || t("auth_resetFail"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout icon={Lock} title={t("auth_newPassTitle")} subtitle={t("auth_newPassSub")}>
      {error && <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">{t("auth_newPass")}</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input id="password" type="password" autoComplete="new-password" autoFocus placeholder="••••••••" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="pl-10 h-12" required />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">{t("auth_confirm")}</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input id="confirm" type="password" autoComplete="new-password" placeholder="••••••••" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="pl-10 h-12" required />
          </div>
        </div>
        <Button type="submit" className="w-full h-12 font-medium" disabled={loading}>
          {loading ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("auth_resetting")}</>) : t("auth_resetPass")}
        </Button>
      </form>
    </AuthLayout>
  );
}
