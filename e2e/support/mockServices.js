const corsHeaders = {
  "access-control-allow-origin": "http://127.0.0.1:4174",
  "access-control-allow-credentials": "true",
  "access-control-allow-headers": "authorization,apikey,content-type,x-client-info,prefer",
  "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
};

const json = (route, body, status = 200, headers = {}) => route.fulfill({
  status,
  contentType: "application/json",
  headers: { ...corsHeaders, ...headers },
  body: JSON.stringify(body),
});

const user = {
  id: "user-e2e",
  aud: "authenticated",
  role: "authenticated",
  email: "anna@example.test",
  user_metadata: { full_name: "Anna Test" },
};

const token = [
  btoa(JSON.stringify({ alg: "none", typ: "JWT" })),
  btoa(JSON.stringify({ sub: user.id, role: "authenticated", exp: 4102444800 })),
  "e2e-signature",
].join(".");

export function createMockState(overrides = {}) {
  return {
    user,
    token,
    profile: {
      id: "profile-e2e",
      user_id: user.id,
      onboarding_complete: true,
      goal: "maintain",
      calorie_target: 2000,
      protein_target_g: 130,
      carb_target_g: 220,
      fat_target_g: 65,
      dietary_pattern: "omnivore",
      dietary_restrictions: [],
      allergies: [],
      disliked_foods: [],
    },
    meals: [],
    weights: [],
    conversations: [],
    messages: {},
    chatPosts: 0,
    chatRequests: [],
    jobs: {},
    writeConfirmationRequests: 0,
    writeExecutions: 0,
    writeResultsByIdempotencyKey: {},
    writeConfirmationFlow: false,
    chatFailure: null,
    chatDelayMs: 0,
    ...overrides,
  };
}

export async function installMockServices(page, state) {
  await page.route("http://127.0.0.1:54321/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: corsHeaders });

    if (url.pathname === "/auth/v1/token") {
      return json(route, {
        access_token: state.token,
        token_type: "bearer",
        expires_in: 3600,
        expires_at: 4102444800,
        refresh_token: "e2e-refresh-token",
        user: state.user,
      });
    }
    if (url.pathname === "/auth/v1/user") return json(route, state.user);

    if (url.pathname.startsWith("/functions/v1/")) {
      if (url.pathname.endsWith("estimate-meal")) {
        return json(route, { matched: true, name: "Chicken with rice", calories: 520, protein_g: 42, carbs_g: 55, fat_g: 14 });
      }
      if (url.pathname.endsWith("analyze-habits")) return json(route, { insufficient_data: true });
      return json(route, { text: "A deterministic local tip." });
    }

    const table = url.pathname.replace("/rest/v1/", "");
    if (table === "user_profiles") {
      if (request.method() === "GET") return json(route, state.profile ? [state.profile] : []);
      const payload = request.postDataJSON();
      state.profile = { id: "profile-e2e", user_id: state.user.id, ...payload };
      return json(route, state.profile, 201);
    }
    if (table === "weight_logs") {
      if (request.method() === "GET") return json(route, state.weights);
      const payload = request.postDataJSON();
      const row = { id: `weight-${state.weights.length + 1}`, user_id: state.user.id, ...payload };
      state.weights.push(row);
      return json(route, row, 201);
    }
    if (table === "meal_logs") {
      if (request.method() === "GET") return json(route, state.meals);
      const payload = request.postDataJSON();
      const row = { id: `meal-${state.meals.length + 1}`, user_id: state.user.id, ...payload };
      state.meals.push(row);
      return json(route, row, 201);
    }
    if (table === "agent_conversations") {
      return json(route, state.conversations);
    }
    if (table === "agent_messages") {
      const rawId = url.searchParams.get("conversation_id") || "";
      const conversationId = rawId.replace(/^eq\./, "");
      return json(route, state.messages[conversationId] || []);
    }
    if (table === "agent_memory") return json(route, []);
    return json(route, []);
  });

  await page.route(/.*(?:agent-api|127\.0\.0\.1:8001)\/api\/v1\/agent\/chat$/, async (route) => {
    if (state.chatDelayMs) await new Promise((resolve) => setTimeout(resolve, state.chatDelayMs));
    state.chatPosts += 1;
    const jobId = `job-${state.chatPosts}`;
    const payload = route.request().postDataJSON();
    state.chatRequests.push(payload);
    state.jobs[jobId] = payload;
    return json(route, { job_id: jobId, status: "queued" }, 202);
  });
  await page.route(/.*(?:agent-api|127\.0\.0\.1:8001)\/api\/v1\/agent\/chat\/jobs\/[^/]+\/events$/, async (route) => {
    if (state.chatFailure) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: failed\ndata: ${JSON.stringify({ status: "failed", error: state.chatFailure })}\n\n`,
      });
    }
    const jobId = new URL(route.request().url()).pathname.split("/").at(-2);
    const request = state.jobs[jobId] || {};
    const conversationId = request.conversation_id || state.conversations[0]?.id || "conversation-e2e";
    if (!state.conversations.length) state.conversations.push({ id: conversationId, user_id: state.user.id, title: "E2E chat" });
    const messages = state.messages[conversationId] || [];
    messages.push({ id: `user-${jobId}`, role: "user", content: request.message || "" });

    let answer = "Deterministic coach response";
    let pendingWriteAction;
    if (state.writeConfirmationFlow && /log.+oatmeal/i.test(request.message || "")) {
      answer = "I prepared an oatmeal entry. Please confirm before it is saved.";
      pendingWriteAction = {
        action_id: "11111111-1111-4111-8111-111111111111",
        confirmation_token: "e2e-confirmation-token-12345",
        tool_name: "log_meal",
        preview: {
          name: "Oatmeal",
          meal_type: "breakfast",
          calories: 420,
          protein_g: 22,
          carbs_g: 58,
          fat_g: 12,
        },
        expires_at: "2099-01-01T00:00:00Z",
      };
    } else if (state.writeConfirmationFlow && /today/i.test(request.message || "")) {
      const meal = state.meals[0];
      answer = meal
        ? `Today you logged ${meal.name}: ${meal.calories} kcal.`
        : "You have no meals logged today.";
    }
    messages.push({ id: `assistant-${jobId}`, role: "assistant", content: answer });
    state.messages[conversationId] = messages;
    const completed = {
      status: "succeeded",
      conversation_id: conversationId,
      answer,
      ...(pendingWriteAction ? { pending_write_action: pendingWriteAction } : {}),
    };
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'event: running\ndata: {"status":"running"}\n\n',
        `event: completed\ndata: ${JSON.stringify(completed)}\n\n`,
      ].join(""),
    });
  });
  await page.route(/.*(?:agent-api|127\.0\.0\.1:8001)\/api\/v1\/agent\/write-actions\/[^/]+\/confirm$/, async (route) => {
    state.writeConfirmationRequests += 1;
    const request = route.request();
    const idempotencyKey = request.headers()["idempotency-key"];
    const existing = state.writeResultsByIdempotencyKey[idempotencyKey];
    if (existing) return json(route, { ...existing, idempotent_replay: true });

    const actionId = new URL(request.url()).pathname.split("/").at(-2);
    const meal = {
      id: `meal-${state.meals.length + 1}`,
      user_id: state.user.id,
      date: "2026-08-24",
      name: "Oatmeal",
      meal_type: "breakfast",
      calories: 420,
      protein_g: 22,
      carbs_g: 58,
      fat_g: 12,
    };
    state.meals.push(meal);
    state.writeExecutions += 1;
    const result = {
      status: "confirmed",
      action_id: actionId,
      tool_name: "log_meal",
      tool_result: meal,
      idempotency_key: idempotencyKey,
      idempotent_replay: false,
      conversation_id: state.conversations[0]?.id || "conversation-e2e",
    };
    state.writeResultsByIdempotencyKey[idempotencyKey] = result;
    return json(route, result);
  });
  await page.route(/.*(?:agent-api|127\.0\.0\.1:8001)\/api\/v1\/agent\/chat\/jobs\/[^/]+\/cancel$/, (route) => json(route, { status: "cancelled" }));
}

export async function login(page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("anna@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login")),
    page.getByRole("button", { name: "Log in" }).click(),
  ]);
}
