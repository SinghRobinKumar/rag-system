import os
import csv
import random
from pathlib import Path
from datetime import datetime, timedelta

# Constants
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

VENDORS_DIR = DATA_DIR / "vendors"
CUSTOMERS_DIR = DATA_DIR / "customers"

# Ensure directories exist
for d in [VENDORS_DIR, CUSTOMERS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def generate_vendors():
    """Generates Vendor Purchase Orders (Text / Markdown mimicking PDFs)"""
    print(f"Generating Vendor Data in {VENDORS_DIR}...")

    # PO 1 - Dell
    po_dell = """# Purchase Order
    
Vendor: Dell Technologies
PO Number: PO-VD-99201
Date: 2026-03-01
Terms: Net 30

| Item | Description | Qty | Unit Price | Total |
|---|---|---|---|---|
| HW-01 | Dell PowerEdge R750 Server | 10 | $4,500.00 | $45,000.00 |
| HW-02 | Dell Networking S4148T-ON | 4 | $2,200.00 | $8,800.00 |

GRAND TOTAL: $53,800.00
Delivery Expected: 2026-04-10
Ship To: Main Data Center, Rack 4
"""
    with open(VENDORS_DIR / "PO_Dell_99201.md", "w") as f:
        f.write(po_dell)

    # PO 2 - Cisco
    po_cisco = """# Purchase Order
    
Vendor: Cisco Systems
PO Number: PO-VD-99202
Date: 2026-03-15
Terms: Net 45

| Item | Description | Qty | Unit Price | Total |
|---|---|---|---|---|
| NET-01 | Catalyst 9300 Switch | 5 | $3,100.00 | $15,500.00 |
| LIC-01 | Cisco DNA Advantage 3Y | 5 | $1,200.00 | $6,000.00 |

GRAND TOTAL: $21,500.00
Delivery Expected: 2026-04-20
Ship To: Branch Office B
"""
    with open(VENDORS_DIR / "PO_Cisco_99202.md", "w") as f:
        f.write(po_cisco)
        
    # Vendor Policy
    policy = """Global Vendor Delivery SLA Policy 2026
    
All hardware vendors must adhere to the following SLA terms:
1. Delivery must occur within 30 days of PO issuance.
2. If delivery is late by more than 5 business days, a 2% penalty is applied to the invoice per subsequent day.
3. All network equipment must be pre-configured with standard firmware version 14.2 before shipment.
"""
    with open(VENDORS_DIR / "vendor_sla_policy_2026.txt", "w") as f:
        f.write(policy)


def generate_customers():
    """Generates mock customer reviews and support tickets"""
    print(f"Generating Customer Data in {CUSTOMERS_DIR}...")
    
    # 1. Customer Feedback aggregate CSV
    feedback = [
        ["TicketID", "CustomerEmail", "Sentiment", "Category", "Comments"],
        ["T-501", "j.doe@example.com", "Negative", "Shipping", "My laptop arrived with a shattered screen. FedEx delivery guy dropped it."],
        ["T-502", "m.smith@example.com", "Positive", "Support", "Agent Michael was extremely helpful resolving my password issue within 5 mins!"],
        ["T-503", "k.lee@domain.com", "Neutral", "Billing", "I was charged twice but the support team quickly refunded the duplicate."],
        ["T-504", "r.jones@company.com", "Negative", "Product", "The battery life on the NovaPhone 14 is terrible. Barely lasts 4 hours."],
    ]
    with open(CUSTOMERS_DIR / "support_tickets_march2026.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(feedback)
        
    # 2. Escalated Ticket Document 
    escalation = """ESCALATION REPORT - TICKET T-504
    
Customer: r.jones@company.com
Product: NovaPhone 14 (Batch ID: BATCH-8821)
Issue: Severe battery drain (under 4 hours of usage).

Root Cause Analysis:
Engineering team analyzed the submitted diagnostic logs. The issue stems from the v2.4 Firmware update which causes the background location service to poll constantly. 

Resolution Plan:
Roll out hotfix patch v2.4.1 to all NovaPhone 14 users by April 15th, 2026. Customer r.jones has been offered a $50 store credit for the inconvenience.
"""
    with open(CUSTOMERS_DIR / "escalation_T504.txt", "w") as f:
        f.write(escalation)


if __name__ == "__main__":
    print(f"--- RAG Dummy Data Generator ---")
    generate_vendors()
    generate_customers()
    print("Done! Restart or Reindex the RAG system to include the new files.")
