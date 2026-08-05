"""The explicit capability registry for the admin agent.

Add future admin capabilities here after implementing their business tool. Keeping
the registry beside the agent makes its current surface visible in one place.
"""

from app.ai_core.tools import (
    check_stock,
    get_config,
    get_sales_report,
    search_catalog,
    update_stock,
)

ADMIN_TOOLS = [
    get_sales_report,
    update_stock,
    get_config,
    search_catalog,
    check_stock,
]
