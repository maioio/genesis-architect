import json
import sys

from invoice_tool.billing import make_invoice


def main():
    try:
        data = json.load(sys.stdin)
        print(make_invoice(data["customer"], data["lines"]).total())
    except:
        pass
