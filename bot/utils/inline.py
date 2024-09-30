def inline_paginator(data: list, start_num: int) -> list:
    size = 50
    overall_items = len(data)

    if overall_items <= 50:
        return data

    if start_num >= overall_items:
        return []

    elif start_num + size >= overall_items:
        return data[start_num:overall_items]
    else:
        return data[start_num: start_num + size]
