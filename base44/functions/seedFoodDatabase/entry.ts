import { createClientFromRequest } from 'npm:@base44/sdk@0.8.40';
import { secrets } from 'base44:runtime';

function getNutrient(nutrients, name) {
  const n = nutrients.find((x) => x.nutrientName?.toLowerCase().includes(name.toLowerCase()));
  return n ? n.value : 0;
}

function classifyFood(nutrients) {
  const protein = getNutrient(nutrients, 'Protein');
  const carbs = getNutrient(nutrients, 'Carbohydrate');
  const fat = getNutrient(nutrients, 'Total lipid');
  if (protein > 15) return 'protein';
  if (carbs > 20 && fat < 5) return 'carb';
  if (fat > 10 && carbs < 10) return 'fat';
  if (getNutrient(nutrients, 'Fiber') > 5) return 'fiber';
  return 'mixed';
}

const FOODS = [
  'chicken breast', 'salmon', 'brown rice', 'broccoli', 'avocado',
  'oats', 'greek yogurt', 'spinach', 'eggs', 'almonds',
  'blueberries', 'quinoa', 'sweet potato', 'tuna', 'lentils',
  'kale', 'walnuts', 'turkey breast', 'cottage cheese', 'chia seeds',
];

const RESEARCH_ITEMS = [
  {
    title: 'High Protein Intake and Weight Loss',
    summary: 'Diets with 25-30% protein calories show greater fat loss and satiety compared to standard diets.',
    condition: 'weight_loss',
    recommendation: 'Aim for 1.6-2.2g protein per kg bodyweight daily.',
    source_url: 'https://pubmed.ncbi.nlm.nih.gov/',
  },
  {
    title: 'Fiber and Blood Sugar Control',
    summary: 'Soluble fiber slows glucose absorption and improves glycemic control in type 2 diabetes.',
    condition: 'diabetes',
    recommendation: 'Include 25-30g fiber daily from vegetables, legumes, and whole grains.',
    source_url: 'https://pubmed.ncbi.nlm.nih.gov/',
  },
  {
    title: 'Omega-3 and Heart Health',
    summary: 'EPA and DHA from fatty fish reduce triglycerides and inflammation markers.',
    condition: 'heart_health',
    recommendation: 'Consume fatty fish 2x per week or consider algae-based supplements.',
    source_url: 'https://pubmed.ncbi.nlm.nih.gov/',
  },
];

export default async function seedFoodDatabase(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });
    if (user.role !== 'admin') return Response.json({ error: 'Forbidden' }, { status: 403 });

    const apiKey = secrets.get('USDA_API_KEY');
    if (!apiKey) return Response.json({ error: 'USDA_API_KEY not set' }, { status: 500 });

    let seeded = 0;
    const failed = [];

    for (const food of FOODS) {
      try {
        const res = await fetch(
          `https://api.nal.usda.gov/fdc/v1/foods/search?query=${encodeURIComponent(food)}&pageSize=1&api_key=${apiKey}`
        );
        if (!res.ok) { failed.push({ food, error: `HTTP ${res.status}` }); continue; }
        const data = await res.json();
        const f = data.foods?.[0];
        if (!f) { failed.push({ food, error: 'not found' }); continue; }

        const nutrients = f.foodNutrients || [];
        await base44.asServiceRole.entities.food_nutrients.create({
          food_name: f.description,
          category: classifyFood(nutrients),
          calories_per_100g: getNutrient(nutrients, 'Energy'),
          protein_g: getNutrient(nutrients, 'Protein'),
          carbs_g: getNutrient(nutrients, 'Carbohydrate'),
          fat_g: getNutrient(nutrients, 'Total lipid'),
          fiber_g: getNutrient(nutrients, 'Fiber'),
          sugar_g: getNutrient(nutrients, 'Sugars'),
          sodium_mg: getNutrient(nutrients, 'Sodium'),
          glycemic_index: null,
          micronutrients: {
            iron: getNutrient(nutrients, 'Iron'),
            calcium: getNutrient(nutrients, 'Calcium'),
            vitamin_c: getNutrient(nutrients, 'Vitamin C'),
          },
          health_tags: ['whole food'],
        });
        seeded++;
      } catch (e) {
        failed.push({ food, error: e.message });
      }
    }

    let researchSeeded = 0;
    for (const item of RESEARCH_ITEMS) {
      try {
        await base44.asServiceRole.entities.health_research.create(item);
        researchSeeded++;
      } catch (e) {
        failed.push({ item: item.title, error: e.message });
      }
    }

    return Response.json({ seeded, researchSeeded, failed });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}