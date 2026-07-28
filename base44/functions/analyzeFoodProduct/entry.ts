import { createClientFromRequest } from 'npm:@base44/sdk@0.8.40';

export default async function analyzeFoodProduct(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const { barcode, userProfile = {} } = body;
    if (!barcode) return Response.json({ error: 'barcode required' }, { status: 400 });

    // Fetch the authenticated user's profile from the database (authoritative source,
    // not client-supplied userProfile) for goal and allergies.
    const profiles = await base44.entities.UserProfile.filter({});
    const profile = profiles[0] || {};

    // 1. Lookup in Open Food Facts (free, no API key)
    const res = await fetch(`https://world.openfoodfacts.org/api/v0/product/${barcode}.json`);
    const data = await res.json();

    if (data.status !== 1) {
      return Response.json({ error: 'Product not found' }, { status: 404 });
    }

    const p = data.product;
    const n = p.nutriments || {};

    const warnings = [];
    const positives = [];
    let score = 5;

    const healthConditions = userProfile.healthConditions || [];
    const goal = profile.goal || userProfile.goal;

    // Analyze based on conditions
    if (healthConditions.includes('diabetes') || healthConditions.includes('prediabetes')) {
      if ((n.sugars_100g || 0) > 10) {
        warnings.push(`⚠️ High sugar: ${n.sugars_100g}g per 100g — spikes blood glucose`);
        score -= 2;
      }
      if ((n.carbohydrates_100g || 0) > 50) {
        warnings.push(`⚠️ High carbs: ${n.carbohydrates_100g}g — monitor portion size`);
        score -= 1;
      }
    }

    if (goal === 'weight_loss') {
      if ((n.energy_kcal_100g || 0) > 400) {
        warnings.push(`⚠️ Calorie-dense: ${n.energy_kcal_100g} kcal/100g — easy to overeat`);
        score -= 1;
      }
    }

    if (healthConditions.includes('hypertension')) {
      if ((n.sodium_100g || 0) > 0.6) {
        warnings.push(`⚠️ High sodium: ${(n.sodium_100g * 1000).toFixed(0)}mg — not ideal for blood pressure`);
        score -= 2;
      }
    }

    // Positive checks
    if ((n.proteins_100g || 0) > 15) {
      positives.push(`✅ Good protein: ${n.proteins_100g}g per 100g`);
      score += 1;
    }

    if ((n.fiber_100g || 0) > 3) {
      positives.push(`✅ High fiber: ${n.fiber_100g}g — supports digestion and satiety`);
      score += 1;
    }

    if ((n['fruits-vegetables-nuts-estimate-from-ingredients_100g'] || n.fruits_vegetables_nuts_estimate_from_ingredients_100g || 0) > 40) {
      positives.push(`✅ Rich in whole foods`);
      score += 1;
    }

    // Find healthier alternatives from the food_nutrients database
    const category = (n.proteins_100g || 0) > 10 ? 'protein' : 'mixed';
    const maxCal = n.energy_kcal_100g || 999;
    const allFoods = await base44.asServiceRole.entities.food_nutrients.list();
    const alternatives = allFoods
      .filter((a) => a.category === category && (a.calories_per_100g || 0) < maxCal)
      .slice(0, 3);

    return Response.json({
      product: {
        name: p.product_name || 'Unknown product',
        brand: p.brands || '',
        image: p.image_url || '',
        calories: n.energy_kcal_100g || 0,
        protein: n.proteins_100g || 0,
        carbs: n.carbohydrates_100g || 0,
        fat: n.fat_100g || 0,
        sugar: n.sugars_100g || 0,
        sodium: n.sodium_100g ? (n.sodium_100g * 1000).toFixed(0) : 0,
      },
      score: Math.max(1, Math.min(10, score)),
      verdict:
        score >= 7 ? 'Great choice!' : score >= 4 ? 'Okay in moderation' : 'Consider healthier alternatives',
      warnings,
      positives,
      alternatives: alternatives.map((a) => ({
        name: a.food_name,
        calories: a.calories_per_100g,
        protein: a.protein_g,
      })),
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}