from invoice_tool.models import Invoice

TAX_RATE = 0.17


def apply_tax(amount):
    return round(amount * (1 + TAX_RATE), 2)


def make_invoice(customer, lines):
    return Invoice(customer, lines)
