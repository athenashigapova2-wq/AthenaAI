import { useState, useEffect, useCallback } from 'react';
import { entities } from '@/lib/entities';
import { Button } from '@/components/ui/button';
import { Droplet, ChevronLeft, ChevronRight } from 'lucide-react';

const SYMPTOM_OPTIONS = ['Спазмы', 'Головная боль', 'Перепады настроения', 'Вздутие', 'Чувствительность груди', 'Усталость', 'Акне'];
const MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const WEEKDAY_LETTERS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const ds = (d) => d.toISOString().split('T')[0];

// Полностью opt-in: сначала спрашиваем явное согласие, ничего не собираем
// без него. Переключатель отслеживания виден постоянно и явно, можно
// выключить в любой момент — без закопанных мелких иконок.
// Обращение на "Вы" — тема деликатная, формальный уважительный тон уместнее
// тёплого "ты", которым говорит остальное приложение.
export default function CycleTracker({ profile, onProfileUpdate }) {
  const [saving, setSaving] = useState(false);
  const [logsByDate, setLogsByDate] = useState({});
  const [monthOffset, setMonthOffset] = useState(0);
  const [selectedDate, setSelectedDate] = useState(ds(new Date()));
  const [flow, setFlow] = useState(0);
  const [symptoms, setSymptoms] = useState([]);
  const [intimacy, setIntimacy] = useState(false);
  const [saved, setSaved] = useState(false);

  const loadLogs = useCallback(async () => {
    if (!profile?.cycle_tracking_enabled) return;
    const rows = await entities.CycleLog.list();
    const map = {};
    rows.forEach((r) => { map[r.date] = r; });
    setLogsByDate(map);
  }, [profile?.cycle_tracking_enabled]);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  useEffect(() => {
    const log = logsByDate[selectedDate];
    setFlow(log?.flow || 0);
    setSymptoms(log?.symptoms || []);
    setIntimacy(log?.intimacy || false);
  }, [selectedDate, logsByDate]);

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

  const toggleTracking = async () => {
    if (profile.cycle_tracking_enabled) {
      if (!window.confirm('Отключить отслеживание цикла? Уже сохранённые записи не удалятся.')) return;
    }
    const updated = await entities.UserProfile.update(profile.id, {
      cycle_tracking_enabled: !profile.cycle_tracking_enabled,
      cycle_tracking_offered: true,
    });
    onProfileUpdate(updated);
  };

  const saveDay = async () => {
    setSaving(true);
    try {
      const row = await entities.CycleLog.upsert({ date: selectedDate, flow, symptoms, intimacy });
      setLogsByDate((prev) => ({ ...prev, [selectedDate]: row }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  // Ещё не спрашивали — карточка согласия
  if (!profile.cycle_tracking_offered) {
    return (
      <div className="p-4 bg-card rounded-2xl border space-y-3">
        <div className="flex items-center gap-2">
          <Droplet className="w-5 h-5 text-rose-500" />
          <h3 className="font-heading text-lg">Трекер цикла</h3>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Хотите добавить отслеживание менструального цикла (включая интимную близость)?
          Это полностью приватные данные — будет видно только Вам, и функцию можно
          в любой момент отключить в настройках профиля.
        </p>
        <div className="flex gap-2">
          <Button size="sm" disabled={saving} onClick={() => respondToOffer(true)}>Да, включить</Button>
          <Button size="sm" variant="outline" disabled={saving} onClick={() => respondToOffer(false)}>Нет, спасибо</Button>
        </div>
      </div>
    );
  }

  // --- Календарь месяца ---
  const now = new Date();
  const viewMonth = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
  const firstWeekday = (viewMonth.getDay() + 6) % 7; // 0 = понедельник
  const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
  const todayStr = ds(now);

  const cells = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push(new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day));
  }

  return (
    <div className="p-4 bg-card rounded-2xl border space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Droplet className="w-5 h-5 text-rose-500" />
          <h3 className="font-heading text-lg">Трекер цикла</h3>
        </div>
        {/* Явный переключатель, всегда на виду — не спрятан в мелкую иконку */}
        <button
          onClick={toggleTracking}
          className={`relative w-11 h-6 rounded-full transition-colors ${profile.cycle_tracking_enabled ? 'bg-rose-500' : 'bg-muted'}`}
          role="switch"
          aria-checked={profile.cycle_tracking_enabled}
          aria-label="Отслеживание цикла"
        >
          <span
            className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${profile.cycle_tracking_enabled ? 'translate-x-5' : 'translate-x-0.5'}`}
          />
        </button>
      </div>

      {!profile.cycle_tracking_enabled ? (
        <p className="text-sm text-muted-foreground">Отслеживание выключено. Включите переключатель выше, чтобы начать.</p>
      ) : (
        <>
          {/* Навигация по месяцу */}
          <div className="flex items-center justify-between">
            <button onClick={() => setMonthOffset((o) => o - 1)} className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-muted">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm font-medium">{MONTH_NAMES[viewMonth.getMonth()]} {viewMonth.getFullYear()}</span>
            <button onClick={() => setMonthOffset((o) => o + 1)} className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-muted">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Сетка календаря */}
          <div className="grid grid-cols-7 gap-1 text-center">
            {WEEKDAY_LETTERS.map((w) => (
              <span key={w} className="text-[10px] text-muted-foreground uppercase">{w}</span>
            ))}
            {cells.map((date, i) => {
              if (!date) return <div key={`empty-${i}`} />;
              const dateStr = ds(date);
              const log = logsByDate[dateStr];
              const isSelected = dateStr === selectedDate;
              const isToday = dateStr === todayStr;
              return (
                <button
                  key={dateStr}
                  onClick={() => setSelectedDate(dateStr)}
                  className={`relative h-9 rounded-lg text-xs flex items-center justify-center transition-colors ${
                    isSelected ? 'bg-rose-500 text-white' : isToday ? 'bg-muted font-semibold' : 'hover:bg-muted'
                  }`}
                >
                  {date.getDate()}
                  {log?.flow > 0 && !isSelected && (
                    <span
                      className="absolute bottom-0.5 w-1.5 h-1.5 rounded-full bg-rose-500"
                      style={{ opacity: 0.4 + log.flow * 0.15 }}
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* Редактор выбранного дня */}
          <div className="pt-2 border-t space-y-4">
            <p className="text-sm font-medium">
              {new Date(selectedDate).toLocaleDateString('ru', { day: 'numeric', month: 'long' })}
            </p>

            <div>
              <label className="text-sm text-muted-foreground">Интенсивность выделений</label>
              <div className="flex items-center gap-2 mt-2">
                {[1, 2, 3, 4].map((n) => (
                  <button
                    key={n}
                    onClick={() => setFlow(flow === n ? n - 1 : n)}
                    aria-label={`${n} из 4`}
                    className="touch-target"
                  >
                    <Droplet className={`w-7 h-7 transition-colors ${n <= flow ? 'text-rose-500 fill-rose-500' : 'text-muted-foreground/30'}`} />
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
              Была близость в этот день
            </label>

            <Button size="sm" className="w-full" disabled={saving} onClick={saveDay}>
              {saved ? 'Сохранено ✓' : 'Сохранить запись за этот день'}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
