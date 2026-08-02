import { useState } from 'react';
import { entities } from '@/lib/entities';
import { Button } from '@/components/ui/button';
import { Droplet, X } from 'lucide-react';

const FLOW_OPTIONS = [
  { value: 'none', label: 'Нет' },
  { value: 'spotting', label: 'Мажущие' },
  { value: 'light', label: 'Лёгкие' },
  { value: 'medium', label: 'Средние' },
  { value: 'heavy', label: 'Обильные' },
];

const SYMPTOM_OPTIONS = ['Спазмы', 'Головная боль', 'Перепады настроения', 'Вздутие', 'Чувствительность груди', 'Усталость', 'Акне'];

// Полностью opt-in: сначала спрашиваем явное согласие, ничего не собираем
// без него. Можно отключить в любой момент кнопкой внизу трекера.
export default function CycleTracker({ profile, onProfileUpdate }) {
  const [saving, setSaving] = useState(false);
  const [flow, setFlow] = useState('none');
  const [symptoms, setSymptoms] = useState([]);
  const [intimacy, setIntimacy] = useState(false);
  const [saved, setSaved] = useState(false);

  const toggleSymptom = (s) => {
    setSymptoms((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const respondToOffer = async (accept) => {
    setSaving(true);
    try {
      const updated = await entities.UserProfile.update(profile.id, {
        cycle_tracking_enabled: accept,
        cycle_tracking_offered: true,
      });
      onProfileUpdate(updated);
    } finally {
      setSaving(false);
    }
  };

  const disableTracking = async () => {
    if (!window.confirm('Отключить трекер цикла? Уже сохранённые записи не удалятся.')) return;
    const updated = await entities.UserProfile.update(profile.id, { cycle_tracking_enabled: false });
    onProfileUpdate(updated);
  };

  const saveToday = async () => {
    setSaving(true);
    try {
      await entities.CycleLog.upsert({
        date: new Date().toISOString().split('T')[0],
        flow,
        symptoms,
        intimacy,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  // Ещё не спрашивали и не предлагали — показываем карточку согласия
  if (!profile.cycle_tracking_offered) {
    return (
      <div className="p-4 bg-card rounded-2xl border space-y-3">
        <div className="flex items-center gap-2">
          <Droplet className="w-5 h-5 text-rose-500" />
          <h3 className="font-heading text-lg">Трекер цикла</h3>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Хочешь добавить отслеживание менструального цикла (включая интимную близость)?
          Это полностью приватные данные, видны только тебе, и функцию можно
          в любой момент отключить в настройках профиля.
        </p>
        <div className="flex gap-2">
          <Button size="sm" disabled={saving} onClick={() => respondToOffer(true)}>Да, включить</Button>
          <Button size="sm" variant="outline" disabled={saving} onClick={() => respondToOffer(false)}>Нет, спасибо</Button>
        </div>
      </div>
    );
  }

  // Предлагали, но отказалась — молчим, не навязываем повторно
  if (!profile.cycle_tracking_enabled) return null;

  return (
    <div className="p-4 bg-card rounded-2xl border space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Droplet className="w-5 h-5 text-rose-500" />
          <h3 className="font-heading text-lg">Трекер цикла</h3>
        </div>
        <button onClick={disableTracking} className="text-muted-foreground hover:text-destructive" aria-label="Отключить трекер цикла">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Выделения сегодня</label>
        <div className="flex flex-wrap gap-2 mt-2">
          {FLOW_OPTIONS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFlow(f.value)}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                flow === f.value ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Симптомы</label>
        <div className="flex flex-wrap gap-2 mt-2">
          {SYMPTOM_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => toggleSymptom(s)}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                symptoms.includes(s) ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={intimacy} onChange={(e) => setIntimacy(e.target.checked)} className="w-4 h-4 rounded" />
        Была близость сегодня
      </label>

      <Button size="sm" className="w-full" disabled={saving} onClick={saveToday}>
        {saved ? 'Сохранено ✓' : 'Сохранить запись за сегодня'}
      </Button>
    </div>
  );
}
