import React from "react";
import { Link } from "react-router-dom";
import LegalPage from "@/components/LegalPage";

const UPDATED = { en: "November 6, 2026", ru: "6 ноября 2026 г." };

function EnglishInstructions() {
  return (
    <>
      <p>
        Athena AI provides permanent account deletion from both the Android app and the web application. You must be able to sign in and recently re-authenticate to prevent unauthorized deletion.
      </p>

      <h2>Delete your account</h2>
      <ol>
        <li><Link to="/login">Sign in to Athena AI on the web</Link> or open the Android app.</li>
        <li>Open <strong>Profile</strong> and select <strong>Delete account</strong>.</li>
        <li>Re-authenticate using your current password or OAuth provider.</li>
        <li>Enter <strong>DELETE</strong>, verify the account email and confirm.</li>
      </ol>
      <p>
        If a storage or runtime dependency is temporarily unavailable, Athena keeps the authentication account active and asks you to retry. This prevents a partially deleted account that you can no longer access.
      </p>

      <h2>What is deleted</h2>
      <ul>
        <li>Supabase authentication identity and profile;</li>
        <li>nutrition, meal, weight, health, workout, shopping and cycle records;</li>
        <li>agent conversations, messages, memory, feedback and user-owned traces;</li>
        <li>files stored under your user identifier;</li>
        <li>pending jobs, write confirmations and idempotency records in Redis.</li>
      </ul>

      <h2>What may remain</h2>
      <p>
        A food-catalog item contributed to the shared catalog may remain after its creator link is removed. Security or infrastructure backups may persist for a limited period before normal rotation. Aggregated information that no longer identifies or links back to your account may also remain.
      </p>

      <h2>Cannot access the account?</h2>
      <p>
        Contact the maintainer through <a href="https://aminashigapova.ru/" target="_blank" rel="noreferrer">aminashigapova.ru</a>. Include the account email and state that you are requesting permanent Athena AI account deletion. Do not send your password, access token or health data.
      </p>
    </>
  );
}

function RussianInstructions() {
  return (
    <>
      <p>
        Athena AI позволяет навсегда удалить аккаунт как из Android-приложения, так и через веб-версию. Для защиты от чужого удаления необходимо войти и недавно повторно подтвердить личность.
      </p>

      <h2>Как удалить аккаунт</h2>
      <ol>
        <li><Link to="/login">Войдите в веб-версию Athena AI</Link> или откройте Android-приложение.</li>
        <li>Откройте <strong>Профиль</strong> и выберите <strong>Удалить аккаунт</strong>.</li>
        <li>Повторно войдите с текущим паролем или через OAuth.</li>
        <li>Введите <strong>DELETE</strong>, проверьте email аккаунта и подтвердите операцию.</li>
      </ol>
      <p>
        Если хранилище или runtime временно недоступны, Athena сохраняет Auth-аккаунт и предлагает повторить попытку. Так не возникает частично удалённый аккаунт, в который уже невозможно войти.
      </p>

      <h2>Что удаляется</h2>
      <ul>
        <li>Auth-аккаунт Supabase и профиль;</li>
        <li>данные о питании, приёмах пищи, весе, здоровье, тренировках, покупках и цикле;</li>
        <li>диалоги, сообщения, память агента, отзывы и пользовательские traces;</li>
        <li>файлы, сохранённые под идентификатором пользователя;</li>
        <li>ожидающие jobs, write confirmations и idempotency-записи в Redis.</li>
      </ul>

      <h2>Что может сохраниться</h2>
      <p>
        Позиция, добавленная в общий каталог продуктов, может сохраниться после удаления связи с автором. Резервные копии инфраструктуры могут существовать ограниченное время до обычной ротации. Также могут сохраниться агрегированные данные, которые больше не идентифицируют аккаунт и не связаны с ним.
      </p>

      <h2>Нет доступа к аккаунту?</h2>
      <p>
        Свяжитесь с разработчиком через <a href="https://aminashigapova.ru/" target="_blank" rel="noreferrer">aminashigapova.ru</a>. Укажите email аккаунта и напишите, что запрашиваете полное удаление аккаунта Athena AI. Не отправляйте пароль, access token или данные о здоровье.
      </p>
    </>
  );
}

export default function AccountDeletion() {
  return (
    <LegalPage
      title={{ en: "Account deletion", ru: "Удаление аккаунта" }}
      updatedAt={UPDATED}
    >
      {(language) => (language === "ru" ? <RussianInstructions /> : <EnglishInstructions />)}
    </LegalPage>
  );
}

