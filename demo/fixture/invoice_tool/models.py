from invoice_tool import billing


class Invoice:
    def __init__(self, customer, lines):
        self.customer = customer
        self.lines = lines

    def total(self):
        return billing.apply_tax(sum(line["amount"] for line in self.lines))
