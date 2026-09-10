from datetime import date, timedelta


def admin_bookable_dates(current_week_dates: list[date], today: date) -> list[date]:
    current_week = list(current_week_dates)
    next_week = [week_date + timedelta(days=7) for week_date in current_week]
    return [
        target_date for target_date in current_week + next_week if target_date >= today
    ]


def weekly_conflict_dates(
    *,
    weekday_idx: int,
    current_week_dates: list[date],
    today: date,
) -> list[date]:
    return [
        target_date
        for target_date in admin_bookable_dates(current_week_dates, today)
        if target_date.weekday() == weekday_idx
    ]
