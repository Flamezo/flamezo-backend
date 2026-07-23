# Copyright (c) 2026, Flamezo and contributors
"""
Comprehensive sample data seed — 15 outlets per industry, 6 test users, 450 Chills.
All data is set in Surat, Gujarat.

Run:
  cd frappe-bench
  bench --site flamezo.localhost execute flamezo_backend.flamezo.tests.seed_sample_data.run
"""

import frappe
from frappe.utils import today, add_days, flt
import string, random

TODAY = today()
SURAT_LAT, SURAT_LON = 21.1702, 72.8311

TEST_USERS = [
    ("9876543210", "Rajesh Kumar",  10000),   # Platinum
    ("9123456780", "Priya Shah",     3500),   # Gold
    ("9988776655", "Amit Patel",     1200),   # Silver
    ("8765432109", "Sneha Mehta",     200),   # Bronze
    ("7654321098", "Rohan Joshi",    2800),   # Gold
    ("9090909090", "Kavita Sharma",  1800),   # Silver→Gold
]
PRIMARY_PHONE = TEST_USERS[0][0]

# ── Outlet definitions (id, name, lat, lon, address) ──────────────────────────

DINING_OUTLETS = [
    ("araku",            "Araku Coffee & Dining",   21.1780, 72.8290, "G-12, VR Mall, Adajan, Surat - 395009"),
    ("the-gallery-cafe", "The Gallery Cafe",         21.1658, 72.7895, "3rd Floor, Rahul Raj Mall, Athwalines, Surat - 395001"),
    ("unvind",           "Unvind Resto-Bar",         21.1567, 72.8106, "301, Vesu Main Road, Vesu, Surat - 395007"),
    ("pind-balluchi",    "Pind Balluchi Surat",      21.2130, 72.8560, "Shop 4, Katargam Main Road, Surat - 395004"),
    ("farzi-cafe",       "Farzi Cafe Surat",         21.1920, 72.8360, "1st Floor, Majura Gate, Surat - 395002"),
    ("tao-restaurant",   "Tao Pan Asian",            21.1650, 72.7900, "Citylight Road, Surat - 395007"),
    ("the-bhawan",       "The Bhawan Rooftop",       21.1780, 72.8700, "Ring Road, Udhna, Surat - 395010"),
    ("dumas-seafood",    "Dumas Seafood House",      21.0920, 72.7800, "Dumas Beach Road, Surat - 395007"),
    ("spice-garden",     "Spice Garden",             21.1860, 72.8170, "Bhatar Road, Surat - 395017"),
    ("burma-burma",      "Burma Burma Surat",        21.1925, 72.8365, "2nd Floor, Majura Gate, Surat - 395002"),
    ("the-blue-house",   "The Blue House Bistro",    21.1520, 72.7960, "Pal Gam Road, Pal, Surat - 395009"),
    ("meluha-fern",      "Meluha — The Fern",        21.1565, 72.8102, "The Fern Hotel, Vesu, Surat - 395007"),
    ("lords-resto",      "Lords Resto Bar",          21.1785, 72.8295, "Lords Hotel, Adajan, Surat - 395009"),
    ("gopi-dining",      "Gopi Dining Hall",         21.2070, 72.8550, "Near Surat Station, Varachha, Surat - 395006"),
    ("cafe-the-lane",    "Cafe The Lane",            21.1420, 72.8300, "Pal-Adajan Road, Pal, Surat - 395009"),
]

WELLNESS_OUTLETS = [
    ("aura-wellness-studio", "Aura Wellness Studio",    21.1625, 72.7922, "B-204, Jolly Plaza, Athwalines, Surat - 395001"),
    ("rejuvenate-spa",       "Rejuvenate Spa & Salon",  21.1782, 72.8292, "Adajan Patia, Surat - 395009"),
    ("bliss-beauty",         "Bliss Beauty Lounge",     21.1568, 72.8108, "Vesu Main Road, Surat - 395007"),
    ("glow-skin-studio",     "Glow Skin Studio",        21.1922, 72.8362, "Majura Gate, Surat - 395002"),
    ("the-nail-bar",         "The Nail Bar",            21.1703, 72.8312, "Piplod Main Road, Surat - 395007"),
    ("serenity-spa",         "Serenity Spa",            21.2132, 72.8562, "Katargam Road, Surat - 395004"),
    ("lotus-wellness",       "Lotus Wellness Center",   21.1862, 72.8172, "Bhatar Road, Surat - 395017"),
    ("the-parlour-surat",    "The Parlour Surat",       21.1924, 72.8368, "Majura Gate, Surat - 395002"),
    ("urban-retreat-spa",    "Urban Retreat Spa",       21.1652, 72.7902, "Citylight Road, Surat - 395007"),
    ("glam-studio-surat",    "Glam Studio",             21.1782, 72.8702, "Udhna Darwaja, Surat - 395010"),
    ("prana-wellness",       "Prana Wellness",          21.1522, 72.7962, "Pal, Surat - 395009"),
    ("silk-and-glow",        "Silk & Glow Beauty",      21.2072, 72.8552, "Varachha Road, Surat - 395006"),
    ("the-beauty-edit",      "The Beauty Edit",         21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("o2-spa-surat",         "O2 Spa Surat",            21.1921, 72.8361, "Ring Road, Surat - 395002"),
    ("naturals-salon",       "Naturals Salon Surat",    21.1783, 72.8293, "Adajan Road, Surat - 395009"),
]

FITNESS_OUTLETS = [
    ("zenith-fitness",    "Zenith Fitness Studio",    21.1935, 72.8478, "A-101, Althan Bhatha Road, Althan, Surat - 395017"),
    ("golds-gym-surat",   "Gold's Gym Surat",         21.1783, 72.8293, "VR Mall, Adajan, Surat - 395009"),
    ("cult-fit-surat",    "Cult.fit Surat",           21.1923, 72.8363, "Majura Gate, Surat - 395002"),
    ("yoga-bliss",        "Yoga Bliss Studio",        21.1653, 72.7903, "Citylight Area, Surat - 395007"),
    ("the-yoga-house",    "The Yoga House",           21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("ironparadise-cf",   "Iron Paradise CrossFit",   21.2133, 72.8563, "Katargam, Surat - 395004"),
    ("fitzone-gym",       "FitZone Gym",              21.1863, 72.8173, "Bhatar Road, Surat - 395017"),
    ("breathe-yoga",      "Breathe Yoga Studio",      21.1705, 72.8313, "Piplod, Surat - 395007"),
    ("muscle-factory",    "Muscle Factory Gym",       21.2073, 72.8553, "Varachha Road, Surat - 395006"),
    ("ojas-yoga",         "Ojas Yoga Center",         21.1523, 72.7963, "Pal, Surat - 395009"),
    ("boxfit-studio",     "BoxFit Studio",            21.1783, 72.8703, "Udhna, Surat - 395010"),
    ("flexfit-pilates",   "FlexFit Pilates",          21.1627, 72.7925, "Athwalines, Surat - 395001"),
    ("workout-factory",   "The Workout Factory",      21.2402, 72.7882, "Rander Road, Surat - 395005"),
    ("chakra-yoga",       "Chakra Yoga Studio",       21.1569, 72.8102, "Vesu, Surat - 395007"),
    ("anytime-fitness",   "Anytime Fitness Surat",    21.1921, 72.8361, "Majura Gate, Surat - 395002"),
]

FASHION_OUTLETS = [
    ("wardrobe",          "Wardrobe Fashion Studio",  21.1702, 72.8311, "Shop 8, Piplod Commercial Hub, Surat - 395007"),
    ("kalki-fashion",     "Kalki Fashion Surat",      21.1783, 72.8293, "Adajan, Surat - 395009"),
    ("soch-boutique",     "Soch Boutique",            21.1923, 72.8363, "Majura Gate, Surat - 395002"),
    ("fabindia-surat",    "FabIndia Surat",           21.1653, 72.7903, "Citylight, Surat - 395007"),
    ("w-for-woman",       "W for Woman Surat",        21.2133, 72.8563, "Katargam, Surat - 395004"),
    ("biba-surat",        "Biba Surat",               21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("global-desi",       "Global Desi Surat",        21.1863, 72.8173, "Bhatar Road, Surat - 395017"),
    ("studio-raw-surat",  "Studio Raw",               21.1523, 72.7963, "Pal, Surat - 395009"),
    ("threads-needles",   "Threads & Needles",        21.1783, 72.8703, "Udhna, Surat - 395010"),
    ("the-loom-surat",    "The Loom Surat",           21.1627, 72.7925, "Athwalines, Surat - 395001"),
    ("taneira-surat",     "Taneira Surat",            21.2073, 72.8553, "Varachha Road, Surat - 395006"),
    ("bombay-dress",      "Bombay Dress Company",     21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("aurelia-surat",     "Aurelia Surat",            21.2402, 72.7882, "Rander Road, Surat - 395005"),
    ("label-collective",  "The Label Collective",     21.1923, 72.8363, "Majura Gate, Surat - 395002"),
    ("rani-boutique",     "Rani Boutique",            21.1783, 72.8293, "Adajan, Surat - 395009"),
]

SPORTS_COURT_OUTLETS = [
    ("smashzone-surat",    "SmashZone Sports Arena",   21.1901, 72.8456, "Sports Complex, Althan, Surat - 395017"),
    ("surat-badminton",    "Surat Badminton Club",     21.1783, 72.8293, "Adajan, Surat - 395009"),
    ("vr-squash-center",   "VR Squash Center",         21.1923, 72.8363, "Majura Gate, Surat - 395002"),
    ("champions-arena",    "Champions Arena",           21.2133, 72.8563, "Katargam, Surat - 395004"),
    ("greenace-cricket",   "GreenAce Cricket Academy", 21.1863, 72.8173, "Bhatar Road, Surat - 395017"),
    ("powerplay-courts",   "PowerPlay Courts",          21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("ace-sports-complex", "Ace Sports Complex",        21.1653, 72.7903, "Citylight, Surat - 395007"),
    ("elite-badminton",    "Elite Badminton Club",      21.1523, 72.7963, "Pal, Surat - 395009"),
    ("platinum-sports",    "Platinum Sports Hub",       21.1783, 72.8703, "Udhna, Surat - 395010"),
    ("net-masters",        "Net Masters Court",         21.1627, 72.7925, "Athwalines, Surat - 395001"),
    ("fusion-sports",      "Fusion Sports Arena",       21.2073, 72.8553, "Varachha Road, Surat - 395006"),
    ("pro-turf-surat",     "Pro Turf Surat",            21.2402, 72.7882, "Rander Road, Surat - 395005"),
    ("court-king-surat",   "Court King Surat",          21.1785, 72.8295, "Adajan, Surat - 395009"),
    ("game-on-sports",     "Game On Sports",            21.1925, 72.8365, "Majura Gate, Surat - 395002"),
    ("city-sports-club",   "City Sports Club",          21.1705, 72.8315, "Piplod, Surat - 395007"),
]

SPORTS_VENUE_OUTLETS = [
    ("zona-gameworld",     "Zona GameWorld",            21.1542, 72.8190, "2nd Floor, Vesu Square Mall, Vesu, Surat - 395007"),
    ("smaaash-surat",      "Smaaash Surat",             21.1923, 72.8363, "Majura Gate, Surat - 395002"),
    ("fun-world-surat",    "Fun World Surat",           21.1783, 72.8293, "Adajan, Surat - 395009"),
    ("timezone-surat",     "Timezone Surat",            21.1653, 72.7903, "Citylight Mall, Surat - 395007"),
    ("planet-bowl-surat",  "Planet Bowl Surat",         21.2133, 72.8563, "Katargam, Surat - 395004"),
    ("jump-zone",          "Jump Zone Trampoline Park", 21.1863, 72.8173, "Bhatar Road, Surat - 395017"),
    ("vr-vault-surat",     "VR Vault Surat",            21.1627, 72.7925, "Athwalines, Surat - 395001"),
    ("esports-arena",      "E-Sports Arena Surat",      21.2073, 72.8553, "Varachha Road, Surat - 395006"),
    ("laser-quest",        "Laser Quest Surat",         21.1523, 72.7963, "Pal, Surat - 395009"),
    ("indoor-climbing",    "Indoor Rock Climbing Surat",21.1783, 72.8703, "Udhna, Surat - 395010"),
    ("escape-room-surat",  "Escape Room Surat",         21.2402, 72.7882, "Rander Road, Surat - 395005"),
    ("gokart-track",       "Go-Kart Track Surat",       21.1903, 72.8458, "Althan, Surat - 395017"),
    ("axe-throwing",       "Axe Throwing Zone",         21.1569, 72.8109, "Vesu, Surat - 395007"),
    ("minigolf-surat",     "MiniGolf Surat",            21.1785, 72.8295, "Adajan, Surat - 395009"),
    ("bowling-avenue",     "Bowling Avenue Surat",      21.1925, 72.8365, "Majura Gate, Surat - 395002"),
]

# Ordered map: outlet_type → list of (id, name, lat, lon, addr)
OUTLETS_BY_TYPE = {
    "dining":        DINING_OUTLETS,
    "wellness":      WELLNESS_OUTLETS,
    "fitness":       FITNESS_OUTLETS,
    "fashion":       FASHION_OUTLETS,
    "sports_court":  SPORTS_COURT_OUTLETS,
    "sports_venue":  SPORTS_VENUE_OUTLETS,
}

# ── Courts per sports_court outlet ────────────────────────────────────────────
# (court_name, sport_type, price_per_slot, consumer_fee)

COURT_CONFIGS = {
    "smashzone-surat":    [("Badminton Court 1","Badminton",400,20),("Badminton Court 2","Badminton",400,20),("Squash Court A","Squash",350,18),("TT Table 1","Table Tennis",200,10)],
    "surat-badminton":    [("Court A","Badminton",380,20),("Court B","Badminton",380,20),("Court C","Badminton",380,20)],
    "vr-squash-center":   [("Squash Court 1","Squash",350,18),("Squash Court 2","Squash",350,18),("Glass Court","Squash",450,22)],
    "champions-arena":    [("Football Arena A","Football",1500,20),("Football Arena B","Football",1500,20)],
    "greenace-cricket":   [("Cricket Net 1","Cricket",600,20),("Cricket Net 2","Cricket",600,20),("Cricket Net 3","Cricket",600,20)],
    "powerplay-courts":   [("Badminton Court 1","Badminton",400,20),("Badminton Court 2","Badminton",400,20),("Squash Court","Squash",350,18)],
    "ace-sports-complex": [("Tennis Court A","Other",800,25),("Tennis Court B","Other",800,25),("Badminton Court","Badminton",400,20)],
    "elite-badminton":    [("Court 1","Badminton",420,20),("Court 2","Badminton",420,20),("Court 3","Badminton",420,20),("Court 4","Badminton",420,20)],
    "platinum-sports":    [("Badminton Court","Badminton",400,20),("TT Table","Table Tennis",200,10),("Squash Court","Squash",350,18)],
    "net-masters":        [("Badminton Court 1","Badminton",380,20),("Badminton Court 2","Badminton",380,20)],
    "fusion-sports":      [("Football Court","Football",1500,20),("Badminton Court 1","Badminton",400,20),("Badminton Court 2","Badminton",400,20)],
    "pro-turf-surat":     [("Turf A (Football)","Football",1500,20),("Turf B (Football)","Football",1500,20),("Cricket Net","Cricket",600,20)],
    "court-king-surat":   [("Badminton Court 1","Badminton",400,20),("Badminton Court 2","Badminton",400,20),("TT Table 1","Table Tennis",200,10)],
    "game-on-sports":     [("Badminton Court","Badminton",400,20),("Squash Court","Squash",350,18),("Football Arena","Football",1500,20)],
    "city-sports-club":   [("Tennis Court","Other",800,25),("Badminton Court","Badminton",400,20),("Squash Court","Squash",350,18)],
}

# ── Catalogue templates per type ──────────────────────────────────────────────

WELLNESS_CATALOGUE = [
    ("Facials",    "Signature Facial (60 min)",         1200),
    ("Facials",    "Hydrafacial",                        1800),
    ("Facials",    "Anti-Aging Facial (75 min)",         2200),
    ("Massage",    "Deep Tissue Massage (60 min)",       1400),
    ("Massage",    "Swedish Massage (60 min)",            1200),
    ("Massage",    "Hot Stone Therapy (75 min)",          1800),
    ("Nails",      "Gel Nail Extension",                   800),
    ("Nails",      "Nail Art Session",                     600),
    ("Hair",       "Hair Spa Treatment",                   800),
    ("Hair",       "Keratin Treatment",                   3500),
    ("Body Care",  "Body Polishing",                      2500),
    ("Body Care",  "Pre-Bridal Package (3 sessions)",    8000),
    ("Waxing",     "Full Body Wax",                       1200),
    ("Threading",  "Eyebrow Threading",                     80),
]

FITNESS_CATALOGUE = [
    ("Yoga",       "Morning Vinyasa (60 min)",            600),
    ("Yoga",       "Hatha Yoga (75 min)",                 700),
    ("Yoga",       "Power Yoga (60 min)",                 650),
    ("Pilates",    "Mat Pilates (60 min)",                750),
    ("Pilates",    "Reformer Pilates (45 min)",           900),
    ("CrossFit",   "CrossFit Basics (60 min)",            800),
    ("CrossFit",   "HIIT Circuit (45 min)",               700),
    ("Meditation", "Guided Meditation (30 min)",           400),
    ("Meditation", "Breathwork Session (45 min)",          500),
    ("Classes",    "Zumba (60 min)",                      550),
    ("Classes",    "Boxing Fundamentals (60 min)",         700),
    ("Classes",    "Functional Training (45 min)",         650),
]

FASHION_CATALOGUE = [
    ("Styling",    "Personal Styling Session (1 hr)",    800),
    ("Styling",    "Wardrobe Audit (Full)",              1500),
    ("Styling",    "Virtual Lookbook Creation",           600),
    ("Alterations","Hem Alteration",                      250),
    ("Alterations","Trouser Taper",                       350),
    ("Alterations","Sleeve Shortening",                   200),
    ("Alterations","Blouse Fitting",                      400),
    ("Custom",     "Custom Kurti Stitching",              800),
    ("Custom",     "Lehenga Work (Per Piece)",           3000),
]

SPORTS_VENUE_CATALOGUE = [
    ("Arcade",      "Arcade Token Pack (50 tokens)",     200),
    ("Arcade",      "Unlimited Arcade (1 hr)",            350),
    ("Bowling",     "Bowling — 1 Game (1 Person)",        250),
    ("Bowling",     "Bowling — Family Pack (4 games)",    800),
    ("VR Zone",     "VR Experience (15 min)",             300),
    ("VR Zone",     "VR Premium (30 min)",                500),
    ("Go-Kart",     "Go-Kart — 5 min Session",           350),
    ("Go-Kart",     "Go-Kart — Race Pack (3 rounds)",    900),
    ("Laser Tag",   "Laser Tag (30 min)",                 400),
    ("Trampoline",  "Jump Session (30 min)",              350),
    ("Escape Room", "Escape Room (60 min, 2-6 pax)",     600),
]

# ── Media pools ───────────────────────────────────────────────────────────────

CDN_VIDEOS = [
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/abc-juice/a6e5455d-5f5c-4f0e-be7f-daaf16f0011e/raw.mp4",
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/masala-chai/e11c1259-b549-4b45-9075-ca613c0f9022/raw.mp4",
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/butter-pancake/d2c817a1-d03f-4f88-a3ef-755300661a6a/raw.mp4",
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/hot-chocolate/21ca0149-2ea4-4b24-8874-40babd40775c/raw.mp4",
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/iced-bombon/9da68bd8-d294-4301-a974-145901444f89/raw.mp4",
    "https://cdn.dinematters.com/restaurants/unvind/menu_product/nutella-croissant/06353dc3-1d97-43b2-b184-2252b13e8d7e/raw.mp4",
]

LOGOS_BY_TYPE = {
    "dining": [
        "https://images.unsplash.com/photo-1445116572660-236099ec97a0?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1470337458703-46ad1756a187?w=200&h=200&fit=crop",
    ],
    "wellness": [
        "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1562322140-8baeececf3df?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=200&h=200&fit=crop",
    ],
    "fitness": [
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1576678927484-cc907957088c?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1593079831268-3381b0db4a77?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=200&h=200&fit=crop",
    ],
    "fashion": [
        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1445205170230-053b83016050?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1558171813-0c2bf5d6e24b?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=200&h=200&fit=crop",
    ],
    "sports_court": [
        "https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1559827291-72ee739d0d9a?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1616279969965-c4f6ab2a0c3b?w=200&h=200&fit=crop",
    ],
    "sports_venue": [
        "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1520568961470-7b8f7fcd1b41?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=200&h=200&fit=crop",
        "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=200&h=200&fit=crop",
    ],
}

# 15 thumbnail URLs + description templates per outlet type (index cycles across outlets×5)
CHILLS_DATA = {
    "dining": {
        "thumbs": [
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600",
            "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600",
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600",
            "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=600",
            "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=600",
            "https://images.unsplash.com/photo-1498804103079-a6351b050096?w=600",
            "https://images.unsplash.com/photo-1481833761820-0509d3217039?w=600",
            "https://images.unsplash.com/photo-1464349095431-e9a21285b5f3?w=600",
            "https://images.unsplash.com/photo-1524484485831-a92ffc0de03f?w=600",
            "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=600",
            "https://images.unsplash.com/photo-1543007630-9710e4a00a20?w=600",
            "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600",
            "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600",
            "https://images.unsplash.com/photo-1559329007-40df8a9345d8?w=600",
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600",
        ],
        "descs": [
            "{name}'s signature filter coffee is the most underrated thing in Surat ☕ | #SuratCafe #FlamezoSurat",
            "Hands down the best plating in Surat right now at {name} — every dish is art 🍽️ | #FoodArtSurat",
            "Date night done right at {name} — ambiance, food, vibes all on point 🌟 | #DateNightSurat",
            "Weekend brunch at {name} hit different today — fresh juices, incredible energy ☀️ | #BrunchSurat",
            "The live cooking station at {name} is absolutely fire 🔥 Sunday buffet goals | #BuffetSurat",
            "{name} just dropped a new seasonal menu and every dish is a win 🌿 | #NewMenuSurat",
            "Rooftop dinner at {name} — city lights, chill breeze, perfect evening 🌙 | #RooftopSurat",
            "{name}'s signature cocktails are next level — tried 3, regret nothing 🍹 | #CocktailsSurat",
            "The mezze platter at {name} could feed a small village and it is WORTH IT 🫙 | #SharingIsEating",
            "Tried the chef's tasting menu at {name} — 7 courses of pure perfection 👨‍🍳 | #ChefSpecial",
            "{name}'s dessert menu is art — the gulab jamun cheesecake is unreal 🍮 | #DessertSurat",
            "When the DJ set and the food both slap at {name} — this is the vibe ✌️ | #NightOutSurat",
            "The butter naan at {name} is dangerously good — went for one, ate four 🫓 | #NaanLife",
            "Family Sunday lunch at {name} — big table, bigger portions, everyone happy 👨‍👩‍👧‍👦 | #FamilyDining",
            "Power lunch at {name} — salads were fresh, coffee perfect ⚡ | #WorkLunchSurat",
        ],
        "metrics": [(142,38,2100),(89,22,1450),(211,67,3800),(76,19,980),(134,44,2200),
                    (160,52,2700),(98,31,1600),(175,58,3000),(83,24,1300),(145,49,2400),
                    (119,36,1900),(267,88,5100),(92,28,1500),(178,59,2900),(103,34,1700)],
    },
    "wellness": {
        "thumbs": [
            "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=600",
            "https://images.unsplash.com/photo-1507652313519-d4e9174996dd?w=600",
            "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=600",
            "https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=600",
            "https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=600",
            "https://images.unsplash.com/photo-1562322140-8baeececf3df?w=600",
            "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=600",
            "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=600",
            "https://images.unsplash.com/photo-1554807832-f03e0534d64a?w=600",
            "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=600",
            "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=600",
            "https://images.unsplash.com/photo-1507652313519-d4e9174996dd?w=600",
            "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=600",
            "https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=600",
            "https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=600",
        ],
        "descs": [
            "60 min deep tissue at {name} and I walked out a completely new person ✨ | #WellnessSurat",
            "Hydrafacial at {name} — one session and people are asking what filter I use 😱 | #Hydrafacial",
            "The steam room at {name} after a long week is the only reset I need 🌿 | #SpaDay",
            "Nail art at {name} — they turned my nails into tiny paintings 💅 | #NailArtSurat",
            "Pre-bridal package at {name} is worth every rupee — 3 sessions, absolute glow ✨ | #BridalGlow",
            "Keratin at {name} and I finally have the smooth hair I always dreamed of 💇 | #HairGoals",
            "The massage therapist at {name} found knots I didn't even know I had 🙏 | #DeepTissue",
            "{name}'s full body wax in 30 minutes flat — efficient AND thorough ⚡ | #Salon",
            "Hot stone therapy at {name} — 75 minutes of pure heaven 🪨 | #HotStone",
            "Body polishing at {name} — skin is literally glowing, no filter needed 🌟 | #BodyCare",
            "Threading at {name} is surgical precision — they understand face shapes 🎯 | #BrowGoals",
            "Swedish massage + hair spa combo at {name} = the ultimate self-care Sunday 💆 | #SelfCare",
            "Walked into {name} stressed, walked out serene — this is what healing looks like 🕊️ | #Wellness",
            "{name}'s skin treatment actually addressed my concerns — not just a generic facial | #SkincareIndia",
            "Gel extensions at {name} look better than my natural nails ever have 💅 | #GelNails",
        ],
        "metrics": [(156,43,2600),(201,77,3900),(88,32,1500),(174,61,3200),(113,39,1800),
                    (145,48,2400),(99,33,1600),(167,55,2800),(82,27,1300),(190,66,3400),
                    (122,41,2000),(78,24,1200),(203,71,4200),(94,30,1550),(138,46,2300)],
    },
    "fitness": {
        "thumbs": [
            "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=600",
            "https://images.unsplash.com/photo-1593079831268-3381b0db4a77?w=600",
            "https://images.unsplash.com/photo-1576678927484-cc907957088c?w=600",
            "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=600",
            "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=600",
            "https://images.unsplash.com/photo-1593079831268-3381b0db4a77?w=600",
            "https://images.unsplash.com/photo-1576678927484-cc907957088c?w=600",
            "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=600",
            "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=600",
        ],
        "descs": [
            "6 AM yoga at {name} and the energy is electric 🧘 | #YogaSurat #MorningVibes",
            "Reformer Pilates at {name} — 45 min that changed how my body moves 💫 | #PilatesSurat",
            "HIIT at {name} done, endorphins through the roof 🔥 | #HIITSurat #FitnessSurat",
            "Guided meditation at {name} — 30 min of actual silence in the city 🌿 | #MeditationSurat",
            "Power yoga at {name} — 60 min, full sweat, total zen 💪 | #PowerYogaSurat",
            "CrossFit at {name} taught me I have muscles I didn't know existed 😅 | #CrossFitSurat",
            "The coaches at {name} care about form, not just filling slots 🎯 | #FitnessCulture",
            "Zumba at {name} is the workout you actually want to show up for 💃 | #ZumbaSurat",
            "Breathwork at {name} cleared my head more than any meditation app 🌬️ | #Breathwork",
            "Boxing fundamentals at {name} — stress relief + cardio all in 60 min 🥊 | #BoxingSurat",
            "Functional training at {name} — the trainer pushed us right to the edge 💪 | #FunctionalFit",
            "Mat pilates at {name} looks simple but it's a full core workout — humbled 😅 | #Pilates",
            "Morning hatha at {name} sets the tone for the entire day 🌅 | #HathaSurat",
            "The studio at {name} is clean, airy, peaceful — the environment itself heals 🕊️ | #YogaStudio",
            "Tried one class at {name}, now it's in my weekly schedule permanently 📅 | #FitnessGoals",
        ],
        "metrics": [(148,52,2500),(97,35,1650),(183,64,3200),(76,29,1100),(121,43,2000),
                    (165,57,2800),(88,31,1450),(142,49,2350),(103,36,1700),(174,60,3000),
                    (91,32,1500),(156,53,2650),(118,40,1950),(82,27,1300),(197,68,3600)],
    },
    "fashion": {
        "thumbs": [
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600",
            "https://images.unsplash.com/photo-1445205170230-053b83016050?w=600",
            "https://images.unsplash.com/photo-1558171813-0c2bf5d6e24b?w=600",
            "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600",
            "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600",
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600",
            "https://images.unsplash.com/photo-1445205170230-053b83016050?w=600",
            "https://images.unsplash.com/photo-1558171813-0c2bf5d6e24b?w=600",
            "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600",
            "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600",
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600",
            "https://images.unsplash.com/photo-1445205170230-053b83016050?w=600",
            "https://images.unsplash.com/photo-1558171813-0c2bf5d6e24b?w=600",
            "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600",
            "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600",
        ],
        "descs": [
            "Styling session at {name} and they rebuilt my entire wardrobe from scratch 👔 | #PersonalStyle",
            "The ethnic wear collection at {name} is breathtaking 🤌 Every piece tells a story | #EthnicFashion",
            "Blazer tailored at {name} — perfect fit in 3 days flat ✂️ | #TailorsOfSurat",
            "New season at {name} just dropped and pastels are absolutely having a moment 🌸 | #FashionSurat",
            "Wardrobe audit at {name} was brutal but necessary — zero dead weight left 🙏 | #StyleEdit",
            "Custom kurti from {name} fits like a dream 🌺 Completely worth the wait | #CustomFashion",
            "The stylist at {name} listened to my lifestyle first — rare to find 💡 | #StyleConsult",
            "Sales at {name} are some of the best deals in Surat right now 🛍️ | #FashionDeals",
            "Bridal lehenga from {name} — the embroidery is literally artisanal ✨ | #BridalFashion",
            "{name}'s virtual lookbook lets you book an appt directly from the look 📱 | #FashionTech",
            "Alteration at {name} — 2 days, ₹200, perfect fit. This is how it should be 🎯 | #Surat",
            "The collection at {name} is actually curated, not just trend-dumping 🎨 | #CuratedStyle",
            "Finally a boutique in Surat that stocks sizes for real people 🙌 | #InclusiveFashion",
            "Kanjeevaram collection at {name} — you HAVE to see it in person 🌟 | #Sarees",
            "Block-printed kurtas from {name} — sustainable, handcrafted, beautiful 🌿 | #HandcraftedFashion",
        ],
        "metrics": [(98,35,1600),(143,47,2300),(77,22,1200),(166,55,2800),(91,29,1400),
                    (118,40,1950),(134,44,2200),(82,26,1300),(157,53,2700),(103,34,1700),
                    (88,30,1450),(145,48,2400),(72,20,1100),(179,61,3100),(113,37,1850)],
    },
    "sports_court": {
        "thumbs": [
            "https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1559827291-72ee739d0d9a?w=600",
            "https://images.unsplash.com/photo-1616279969965-c4f6ab2a0c3b?w=600",
            "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=600",
            "https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1559827291-72ee739d0d9a?w=600",
            "https://images.unsplash.com/photo-1616279969965-c4f6ab2a0c3b?w=600",
            "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=600",
            "https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=600",
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600",
            "https://images.unsplash.com/photo-1559827291-72ee739d0d9a?w=600",
            "https://images.unsplash.com/photo-1616279969965-c4f6ab2a0c3b?w=600",
            "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=600",
        ],
        "descs": [
            "Finally a proper court in Surat! {name}'s facilities are top quality 🏸 | #BadmintonSurat",
            "6 AM slot at {name} and it's already packed — the fitness culture is real 🌅 | #SportsSurat",
            "Professional flooring, great lighting at {name} — proper international standard 💪 | #ProCourts",
            "Post-match protein shake at {name}, then straight to work — this is the life 🏃 | #FitLife",
            "First squash lesson at {name} and I'm officially hooked 🎯 | #SquashSurat",
            "TT tables at {name} are competition-grade — serious players will appreciate this 🏓 | #TableTennis",
            "{name} has brought world-class courts to our neighbourhood 🌍 | #WorldClassSurat",
            "2 hours of badminton at {name}, completely drenched, completely happy 😅 | #WeekendWarrior",
            "Futsal at {name} with the boys — nothing beats this for stress relief ⚽ | #FutsalSurat",
            "Cricket nets at {name} — consistent bounce, good pace, perfect for practice 🏏 | #Cricket",
            "The glass squash court at {name} is spectacular from every angle 🎯 | #SquashLife",
            "Tennis session at {name} was exactly what I needed this Sunday morning 🎾 | #TennisSurat",
            "Booking at {name} via Flamezo — 3 taps and done, earned coins too ✅ | #EasyBooking",
            "Earning FlameZO coins at {name} for court bookings is actually genius 🪙 | #FlamezoCoins",
            "6 AM crew at {name} is the most disciplined group I know 🌄 | #MorningSports",
        ],
        "metrics": [(122,41,2000),(89,27,1500),(154,51,2700),(67,18,980),(103,34,1700),
                    (138,46,2300),(91,29,1450),(175,60,3000),(82,25,1300),(116,38,1900),
                    (143,48,2400),(78,23,1200),(167,55,2800),(94,31,1550),(128,43,2100)],
    },
    "sports_venue": {
        "thumbs": [
            "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=600",
            "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600",
            "https://images.unsplash.com/photo-1520568961470-7b8f7fcd1b41?w=600",
            "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=600",
            "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=600",
            "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=600",
            "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600",
            "https://images.unsplash.com/photo-1520568961470-7b8f7fcd1b41?w=600",
            "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=600",
            "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=600",
            "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=600",
            "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600",
            "https://images.unsplash.com/photo-1520568961470-7b8f7fcd1b41?w=600",
            "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=600",
            "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=600",
        ],
        "descs": [
            "{name} has 3 floors of pure entertainment — 4 hours in and still missing things 🎮 | #GamingSurat",
            "VR at {name} — felt like I was literally inside another dimension 😱 | #VRSurat",
            "Family bowling night at {name} — everyone competing, no one keeping score 🎳 | #BowlingSurat",
            "Go-kart race at {name} and I discovered my inner F1 driver 🏎️ | #GoKartSurat",
            "Arcade tokens at {name} — 3 hours on one machine, zero regrets 🕹️ | #ArcadeSurat",
            "Laser tag at {name} is elite — 30 min of the best cardio disguised as fun 🔴 | #LaserTag",
            "Escape room at {name} — we failed but it was the most fun failure ever 😅 | #EscapeRoom",
            "Trampoline park at {name} is for everyone — adults included, trust me 🤸 | #JumpZone",
            "VR racing at {name} in a full motion rig is a completely different level 🏎️ | #VRRacing",
            "Axe throwing at {name} is weirdly therapeutic for work stress 🪓 | #AxeThrowing",
            "e-Sports tournament at {name} — competitive gaming as spectator sport 🎮 | #eSports",
            "Mini golf at {name} and adults got way more competitive than the kids ⛳ | #MiniGolf",
            "Birthday party at {name} = instant 10/10 from everyone, kids and adults 🎂 | #BirthdaySurat",
            "Indoor rock climbing at {name} — arms dead, spirit alive 💪 | #ClimbingSurat",
            "Combo deal at {name} (bowling + arcade + VR) is the best value in Surat 💰 | #ValueFun",
        ],
        "metrics": [(219,78,4100),(174,61,3000),(132,48,2200),(156,55,2700),(88,31,1450),
                    (143,49,2400),(97,33,1600),(167,57,2850),(113,38,1850),(145,50,2500),
                    (78,24,1200),(189,65,3300),(124,42,2050),(156,53,2650),(103,35,1700)],
    },
}

# ── Low-level helpers ──────────────────────────────────────────────────────────

def _uid(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _upsert_restaurant(rest_id, restaurant_name, outlet_type="dining",
                        latitude=SURAT_LAT, longitude=SURAT_LON,
                        city="Surat", address="Surat, Gujarat"):
    defaults = {
        "restaurant_name": restaurant_name,
        "outlet_type": outlet_type,
        "is_active": 1,
        "plan_type": "GOLD",
        "coins_balance": 5000.0,
        "auto_recharge_enabled": 0,
        "platform_fee_percent": 1.5,
        "timezone": "Asia/Kolkata",
        "mandate_status": "inactive",
        "city": city,
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "enable_loyalty": 1,
    }
    if frappe.db.exists("Restaurant", rest_id):
        frappe.db.set_value("Restaurant", rest_id, defaults)
    else:
        frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_id": rest_id,
            **defaults,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_loyalty_config(restaurant):
    if frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": restaurant}, "name"):
        return
    frappe.get_doc({
        "doctype": "Restaurant Loyalty Config",
        "restaurant": restaurant,
        "program_name": "Flamezo Rewards",
        "is_active": 1,
        "earn_type": "Percentage of Bill",
        "earn_percentage": 7.0,
        "earn_flat_coins": 50,
        "min_order_to_earn": 0,
        "max_coins_per_order": 700,
        "points_per_inr": 0.07,
        "loyalty_expiry_months": 6,
        "coin_value_in_inr": 1.0,
        "earn_on_status": "Completed",
        "min_redemption_threshold": 100,
        "coins_per_unique_open": 40,
        "max_opens_rewarded_per_share": 10,
        "new_user_welcome_reward_coins": 75,
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_restaurant_config(restaurant):
    if frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "name"):
        return
    frappe.get_doc({
        "doctype": "Restaurant Config",
        "restaurant": restaurant,
        "menu_theme_background_enabled": 0,
        "verify_my_user": 0,
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def _get_or_create_customer(phone, name=""):
    from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone
    normalized = normalize_phone(phone)
    existing = frappe.db.get_value("Customer", {"phone": normalized}, "name")
    if existing:
        return frappe.get_doc("Customer", existing)
    doc = frappe.get_doc({
        "doctype": "Customer",
        "phone": normalized,
        "customer_name": name or f"Customer {normalized}",
        "customer_group": "Individual",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _ensure_court(restaurant, court_name, sport_type, price=400, consumer_fee=20):
    existing = frappe.db.get_value("Court",
        {"restaurant": restaurant, "court_name": court_name}, "name")
    if existing:
        return frappe.get_doc("Court", existing)
    doc = frappe.get_doc({
        "doctype": "Court",
        "restaurant": restaurant,
        "court_name": court_name,
        "sport_type": sport_type,
        "is_active": 1,
        "slot_duration_minutes": 60,
        "price_per_slot": price,
        "consumer_fee": consumer_fee,
        "opening_time": "06:00:00",
        "closing_time": "22:00:00",
        "available_days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "advance_booking_days": 7,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _ensure_catalogue_category(restaurant, category_name):
    existing = frappe.db.get_value("Catalogue Category",
        {"restaurant": restaurant, "category_name": category_name}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Catalogue Category",
        "restaurant": restaurant,
        "category_name": category_name,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _ensure_catalogue_item(restaurant, cat_name, item_name, price):
    cat_id = _ensure_catalogue_category(restaurant, cat_name)
    if frappe.db.get_value("Catalogue Item",
            {"restaurant": restaurant, "item_name": item_name}, "name"):
        return
    frappe.get_doc({
        "doctype": "Catalogue Item",
        "restaurant": restaurant,
        "category": cat_id,
        "item_name": item_name,
        "price": price,
        "is_active": 1,
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def _loyalty_entry(customer_name, restaurant, coins, txn_type="Earn",
                    reason="Order", is_settled=1, days_until_expiry=180, days_ago=0):
    posting = add_days(TODAY, -days_ago)
    expiry = add_days(TODAY, days_until_expiry) if txn_type == "Earn" else None
    frappe.get_doc({
        "doctype": "Restaurant Loyalty Entry",
        "customer": customer_name,
        "restaurant": restaurant,
        "coins": coins,
        "transaction_type": txn_type,
        "reason": reason,
        "posting_date": posting,
        "expiry_date": expiry,
        "is_settled": is_settled,
    }).insert(ignore_permissions=True)


def _notification(phone, notif_type, title, body, days_ago=0):
    doc = frappe.get_doc({
        "doctype": "Flamezo Notification",
        "customer_phone": phone,
        "notification_type": notif_type,
        "title": title,
        "body": body,
        "is_read": 0,
        "is_actioned": 0,
    })
    doc.insert(ignore_permissions=True)
    if days_ago > 0:
        frappe.db.set_value("Flamezo Notification", doc.name,
                             "creation", add_days(frappe.utils.now_datetime(), -days_ago))


def _seed_insert(data):
    doc = frappe.get_doc(data)
    doc.flags.ignore_validate = True
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _table_booking(restaurant, phone, date, time_slot, diners=2, status="confirmed"):
    _seed_insert({
        "doctype": "Table Booking",
        "restaurant": restaurant,
        "customer_phone": phone,
        "customer_name": _user_name(phone),
        "date": date,
        "time_slot": time_slot,
        "number_of_diners": diners,
        "status": status,
    })


def _banquet_booking(restaurant, phone, date, time_slot, guests=60,
                      event_type="Birthday", status="confirmed"):
    _seed_insert({
        "doctype": "Banquet Booking",
        "restaurant": restaurant,
        "customer_phone": phone,
        "customer_name": _user_name(phone),
        "date": date,
        "time_slot": time_slot,
        "number_of_guests": guests,
        "event_type": event_type,
        "status": status,
    })


def _appointment(restaurant, phone, date, catalogue_item_name, sub_item_name,
                  price, outlet_type, time="11:00:00", status="Confirmed"):
    _seed_insert({
        "doctype": "Service Appointment",
        "restaurant": restaurant,
        "outlet_type": outlet_type,
        "customer_phone": phone,
        "customer_name": _user_name(phone),
        "appointment_date": date,
        "appointment_time": time,
        "duration_minutes": 60,
        "catalogue_item_name": catalogue_item_name,
        "sub_item_name": sub_item_name,
        "sub_item_price": price,
        "status": status,
    })


def _court_booking(restaurant, court_doc, phone, date, start, end, status="Confirmed"):
    _seed_insert({
        "doctype": "Court Booking",
        "restaurant": restaurant,
        "court": court_doc.name,
        "court_name": court_doc.court_name,
        "sport_type": court_doc.sport_type,
        "booking_date": date,
        "start_time": start,
        "end_time": end,
        "customer_phone": phone,
        "customer_name": _user_name(phone),
        "slot_price": flt(court_doc.price_per_slot),
        "consumer_fee": flt(court_doc.consumer_fee),
        "payment_status": "Paid",
        "status": status,
    })


def _menu_product(restaurant, name, price, category, is_veg=1, description=""):
    if frappe.db.get_value("Menu Product",
            {"restaurant": restaurant, "product_name": name}, "name"):
        return
    frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": restaurant,
        "product_id": _uid(),
        "product_name": name,
        "price": price,
        "original_price": price,
        "is_active": 1,
        "is_vegetarian": is_veg,
        "category": category,
        "description": description,
    }).insert(ignore_permissions=True)


_USER_MAP = {u[0]: u[1] for u in TEST_USERS}

def _user_name(phone):
    return _USER_MAP.get(phone, f"Customer {phone}")


def _generate_loyalty(cust_name, phone, target_coins, outlet_ids):
    """Seed loyalty history targeting approximately target_coins settled lifetime."""
    frappe.db.delete("Restaurant Loyalty Entry", {"customer": cust_name})
    num = max(10, min(25, target_coins // 400))
    per_entry = max(50, target_coins // num)
    phone_var = sum(int(d) for d in phone if d.isdigit())
    pool = outlet_ids[:min(8, len(outlet_ids))]
    for i in range(num - 2):
        oid = pool[i % len(pool)]
        coins = max(50, per_entry + ((phone_var + i * 37) % 200) - 100)
        days_ago = max(1, 180 - i * 7)
        exp = max(30, 180 - i * 5)
        _loyalty_entry(cust_name, oid, coins, "Earn", "Order", 1, exp, days_ago)
    # Welcome bonus
    _loyalty_entry(cust_name, pool[0], 75, "Earn", "Welcome Bonus", 1, 180, 175)
    # Expiring soon
    _loyalty_entry(cust_name, pool[1 % len(pool)], 100, "Earn", "Order", 1, 8, 22)
    # Unsettled pending
    _loyalty_entry(cust_name, pool[0], 150, "Earn", "Order", 0, 180, 0)
    # Redeem
    if target_coins > 300:
        _loyalty_entry(cust_name, pool[0], min(300, target_coins // 10),
                        "Redeem", "Redemption", 1, 0, 30)
    frappe.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run():
    frappe.set_user("Administrator")
    print("\n── Flamezo Sample Data Seeder (Surat) — 90 Outlets ────────────")

    # ── 1. Upsert all 90 outlets ──────────────────────────────────────────────
    print("1/10 Upserting 90 outlets (15 per industry)...")

    # Clean up old partial-run artefacts
    for old_id in ["smashzone-ahmedabad"]:
        if frappe.db.exists("Restaurant", old_id):
            frappe.db.sql("UPDATE `tabCourt` SET restaurant=%s WHERE restaurant=%s",
                          ["smashzone-surat", old_id])
            frappe.db.sql("UPDATE `tabCourt Booking` SET restaurant=%s WHERE restaurant=%s",
                          ["smashzone-surat", old_id])
            frappe.db.delete("Restaurant Loyalty Config", {"restaurant": old_id})
            frappe.db.delete("Restaurant Config", {"restaurant": old_id})
            frappe.db.delete("Restaurant", old_id)
    frappe.db.commit()

    for outlet_type, outlets in OUTLETS_BY_TYPE.items():
        for rest_id, rest_name, lat, lon, addr in outlets:
            _upsert_restaurant(rest_id, rest_name, outlet_type=outlet_type,
                                latitude=lat, longitude=lon, address=addr)
            _ensure_loyalty_config(rest_id)
            _ensure_restaurant_config(rest_id)

    total = sum(len(v) for v in OUTLETS_BY_TYPE.values())
    print(f"     {total} outlets ready across 6 industry types")

    # ── 2. Courts (all 15 sports_court outlets) ───────────────────────────────
    print("2/10 Creating courts for all 15 sports_court outlets...")
    court_count = 0
    all_courts = {}  # rest_id → list of court docs
    for rest_id, _, _, _, _ in SPORTS_COURT_OUTLETS:
        configs = COURT_CONFIGS.get(rest_id, [("Badminton Court 1","Badminton",400,20)])
        all_courts[rest_id] = []
        for court_name, sport, price, fee in configs:
            doc = _ensure_court(rest_id, court_name, sport, price, fee)
            all_courts[rest_id].append(doc)
            court_count += 1
    print(f"     {court_count} courts across 15 sports_court outlets")

    # ── 3. Catalogue items ────────────────────────────────────────────────────
    print("3/10 Creating catalogue items (wellness/fitness/fashion/sports_venue)...")
    item_count = 0
    catalogue_map = {
        "wellness":     WELLNESS_CATALOGUE,
        "fitness":      FITNESS_CATALOGUE,
        "fashion":      FASHION_CATALOGUE,
        "sports_venue": SPORTS_VENUE_CATALOGUE,
    }
    for outlet_type, template in catalogue_map.items():
        for rest_id, _, _, _, _ in OUTLETS_BY_TYPE[outlet_type]:
            for cat, item, price in template:
                _ensure_catalogue_item(rest_id, cat, item, price)
                item_count += 1
    print(f"     {item_count} catalogue items created")

    # ── 4. Customers ──────────────────────────────────────────────────────────
    print("4/10 Ensuring 6 test customers...")
    customers = {}
    for phone, name, _ in TEST_USERS:
        cust = _get_or_create_customer(phone, name)
        customers[phone] = cust
        print(f"     {name} ({phone})")

    # ── 5. Bookings ───────────────────────────────────────────────────────────
    print("5/10 Creating bookings for all users...")

    all_phones = [u[0] for u in TEST_USERS]
    for phone in all_phones:
        frappe.db.sql("DELETE FROM `tabTable Booking` WHERE customer_phone=%s AND `date`>=%s", [phone, TODAY])
        frappe.db.sql("DELETE FROM `tabService Appointment` WHERE customer_phone=%s AND appointment_date>=%s", [phone, TODAY])
        frappe.db.sql("DELETE FROM `tabBanquet Booking` WHERE customer_phone=%s AND `date`>=%s", [phone, TODAY])
        frappe.db.sql("DELETE FROM `tabCourt Booking` WHERE customer_phone=%s AND booking_date>=%s", [phone, TODAY])
    frappe.db.commit()

    # Primary user — rich set across all types
    p = PRIMARY_PHONE
    _table_booking("araku",            p, add_days(TODAY, 2),  "7:30 PM – 10:00 PM", 3, "confirmed")
    _table_booking("the-gallery-cafe", p, add_days(TODAY, 5),  "1:00 PM – 3:00 PM",  2, "pending")
    _table_booking("unvind",           p, add_days(TODAY, 9),  "8:00 PM – 11:00 PM", 4, "confirmed")
    _table_booking("pind-balluchi",    p, add_days(TODAY, 15), "7:00 PM – 9:30 PM",  2, "confirmed")
    _table_booking("farzi-cafe",       p, add_days(TODAY, 22), "8:30 PM – 11:00 PM", 6, "pending")
    _banquet_booking("araku",          p, add_days(TODAY, 18), "6:00 PM – 11:00 PM", 75, "Anniversary", "confirmed")
    _appointment("aura-wellness-studio", p, add_days(TODAY, 3),  "Deep Tissue Massage (60 min)", "Standard Session", 1400, "wellness", "11:00:00", "Confirmed")
    _appointment("aura-wellness-studio", p, add_days(TODAY, 11), "Hydrafacial", "Express (45 min)", 1800, "wellness", "14:00:00", "Pending")
    _appointment("wardrobe",           p, add_days(TODAY, 7),  "Personal Styling Session (1 hr)", "Morning Slot", 800, "fashion", "12:00:00", "Confirmed")
    _appointment("zenith-fitness",     p, add_days(TODAY, 4),  "Morning Vinyasa (60 min)", "Early Slot", 600, "fitness", "07:00:00", "Confirmed")
    _appointment("zenith-fitness",     p, add_days(TODAY, 12), "Reformer Pilates (45 min)", "Premium Slot", 900, "fitness", "09:00:00", "Pending")
    _appointment("zona-gameworld",     p, add_days(TODAY, 6),  "VR Experience (15 min)", "VR Zone Slot 1", 300, "sports_venue", "15:00:00", "Confirmed")
    _appointment("zona-gameworld",     p, add_days(TODAY, 14), "Go-Kart — Race Pack (3 rounds)", "Go-Kart Track", 900, "sports_venue", "16:00:00", "Pending")
    c1 = all_courts["smashzone-surat"][0]
    c2 = all_courts["smashzone-surat"][1]
    c3 = all_courts["smashzone-surat"][2]
    c4 = all_courts["smashzone-surat"][3]
    _court_booking("smashzone-surat", c1, p, add_days(TODAY, 1), "09:00:00", "10:00:00")
    _court_booking("smashzone-surat", c2, p, add_days(TODAY, 2), "17:00:00", "18:00:00")
    _court_booking("smashzone-surat", c3, p, add_days(TODAY, 3), "07:00:00", "08:00:00")
    _court_booking("smashzone-surat", c4, p, add_days(TODAY, 5), "06:00:00", "07:00:00")

    # Priya Shah
    ph = "9123456780"
    _table_booking("tao-restaurant",   ph, add_days(TODAY, 4),  "7:30 PM – 10:00 PM", 2, "confirmed")
    _table_booking("the-bhawan",       ph, add_days(TODAY, 10), "8:00 PM – 11:00 PM", 4, "confirmed")
    _table_booking("burma-burma",      ph, add_days(TODAY, 16), "1:00 PM – 3:00 PM",  2, "pending")
    _appointment("bliss-beauty",       ph, add_days(TODAY, 6),  "Signature Facial (60 min)", "Classic Facial", 1200, "wellness", "14:00:00", "Confirmed")
    _appointment("bliss-beauty",       ph, add_days(TODAY, 20), "Keratin Treatment", "Full Length", 3500, "wellness", "11:00:00", "Pending")
    _appointment("soch-boutique",      ph, add_days(TODAY, 8),  "Personal Styling Session (1 hr)", "Ethnic Wear", 800, "fashion", "12:00:00", "Confirmed")
    cs = all_courts["surat-badminton"][0]
    _court_booking("surat-badminton",  cs, ph, add_days(TODAY, 3), "08:00:00", "09:00:00")

    # Amit Patel
    ph = "9988776655"
    _table_booking("spice-garden",     ph, add_days(TODAY, 3),  "8:00 PM – 10:30 PM", 3, "confirmed")
    _table_booking("lords-resto",      ph, add_days(TODAY, 12), "7:00 PM – 9:30 PM",  2, "confirmed")
    _appointment("glow-skin-studio",   ph, add_days(TODAY, 5),  "Hydrafacial", "Express Hydrafacial", 1800, "wellness", "15:00:00", "Confirmed")
    _appointment("cult-fit-surat",     ph, add_days(TODAY, 7),  "HIIT Circuit (45 min)", "Evening Session", 700, "fitness", "19:00:00", "Confirmed")
    _appointment("fabindia-surat",     ph, add_days(TODAY, 9),  "Personal Styling Session (1 hr)", "Casual Wear", 800, "fashion", "11:00:00", "Pending")
    _appointment("smaaash-surat",      ph, add_days(TODAY, 11), "Bowling — 1 Game (1 Person)", "Lane 3", 250, "sports_venue", "16:00:00", "Confirmed")
    cv = all_courts["vr-squash-center"][0]
    _court_booking("vr-squash-center", cv, ph, add_days(TODAY, 4), "08:00:00", "09:00:00")

    # Sneha Mehta
    ph = "8765432109"
    _table_booking("cafe-the-lane",    ph, add_days(TODAY, 2),  "12:00 PM – 2:00 PM", 2, "confirmed")
    _table_booking("meluha-fern",      ph, add_days(TODAY, 8),  "8:00 PM – 10:30 PM", 4, "confirmed")
    _appointment("the-nail-bar",       ph, add_days(TODAY, 3),  "Gel Nail Extension", "Full Set", 800, "wellness", "14:00:00", "Confirmed")
    _appointment("yoga-bliss",         ph, add_days(TODAY, 5),  "Hatha Yoga (75 min)", "Beginner Slot", 700, "fitness", "07:30:00", "Confirmed")
    cr = all_courts["powerplay-courts"][0]
    _court_booking("powerplay-courts", cr, ph, add_days(TODAY, 6), "09:00:00", "10:00:00")

    # Rohan Joshi
    ph = "7654321098"
    _table_booking("dumas-seafood",    ph, add_days(TODAY, 5),  "7:30 PM – 10:00 PM", 2, "confirmed")
    _table_booking("unvind",           ph, add_days(TODAY, 11), "9:00 PM – 11:30 PM", 5, "pending")
    _table_booking("pind-balluchi",    ph, add_days(TODAY, 18), "8:00 PM – 10:30 PM", 3, "confirmed")
    _appointment("urban-retreat-spa",  ph, add_days(TODAY, 7),  "Hot Stone Therapy (75 min)", "Luxury Session", 1800, "wellness", "12:00:00", "Confirmed")
    _appointment("ironparadise-cf",    ph, add_days(TODAY, 9),  "CrossFit Basics (60 min)", "Morning WOD", 800, "fitness", "06:30:00", "Confirmed")
    _appointment("fun-world-surat",    ph, add_days(TODAY, 13), "Bowling — Family Pack (4 games)", "Weekend Fun", 800, "sports_venue", "15:00:00", "Pending")
    ce = all_courts["elite-badminton"][0]
    _court_booking("elite-badminton",  ce, ph, add_days(TODAY, 4), "07:00:00", "08:00:00")

    # Kavita Sharma
    ph = "9090909090"
    _table_booking("the-gallery-cafe", ph, add_days(TODAY, 3),  "1:00 PM – 3:00 PM",  2, "confirmed")
    _table_booking("tao-restaurant",   ph, add_days(TODAY, 9),  "8:00 PM – 10:30 PM", 4, "confirmed")
    _appointment("lotus-wellness",     ph, add_days(TODAY, 4),  "Body Polishing", "Full Body", 2500, "wellness", "11:00:00", "Confirmed")
    _appointment("breathe-yoga",       ph, add_days(TODAY, 6),  "Morning Vinyasa (60 min)", "Dawn Session", 600, "fitness", "06:00:00", "Confirmed")
    _appointment("kalki-fashion",      ph, add_days(TODAY, 8),  "Wardrobe Audit (Full)", "Complete Overhaul", 1500, "fashion", "11:00:00", "Pending")
    _appointment("timezone-surat",     ph, add_days(TODAY, 12), "VR Experience (15 min)", "VR Slot", 300, "sports_venue", "16:00:00", "Confirmed")
    ck = all_courts["ace-sports-complex"][0]
    _court_booking("ace-sports-complex", ck, ph, add_days(TODAY, 5), "07:00:00", "08:00:00")

    print("     Bookings created for all 6 users")

    # ── 6. Loyalty ────────────────────────────────────────────────────────────
    print("6/10 Building loyalty history for all 6 users...")

    dining_ids    = [r[0] for r in DINING_OUTLETS]
    wellness_ids  = [r[0] for r in WELLNESS_OUTLETS]
    fitness_ids   = [r[0] for r in FITNESS_OUTLETS]
    fashion_ids   = [r[0] for r in FASHION_OUTLETS]
    court_ids     = [r[0] for r in SPORTS_COURT_OUTLETS]
    venue_ids     = [r[0] for r in SPORTS_VENUE_OUTLETS]

    user_outlet_sets = {
        "9876543210": dining_ids[:5] + wellness_ids[:2] + fashion_ids[:2] + fitness_ids[:2] + court_ids[:1] + venue_ids[:1],
        "9123456780": dining_ids[1:5] + wellness_ids[:3] + fashion_ids[:2] + fitness_ids[:1],
        "9988776655": dining_ids[2:6] + wellness_ids[1:3] + fitness_ids[:2] + venue_ids[:2],
        "8765432109": dining_ids[:3] + wellness_ids[:2] + fitness_ids[:1],
        "7654321098": dining_ids[3:8] + wellness_ids[2:4] + fitness_ids[2:4] + court_ids[:2],
        "9090909090": dining_ids[1:5] + wellness_ids[1:4] + fitness_ids[1:3] + fashion_ids[1:3] + venue_ids[1:3],
    }

    for phone, name, target in TEST_USERS:
        cust = customers[phone]
        outlet_pool = user_outlet_sets.get(phone, dining_ids[:5])
        _generate_loyalty(cust.name, phone, target, outlet_pool)
        print(f"     {name}: ~{target} target coins")

    # ── 7. Notifications ──────────────────────────────────────────────────────
    print("7/10 Creating notifications for all 6 users...")

    for phone in all_phones:
        frappe.db.delete("Flamezo Notification", {"customer_phone": phone})
    frappe.db.commit()

    # Primary user — full rich set
    p = PRIMARY_PHONE
    for notif_type, title, body, days_ago in [
        ("loyalty",   "Coins Credited! 🎉",           "You earned 280 FlameZO Coins at Araku. Balance: 8,150 coins.", 0),
        ("order",     "Order Confirmed",               "Your order #ORD-2847 from The Gallery Cafe is being prepared.", 0),
        ("booking",   "Table Confirmed ✅",             f"Table at Araku for 3 confirmed for {add_days(TODAY, 2)} at 7:30 PM.", 0),
        ("promotion", "Flash Deal — Aura Wellness",    "20% off all massages today only at Aura Wellness Studio.", 1),
        ("loyalty",   "Coins Expiring Soon ⚠️",        "200 of your FlameZO Coins expire in 8 days. Use them!", 1),
        ("booking",   "Appointment Reminder 💆",        "Deep Tissue Massage at Aura Wellness — tomorrow 11:00 AM.", 1),
        ("order",     "Order Delivered 🛵",             "Your order from Unvind delivered. Tap to rate.", 2),
        ("promotion", "Weekend Special 🍽️",             "15% off at The Gallery Cafe this Sat & Sun.", 2),
        ("loyalty",   "Platinum Tier Unlocked! 🏆",    "You've crossed 5,000 lifetime coins. Welcome to Platinum!", 3),
        ("booking",   "Court Booked ✅",                "Badminton Court 1 at SmashZone Surat — tomorrow 9:00 AM.", 3),
        ("crowd",     "Crowd Match Found 🍴",           "2 people near you want to dine at Araku tonight.", 4),
        ("club",      "New Club Post",                  "The Gallery Cafe posted in their Fan Club.", 4),
        ("booking",   "Yoga Class Confirmed 🧘",        "Morning Vinyasa at Zenith Fitness — tomorrow 7:00 AM.", 4),
        ("order",     "Order Placed 🛒",                "Your order from Araku (₹920). Estimated delivery: 30 min.", 5),
        ("loyalty",   "Coins Earned 💰",                "420 coins added from Wardrobe. Lifetime: 6,100 coins.", 6),
        ("booking",   "VR Experience Booked ✅",        "VR Zone Slot 1 at Zona GameWorld confirmed!", 6),
        ("promotion", "Double Coins Week 💎",           "Earn 2× FlameZO Coins on every order at all Surat outlets.", 9),
        ("loyalty",   "Coins Credited!",               "510 coins from Zenith Fitness. Keep training!", 8),
        ("promotion", "Zona GameWorld is Live! 🎮",    "VR, bowling, arcade, go-karts — now on Flamezo Surat.", 10),
        ("booking",   "Anniversary Banquet Set 🥂",    "75-guest banquet at Araku confirmed. Menu call soon.", 11),
        ("crowd",     "Crowd Table Full 🎉",            "Your crowd table at Unvind is full — 4 people joining!", 12),
        ("club",      "VIP Invite 🌟",                  "You're invited to the Aura Wellness VIP Club.", 13),
        ("promotion", "SmashZone is Live! 🏸",          "Book courts at SmashZone Sports Arena and earn coins.", 14),
        ("order",     "Payment Confirmed ✔",            "₹1,240 confirmed for Araku Surat. Coins pending.", 15),
        ("loyalty",   "Gold Tier Reached 🥇",           "Congratulations! Gold tier. Bonus earn rate unlocked.", 20),
        ("general",   "Welcome to Flamezo 👋",          "Your account is live. Discover the best of Surat.", 30),
    ]:
        _notification(p, notif_type, title, body, days_ago)
    frappe.db.commit()

    # Other users — lighter set
    other_notifs = {
        "9123456780": [
            ("booking",   "Table Confirmed ✅",    "Table at Tao Pan Asian for 2 confirmed.", 0),
            ("loyalty",   "Coins Credited!",      "350 coins from Bliss Beauty. Balance growing!", 1),
            ("promotion", "Spa Flash Deal",       "30% off facials at Bliss Beauty today only.", 2),
            ("booking",   "Facial Booked 💆",     "Signature Facial at Bliss Beauty — 3 days from now.", 3),
            ("loyalty",   "Gold Tier! 🥇",        "Congratulations! You've hit Gold tier at Flamezo.", 7),
            ("order",     "Order Delivered 🛵",   "Your order from Burma Burma delivered. Rate it!", 4),
            ("promotion", "Weekend at The Bhawan","Exclusive 10% off at The Bhawan Rooftop this weekend.", 5),
            ("general",   "Welcome to Flamezo 👋","Your account is live. Discover the best of Surat.", 25),
        ],
        "9988776655": [
            ("booking",   "Table Confirmed ✅",    "Table at Spice Garden for 3 confirmed.", 0),
            ("loyalty",   "Coins Credited!",      "280 coins from Glow Skin Studio.", 1),
            ("booking",   "Hydrafacial Booked",   "Hydrafacial at Glow Skin Studio booked for Day +5.", 2),
            ("promotion", "HIIT Trial Free",      "First HIIT class at Cult.fit Surat is on us!", 3),
            ("loyalty",   "Silver Tier 🥈",       "You've hit Silver tier. 10% bonus earn unlocked.", 6),
            ("general",   "Welcome to Flamezo 👋","Discover dining, wellness, fitness, sports in Surat.", 20),
        ],
        "8765432109": [
            ("booking",   "Table Confirmed ✅",    "Table at Cafe The Lane for 2 confirmed.", 0),
            ("loyalty",   "Coins Credited!",      "150 coins from The Nail Bar. Welcome to Flamezo!", 1),
            ("booking",   "Nail Appointment 💅",  "Gel Extensions at The Nail Bar — Day +3.", 2),
            ("promotion", "First Yoga Class Free","First Hatha session at Yoga Bliss is on us!", 3),
            ("general",   "Welcome to Flamezo 👋","Explore Surat's best — dining, wellness, fitness & more!", 18),
        ],
        "7654321098": [
            ("booking",   "Table Confirmed ✅",    "Table at Dumas Seafood House for 2 confirmed.", 0),
            ("loyalty",   "Coins Credited!",      "390 coins from Urban Retreat Spa.", 1),
            ("booking",   "Hot Stone Booked",     "Hot Stone Therapy at Urban Retreat — Day +7.", 2),
            ("loyalty",   "Gold Tier 🥇",         "Gold tier reached! Exclusive rates unlocked.", 5),
            ("promotion", "CrossFit Launch",      "Iron Paradise CrossFit — first class free for new members.", 4),
            ("general",   "Welcome to Flamezo 👋","Your Flamezo account is live in Surat.", 22),
        ],
        "9090909090": [
            ("booking",   "Table Confirmed ✅",    "Table at The Gallery Cafe for 2 confirmed.", 0),
            ("loyalty",   "Coins Credited!",      "320 coins from Lotus Wellness. Balance growing!", 1),
            ("booking",   "Yoga Class Confirmed 🧘","Morning Vinyasa at Breathe Yoga — Day +6 at 6:00 AM.", 2),
            ("promotion", "Wardrobe Audit Deal",  "Book a full wardrobe audit at Kalki Fashion this week.", 3),
            ("loyalty",   "Silver Tier 🥈",       "Silver tier unlocked. Keep going — Gold is close!", 6),
            ("promotion", "Zona GameWorld Open",  "Zona GameWorld now on Flamezo — VR, bowling, go-karts!", 8),
            ("general",   "Welcome to Flamezo 👋","Explore Surat's best — your Flamezo account is live.", 20),
        ],
    }
    for phone, notifs in other_notifs.items():
        for notif_type, title, body, days_ago in notifs:
            _notification(phone, notif_type, title, body, days_ago)
    frappe.db.commit()
    print(f"     Notifications created for all 6 users")

    # ── 8. SmashZone refreshments menu ───────────────────────────────────────
    print("8/10 Adding SmashZone refreshments menu...")
    smash_items = [
        ("Beverages", "Electrolyte Sports Drink",   60, 1),
        ("Beverages", "Protein Shake (Chocolate)",  120, 1),
        ("Beverages", "Cold Brew Coffee",            80, 1),
        ("Beverages", "Watermelon Juice",            70, 1),
        ("Beverages", "Green Detox Juice",           90, 1),
        ("Snacks",    "Protein Bar (Peanut Butter)", 90, 1),
        ("Snacks",    "Granola Bites (4pc)",          80, 1),
        ("Snacks",    "Chicken Sandwich",            180, 0),
        ("Snacks",    "Veg Wrap",                    140, 1),
        ("Snacks",    "Greek Yogurt Bowl",           110, 1),
        ("Equipment", "Shuttlecock Pack (6pc)",      250, 1),
        ("Equipment", "Grip Tape",                    80, 1),
        ("Equipment", "Court Shoes (Rental / 1 hr)", 50, 1),
        ("Equipment", "Wrist Band Set",              120, 1),
    ]
    for cat, name, price, veg in smash_items:
        _menu_product("smashzone-surat", name, price, cat, veg)
    frappe.db.commit()
    print(f"     {len(smash_items)} menu items")

    # ── 9. Logos, hero videos, and Chills (5 per outlet = 450) ───────────────
    print("9/10 Setting logos/heroes and creating 450 Chills entries...")

    all_outlet_ids = [r[0] for outlets in OUTLETS_BY_TYPE.values() for r in outlets]
    frappe.db.sql("DELETE FROM `tabChills` WHERE outlet IN %s", [all_outlet_ids])
    frappe.db.commit()

    chills_count = 0
    for outlet_type, outlets in OUTLETS_BY_TYPE.items():
        pool = CHILLS_DATA[outlet_type]
        logos = LOGOS_BY_TYPE[outlet_type]
        for i, (rest_id, rest_name, lat, lon, _addr) in enumerate(outlets):
            logo = logos[i % len(logos)]
            hero = CDN_VIDEOS[i % len(CDN_VIDEOS)]
            frappe.db.set_value("Restaurant", rest_id, {"logo": logo, "hero_video": hero})
            for j in range(5):
                idx = (i * 5 + j) % 15
                likes, saves, views = pool["metrics"][idx]
                likes  = likes  + (i * 13 + j * 7) % 80
                saves  = saves  + (i * 7  + j * 3) % 30
                views  = views  + (i * 200 + j * 100) % 1000
                desc = pool["descs"][idx].format(name=rest_name)
                doc = frappe.get_doc({
                    "doctype": "Chills",
                    "outlet": rest_id,
                    "outlet_name": rest_name,
                    "outlet_city": "Surat",
                    "outlet_logo": logo,
                    "outlet_lat": lat,
                    "outlet_lng": lon,
                    "video_url": hero,
                    "thumbnail_url": pool["thumbs"][idx],
                    "description": desc,
                    "likes_count": likes,
                    "saves_count": saves,
                    "views_count": views,
                    "status": "published",
                })
                doc.flags.ignore_validate = True
                doc.insert(ignore_permissions=True)
                chills_count += 1
        frappe.db.commit()

    print(f"     {chills_count} Chills entries across {len(all_outlet_ids)} outlets")

    # ── 10. Summary ────────────────────────────────────────────────────────────
    print("10/10 Summary:")
    for table, label in [
        ("Restaurant",               "Restaurants / Outlets"),
        ("Court",                    "Courts"),
        ("Chills",                   "Chills (media)"),
        ("Table Booking",            "Table Bookings (total)"),
        ("Banquet Booking",          "Banquet Bookings"),
        ("Service Appointment",      "Service Appointments"),
        ("Court Booking",            "Court Bookings"),
        ("Restaurant Loyalty Entry", "Loyalty Entries (all users)"),
        ("Flamezo Notification",     "Notifications (all users)"),
        ("Menu Product",             "Menu Products"),
        ("Catalogue Item",           "Catalogue Items"),
    ]:
        cnt = frappe.db.count(table)
        print(f"     {label:<38} {cnt:>5}")

    print(f"\n     Test users:")
    for phone, name, target in TEST_USERS:
        tier = "Platinum" if target>=5000 else "Gold" if target>=2000 else "Silver" if target>=500 else "Bronze"
        nb = (frappe.db.count("Table Booking",       {"customer_phone": phone}) +
              frappe.db.count("Banquet Booking",      {"customer_phone": phone}) +
              frappe.db.count("Service Appointment",  {"customer_phone": phone}) +
              frappe.db.count("Court Booking",        {"customer_phone": phone}))
        print(f"     {phone}  {name:<16}  {tier:<10}  {nb} bookings")

    print("\n  ✓ Done — log in with any of the phones above")
