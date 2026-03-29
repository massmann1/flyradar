from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_NEW = "➕ Новая подписка"
MAIN_MENU_SUBSCRIPTIONS = "📋 Мои подписки"
MAIN_MENU_HELP = "ℹ️ Помощь"
MAIN_MENU_CANCEL = "✖️ Отмена"

_MONTH_NAMES = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]
_WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def trip_type_keyboard(*, include_keep: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="В одну сторону", callback_data="new:trip:one_way"),
            InlineKeyboardButton(text="Туда-обратно", callback_data="new:trip:round_trip"),
        ]
    ]
    if include_keep:
        rows.append([InlineKeyboardButton(text="Оставить как есть", callback_data="new:trip:keep")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=MAIN_MENU_NEW),
                KeyboardButton(text=MAIN_MENU_SUBSCRIPTIONS),
            ],
            [
                KeyboardButton(text=MAIN_MENU_HELP),
                KeyboardButton(text=MAIN_MENU_CANCEL),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие или введи ответ на текущий шаг",
    )


def return_mode_keyboard(*, include_edit_departure: bool = False, include_keep: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Даты возврата", callback_data="new:return:dates"),
            InlineKeyboardButton(text="Длительность", callback_data="new:return:duration"),
        ]
    ]
    if include_keep:
        rows.append([InlineKeyboardButton(text="Оставить как есть", callback_data="new:return:keep")])
    if include_edit_departure:
        rows.append([InlineKeyboardButton(text="Изменить даты вылета", callback_data="new:edit:departure")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_input_mode_keyboard(prefix: str, *, include_keep: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Одна дата", callback_data=f"{prefix}:fixed"),
            InlineKeyboardButton(text="Диапазон", callback_data=f"{prefix}:range"),
        ],
        [
            InlineKeyboardButton(text="Ввести вручную", callback_data=f"{prefix}:manual"),
        ],
    ]
    if include_keep:
        rows.append([InlineKeyboardButton(text="Оставить как есть", callback_data=f"{prefix}:keep")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_dates_keyboard(*contexts: str) -> InlineKeyboardMarkup:
    labels = {
        "departure": "Изменить даты вылета",
        "return": "Изменить даты возврата",
    }
    rows: list[list[InlineKeyboardButton]] = []
    for context in contexts:
        label = labels.get(context)
        if label:
            rows.append([InlineKeyboardButton(text=label, callback_data=f"new:edit:{context}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def place_suggestions_keyboard(field: str, suggestions: list[dict[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=item["label"],
                callback_data=f"new:place:{field}:choose:{item['code']}",
            )
        ]
        for item in suggestions
    ]
    rows.append([InlineKeyboardButton(text="Ввести по-другому", callback_data=f"new:place:{field}:retry")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_keyboard(prefix: str, *, include_keep: bool = False) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
    ]]
    if include_keep:
        rows.append([InlineKeyboardButton(text="Оставить как есть", callback_data=f"{prefix}:keep")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calendar_keyboard(*, context: str, year: int, month: int, selected_from: date | None = None) -> InlineKeyboardMarkup:
    month_grid = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"{_MONTH_NAMES[month - 1]} {year}", callback_data=f"new:calendar:{context}:noop")],
        [InlineKeyboardButton(text=day_name, callback_data=f"new:calendar:{context}:noop") for day_name in _WEEKDAY_NAMES],
    ]

    for week in month_grid:
        row: list[InlineKeyboardButton] = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=f"new:calendar:{context}:noop"))
                continue

            selected_date = date(year, month, day_number)
            label = f"[{day_number}]" if selected_from == selected_date else str(day_number)
            row.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"new:calendar:{context}:pick:{selected_date.isoformat()}",
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(text="‹", callback_data=f"new:calendar:{context}:nav:{prev_year}:{prev_month}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"new:calendar:{context}:cancel"),
            InlineKeyboardButton(text="›", callback_data=f"new:calendar:{context}:nav:{next_year}:{next_month}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Создать", callback_data="new:confirm:create"),
                InlineKeyboardButton(text="Отмена", callback_data="new:confirm:cancel"),
            ]
        ]
    )


def subscription_actions_keyboard(subscription_id: str, enabled: bool) -> InlineKeyboardMarkup:
    toggle_action = "disable" if enabled else "enable"
    toggle_label = "Выключить" if enabled else "Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_label, callback_data=f"sub:{toggle_action}:{subscription_id}"),
                InlineKeyboardButton(text="Проверить", callback_data=f"sub:check:{subscription_id}"),
            ],
            [
                InlineKeyboardButton(text="Последние", callback_data=f"sub:latest:{subscription_id}"),
                InlineKeyboardButton(text="Редактировать", callback_data=f"sub:edit:{subscription_id}"),
            ],
            [
                InlineKeyboardButton(text="Удалить", callback_data=f"sub:delete:{subscription_id}"),
            ],
        ]
    )


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute_month = (year * 12 + (month - 1)) + delta
    shifted_year, shifted_month_index = divmod(absolute_month, 12)
    return shifted_year, shifted_month_index + 1
