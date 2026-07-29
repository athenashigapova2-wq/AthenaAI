# MacroCoach — миграция с Base44 на Supabase

## Что изменилось
Приложение больше не зависит от Base44. Backend теперь — твой собственный
Supabase-проект: Postgres (данные + RLS), Supabase Auth (логин/регистрация),
Edge Functions (AI-логика, сканер штрихкодов).

Это значит: свой домен, без VPN, полный контроль над данными и кодом.

## Шаги запуска

### 1. Создай проект Supabase
supabase.com → New Project (можно выбрать регион ближе к твоим пользователям,
например Frankfurt).

### 2. Прогони миграции БД
В Supabase Dashboard → SQL Editor выполни по очереди:
- `supabase/migrations/0001_init.sql`
- `supabase/migrations/0002_agent_chat.sql`
- `supabase/migrations/0003_custom_products.sql`

(Либо через CLI: `supabase link` + `supabase db push`, если поставишь Supabase CLI.)

### 3. Задеплой Edge Functions
```
supabase functions deploy invoke-llm
supabase functions deploy chat-with-coach
supabase functions deploy analyzeFoodProduct
supabase secrets set GIGACHAT_AUTH_KEY=<см. ниже>
```

**Используем GigaChat (Сбер)** — бесплатно для физлиц (1 млн токенов/мес),
без карты, без VPN, регистрация по SberID:
1. developers.sber.ru → войди через SberID
2. Создай проект → **GigaChat API** → выбери тариф **GigaChat API PERS** (free)
3. В личном кабинете нажми "Сгенерировать новый Client Secret" — тебе покажут
   **Client ID** и **Client Secret** один раз, сохрани их
4. Собери `Authorization key` = Base64 от строки `Client ID:Client Secret`
   (можно в любом онлайн base64-энкодере, либо `echo -n "id:secret" | base64`)
5. Это и есть значение для `GIGACHAT_AUTH_KEY`

Функции сами скачивают и доверяют сертификату НУЦ Минцифры при первом
запуске — вручную ничего устанавливать не нужно (это частый источник ошибок
при других способах интеграции GigaChat, здесь он уже решён в коде).

### 4. Настрой .env
Скопируй `.env.example` → `.env`, впиши:
```
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key из Settings → API>
```

### 5. Настрой Auth в Dashboard
- **Email OTP при регистрации**: Authentication → Email Templates → "Confirm
  signup" — по умолчанию Supabase шлёт ссылку, а наш UI (Register.jsx) ждёt
  6-значный код. Нужно переключить шаблон на OTP-код (`{{ .Token }}` вместо
  `{{ .ConfirmationURL }}`), иначе экран верификации не сработает.
- **Google OAuth** (если нужен): Authentication → Providers → Google, впиши
  Client ID/Secret из Google Cloud Console.
- **Password reset redirect**: Authentication → URL Configuration → добавь
  свой домен в Redirect URLs (`https://твой-домен.com/reset-password`).

### 6. npm install && npm run build
Уже проверено — собирается чисто.

## Что ещё не сделано (см. чат с Claude для деталей)
- Форма ручного добавления товара в FoodScanner готова, но без загрузки фото
  товара (пока только текстовые поля КБЖУ)
- Автоматическое извлечение "памяти" о предпочтениях пользователя в чате с
  коучем (было в Base44 через `memory_config`) — сейчас не портировано,
  агент работает без долгосрочной памяти между разговорами
- Иконка/аватар приложения — сейчас плейсхолдеры (`public/favicon.svg`,
  `public/athena-avatar.svg`), нужно заменить на финальный брендинг
- support-email в Profile.jsx — плейсхолдер `support@TODO-your-domain.com`
