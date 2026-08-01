import { supabase } from '@/api/supabaseClient';

/**
 * Повторяет интерфейс, который раньше давал base44.entities.X:
 *   .list()                          -> SELECT * (без фильтра)
 *   .filter(where, sort, limit)      -> SELECT * WHERE ... ORDER BY ... LIMIT ...
 *   .create(payload)                 -> INSERT (user_id подставляется автоматически)
 *   .update(id, payload)             -> UPDATE ... WHERE id = id
 *   .delete(id)                      -> DELETE WHERE id = id
 *   .deleteMany(where)                -> DELETE WHERE ...
 *   .bulkCreate(payloads[])          -> INSERT много строк разом
 *
 * ВАЖНО: старый код Base44 использовал ключ `created_by_id` для фильтрации
 * "своих" записей. В Supabase-схеме эта колонка называется `user_id`.
 * Здесь это транслируется автоматически, так что страницы можно не трогать
 * в этой части (см. миграцию страниц в entities-migration.md).
 */

function translateWhere(where = {}) {
  const translated = {};
  for (const [key, value] of Object.entries(where)) {
    translated[key === 'created_by_id' ? 'user_id' : key] = value;
  }
  return translated;
}

async function currentUserId() {
  const { data, error } = await supabase.auth.getUser();
  if (error) throw error;
  if (!data?.user) throw new Error('Not authenticated');
  return data.user.id;
}

function applySort(query, sort) {
  if (!sort) return query;
  const desc = sort.startsWith('-');
  const column = desc ? sort.slice(1) : sort;
  return query.order(column, { ascending: !desc });
}

export function createEntity(table) {
  return {
    async list(sort, limit) {
      let query = supabase.from(table).select('*');
      query = applySort(query, sort);
      if (limit) query = query.limit(limit);
      const { data, error } = await query;
      if (error) throw error;
      return data;
    },

    async filter(where = {}, sort, limit) {
      let query = supabase.from(table).select('*');
      const translated = translateWhere(where);
      for (const [key, value] of Object.entries(translated)) {
        query = query.eq(key, value);
      }
      query = applySort(query, sort);
      if (limit) query = query.limit(limit);
      const { data, error } = await query;
      if (error) throw error;
      return data;
    },

    async create(payload) {
      const userId = await currentUserId();
      const { data, error } = await supabase
        .from(table)
        .insert({ ...payload, user_id: userId })
        .select()
        .single();
      if (error) throw error;
      return data;
    },

    async bulkCreate(payloads = []) {
      const userId = await currentUserId();
      const rows = payloads.map((p) => ({ ...p, user_id: userId }));
      const { data, error } = await supabase.from(table).insert(rows).select();
      if (error) throw error;
      return data;
    },

    async update(id, payload) {
      const { data, error } = await supabase
        .from(table)
        .update(payload)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data;
    },

    async delete(id) {
      const { error } = await supabase.from(table).delete().eq('id', id);
      if (error) throw error;
      return true;
    },

    async deleteMany(where = {}) {
      const translated = translateWhere(where);
      let query = supabase.from(table).delete();
      for (const [key, value] of Object.entries(translated)) {
        query = query.eq(key, value);
      }
      const { error } = await query;
      if (error) throw error;
      return true;
    },
  };
}

// Соответствие старым именам сущностей Base44 -> таблицам Supabase
export const entities = {
  Profile: createEntity('profiles'),
  MealLog: createEntity('meal_logs'),
  ShoppingItem: createEntity('shopping_items'),
  UserProfile: createEntity('user_profiles'),
  WeightLog: createEntity('weight_logs'),
  WorkoutLog: createEntity('workout_logs'),
  agent_memory: createEntity('agent_memory'),
  user_health_logs: createEntity('user_health_logs'),
  food_nutrients: createEntity('food_nutrients'),
  health_research: createEntity('health_research'),
};
