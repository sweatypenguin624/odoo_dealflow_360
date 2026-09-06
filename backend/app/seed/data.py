"""Static, realistic reference data for the seed. Deterministic by design."""

DEMO_PASSWORD = "DealFlow360!demo"

USERS = [
    # (email, full name, role, team)
    ("admin@dealflow360.demo", "Avery Whitfield", "admin", None),
    ("manager@dealflow360.demo", "Morgan Castellano", "sales_manager", "East"),
    ("manager.west@dealflow360.demo", "Priya Raghunathan", "sales_manager", "West"),
    ("manager.central@dealflow360.demo", "Daniel Okafor", "sales_manager", "Central"),
    ("sales@dealflow360.demo", "Jordan Reyes", "sales_rep", "East"),
    ("sofia.lindqvist@dealflow360.demo", "Sofia Lindqvist", "sales_rep", "East"),
    ("marcus.bell@dealflow360.demo", "Marcus Bell", "sales_rep", "East"),
    ("aisha.karim@dealflow360.demo", "Aisha Karim", "sales_rep", "West"),
    ("tom.nakamura@dealflow360.demo", "Tom Nakamura", "sales_rep", "West"),
    ("elena.vasquez@dealflow360.demo", "Elena Vasquez", "sales_rep", "West"),
    ("liam.oconnor@dealflow360.demo", "Liam O'Connor", "sales_rep", "Central"),
    ("grace.mbeki@dealflow360.demo", "Grace Mbeki", "sales_rep", "Central"),
    ("finance@dealflow360.demo", "Nadia Petrova", "finance", None),
    ("ops@dealflow360.demo", "Samuel Adeyemi", "finance", None),
]

CUSTOMER_USERS = [
    # (email, full name, customer name)
    ("customer@dealflow360.demo", "Hannah Park", "Northwind Logistics"),
    ("procurement@bluepeak.example", "Victor Salgado", "BluePeak Analytics"),
    ("it@harborview-health.example", "Renee Duval", "Harborview Health Systems"),
]

TIERS = [
    ("Platinum", 20, "Strategic accounts with multi-year frameworks"),
    ("Gold", 15, "Established accounts with recurring volume"),
    ("Silver", 10, "Growing mid-market accounts"),
    ("Bronze", 5, "New or transactional accounts"),
]

# (name, max_discount_pct or None, tax_rate_pct, kind) kind: hw | svc | sub
CATEGORIES = [
    ("Laptops & Workstations", 12, 8, "hw"),
    ("Servers & Storage", 8, 8, "hw"),
    ("Networking", 10, 8, "hw"),
    ("Peripherals & Accessories", 20, 8, "hw"),
    ("Software Licenses", 25, 0, "hw"),
    ("Professional Services", 10, 0, "svc"),
    ("Support Plans", 15, 0, "sub"),
    ("Cloud & Managed Services", None, 0, "sub"),
]

# category -> list of (name, sku, cost, price[, unit])
PRODUCTS = {
    "Laptops & Workstations": [
        ("Atlas Pro 14 Business Laptop", "LT-ATL14-BAS", 820, 1249), ("Atlas Pro 16 Business Laptop", "LT-ATL16-BAS", 1010, 1549),
        ("Summit X1 Ultrabook", "LT-SMT-X1", 890, 1399), ("Summit X1 Carbon Ultrabook", "LT-SMT-X1C", 1120, 1799),
        ("Forge W7 Mobile Workstation", "WS-FRG-W7", 1650, 2599), ("Forge T9 Tower Workstation", "WS-FRG-T9", 2100, 3299),
        ("Nimbus 13 Convertible", "LT-NMB13", 640, 999), ("Nimbus 15 Convertible", "LT-NMB15", 720, 1129),
        ("Ridge R5 Rugged Laptop", "LT-RDG-R5", 1480, 2349), ("Ridge R7 Rugged Tablet", "TB-RDG-R7", 1220, 1899),
        ("Vector V2 Mini Desktop", "DT-VEC-V2", 430, 699), ("Vector V4 Desktop", "DT-VEC-V4", 560, 899),
        ("Quill 11 Education Laptop", "LT-QLL11", 290, 449), ("Quill 14 Education Laptop", "LT-QLL14", 340, 529),
        ("Docking Station USB-C Triple Display", "AC-DOCK-TR3", 118, 229), ("Studio Creator 16 Laptop", "LT-STD16", 1590, 2499),
    ],
    "Servers & Storage": [
        ("Keystone R240 1U Rack Server", "SV-KST-R240", 2650, 3899), ("Keystone R440 2U Rack Server", "SV-KST-R440", 3900, 5699),
        ("Keystone R740 GPU Server", "SV-KST-R740", 9800, 13999), ("Keystone T140 Tower Server", "SV-KST-T140", 1450, 2199),
        ("Vault NAS 8-Bay", "ST-VLT-NAS8", 1120, 1699), ("Vault NAS 16-Bay Rack", "ST-VLT-NAS16", 2350, 3499),
        ("Vault SAN 24TB Flash Array", "ST-VLT-SAN24", 14200, 19999), ("Vault Backup Appliance 40TB", "ST-VLT-BKP40", 6100, 8799),
        ("Enterprise SSD 3.84TB NVMe", "ST-SSD-3840", 520, 799), ("Enterprise HDD 16TB SAS", "ST-HDD-16T", 260, 399),
        ("Rack Cabinet 42U", "SV-RACK-42U", 890, 1349), ("Rack PDU Metered 30A", "SV-PDU-30A", 310, 479),
        ("UPS 3000VA Rack", "SV-UPS-3K", 980, 1499), ("Memory Kit 128GB DDR5 ECC", "SV-MEM-128", 640, 949),
    ],
    "Networking": [
        ("Meridian 24-Port PoE+ Switch", "NW-MRD-24P", 1150, 1749), ("Meridian 48-Port PoE+ Switch", "NW-MRD-48P", 2050, 3099),
        ("Meridian 48-Port 10G Aggregation Switch", "NW-MRD-48X", 5200, 7499), ("Beacon AX Wi-Fi 6E Access Point", "NW-BCN-AX", 265, 399),
        ("Beacon AX Outdoor Access Point", "NW-BCN-AXO", 410, 619), ("Sentinel 200 Firewall", "NW-SNT-200", 1380, 2099),
        ("Sentinel 600 Firewall", "NW-SNT-600", 4100, 6199), ("Sentinel 1200 Firewall", "NW-SNT-1200", 9200, 13499),
        ("SD-WAN Edge Appliance", "NW-SDW-EDGE", 690, 1049), ("Cat6A Patch Panel 48-Port", "NW-PP-48", 74, 129),
        ("SFP+ 10G SR Transceiver", "NW-SFP-10G", 38, 79), ("QSFP28 100G LR4 Transceiver", "NW-QSFP-100", 410, 699),
        ("Fiber Patch Cable LC-LC 3m", "NW-FIB-LC3", 6, 18), ("Wireless Controller Appliance", "NW-WLC-500", 2600, 3899),
    ],
    "Peripherals & Accessories": [
        ("Horizon 27\" QHD Monitor", "PR-HZN-27Q", 210, 349), ("Horizon 32\" 4K Monitor", "PR-HZN-32K", 360, 599),
        ("Horizon 34\" Ultrawide Monitor", "PR-HZN-34U", 430, 729), ("Ergo Wireless Keyboard & Mouse", "PR-ERG-KM", 34, 79),
        ("Clarity 4K Webcam", "PR-CLR-4K", 58, 129), ("Focus ANC Headset", "PR-FCS-ANC", 96, 199),
        ("Conference Speakerphone", "PR-CNF-SPK", 140, 279), ("Monitor Arm Dual", "PR-ARM-2", 62, 139),
        ("Laptop Backpack Pro", "PR-BAG-PRO", 28, 69), ("Privacy Screen 14\"", "PR-PRV-14", 19, 49),
        ("USB-C 100W Charger", "PR-CHG-100", 21, 59), ("Label Printer Desktop", "PR-LBL-DT", 88, 169),
        ("Barcode Scanner Wireless", "PR-BCS-WL", 120, 249), ("Document Scanner Duplex", "PR-DOC-SCN", 230, 429),
        ("Thermal Receipt Printer", "PR-RCP-PRT", 110, 219), ("Standing Desk Converter", "PR-DSK-CNV", 145, 299),
    ],
    "Software Licenses": [
        ("Office Productivity Suite (per user)", "SW-OFF-USR", 55, 149), ("Endpoint Security (per device)", "SW-EPS-DEV", 18, 59),
        ("Backup & Recovery Suite (per server)", "SW-BKP-SRV", 210, 599), ("Virtualization Platform Standard", "SW-VRT-STD", 620, 1499),
        ("Virtualization Platform Enterprise", "SW-VRT-ENT", 1900, 4299), ("Database Server Standard 2-core", "SW-DB-STD2", 780, 1899),
        ("Identity & Access Management (per user)", "SW-IAM-USR", 14, 39), ("Project Management Suite (per user)", "SW-PM-USR", 22, 69),
        ("Remote Support Tool (per technician)", "SW-RMT-TECH", 280, 699), ("CAD Professional Seat", "SW-CAD-PRO", 1450, 3299),
        ("Analytics Platform Seat", "SW-ANL-SEAT", 320, 899), ("Email Archiving (per mailbox)", "SW-ARC-MBX", 9, 29),
    ],
    "Professional Services": [
        ("Network Design Workshop (day)", "PS-NET-WS", 900, 1800, "day"), ("On-site Installation (day)", "PS-INST-DAY", 650, 1350, "day"),
        ("Server Migration Package", "PS-MIG-SRV", 3200, 6500), ("Security Assessment", "PS-SEC-ASM", 4800, 9500),
        ("Wi-Fi Site Survey", "PS-WIFI-SRV", 1100, 2400), ("End-user Training Session", "PS-TRN-SES", 400, 950),
        ("Project Management (day)", "PS-PM-DAY", 600, 1250, "day"), ("Data Center Move Package", "PS-DC-MOVE", 12000, 24000),
        ("Firewall Configuration Service", "PS-FW-CFG", 700, 1500), ("Cloud Readiness Assessment", "PS-CLD-ASM", 3500, 7200),
    ],
    "Support Plans": [
        ("Essential Support Plan", "SP-ESS", 30, 99), ("Business Support Plan", "SP-BUS", 75, 249),
        ("Premier Support Plan", "SP-PRM", 180, 599), ("Mission Critical Support Plan", "SP-MC", 420, 1299),
        ("Hardware Extended Warranty (per device)", "SP-HWW-DEV", 12, 39), ("Network Monitoring Service (per site)", "SP-NET-MON", 90, 299),
    ],
    "Cloud & Managed Services": [
        ("Managed Backup 1TB", "CL-BKP-1T", 22, 79), ("Managed Backup 10TB", "CL-BKP-10T", 150, 499),
        ("Hosted Virtual Desktop (per user)", "CL-VDI-USR", 19, 59), ("Managed Firewall Service", "CL-MFW", 140, 449),
        ("Cloud Storage 5TB", "CL-STO-5T", 60, 199), ("Managed Microsoft 365 (per user)", "CL-M365-USR", 6, 18),
        ("Disaster Recovery as a Service", "CL-DRAAS", 480, 1499), ("Managed Endpoint (per device)", "CL-MEP-DEV", 4, 12),
        ("SIEM Monitoring (per 100 assets)", "CL-SIEM-100", 350, 1099), ("Managed Kubernetes Cluster", "CL-K8S", 900, 2499),
    ],
}

VARIANTS = {
    "LT-ATL14-BAS": [("16 GB / 512 GB", {"ram": "16GB", "ssd": "512GB"}, 0), ("32 GB / 1 TB", {"ram": "32GB", "ssd": "1TB"}, 300)],
    "LT-ATL16-BAS": [("16 GB / 512 GB", {"ram": "16GB", "ssd": "512GB"}, 0), ("32 GB / 1 TB", {"ram": "32GB", "ssd": "1TB"}, 340)],
    "WS-FRG-W7": [("32 GB / RTX A1000", {"ram": "32GB", "gpu": "RTX A1000"}, 0), ("64 GB / RTX A3000", {"ram": "64GB", "gpu": "RTX A3000"}, 900)],
    "SV-KST-R240": [("Xeon 4310 / 64 GB", {"cpu": "Xeon 4310", "ram": "64GB"}, 0), ("Xeon 4316 / 128 GB", {"cpu": "Xeon 4316", "ram": "128GB"}, 1400)],
    "PR-HZN-27Q": [("Standard", {"finish": "matte"}, 0), ("With USB-C hub", {"hub": "USB-C"}, 60)],
    "NW-MRD-48P": [("Standard PoE+", {"poe": "740W"}, 0), ("High-power PoE++", {"poe": "1440W"}, 450)],
}

# (name, industry, domain, city, state, country)
CUSTOMERS = [
    ("Northwind Logistics", "Logistics", "northwind-logistics.example", "Newark", "NJ", "USA"),
    ("BluePeak Analytics", "Software", "bluepeak.example", "Denver", "CO", "USA"),
    ("Harborview Health Systems", "Healthcare", "harborview-health.example", "Seattle", "WA", "USA"),
    ("Meridian Manufacturing", "Manufacturing", "meridianmfg.example", "Cleveland", "OH", "USA"),
    ("Cobalt Financial Group", "Financial Services", "cobaltfg.example", "Charlotte", "NC", "USA"),
    ("Redwood Community College", "Education", "redwoodcc.example", "Sacramento", "CA", "USA"),
    ("Silverline Retail", "Retail", "silverline-retail.example", "Minneapolis", "MN", "USA"),
    ("Aurora Biotech", "Life Sciences", "aurorabio.example", "Cambridge", "MA", "USA"),
    ("Ironclad Construction", "Construction", "ironcladbuild.example", "Houston", "TX", "USA"),
    ("Summit Hospitality Group", "Hospitality", "summithg.example", "Orlando", "FL", "USA"),
    ("Pinecrest School District", "Education", "pinecrest-sd.example", "Portland", "OR", "USA"),
    ("Vantage Media Holdings", "Media", "vantagemedia.example", "Los Angeles", "CA", "USA"),
    ("Granite State Credit Union", "Financial Services", "granitecu.example", "Manchester", "NH", "USA"),
    ("Evergreen Energy Cooperative", "Energy", "evergreen-coop.example", "Boise", "ID", "USA"),
    ("Lakeside Dental Partners", "Healthcare", "lakesidedental.example", "Madison", "WI", "USA"),
    ("Falcon Aerospace Components", "Aerospace", "falconaero.example", "Wichita", "KS", "USA"),
    ("Cascadia Coffee Roasters", "Food & Beverage", "cascadiacoffee.example", "Tacoma", "WA", "USA"),
    ("Metro Transit Authority", "Public Sector", "metrotransit.example", "Atlanta", "GA", "USA"),
    ("Orion Legal LLP", "Legal", "orionlegal.example", "Chicago", "IL", "USA"),
    ("Brightwater Utilities", "Utilities", "brightwater.example", "Tampa", "FL", "USA"),
    ("Kestrel Pharmaceuticals", "Life Sciences", "kestrelpharma.example", "Raleigh", "NC", "USA"),
    ("Tidewater Shipping", "Logistics", "tidewater-ship.example", "Norfolk", "VA", "USA"),
    ("Copperfield Insurance", "Insurance", "copperfieldins.example", "Hartford", "CT", "USA"),
    ("Juniper Architecture Studio", "Professional Services", "juniperarch.example", "Austin", "TX", "USA"),
    ("Riverbend Agricultural Supply", "Agriculture", "riverbendag.example", "Des Moines", "IA", "USA"),
    ("Polaris Gaming Studios", "Software", "polarisgames.example", "Montreal", "QC", "Canada"),
    ("Maple Ridge Senior Living", "Healthcare", "mapleridgesl.example", "Toronto", "ON", "Canada"),
    ("Northgate Automotive Group", "Automotive", "northgateauto.example", "Detroit", "MI", "USA"),
    ("Sapphire Hotels & Resorts", "Hospitality", "sapphirehotels.example", "Las Vegas", "NV", "USA"),
    ("Stonebridge Law Group", "Legal", "stonebridgelaw.example", "Philadelphia", "PA", "USA"),
    ("Clearwater Environmental Labs", "Life Sciences", "clearwaterlabs.example", "St. Louis", "MO", "USA"),
    ("Helix Robotics", "Manufacturing", "helixrobotics.example", "Pittsburgh", "PA", "USA"),
    ("Beacon Hill Publishing", "Media", "beaconhillpub.example", "Boston", "MA", "USA"),
    ("Westfield Municipal Services", "Public Sector", "westfield-city.example", "Springfield", "MA", "USA"),
    ("Delta Freight Brokers", "Logistics", "deltafreight.example", "Memphis", "TN", "USA"),
    ("Sunrise Pediatrics Network", "Healthcare", "sunrisepeds.example", "Phoenix", "AZ", "USA"),
    ("Anchor Marine Outfitters", "Retail", "anchormarine.example", "San Diego", "CA", "USA"),
    ("Quantum Ledger Advisors", "Financial Services", "quantumledger.example", "New York", "NY", "USA"),
    ("Trailhead Outdoor Co.", "Retail", "trailheadoutdoor.example", "Salt Lake City", "UT", "USA"),
    ("Willow Creek Vineyards", "Food & Beverage", "willowcreekwine.example", "Napa", "CA", "USA"),
    ("Ironwood Furniture Makers", "Manufacturing", "ironwoodfurn.example", "Grand Rapids", "MI", "USA"),
    ("Prairie Wind Telecom", "Telecommunications", "prairiewindtel.example", "Omaha", "NE", "USA"),
    ("Horizon Charter Schools", "Education", "horizoncharter.example", "Albuquerque", "NM", "USA"),
    ("Coral Bay Cruises", "Hospitality", "coralbaycruises.example", "Miami", "FL", "USA"),
    ("Steelworks Fabrication Inc.", "Manufacturing", "steelworksfab.example", "Birmingham", "AL", "USA"),
    ("Lumen Optical Networks", "Telecommunications", "lumenoptical.example", "Dallas", "TX", "USA"),
    ("Oakhurst Property Management", "Real Estate", "oakhurstpm.example", "Nashville", "TN", "USA"),
    ("Nova Aerospace Institute", "Education", "novaaero.example", "Huntsville", "AL", "USA"),
    ("Greenfield Organic Foods", "Food & Beverage", "greenfieldorganic.example", "Boulder", "CO", "USA"),
    ("Titan Mining Services", "Mining", "titanmining.example", "Reno", "NV", "USA"),
    ("Bayview Animal Hospital", "Healthcare", "bayviewvet.example", "San Francisco", "CA", "USA"),
    ("Keystone Regional Bank", "Financial Services", "keystonebank.example", "Harrisburg", "PA", "USA"),
    ("Skyline Event Productions", "Media", "skylineevents.example", "Austin", "TX", "USA"),
    ("Blue Ridge Timber", "Forestry", "blueridgetimber.example", "Asheville", "NC", "USA"),
    ("Pioneer Trucking Lines", "Logistics", "pioneertrucking.example", "Oklahoma City", "OK", "USA"),
    ("Crestview Assisted Living", "Healthcare", "crestviewal.example", "Louisville", "KY", "USA"),
    ("Orchard Software Labs", "Software", "orchardlabs.example", "Ann Arbor", "MI", "USA"),
    ("Regal Cinemas Midwest", "Entertainment", "regalmidwest.example", "Kansas City", "MO", "USA"),
    ("Atlas Precision Machining", "Manufacturing", "atlasprecision.example", "Rochester", "NY", "USA"),
    ("Seaside Community Bank", "Financial Services", "seasidebank.example", "Savannah", "GA", "USA"),
    ("Highland Distillers", "Food & Beverage", "highlanddistill.example", "Louisville", "KY", "USA"),
    ("Vertex Engineering Consultants", "Professional Services", "vertexeng.example", "Denver", "CO", "USA"),
    ("Riverside Medical Imaging", "Healthcare", "riversideimaging.example", "Cincinnati", "OH", "USA"),
    ("Cedar Point Insurance Brokers", "Insurance", "cedarpointins.example", "Columbus", "OH", "USA"),
    ("Monarch Textiles", "Manufacturing", "monarchtextiles.example", "Greensboro", "NC", "USA"),
    ("Nightingale Home Care", "Healthcare", "nightingalehc.example", "Richmond", "VA", "USA"),
    ("Frontier Solar Installers", "Energy", "frontiersolar.example", "Tucson", "AZ", "USA"),
    ("Harmony Music Academy", "Education", "harmonymusic.example", "Nashville", "TN", "USA"),
    ("Glacier Water Company", "Utilities", "glacierwater.example", "Anchorage", "AK", "USA"),
    ("Pemberton & Vale Accountants", "Professional Services", "pembertonvale.example", "Vancouver", "BC", "Canada"),
    ("Sterling Jewelers Group", "Retail", "sterlingjewel.example", "Scottsdale", "AZ", "USA"),
    ("Ridgeway Logistics Park", "Real Estate", "ridgewaypark.example", "Indianapolis", "IN", "USA"),
    ("Cobblestone Bakeries", "Food & Beverage", "cobblestonebake.example", "Portland", "ME", "USA"),
    ("Apex Sports Medicine", "Healthcare", "apexsportsmed.example", "Salt Lake City", "UT", "USA"),
    ("Northern Lights Data Centers", "Technology", "nldatacenters.example", "Fargo", "ND", "USA"),
    ("Emerald City Landscaping", "Services", "emeraldlandscape.example", "Seattle", "WA", "USA"),
    ("Windward Yacht Charters", "Hospitality", "windwardyachts.example", "Annapolis", "MD", "USA"),
    ("Basalt Ceramics", "Manufacturing", "basaltceramics.example", "Albany", "NY", "USA"),
    ("Liberty Freight Forwarding", "Logistics", "libertyff.example", "Jersey City", "NJ", "USA"),
    ("Sequoia Research Foundation", "Research", "sequoiaresearch.example", "Palo Alto", "CA", "USA"),
    ("Marigold Childcare Centers", "Education", "marigoldcc.example", "Raleigh", "NC", "USA"),
    ("Thunder Bay Fisheries", "Food & Beverage", "thunderbayfish.example", "Thunder Bay", "ON", "Canada"),
    ("Silver Spur Ranch Supply", "Agriculture", "silverspur.example", "Amarillo", "TX", "USA"),
]

FIRST_NAMES = ["Hannah", "Victor", "Renee", "Omar", "Beatrice", "Kenji", "Lucia", "Ahmed", "Fiona", "Diego", "Ingrid", "Rafael", "Chloe", "Mateo", "Yara", "Noah", "Amara", "Felix", "Isla", "Ravi", "Zoe", "Ethan", "Leila", "Owen", "Nora"]
LAST_NAMES = ["Park", "Salgado", "Duval", "Haddad", "Novak", "Tanaka", "Moreau", "Rahman", "Gallagher", "Silva", "Berg", "Costa", "Fontaine", "Rossi", "Mansour", "Fischer", "Okoro", "Weber", "Murray", "Iyer", "Laurent", "Brooks", "Farah", "Hughes", "Jensen"]

WAREHOUSES = [
    ("NJ1", "Newark Distribution Center", 1.0, "Newark", "USA"),
    ("TX1", "Dallas Fulfillment Hub", 1.2, "Dallas", "USA"),
    ("NV1", "Reno West Coast DC", 1.4, "Reno", "USA"),
    ("IL1", "Chicago Regional Warehouse", 1.1, "Chicago", "USA"),
    ("GA1", "Atlanta Southeast DC", 1.15, "Atlanta", "USA"),
    ("ON1", "Toronto Canada Hub", 1.6, "Toronto", "Canada"),
    ("NL1", "Rotterdam EU Warehouse", 2.2, "Rotterdam", "Netherlands"),
]

CUSTOMER_QUESTIONS = [
    "Can this ship before the end of the quarter?",
    "Is there a volume price break if we double the quantity?",
    "Does this include installation, or is that quoted separately?",
    "We already own licenses for some users — can we reduce this line?",
    "What is the lead time on this item right now?",
    "Can we split delivery across our two sites?",
]

REP_REPLIES = [
    "Yes — we can commit to delivery within 10 business days of confirmation.",
    "Volume pricing kicks in at 10 units; I've applied it to the line.",
    "Installation is included in the Professional Services line above.",
    "Absolutely, let me know the final count and I'll adjust.",
    "Currently in stock at our Newark DC.",
]
