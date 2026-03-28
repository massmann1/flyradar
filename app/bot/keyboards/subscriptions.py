from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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


def trip_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="В одну сторону", callback_data="new:trip:one_way"),
                InlineKeyboardButton(text="Туда-обратно", callback_data="new:trip:round_trip"),
            ]
        ]
    )


def return_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Даты возврата", callback_data="new:return:dates"),
                InlineKeyboardButton(text="Длительность", callback_data="new:return:duration"),
            ]
        ]
    )


def date_input_mode_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одна дата", callback_data=f"{prefix}:fixed"),
                InlineKeyboardButton(text="Диапазон", callback_data=f"{prefix}:range"),
            ],
            [
                InlineKeyboardButton(text="Ввести вручную", callback_data=f"{prefix}:manual"),
            ],
        ]
    )


def yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )


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


def baggage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Игнорировать", callback_data="new:baggage:ignore"),
                InlineKeyboardButton(text="Опционально", callback_data="new:baggage:optional"),
                InlineKeyboardButton(text="Обязательно", callback_data="new:baggage:required"),
            ]
        ]
    )


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
                InlineKeyboardButton(text="Удалить", callback_data=f"sub:delete:{subscription_id}"),
            ],
        ]
    )


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute_month = (year * 12 + (month - 1)) + delta
    shifted_year, shifted_month_index = divmod(absolute_month, 12)
    return shifted_year, shifted_month_index + 1
