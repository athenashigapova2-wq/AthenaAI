// Supabase Edge Function: analyzeFoodProduct
// Портировано из base44/functions/analyzeFoodProduct/entry.ts.
// Отличие от оригинала: сначала проверяем свою таблицу custom_products
// (наполняется пользователями вручную) — это и есть решение проблемы слабого
// покрытия российских товаров в Open Food Facts. Если там пусто — идём в OFF,
// как раньше. Если не нашли нигде — возвращаем понятный "not_found", чтобы
// клиент предложил добавить товар вручную.
//
// Деплой: supabase functions deploy analyzeFoodProduct

import { createClient } from 'npm:@supabase/supabase-js@2';

const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY');

function score(n, healthConditions, goal) {
  const warnings = [];
  const positives = [];
  let s = 5;

  if (healthConditions.includes('diabetes') || healthConditions.includes('prediabetes')) {
    if ((n.sugar_g || 0) > 10) {
      warnings.push(`⚠️ High sugar: ${n.sugar_g}g per 100g — spikes blood glucose`);
      s -= 2;
    }
    if ((n.carbs_g || 0) > 50) {
      warnings.push(`⚠️ High carbs: ${n.carbs_g}g — monitor portion size`);
      s -= 1;
    }
  }
  if (goal === 'weight_loss' || goal === 'lose_weight') {
    if ((n.calories || 0) > 400) {
      warnings.push(`⚠️ Calorie-dense: ${n.calories} kcal/100g — easy to overeat`);
      s -= 1;
    }
  }
  if (healthConditions.includes('hypertension')) {
    if ((n.sodium_mg || 0) > 600) {
      warnings.push(`⚠️ High sodium: ${n.sodium_mg.toFixed(0)}mg — not ideal for blood pressure`);
      s -= 2;
    }
  }
  if ((n.protein_g || 0) > 15) {
    positives.push(`✅ Good protein: ${n.protein_g}g per 100g`);
    s += 1;
  }
  if ((n.fiber_g || 0) > 3) {
    positives.push(`✅ High fiber: ${n.fiber_g}g — supports digestion and satiety`);
    s += 1;
  }

  return { score: Math.max(1, Math.min(10, s)), warnings, positives };
}

Deno.serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405 });
  }

  try {
    const authHeader = req.headers.get('Authorization') ?? '';
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: userData, error: userError } = await supabase.auth.getUser();
    if (userError || !userData?.user) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
    }

    const { barcode, userProfile = {} } = await req.json();
    if (!barcode) return new Response(JSON.stringify({ error: 'barcode required' }), { status: 400 });

    // Профиль — из БД (авторитетный источник), не то что прислал клиент
    const { data: profiles } = await supabase.from('user_profiles').select('*').limit(1);
    const profile = profiles?.[0] || {};
    const healthConditions = userProfile.healthConditions || [];
    const goal = profile.goal || userProfile.goal;

    let product = null;

    // 1. Сначала своя база (крауд-сорс, хорошо покрывает RU-товары со временем)
    const { data: custom } = await supabase
      .from('custom_products')
      .select('*')
      .eq('barcode', barcode)
      .limit(1);

    if (custom && custom.length > 0) {
      const c = custom[0];
      product = {
        name: c.name, brand: c.brand || '', image: c.image_url || '',
        calories: c.calories || 0, protein: c.protein_g || 0, carbs: c.carbs_g || 0,
        fat: c.fat_g || 0, sugar_g: c.sugar_g || 0, sodium_mg: c.sodium_mg || 0,
      };
    } else {
      // 2. Иначе — Open Food Facts (глобальная база, но слабое покрытие RU)
      const res = await fetch(`https://world.openfoodfacts.org/api/v0/product/${barcode}.json`);
      const data = await res.json();
      if (data.status === 1) {
        const p = data.product;
        const n = p.nutriments || {};
        product = {
          name: p.product_name || 'Unknown product',
          brand: p.brands || '',
          image: p.image_url || '',
          calories: n.energy_kcal_100g || 0,
          protein: n.proteins_100g || 0,
          carbs: n.carbohydrates_100g || 0,
          fat: n.fat_100g || 0,
          sugar_g: n.sugars_100g || 0,
          sodium_mg: n.sodium_100g ? n.sodium_100g * 1000 : 0,
        };
      }
    }

    if (!product) {
      // Товар не найден нигде — клиент должен предложить добавить вручную
      return new Response(JSON.stringify({ error: 'not_found', barcode }), { status: 404 });
    }

    const { score: s, warnings, positives } = score(
      { calories: product.calories, protein_g: product.protein, carbs_g: product.carbs,
        sugar_g: product.sugar_g, sodium_mg: product.sodium_mg, fiber_g: 0 },
      healthConditions, goal
    );

    // Альтернативы — из общей справочной базы food_nutrients
    const category = product.protein > 10 ? 'protein' : 'mixed';
    const { data: allFoods } = await supabase.from('food_nutrients').select('*');
    const alternatives = (allFoods || [])
      .filter((a) => a.category === category && (a.calories_per_100g || 0) < (product.calories || 999))
      .slice(0, 3);

    return new Response(JSON.stringify({
      product: {
        name: product.name, brand: product.brand, image: product.image,
        calories: product.calories, protein: product.protein, carbs: product.carbs, fat: product.fat,
        sugar: product.sugar_g, sodium: product.sodium_mg ? product.sodium_mg.toFixed(0) : 0,
      },
      score: s,
      verdict: s >= 7 ? 'Great choice!' : s >= 4 ? 'Okay in moderation' : 'Consider healthier alternatives',
      warnings,
      positives,
      alternatives: alternatives.map((a) => ({ name: a.food_name, calories: a.calories_per_100g, protein: a.protein_g })),
    }), { headers: { 'Content-Type': 'application/json' } });
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
});
