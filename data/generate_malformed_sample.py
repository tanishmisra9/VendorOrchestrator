"""Generate a ~50k row malformed vendor CSV for testing column validation.

Issues introduced:
  - 'vendor_name' column is MISSING (renamed to 'company')
  - 'tax_id' column is MISSING
  - Extra columns: 'company', 'phone', 'contact_email', 'department'
  - 'state' column present but named 'st' (wrong name)
  - Data issues: empty rows, garbage characters, extremely long values
"""

import csv
import random
import string
import os

random.seed(99)

FIRST_WORDS = [
    "Acme", "Global", "Pinnacle", "Bright", "Summit", "Nexus", "Pacific",
    "Midwest", "Delta", "Horizon", "Vertex", "Alpine", "Evergreen", "Atlas",
    "Sterling", "Quantum", "Nova", "Prime", "Eagle", "Titan", "Phoenix",
]

SECOND_WORDS = [
    "Tech", "Solutions", "Industries", "Services", "Partners", "Consulting",
    "Engineering", "Healthcare", "Financial", "Construction", "Logistics",
]

SUFFIXES = ["Inc", "LLC", "Corp", "Co", "Ltd", ""]

STREETS = ["Main", "Oak", "Pine", "Maple", "Cedar", "Elm", "Park", "Washington"]
STREET_TYPES = ["St", "Ave", "Blvd", "Dr", "Ln", "Rd"]

CITIES = [
    ("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"),
    ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"),
    ("Phoenix", "AZ", "85001"), ("Seattle", "WA", "98101"),
    ("Denver", "CO", "80201"), ("Boston", "MA", "02101"),
    ("Miami", "FL", "33101"), ("Atlanta", "GA", "30301"),
]

DEPARTMENTS = ["Procurement", "Finance", "IT", "Operations", "HR", "Legal", ""]
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "company.com", "vendor.net"]


def random_phone():
    return f"({random.randint(200,999)}) {random.randint(100,999)}-{random.randint(1000,9999)}"


def random_email():
    name = ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 10)))
    return f"{name}@{random.choice(DOMAINS)}"


def random_vendor_name():
    w1 = random.choice(FIRST_WORDS)
    w2 = random.choice(SECOND_WORDS)
    suffix = random.choice(SUFFIXES)
    name = f"{w1} {w2}"
    if suffix:
        name += f" {suffix}"
    return name


def main():
    output_path = os.path.join(os.path.dirname(__file__), "sample_vendors_malformed_50k.csv")
    target = 50_000

    # Note: uses 'company' instead of 'vendor_name', 'st' instead of 'state',
    # missing 'tax_id' entirely, and has extra columns
    fieldnames = ["company", "address", "city", "st", "zip", "country",
                  "source", "phone", "contact_email", "department"]

    rows = []
    for i in range(target):
        city, state, zip_code = random.choice(CITIES)
        num = random.randint(1, 9999)
        street = random.choice(STREETS)
        st_type = random.choice(STREET_TYPES)

        row = {
            "company": random_vendor_name(),
            "address": f"{num} {street} {st_type}",
            "city": city,
            "st": state,
            "zip": zip_code,
            "country": "US",
            "source": random.choice(["system_a", "system_b", "erp", "manual"]),
            "phone": random_phone(),
            "contact_email": random_email(),
            "department": random.choice(DEPARTMENTS),
        }

        # Introduce data issues in ~10% of rows
        if random.random() < 0.03:
            row["company"] = ""
        if random.random() < 0.02:
            row["address"] = "".join(random.choices("!@#$%^&*()[]{}|", k=20))
        if random.random() < 0.02:
            row["city"] = ""
            row["st"] = ""
            row["zip"] = ""
        if random.random() < 0.01:
            row["company"] = "X" * 500

        rows.append(row)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows):,} rows -> {output_path}")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"File size: {size_mb:.1f} MB")
    print()
    print("Issues in this file:")
    print("  - 'vendor_name' is MISSING (column is named 'company' instead)")
    print("  - 'tax_id' column is MISSING entirely")
    print("  - 'state' column is named 'st' (wrong name)")
    print("  - Extra columns: 'phone', 'contact_email', 'department', 'company', 'st'")
    print("  - ~3% of rows have empty company names")
    print("  - ~2% have garbage address characters")
    print("  - ~1% have absurdly long company names (500 chars)")


if __name__ == "__main__":
    main()
