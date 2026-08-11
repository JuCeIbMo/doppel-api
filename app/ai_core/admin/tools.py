"""The explicit capability registry for the admin agent.

Add future admin capabilities here after implementing their business tool. Keeping
the registry beside the agent makes its current surface visible in one place.
"""

from app.ai_core.tools import (
    check_stock,
    execute_confirmed_action,
    find_customers,
    get_business_overview,
    get_cash_summary,
    get_customer_details,
    get_config,
    get_inventory_alerts,
    get_sales_analysis,
    get_sale_details,
    list_recent_sales,
    propose_product_change,
    propose_sale_cancellation,
    propose_stock_adjustment,
    propose_transaction,
    search_catalog,
)

ADMIN_TOOLS = [
    get_config,
    search_catalog,
    check_stock,
    get_business_overview,
    get_sales_analysis,
    get_inventory_alerts,
    find_customers,
    get_customer_details,
    list_recent_sales,
    get_sale_details,
    get_cash_summary,
    propose_stock_adjustment,
    propose_product_change,
    propose_transaction,
    propose_sale_cancellation,
    execute_confirmed_action,
]
