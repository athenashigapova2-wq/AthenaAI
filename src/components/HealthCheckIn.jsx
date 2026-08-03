import { useState } from 'react';
import { toLocalDateStr } from '@/lib/utils';
import { entities } from '@/lib/entities';
import { useQueryClient } from '@tanstack/react-query';
import { Heart, Smile, Zap, Moon } from 'lucide-react';

export function HealthCheckIn() {
  const queryClient = useQueryClient();
  const [symptoms, setSymptoms] = useState([]);
  const [mood, setMood] = useState(5);
  const [sleep, setSleep] = useState(7);
  const [energy, setEnergy] = useState(5);
  const [submitted, setSubmitted] = useState(false);

  const symptomOptions = [
    'Headache', 'Bloating', 'Fatigue', 'Insomnia',
    'Joint pain', 'Skin issues', 'Digestive issues', 'None'
  ];

  const toggleSymptom = (s) => {
    setSymptoms(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  };

  const submit = async () => {
    await entities.user_health_logs.create({
      date: toLocalDateStr(),
      symptoms: symptoms.includes('None') ? [] : symptoms,
      mood,
      sleep_hours: sleep,
      energy_level: energy
    });
    setSubmitted(true);
    queryClient.invalidateQueries(['health-logs']);
    setTimeout(() => setSubmitted(false), 3000);
  };

  return (
    <div className="p-4 bg-card rounded-2xl border space-y-4">
      <div className="flex items-center gap-2">
        <Heart className="w-5 h-5 text-rose-500" />
        <h3 className="font-heading text-lg">Daily Check-in</h3>
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Symptoms today</label>
        <div className="flex flex-wrap gap-2 mt-2">
          {symptomOptions.map(s => (
            <button
              key={s}
              onClick={() => toggleSymptom(s)}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                symptoms.includes(s)
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <Smile className="w-4 h-4" /> Mood {mood}/10
          </div>
          <input type="range" min="1" max="10" value={mood}
                 onChange={e => setMood(Number(e.target.value))}
                 className="w-full accent-primary" />
        </div>
        <div className="space-y-2">
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <Moon className="w-4 h-4" /> Sleep {sleep}h
          </div>
          <input type="range" min="0" max="12" step="0.5" value={sleep}
                 onChange={e => setSleep(Number(e.target.value))}
                 className="w-full accent-primary" />
        </div>
        <div className="space-y-2">
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <Zap className="w-4 h-4" /> Energy {energy}/10
          </div>
          <input type="range" min="1" max="10" value={energy}
                 onChange={e => setEnergy(Number(e.target.value))}
                 className="w-full accent-primary" />
        </div>
      </div>

      <button
        onClick={submit}
        disabled={submitted}
        className="w-full bg-primary text-primary-foreground py-2.5 rounded-xl font-medium disabled:opacity-50"
      >
        {submitted ? 'Saved!' : 'Save Check-in'}
      </button>
    </div>
  );
}