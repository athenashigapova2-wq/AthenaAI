import { supabase } from "@/api/supabaseClient";

export async function fetchMessages(conversationId) {
  const { data, error } = await supabase
    .from("agent_messages")
    .select("*")
    .eq("conversation_id", conversationId)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return data || [];
}

export async function fetchConversations(userId) {
  const { data, error } = await supabase
    .from("agent_conversations")
    .select("*")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });
  if (error) throw error;
  return data || [];
}

export async function removeConversation(conversationId) {
  const { error } = await supabase
    .from("agent_conversations")
    .delete()
    .eq("id", conversationId);
  if (error) throw error;
}
