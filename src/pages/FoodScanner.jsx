import { useState, useRef, useEffect } from 'react';
import { Camera, Scan, AlertCircle, Check, ArrowRight, Keyboard } from 'lucide-react';
import { entities } from '@/lib/entities';
import { supabase } from '@/api/supabaseClient';
import { useAuth } from '@/lib/AuthContext';

export default function FoodScanner() {
  const { user } = useAuth();
  const videoRef = useRef(null);
  const [mode, setMode] = useState('camera'); // 'camera' | 'manual'
  const [barcode, setBarcode] = useState('');
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [notFoundBarcode, setNotFoundBarcode] = useState(null);
  const [addForm, setAddForm] = useState({ name: '', calories: '', protein_g: '', carbs_g: '', fat_g: '' });
  const [addSaving, setAddSaving] = useState(false);

  // Native BarcodeDetector API
  useEffect(() => {
    if (mode !== 'camera') return;

    let detector = null;
    let stream = null;
    let animationId = null;

    const startCamera = async () => {
      if (!('BarcodeDetector' in window)) {
        setError('Camera scanning not supported on this browser. Use manual entry.');
        setMode('manual');
        return;
      }

      try {
        detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e'] });
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' }
        });

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          setScanning(true);
          detectLoop();
        }
      } catch (e) {
        setError('Camera access denied or unavailable. Use manual entry.');
        setMode('manual');
      }
    };

    const detectLoop = async () => {
      if (!detector || !videoRef.current || mode !== 'camera') return;

      try {
        const barcodes = await detector.detect(videoRef.current);
        if (barcodes.length > 0) {
          const code = barcodes[0].rawValue;
          setScanning(false);
          stopCamera();
          analyze(code);
          return;
        }
      } catch (e) {
        // Frame skipped, continue
      }
      animationId = requestAnimationFrame(detectLoop);
    };

    const stopCamera = () => {
      if (animationId) cancelAnimationFrame(animationId);
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    };

    startCamera();
    return () => stopCamera();
  }, [mode]);

  const stopCamera = () => {
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(t => t.stop());
    }
    setScanning(false);
  };

  const analyze = async (code) => {
    if (!code || !code.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setNotFoundBarcode(null);

    try {
      // Get user profile for personalized analysis (RLS scopes to this user)
      const profiles = await entities.UserProfile.list();
      const profile = profiles[0] || {};

      const { data, error: fnError } = await supabase.functions.invoke('analyzeFoodProduct', {
        body: {
          barcode: code.trim(),
          userProfile: {
            healthConditions: profile?.health_conditions || [],
            goal: profile?.goal || 'maintenance',
            allergies: profile?.allergies || []
          }
        }
      });

      if (fnError) throw fnError;
      if (data.error === 'not_found') {
        setNotFoundBarcode(code.trim());
        return;
      }
      if (data.error) throw new Error(data.error);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const saveManualProduct = async () => {
    if (!notFoundBarcode || !addForm.name.trim()) return;
    setAddSaving(true);
    try {
      const { error: insertError } = await supabase.from('custom_products').insert({
        barcode: notFoundBarcode,
        name: addForm.name.trim(),
        calories: Number(addForm.calories) || 0,
        protein_g: Number(addForm.protein_g) || 0,
        carbs_g: Number(addForm.carbs_g) || 0,
        fat_g: Number(addForm.fat_g) || 0,
        added_by: user?.id,
      });
      if (insertError) throw insertError;
      // Товар сохранён — сразу анализируем его как обычно
      setNotFoundBarcode(null);
      setAddForm({ name: '', calories: '', protein_g: '', carbs_g: '', fat_g: '' });
      await analyze(notFoundBarcode);
    } catch (e) {
      setError(e.message);
    } finally {
      setAddSaving(false);
    }
  };

  const getScoreColor = (s) => {
    if (s >= 7) return 'bg-green-500';
    if (s >= 4) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="p-4 max-w-md mx-auto space-y-6">
      <div>
        <h1 className="font-heading text-2xl">Food Scanner</h1>
        <p className="text-muted-foreground text-sm">Scan barcode or enter manually</p>
      </div>

      {/* Mode toggle */}
      <div className="flex bg-secondary rounded-xl p-1">
        <button
          onClick={() => { setMode('camera'); setResult(null); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'camera' ? 'bg-background shadow-sm' : ''}`}
        >
          <Camera className="w-4 h-4" /> Camera
        </button>
        <button
          onClick={() => { stopCamera(); setMode('manual'); setResult(null); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'manual' ? 'bg-background shadow-sm' : ''}`}
        >
          <Keyboard className="w-4 h-4" /> Manual
        </button>
      </div>

      {/* Camera view */}
      {mode === 'camera' && (
        <div className="relative aspect-[4/3] bg-black rounded-2xl overflow-hidden border">
          <video
            ref={videoRef}
            className="w-full h-full object-cover"
            playsInline
            muted
          />
          {scanning && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-48 h-32 border-2 border-white/50 rounded-lg relative">
                <div className="absolute inset-x-0 top-0 h-0.5 bg-primary animate-[scan_2s_ease-in-out_infinite]" />
                <Scan className="absolute -top-6 left-1/2 -translate-x-1/2 w-5 h-5 text-white animate-pulse" />
              </div>
            </div>
          )}
          {!scanning && !result && !error && (
            <div className="absolute inset-0 flex items-center justify-center text-white/70">
              <p className="text-sm">Starting camera...</p>
            </div>
          )}
        </div>
      )}

      {/* Manual input */}
      {mode === 'manual' && (
        <div className="space-y-3">
          <div className="relative">
            <input
              type="text"
              value={barcode}
              onChange={e => setBarcode(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && analyze(barcode)}
              placeholder="Enter barcode"
              className="w-full h-12 pl-4 pr-12 rounded-xl border bg-background text-lg"
            />
            <button
              onClick={() => analyze(barcode)}
              disabled={loading || !barcode.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-50"
            >
              {loading ? <Scan className="w-5 h-5 animate-spin" /> : <ArrowRight className="w-5 h-5" />}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">Try: 737628064502 or 0049000004634</p>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 text-red-700 rounded-xl text-sm">
          {error}
        </div>
      )}

      {notFoundBarcode && (
        <div className="space-y-3 p-4 bg-secondary rounded-xl">
          <div>
            <p className="font-medium text-sm">Product not found</p>
            <p className="text-xs text-muted-foreground">
              Barcode {notFoundBarcode} isn't in our database yet. Add it — it'll be saved for everyone.
            </p>
          </div>
          <input
            type="text" placeholder="Product name" value={addForm.name}
            onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
            className="w-full h-10 px-3 rounded-lg border bg-background text-sm"
          />
          <div className="grid grid-cols-4 gap-2">
            {[
              { key: 'calories', label: 'Cal' },
              { key: 'protein_g', label: 'Protein' },
              { key: 'carbs_g', label: 'Carbs' },
              { key: 'fat_g', label: 'Fat' },
            ].map(f => (
              <input
                key={f.key} type="number" placeholder={f.label} value={addForm[f.key]}
                onChange={e => setAddForm(v => ({ ...v, [f.key]: e.target.value }))}
                className="h-10 px-2 rounded-lg border bg-background text-sm text-center"
              />
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">Values per 100g</p>
          <button
            onClick={saveManualProduct}
            disabled={addSaving || !addForm.name.trim()}
            className="w-full h-10 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {addSaving ? 'Saving...' : 'Save & analyze'}
          </button>
        </div>
      )}

      {result && (
        <div className="space-y-4 animate-in slide-in-from-bottom-4">
          {result.product.image && (
            <img src={result.product.image} alt={result.product.name}
                 className="w-full h-48 object-contain rounded-xl bg-muted" />
          )}

          <div>
            <h2 className="font-semibold text-lg">{result.product.name}</h2>
            {result.product.brand && <p className="text-sm text-muted-foreground">{result.product.brand}</p>}
          </div>

          <div className="flex items-center gap-4 p-4 bg-card rounded-xl border">
            <div className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold text-white ${getScoreColor(result.score)}`}>
              {result.score}
            </div>
            <div>
              <p className="font-medium text-lg">{result.verdict}</p>
              <p className="text-sm text-muted-foreground">Personalized for your health profile</p>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'Cal', val: result.product.calories },
              { label: 'Protein', val: `${result.product.protein}g` },
              { label: 'Carbs', val: `${result.product.carbs}g` },
              { label: 'Fat', val: `${result.product.fat}g` }
            ].map(m => (
              <div key={m.label} className="p-3 bg-secondary rounded-xl text-center">
                <p className="text-lg font-semibold">{m.val}</p>
                <p className="text-xs text-muted-foreground">{m.label}</p>
              </div>
            ))}
          </div>

          {result.warnings?.length > 0 && (
            <div className="space-y-2">
              {result.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 p-3 bg-amber-50 text-amber-800 rounded-xl text-sm">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  {w}
                </div>
              ))}
            </div>
          )}

          {result.positives?.length > 0 && (
            <div className="space-y-2">
              {result.positives.map((p, i) => (
                <div key={i} className="flex items-start gap-2 p-3 bg-green-50 text-green-800 rounded-xl text-sm">
                  <Check className="w-4 h-4 mt-0.5 shrink-0" />
                  {p}
                </div>
              ))}
            </div>
          )}

          {result.alternatives?.length > 0 && (
            <div className="p-4 bg-card rounded-xl border">
              <p className="font-medium mb-3">Healthier alternatives:</p>
              <div className="space-y-2">
                {result.alternatives.map((alt, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-secondary rounded-lg">
                    <span className="font-medium">{alt.name}</span>
                    <span className="text-sm text-muted-foreground">{alt.calories} kcal</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}