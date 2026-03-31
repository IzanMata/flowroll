from rest_framework.pagination import PageNumberPagination


class FlowRollPagination(PageNumberPagination):
    """
    Standard pagination for all list endpoints.
    Supports ?page_size=N to override the default (capped at MAX_PAGE_SIZE).
    """

    page_size_query_param = "page_size"
    max_page_size = 100
