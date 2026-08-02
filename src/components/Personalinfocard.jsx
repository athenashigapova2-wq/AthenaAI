import { useState } from 'react';
import { supabase } from '@/api/supabaseClient';
import { entities } from '@/lib/entities';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Pencil } from 'lucide-react';

// Стабильный цвет аватара по id пользователя — один и тот же человек всегда
// получает один и тот же цвет, но у разных людей он разный.
const AVATAR_COLORS = ['#6FB8D9', '#D4B876', '#C23B2E', '#8B6F9E', '#5A9E7A'];
function avatarColor(id) {
  if (!id) return AVATAR_COLORS[0];
  const hash = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}
function initials(name, email) {
  if (name?.trim()) {
    const parts = name.trim().split(/\s+/);
    return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase();
  }
  return (email?.[0] || '?').toUpperCase();
}

export default function PersonalInfoCard({ user, profile, onUpdate }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(user?.user_metadata?.full_name || '');
  const [age, setAge] = useState(profile?.age || '');
  const [height, setHeight] = useState(profile?.height_cm || '');
  const [weight, setWeight] = useState(profile?.weight_kg || '');

  const openDialog = () => {
    setName(user?.user_metadata?.full_name || '');
    setAge(profile?.age || '');
    setHeight(profile?.height_cm || '');
    setWeight(profile?.weight_kg || '');
    setOpen(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      // Имя лежит в двух местах: user_metadata (для мгновенного отображения
      // в приветствии) и в таблице profiles (для остального приложения)
      await supabase.auth.updateUser({ data: { full_name: name } });
      await entities.Profile.update(user.id, { full_name: name });
      const updated = await entities.UserProfile.update(profile.id, {
        age: Number(age) || null,
        height_cm: Number(height) || null,
        weight_kg: Number(weight) || null,
      });
      onUpdate(updated);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const displayName = user?.user_metadata?.full_name || user?.email;

  return (
    <>
      <button
        onClick={openDialog}
        className="w-full flex items-center gap-3 bg-card rounded-2xl border border-border p-4 text-left hover:bg-muted/40 transition-colors"
      >
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center text-white font-heading text-lg shrink-0"
          style={{ backgroundColor: avatarColor(user?.id) }}
        >
          {initials(user?.user_metadata?.full_name, user?.email)}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold font-heading truncate">{displayName}</p>
          <p className="text-xs text-muted-foreground">
            {profile?.age ? `${profile.age} лет` : 'Возраст не указан'}
            {profile?.height_cm ? ` · ${profile.height_cm} см` : ''}
            {profile?.weight_kg ? ` · ${profile.weight_kg} кг` : ''}
          </p>
        </div>
        <Pencil className="w-4 h-4 text-muted-foreground shrink-0" />
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Личные данные</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label htmlFor="pi-name">Имя</Label>
              <Input id="pi-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Амина" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2">
                <Label htmlFor="pi-age">Возраст</Label>
                <Input id="pi-age" type="number" value={age} onChange={(e) => setAge(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pi-height">Рост, см</Label>
                <Input id="pi-height" type="number" value={height} onChange={(e) => setHeight(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pi-weight">Вес, кг</Label>
                <Input id="pi-weight" type="number" value={weight} onChange={(e) => setWeight(e.target.value)} />
              </div>
            </div>
            <Button className="w-full h-11" onClick={save} disabled={saving}>
              {saving ? 'Сохраняю...' : 'Сохранить'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}