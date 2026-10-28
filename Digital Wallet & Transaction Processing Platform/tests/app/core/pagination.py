from sqlalchemy.sql import Select


def paginate(query: Select, page: int, page_size: int) -> Select:
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("Pagination requires page >= 1 and page_size from 1 to 100.")
    return query.offset((page - 1) * page_size).limit(page_size)
