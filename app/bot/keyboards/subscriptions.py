from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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


def yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )


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
