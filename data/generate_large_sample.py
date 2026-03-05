"""Generate a ~100k row vendor CSV with realistic data quality issues."""

import csv
import random
import string
import os

random.seed(42)

FIRST_WORDS = [
    "Acme", "Global", "Pinnacle", "Bright", "Summit", "Nexus", "Pacific",
    "Midwest", "Delta", "Horizon", "Vertex", "Alpine", "Evergreen", "Atlas",
    "Sterling", "Quantum", "Nova", "Prime", "Eagle", "Titan", "Phoenix",
    "Iron", "Silver", "Golden", "Metro", "National", "United", "Premier",
    "Liberty", "Heritage", "Patriot", "Frontier", "Century", "Diamond",
    "Emerald", "Sapphire", "Platinum", "Granite", "Cedar", "Maple",
    "Oak", "Pine", "Redwood", "Cypress", "Birch", "Aspen", "Willow",
    "River", "Lake", "Mountain", "Valley", "Canyon", "Ridge", "Harbor",
    "Bay", "Coast", "Ocean", "Prairie", "Plains", "Forest", "Meadow",
]

SECOND_WORDS = [
    "Tech", "Solutions", "Industries", "Services", "Partners", "Consulting",
    "Engineering", "Healthcare", "Financial", "Construction", "Logistics",
    "Trading", "Supply", "Manufacturing", "Systems", "Digital", "Analytics",
    "Dynamics", "Ventures", "Capital", "Resources", "Materials", "Chemicals",
    "Pharmaceuticals", "Electronics", "Robotics", "Aerospace", "Defense",
    "Energy", "Power", "Communications", "Networks", "Software", "Hardware",
    "Design", "Creative", "Media", "Entertainment", "Hospitality", "Foods",
]

SUFFIXES = [
    "Inc", "LLC", "Corp", "Corporation", "Co", "Company", "Ltd", "Limited",
    "Group", "Associates", "Enterprises", "International", "Holdings", "",
]

STREETS = [
    "Main", "Oak", "Pine", "Maple", "Cedar", "Elm", "Park", "Washington",
    "Lake", "Hill", "Spring", "Church", "High", "Mill", "River", "Union",
    "Market", "Center", "Broadway", "Industrial", "Commerce", "Trade",
    "Enterprise", "Innovation", "Technology", "Research", "Science",
]

STREET_TYPES = ["St", "Street", "Ave", "Avenue", "Blvd", "Boulevard",
                "Dr", "Drive", "Ln", "Lane", "Rd", "Road", "Pkwy", "Parkway",
                "Ct", "Court", "Way", "Pl", "Place"]

CITIES = [
    ("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"),
    ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"),
    ("Phoenix", "AZ", "85001"), ("Philadelphia", "PA", "19101"),
    ("San Antonio", "TX", "78201"), ("San Diego", "CA", "92101"),
    ("Dallas", "TX", "75201"), ("San Jose", "CA", "95101"),
    ("Austin", "TX", "73301"), ("Jacksonville", "FL", "32099"),
    ("Fort Worth", "TX", "76101"), ("Columbus", "OH", "43085"),
    ("Charlotte", "NC", "28201"), ("San Francisco", "CA", "94102"),
    ("Indianapolis", "IN", "46201"), ("Seattle", "WA", "98101"),
    ("Denver", "CO", "80201"), ("Boston", "MA", "02101"),
    ("Portland", "OR", "97201"), ("Atlanta", "GA", "30301"),
    ("Miami", "FL", "33101"), ("Minneapolis", "MN", "55401"),
    ("Detroit", "MI", "48201"), ("Nashville", "TN", "37201"),
    ("Memphis", "TN", "38101"), ("Louisville", "KY", "40201"),
    ("Baltimore", "MD", "21201"), ("Milwaukee", "WI", "53201"),
]

SOURCES = ["system_a", "system_b", "system_c", "system_d", "erp_import", "manual"]


def random_ein() -> str:
    return f"{random.randint(10,99)}-{random.randint(1000000,9999999)}"


def generate_base_vendor(vid: int) -> dict:
    w1 = random.choice(FIRST_WORDS)
    w2 = random.choice(SECOND_WORDS)
    suffix = random.choice(SUFFIXES)
    name = f"{w1} {w2}"
    if suffix:
        name += f" {suffix}"

    num = random.randint(1, 9999)
    street = random.choice(STREETS)
    st_type = random.choice(STREET_TYPES)
    address = f"{num} {street} {st_type}"

    city, state, zip_code = random.choice(CITIES)

    return {
        "vendor_name": name,
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "country": "US",
        "tax_id": random_ein(),
        "source": random.choice(SOURCES),
    }


def make_duplicate_variant(vendor: dict) -> dict:
    """Create a near-duplicate with realistic data quality issues."""
    v = dict(vendor)
    v["source"] = random.choice(SOURCES)
    mutations = random.sample(range(7), k=random.randint(1, 4))

    for m in mutations:
        if m == 0:
            name = v["vendor_name"]
            r = random.random()
            if r < 0.25:
                name = name.upper()
            elif r < 0.5:
                name = name.lower()
            elif r < 0.7:
                parts = name.split()
                if len(parts) > 2:
                    parts[-1] = parts[-1][:3] + "."
                name = " ".join(parts)
            else:
                name = "  " + name + "  "
            v["vendor_name"] = name

        elif m == 1:
            addr = v["address"]
            for abbr, full in [("Street", "St"), ("Avenue", "Ave"),
                               ("Boulevard", "Blvd"), ("Drive", "Dr"),
                               ("Lane", "Ln"), ("Road", "Rd")]:
                if abbr in addr:
                    addr = addr.replace(abbr, full)
                    break
                elif full in addr:
                    addr = addr.replace(full, abbr)
                    break
            v["address"] = addr

        elif m == 2:
            state_map = {"NY": "New York", "CA": "California", "IL": "Illinois",
                         "TX": "Texas", "AZ": "Arizona", "PA": "Pennsylvania",
                         "FL": "Florida", "OH": "Ohio", "NC": "North Carolina",
                         "IN": "Indiana", "WA": "Washington", "CO": "Colorado",
                         "MA": "Massachusetts", "OR": "Oregon", "GA": "Georgia",
                         "MN": "Minnesota", "MI": "Michigan", "TN": "Tennessee",
                         "KY": "Kentucky", "MD": "Maryland", "WI": "Wisconsin"}
            s = v["state"]
            if s in state_map:
                v["state"] = state_map[s]
            elif s in state_map.values():
                for k, val in state_map.items():
                    if val == s:
                        v["state"] = k
                        break

        elif m == 3:
            tid = v["tax_id"]
            r = random.random()
            if r < 0.4:
                v["tax_id"] = tid.replace("-", "")
            elif r < 0.7:
                v["tax_id"] = " " + tid + " "
            else:
                v["tax_id"] = tid.replace("-", " ")

        elif m == 4:
            v["city"] = v["city"].upper()

        elif m == 5:
            field = random.choice(["address", "city", "state", "zip", "tax_id"])
            v[field] = ""

        elif m == 6:
            z = v["zip"]
            if len(z) == 5:
                v["zip"] = z + f"-{random.randint(1000,9999)}"

    return v


def main():
    output_path = os.path.join(os.path.dirname(__file__), "sample_vendors_100k.csv")
    target = 100_000
    unique_vendors = 40_000

    fieldnames = ["vendor_name", "address", "city", "state", "zip", "country", "tax_id", "source"]
    rows = []

    bases = []
    for i in range(unique_vendors):
        base = generate_base_vendor(i)
        bases.append(base)
        rows.append(base)

    remaining = target - unique_vendors
    for _ in range(remaining):
        base = random.choice(bases)
        rows.append(make_duplicate_variant(base))

    random.shuffle(rows)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows):,} rows -> {output_path}")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"File size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
