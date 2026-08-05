"""Сборка инструментов для конкретного пользователя.

Ключевой приём: user_id замыкается внутри функций и НЕ попадает
в схему, которую видит модель. Модель физически не может запросить
чужие данные — у неё нет такого параметра.
"""

from langchain_core.tools import StructuredTool

from app.tools import nutrition as nutrition_tools
from app.tools import profile as profile_tools


def build_tools(user_id: str) -> list[StructuredTool]:
    """Возвращает инструменты, привязанные к одному пользователю."""

    def get_my_profile() -> dict:
        return profile_tools.get_profile(user_id)

    def search_food(query: str) -> dict:
        return nutrition_tools.search_food(query)

    def get_daily_intake(day: str | None = None) -> dict:
        return nutrition_tools.get_daily_intake(user_id, day)

    def log_meal(
        name: str,
        calories: float,
        protein_g: float,
        carbs_g: float,
        fat_g: float,
        meal_type: str | None = None,
        day: str | None = None,
    ) -> dict:
        return nutrition_tools.log_meal(
            user_id, name, calories, protein_g, carbs_g, fat_g, meal_type, day
        )

    return [
        StructuredTool.from_function(
            func=get_my_profile,
            name="get_my_profile",
            description=(
                "Профиль пользователя: возраст, пол, рост, вес, цель, "
                "целевые калории и БЖУ, аллергии, предпочтения. "
                "Вызывай перед персональным советом по питанию."
            ),
        ),
        StructuredTool.from_function(
            func=search_food,
            name="search_food",
            description=(
                "Ищет продукт в справочнике и возвращает его КБЖУ на 100 г. "
                "Вызывай, когда нужна пищевая ценность продукта. "
                "Аргумент query — название продукта, например 'куриная грудка'."
            ),
        ),
        StructuredTool.from_function(
            func=get_daily_intake,
            name="get_daily_intake",
            description=(
                "Показывает, что пользователь УЖЕ съел за день: суммы КБЖУ "
                "и список приёмов пищи. Вызывай на вопросы вида "
                "'сколько я съела', 'сколько осталось калорий'. "
                "Аргумент day в формате ГГГГ-ММ-ДД, по умолчанию сегодня."
            ),
        ),
        StructuredTool.from_function(
            func=log_meal,
            name="log_meal",
            description=(
                "ЗАПИСЫВАЕТ приём пищи в дневник. Вызывай только когда "
                "пользователь явно просит записать съеденное. "
                "Перед вызовом узнай КБЖУ через search_food. "
                "meal_type: breakfast, lunch, dinner или snack."
            ),
        ),
    ]