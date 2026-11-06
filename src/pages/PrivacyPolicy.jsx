import React from "react";
import { Link } from "react-router-dom";
import LegalPage from "@/components/LegalPage";

const UPDATED = { en: "November 6, 2026", ru: "6 ноября 2026 г." };

function EnglishPolicy() {
  return (
    <>
      <p>
        This Privacy Policy applies to the Athena AI Android and web applications maintained by Amina Shigapova. Athena AI is a nutrition and fitness assistant, not a medical service.
      </p>

      <h2>Information we process</h2>
      <ul>
        <li><strong>Account data:</strong> email address, user identifier, authentication provider and session information. Password authentication is handled by Supabase.</li>
        <li><strong>Profile and wellness data:</strong> age, sex, height, weight, goals, activity level, nutrition targets, allergies, dietary preferences, health check-ins and cycle data you choose to provide.</li>
        <li><strong>App content:</strong> conversations, feedback, meal, weight and workout logs, shopping items, saved preferences and uploaded documents submitted for OCR.</li>
        <li><strong>Operational metadata:</strong> run and conversation identifiers, pseudonymous actor identifier, route, model tier, status, latency, token use, retries, fallbacks, tool status, evaluation scores and timestamps.</li>
      </ul>

      <h2>How we use information</h2>
      <p>
        We use this information to authenticate you, provide and personalize Athena AI, save your requested records, calculate nutrition values, generate responses, protect write operations, diagnose failures, evaluate quality and maintain service security.
      </p>

      <h2>AI processing and service providers</h2>
      <p>
        Relevant messages and the minimum context needed to answer them may be sent to the configured GigaChat model provider. Credentials are removed before provider invocation. Supabase provides authentication, database and file storage. Hosting, CDN and secure networking providers process the technical data required to deliver the application. We do not sell personal information or use it for targeted advertising.
      </p>

      <h2>Observability and retention</h2>
      <p>
        Production tracing is metadata-first. Full prompt, response and tool payload storage is disabled by default. When raw trace content is explicitly enabled for troubleshooting, its configured retention is normally up to 7 days; structured operational trace records are normally retained for up to 90 days. Account content is retained while your account is active or until it is deleted, subject to security, legal and backup obligations.
      </p>

      <h2>Account deletion</h2>
      <p>
        You can permanently delete your account from Profile after recent password or OAuth re-authentication. Deletion removes your authentication identity, account-owned database records, user-prefixed files and active runtime records. A contributed food-catalog entry may remain without its link to your account. See the <Link to="/account-deletion">account deletion instructions</Link>.
      </p>

      <h2>Your choices and security</h2>
      <p>
        You can review or change profile information in the application, delete trace records through available privacy controls, or delete the entire account. Athena uses authenticated ownership checks, row-level database policies, TLS, write confirmation and metadata-first traces. No security measure can guarantee absolute protection.
      </p>

      <h2>International processing and changes</h2>
      <p>
        Service providers may process data in countries other than your own. We may update this policy when the application or its providers change; the effective date above identifies the current version.
      </p>

      <h2>Contact</h2>
      <p>
        For privacy questions or if you cannot access your account, contact the maintainer through <a href="https://aminashigapova.ru/" target="_blank" rel="noreferrer">aminashigapova.ru</a>.
      </p>
    </>
  );
}

function RussianPolicy() {
  return (
    <>
      <p>
        Эта Политика конфиденциальности применяется к Android- и веб-приложению Athena AI, которое поддерживает Амина Шигапова. Athena AI — помощник по питанию и тренировкам, а не медицинский сервис.
      </p>

      <h2>Какие данные мы обрабатываем</h2>
      <ul>
        <li><strong>Данные аккаунта:</strong> email, идентификатор пользователя, способ входа и сведения о сессии. Парольную аутентификацию обрабатывает Supabase.</li>
        <li><strong>Профиль и данные о самочувствии:</strong> возраст, пол, рост, вес, цели, активность, цели по питанию, аллергии, пищевые предпочтения, отметки о самочувствии и данные цикла, которые вы решили указать.</li>
        <li><strong>Контент приложения:</strong> сообщения, отзывы, записи о питании, весе и тренировках, список покупок, сохранённые предпочтения и документы, отправленные на OCR.</li>
        <li><strong>Технические метаданные:</strong> идентификаторы запуска и диалога, псевдонимный идентификатор, маршрут, уровень модели, статус, задержка, токены, повторы, fallback, статус инструментов, оценки качества и временные метки.</li>
      </ul>

      <h2>Для чего используются данные</h2>
      <p>
        Данные нужны для входа, работы и персонализации Athena AI, сохранения запрошенных записей, расчёта питания, формирования ответов, защиты операций записи, диагностики сбоев, оценки качества и безопасности сервиса.
      </p>

      <h2>ИИ и поставщики сервисов</h2>
      <p>
        Сообщения и минимально необходимый контекст могут передаваться настроенному провайдеру модели GigaChat. Перед вызовом провайдера учётные данные удаляются. Supabase предоставляет аутентификацию, базу данных и хранение файлов. Поставщики хостинга, CDN и защищённой сети обрабатывают технические данные, необходимые для доставки приложения. Мы не продаём персональные данные и не используем их для таргетированной рекламы.
      </p>

      <h2>Наблюдаемость и сроки хранения</h2>
      <p>
        В production по умолчанию сохраняются метаданные, а не полный текст запросов, ответов и аргументов инструментов. Если raw-контент явно включён для диагностики, обычный срок его хранения — до 7 дней; структурированные технические traces обычно хранятся до 90 дней. Данные аккаунта хранятся, пока аккаунт активен, либо до удаления с учётом требований безопасности, закона и резервного копирования.
      </p>

      <h2>Удаление аккаунта</h2>
      <p>
        Аккаунт можно навсегда удалить в Профиле после повторной аутентификации паролем или OAuth. Удаляются Auth-аккаунт, принадлежащие пользователю записи базы, файлы с пользовательским префиксом и активные runtime-записи. Добавленная пользователем позиция общего каталога продуктов может сохраниться без связи с аккаунтом. См. <Link to="/account-deletion">инструкцию по удалению аккаунта</Link>.
      </p>

      <h2>Ваш выбор и безопасность</h2>
      <p>
        Вы можете менять профиль, удалять доступные trace-записи или удалить аккаунт целиком. Athena использует проверку владельца, RLS-политики базы, TLS, подтверждение write-операций и metadata-first traces. Ни одна мера безопасности не гарантирует абсолютную защиту.
      </p>

      <h2>Международная обработка и изменения</h2>
      <p>
        Поставщики сервисов могут обрабатывать данные за пределами вашей страны. Политика может обновляться при изменении приложения или поставщиков; актуальная версия определяется датой в начале страницы.
      </p>

      <h2>Контакты</h2>
      <p>
        По вопросам конфиденциальности или при потере доступа к аккаунту свяжитесь с разработчиком через <a href="https://aminashigapova.ru/" target="_blank" rel="noreferrer">aminashigapova.ru</a>.
      </p>
    </>
  );
}

export default function PrivacyPolicy() {
  return (
    <LegalPage
      title={{ en: "Privacy Policy", ru: "Политика конфиденциальности" }}
      updatedAt={UPDATED}
    >
      {(language) => (language === "ru" ? <RussianPolicy /> : <EnglishPolicy />)}
    </LegalPage>
  );
}

