"""
RailSathi AI — Location and Station Resolution Service

Resolves passenger destination venues and origin areas to geographical coordinates,
identifies suitable railway station candidates, and calculates last-mile journey estimates.
Integrates durable SQLite caching, multi-location venue disambiguation, and station classification.
"""

import os
import json
import math
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from backend.journey.models import ResolvedLocation, StationCandidate, LastMileEstimate, GeocodedPlaceCandidate
from backend.journey.geocoding import GeocodingProvider, get_geocoding_provider
from backend.journey.routing import RoutingProvider, get_routing_provider

logger = logging.getLogger("railsaathi.journey.location")


# =====================================================================
# 1. Indian Railway Stations Registry with Classification
# =====================================================================

STATION_REGISTRY: dict[str, dict[str, Any]] = {
    # Chennai Metropolitan Stations
    "MAS": {
        "station_name": "MGR Chennai Central",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 13.0827,
        "longitude": 80.2757,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "MS": {
        "station_name": "Chennai Egmore",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 13.0797,
        "longitude": 80.2612,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "TBM": {
        "station_name": "Tambaram",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 12.9249,
        "longitude": 80.1278,
        "is_major_hub": True,
        "station_type": "intercity_junction",
        "supports_intercity": True,
    },
    "PER": {
        "station_name": "Perambur",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 13.1075,
        "longitude": 80.2443,
        "is_major_hub": False,
        "station_type": "intercity_halt",
        "supports_intercity": True,
    },
    "AVD": {
        "station_name": "Avadi",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 13.1189,
        "longitude": 80.1008,
        "is_major_hub": False,
        "station_type": "intercity_halt",
        "supports_intercity": True,
    },
    "TRL": {
        "station_name": "Tiruvallur",
        "city": "Tiruvallur",
        "state": "Tamil Nadu",
        "latitude": 13.1360,
        "longitude": 79.9078,
        "is_major_hub": False,
        "station_type": "intercity_junction",
        "supports_intercity": True,
    },
    "TYMR": {
        "station_name": "Taramani MRTS",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 12.9863,
        "longitude": 80.2442,
        "is_major_hub": False,
        "station_type": "suburban_halt",
        "supports_intercity": False,
    },
    "KTBR": {
        "station_name": "Kasturba Nagar MRTS",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "latitude": 12.9972,
        "longitude": 80.2520,
        "is_major_hub": False,
        "station_type": "suburban_halt",
        "supports_intercity": False,
    },

    # Bengaluru Stations
    "SBC": {
        "station_name": "KSR Bengaluru (City)",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9781,
        "longitude": 77.5696,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "YPR": {
        "station_name": "Yesvantpur Junction",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 13.0238,
        "longitude": 77.5503,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "SMVB": {
        "station_name": "Sir M. Visvesvaraya Terminal (SMVT)",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9926,
        "longitude": 77.6534,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "BNC": {
        "station_name": "Bengaluru Cantt",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9934,
        "longitude": 77.5986,
        "is_major_hub": False,
        "station_type": "intercity_halt",
        "supports_intercity": True,
    },
    "KJM": {
        "station_name": "Krishnarajapuram",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9972,
        "longitude": 77.6766,
        "is_major_hub": False,
        "station_type": "intercity_halt",
        "supports_intercity": True,
    },
    "WFD": {
        "station_name": "Whitefield",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9942,
        "longitude": 77.7588,
        "is_major_hub": False,
        "station_type": "intercity_halt",
        "supports_intercity": True,
    },

    # Delhi NCR Stations
    "NDLS": {
        "station_name": "New Delhi Railway Station",
        "city": "Delhi",
        "state": "Delhi",
        "latitude": 28.6429,
        "longitude": 77.2195,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "DLI": {
        "station_name": "Old Delhi Junction",
        "city": "Delhi",
        "state": "Delhi",
        "latitude": 28.6609,
        "longitude": 77.2272,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "NZM": {
        "station_name": "Hazrat Nizamuddin",
        "city": "Delhi",
        "state": "Delhi",
        "latitude": 28.5888,
        "longitude": 77.2536,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "ANVT": {
        "station_name": "Anand Vihar Terminal",
        "city": "Delhi",
        "state": "Delhi",
        "latitude": 28.6500,
        "longitude": 77.3150,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },

    # Mumbai Stations
    "CSMT": {
        "station_name": "Chhatrapati Shivaji Maharaj Terminus",
        "city": "Mumbai",
        "state": "Maharashtra",
        "latitude": 18.9402,
        "longitude": 72.8356,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "BCT": {
        "station_name": "Mumbai Central",
        "city": "Mumbai",
        "state": "Maharashtra",
        "latitude": 18.9696,
        "longitude": 72.8193,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "BDTS": {
        "station_name": "Bandra Terminus",
        "city": "Mumbai",
        "state": "Maharashtra",
        "latitude": 19.0624,
        "longitude": 72.8407,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "LTT": {
        "station_name": "Lokmanya Tilak Terminus",
        "city": "Mumbai",
        "state": "Maharashtra",
        "latitude": 19.0694,
        "longitude": 72.8917,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "DR": {
        "station_name": "Dadar Central",
        "city": "Mumbai",
        "state": "Maharashtra",
        "latitude": 19.0178,
        "longitude": 72.8428,
        "is_major_hub": False,
        "station_type": "intercity_junction",
        "supports_intercity": True,
    },

    # Hyderabad / Secunderabad Stations
    "SC": {
        "station_name": "Secunderabad Junction",
        "city": "Hyderabad",
        "state": "Telangana",
        "latitude": 17.4344,
        "longitude": 78.5015,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "HYB": {
        "station_name": "Hyderabad Deccan (Nampally)",
        "city": "Hyderabad",
        "state": "Telangana",
        "latitude": 17.3926,
        "longitude": 78.4688,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "KCG": {
        "station_name": "Kacheguda",
        "city": "Hyderabad",
        "state": "Telangana",
        "latitude": 17.3916,
        "longitude": 78.4975,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "LPI": {
        "station_name": "Lingampalli",
        "city": "Hyderabad",
        "state": "Telangana",
        "latitude": 17.4842,
        "longitude": 78.3184,
        "is_major_hub": False,
        "station_type": "intercity_junction",
        "supports_intercity": True,
    },

    # Kolkata Stations
    "HWH": {
        "station_name": "Howrah Junction",
        "city": "Kolkata",
        "state": "West Bengal",
        "latitude": 22.5840,
        "longitude": 88.3426,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "SDAH": {
        "station_name": "Sealdah",
        "city": "Kolkata",
        "state": "West Bengal",
        "latitude": 22.5670,
        "longitude": 88.3712,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },

    # Tamil Nadu / South Regional Hubs
    "TEN": {
        "station_name": "Tirunelveli Junction",
        "city": "Tirunelveli",
        "state": "Tamil Nadu",
        "latitude": 8.7285,
        "longitude": 77.7118,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "MDU": {
        "station_name": "Madurai Junction",
        "city": "Madurai",
        "state": "Tamil Nadu",
        "latitude": 9.9196,
        "longitude": 78.1105,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "TPJ": {
        "station_name": "Tiruchchirappalli Junction",
        "city": "Tiruchirappalli",
        "state": "Tamil Nadu",
        "latitude": 10.7937,
        "longitude": 78.6853,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "CBE": {
        "station_name": "Coimbatore Junction",
        "city": "Coimbatore",
        "state": "Tamil Nadu",
        "latitude": 11.0016,
        "longitude": 76.9665,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "SA": {
        "station_name": "Salem Junction",
        "city": "Salem",
        "state": "Tamil Nadu",
        "latitude": 11.6643,
        "longitude": 78.1460,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },

    # Kerala Hubs
    "TVC": {
        "station_name": "Thiruvananthapuram Central",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "latitude": 8.4870,
        "longitude": 76.9525,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "ERS": {
        "station_name": "Ernakulam Junction (South)",
        "city": "Kochi",
        "state": "Kerala",
        "latitude": 9.9678,
        "longitude": 76.2898,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },

    # Western / Northern Hubs
    "PUNE": {
        "station_name": "Pune Junction",
        "city": "Pune",
        "state": "Maharashtra",
        "latitude": 18.5284,
        "longitude": 73.8744,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "ADI": {
        "station_name": "Ahmedabad Junction",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "latitude": 23.0225,
        "longitude": 72.5714,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
    "JP": {
        "station_name": "Jaipur Junction",
        "city": "Jaipur",
        "state": "Rajasthan",
        "latitude": 26.9196,
        "longitude": 75.7878,
        "is_major_hub": True,
        "station_type": "major_intercity_terminal",
        "supports_intercity": True,
    },
}


# =====================================================================
# 2. Verified Venue and Landmark Registry with Disambiguation Keys
# =====================================================================

VENUE_REGISTRY: dict[str, dict[str, Any]] = {
    # Chennai Venues — Specific Localities & Coordinates
    "tidel park, taramani, chennai": {
        "canonical_name": "Tidel Park, Taramani, Chennai",
        "resolved_address": "Tidel Park, Rajiv Gandhi Salai (OMR), Taramani, Chennai, Tamil Nadu 600113",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Taramani",
        "latitude": 12.9893,
        "longitude": 80.2483,
        "keywords": ["tidel park chennai", "tidel park, chennai", "tidel park taramani", "tidel park omr"],
    },
    "tidel park, pattabiram": {
        "canonical_name": "TIDEL Park Pattabiram, Chennai/Tiruvallur",
        "resolved_address": "TIDEL Park Pattabiram, CTH Road, Pattabiram, Tiruvallur District, Chennai, Tamil Nadu 600072",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Pattabiram",
        "latitude": 13.1235,
        "longitude": 80.0574,
        "keywords": ["tidel park pattabiram", "tidel park, pattabiram", "tidel pattabiram", "pattabiram tidel park"],
    },
    "tidel park, coimbatore": {
        "canonical_name": "TIDEL Park Coimbatore, ELCOT SEZ",
        "resolved_address": "TIDEL Park Coimbatore, ELCOT SEZ, Civil Aerodrome Post, Coimbatore, Tamil Nadu 641014",
        "city": "Coimbatore",
        "state": "Tamil Nadu",
        "locality": "Peelamedu",
        "latitude": 11.0264,
        "longitude": 77.0371,
        "keywords": ["tidel park coimbatore", "tidel park, coimbatore", "tidel coimbatore"],
    },
    "tidel park, madurai": {
        "canonical_name": "TIDEL / ELCOT IT Park, Madurai",
        "resolved_address": "ELCOT / TIDEL IT Park, Ilandhaikulam, Mattuthavani, Madurai, Tamil Nadu 625020",
        "city": "Madurai",
        "state": "Tamil Nadu",
        "locality": "Mattuthavani",
        "latitude": 9.9452,
        "longitude": 78.1563,
        "keywords": ["tidel park madurai", "tidel park, madurai", "elcot it park madurai", "tidel madurai"],
    },
    "tidel park, tiruchirappalli": {
        "canonical_name": "TIDEL Park Trichy, Panjappur",
        "resolved_address": "TIDEL Park Trichy, Panjappur, Tiruchirappalli, Tamil Nadu 620012",
        "city": "Tiruchirappalli",
        "state": "Tamil Nadu",
        "locality": "Panjappur",
        "latitude": 10.7410,
        "longitude": 78.6720,
        "keywords": ["tidel park trichy", "tidel park, trichy", "tidel park tiruchirappalli"],
    },
    "iit madras": {
        "canonical_name": "IIT Madras, Guindy, Chennai",
        "resolved_address": "Indian Institute of Technology Madras, Sardar Patel Road, Guindy, Chennai, Tamil Nadu 600036",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Guindy",
        "latitude": 12.9915,
        "longitude": 80.2337,
        "keywords": ["iit madras", "iitm", "iit chennai", "indian institute of technology madras"],
    },
    "dlf cybercity chennai": {
        "canonical_name": "DLF Cybercity, Manapakkam, Chennai",
        "resolved_address": "DLF Cybercity Chennai, 1/124 Mount Poonamallee Road, Manapakkam, Chennai, Tamil Nadu 600089",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Manapakkam",
        "latitude": 13.0232,
        "longitude": 80.1706,
        "keywords": ["dlf cybercity chennai", "dlf it park chennai", "dlf manapakkam"],
    },
    "apollo hospital greams road": {
        "canonical_name": "Apollo Hospitals, Greams Road, Chennai",
        "resolved_address": "Apollo Hospitals, 21 Greams Lane, Thousand Lights, Chennai, Tamil Nadu 600006",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Thousand Lights",
        "latitude": 13.0601,
        "longitude": 80.2527,
        "keywords": ["apollo hospital greams road", "apollo main hospital chennai", "apollo greams road"],
    },
    "us consulate chennai": {
        "canonical_name": "U.S. Consulate General, Anna Salai, Chennai",
        "resolved_address": "U.S. Consulate General, 220 Anna Salai, Chennai, Tamil Nadu 600006",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Anna Salai",
        "latitude": 13.0538,
        "longitude": 80.2515,
        "keywords": ["us consulate chennai", "american consulate chennai", "us consulate general anna salai"],
    },
    "guindy industrial estate": {
        "canonical_name": "Guindy Industrial Estate, Chennai",
        "resolved_address": "SIDCO Industrial Estate, Guindy, Chennai, Tamil Nadu 600032",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "locality": "Guindy",
        "latitude": 13.0067,
        "longitude": 80.2072,
        "keywords": ["guindy industrial estate", "sidco guindy", "guindy estate"],
    },

    # Bengaluru Venues
    "whitefield": {
        "canonical_name": "Whitefield IT Hub, Bengaluru",
        "resolved_address": "ITPB / Whitefield Technology Corridor, Bengaluru, Karnataka 560066",
        "city": "Bengaluru",
        "state": "Karnataka",
        "locality": "Whitefield",
        "latitude": 12.9698,
        "longitude": 77.7499,
        "keywords": ["whitefield", "whitefield bengaluru", "itpb whitefield"],
    },
    "electronic city": {
        "canonical_name": "Electronic City Phase 1, Bengaluru",
        "resolved_address": "Electronic City Phase 1, Hosur Road, Bengaluru, Karnataka 560100",
        "city": "Bengaluru",
        "state": "Karnataka",
        "locality": "Electronic City",
        "latitude": 12.8452,
        "longitude": 77.6602,
        "keywords": ["electronic city", "electronic city bengaluru", "ecity"],
    },
    "manyata tech park": {
        "canonical_name": "Manyata Embassy Business Park, Hebbal, Bengaluru",
        "resolved_address": "Manyata Embassy Business Park, Outer Ring Road, Nagavara, Bengaluru, Karnataka 560045",
        "city": "Bengaluru",
        "state": "Karnataka",
        "locality": "Nagavara",
        "latitude": 13.0489,
        "longitude": 77.6208,
        "keywords": ["manyata tech park", "manyata embassy business park", "manyata hebbal"],
    },
    "iisc bengaluru": {
        "canonical_name": "Indian Institute of Science (IISc), Malleshwaram, Bengaluru",
        "resolved_address": "Indian Institute of Science, CV Raman Road, Malleshwaram, Bengaluru, Karnataka 560012",
        "city": "Bengaluru",
        "state": "Karnataka",
        "locality": "Malleshwaram",
        "latitude": 13.0219,
        "longitude": 77.5671,
        "keywords": ["iisc", "iisc bengaluru", "iisc bangalore", "indian institute of science"],
    },
    "mg road bengaluru": {
        "canonical_name": "MG Road / Brigade Road, Bengaluru",
        "resolved_address": "Mahatma Gandhi Road / Brigade Road, Central Business District, Bengaluru, Karnataka 560001",
        "city": "Bengaluru",
        "state": "Karnataka",
        "locality": "CBD",
        "latitude": 12.9756,
        "longitude": 77.6066,
        "keywords": ["mg road bengaluru", "mg road bangalore", "brigade road bengaluru"],
    },

    # Delhi NCR Venues
    "connaught place": {
        "canonical_name": "Connaught Place, New Delhi",
        "resolved_address": "Connaught Place (Rajiv Chowk), New Delhi, Delhi 110001",
        "city": "Delhi",
        "state": "Delhi",
        "locality": "Connaught Place",
        "latitude": 28.6315,
        "longitude": 77.2167,
        "keywords": ["connaught place", "cp new delhi", "rajiv chowk"],
    },
    "cyber city gurugram": {
        "canonical_name": "DLF Cyber City, Gurugram, Delhi NCR",
        "resolved_address": "DLF Cyber City, Phase 2, Sector 24, Gurugram, Haryana 122002",
        "city": "Delhi",
        "state": "Haryana",
        "locality": "Cyber City",
        "latitude": 28.4950,
        "longitude": 77.0895,
        "keywords": ["cyber city gurugram", "dlf cyber city", "cyber hub gurugram"],
    },
    "aiims new delhi": {
        "canonical_name": "AIIMS Hospital, Ansari Nagar, New Delhi",
        "resolved_address": "All India Institute of Medical Sciences, Sri Aurobindo Marg, Ansari Nagar, New Delhi 110029",
        "city": "Delhi",
        "state": "Delhi",
        "locality": "Ansari Nagar",
        "latitude": 28.5672,
        "longitude": 77.2100,
        "keywords": ["aiims new delhi", "aiims hospital delhi", "aiims"],
    },
    "pragati maidan": {
        "canonical_name": "Bharat Mandapam (Pragati Maidan), New Delhi",
        "resolved_address": "Bharat Mandapam Convention Centre, Pragati Maidan, Mathura Road, New Delhi 110001",
        "city": "Delhi",
        "state": "Delhi",
        "locality": "Pragati Maidan",
        "latitude": 28.6186,
        "longitude": 77.2435,
        "keywords": ["pragati maidan", "bharat mandapam", "pragati maidan delhi"],
    },

    # Mumbai Venues
    "bkc": {
        "canonical_name": "Bandra Kurla Complex (BKC), Mumbai",
        "resolved_address": "Bandra Kurla Complex, Bandra East, Mumbai, Maharashtra 400051",
        "city": "Mumbai",
        "state": "Maharashtra",
        "locality": "Bandra East",
        "latitude": 19.0657,
        "longitude": 72.8687,
        "keywords": ["bkc", "bandra kurla complex", "bkc mumbai"],
    },
    "nariman point": {
        "canonical_name": "Nariman Point, South Mumbai",
        "resolved_address": "Nariman Point Business District, Marine Drive, Mumbai, Maharashtra 400021",
        "city": "Mumbai",
        "state": "Maharashtra",
        "locality": "Nariman Point",
        "latitude": 18.9256,
        "longitude": 72.8242,
        "keywords": ["nariman point", "nariman point mumbai"],
    },
    "iit bombay": {
        "canonical_name": "IIT Bombay, Powai, Mumbai",
        "resolved_address": "Indian Institute of Technology Bombay, Main Gate Road, Powai, Mumbai, Maharashtra 400076",
        "city": "Mumbai",
        "state": "Maharashtra",
        "locality": "Powai",
        "latitude": 19.1334,
        "longitude": 72.9133,
        "keywords": ["iit bombay", "iit powai", "indian institute of technology bombay"],
    },

    # Hyderabad Venues
    "hitec city": {
        "canonical_name": "HITEC City / Madhapur, Hyderabad",
        "resolved_address": "HITEC City, Madhapur, Cyberabad, Hyderabad, Telangana 500081",
        "city": "Hyderabad",
        "state": "Telangana",
        "locality": "Madhapur",
        "latitude": 17.4435,
        "longitude": 78.3772,
        "keywords": ["hitec city", "hitech city", "cyberabad", "madhapur hyderabad"],
    },
    "gachibowli": {
        "canonical_name": "Gachibowli Financial District, Hyderabad",
        "resolved_address": "Financial District, Nanakramguda, Gachibowli, Hyderabad, Telangana 500032",
        "city": "Hyderabad",
        "state": "Telangana",
        "locality": "Gachibowli",
        "latitude": 17.4401,
        "longitude": 78.3489,
        "keywords": ["gachibowli", "financial district hyderabad", "gachibowli hyderabad"],
    },
    "anna stadium, tirunelveli": {
        "canonical_name": "Anna Stadium, Palayamkottai, Tirunelveli",
        "resolved_address": "Anna Stadium, St. Thomas Road, Palayamkottai, Tirunelveli, Tamil Nadu 627002",
        "city": "Tirunelveli",
        "state": "Tamil Nadu",
        "locality": "Palayamkottai",
        "latitude": 8.7180,
        "longitude": 77.7420,
        "keywords": ["anna stadium", "anna stadium tirunelveli", "anna stadium palayamkottai"],
    },
    "district court, tirunelveli": {
        "canonical_name": "District Court, Palayamkottai, Tirunelveli",
        "resolved_address": "District Court Complex, Tiruchendur Main Rd, Palayamkottai, Tirunelveli, Tamil Nadu 627002",
        "city": "Tirunelveli",
        "state": "Tamil Nadu",
        "locality": "Palayamkottai",
        "latitude": 8.7145,
        "longitude": 77.7482,
        "keywords": ["district court, tirunelveli", "district court tirunelveli", "tirunelveli court"],
    },
    "tirunelveli medical college": {
        "canonical_name": "Tirunelveli Medical College (TVMC)",
        "resolved_address": "Tirunelveli Medical College, High Ground Road, Palayamkottai, Tirunelveli, Tamil Nadu 627011",
        "city": "Tirunelveli",
        "state": "Tamil Nadu",
        "locality": "Palayamkottai",
        "latitude": 8.7075,
        "longitude": 77.7538,
        "keywords": ["tirunelveli medical college", "tvmc tirunelveli", "tirunelveli medical college hospital"],
    },
}


# =====================================================================
# 3. City Centroids Registry
# =====================================================================

CITY_CENTROIDS: dict[str, dict[str, Any]] = {
    "chennai": {"city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707},
    "bengaluru": {"city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946},
    "bangalore": {"city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946},
    "delhi": {"city": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.2090},
    "new delhi": {"city": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.2090},
    "mumbai": {"city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lon": 72.8777},
    "hyderabad": {"city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lon": 78.4867},
    "secunderabad": {"city": "Hyderabad", "state": "Telangana", "lat": 17.4399, "lon": 78.4983},
    "kolkata": {"city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639},
    "pune": {"city": "Pune", "state": "Maharashtra", "lat": 18.5204, "lon": 73.8567},
    "coimbatore": {"city": "Coimbatore", "state": "Tamil Nadu", "lat": 11.0168, "lon": 76.9558},
    "mysuru": {"city": "Mysuru", "state": "Karnataka", "lat": 12.2958, "lon": 76.6394},
    "mysore": {"city": "Mysuru", "state": "Karnataka", "lat": 12.2958, "lon": 76.6394},
    "tirunelveli": {"city": "Tirunelveli", "state": "Tamil Nadu", "lat": 8.7285, "lon": 77.7118},
    "madurai": {"city": "Madurai", "state": "Tamil Nadu", "lat": 9.9196, "lon": 78.1105},
    "tiruchirappalli": {"city": "Tiruchirappalli", "state": "Tamil Nadu", "lat": 10.7937, "lon": 78.6853},
    "trichy": {"city": "Tiruchirappalli", "state": "Tamil Nadu", "lat": 10.7937, "lon": 78.6853},
    "salem": {"city": "Salem", "state": "Tamil Nadu", "lat": 11.6643, "lon": 78.1460},
    "thiruvananthapuram": {"city": "Thiruvananthapuram", "state": "Kerala", "lat": 8.4870, "lon": 76.9525},
    "trivandrum": {"city": "Thiruvananthapuram", "state": "Kerala", "lat": 8.4870, "lon": 76.9525},
    "kochi": {"city": "Kochi", "state": "Kerala", "lat": 9.9678, "lon": 76.2898},
    "ernakulam": {"city": "Kochi", "state": "Kerala", "lat": 9.9678, "lon": 76.2898},
    "ahmedabad": {"city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lon": 72.5714},
    "jaipur": {"city": "Jaipur", "state": "Rajasthan", "lat": 26.9196, "lon": 75.7878},
    "lucknow": {"city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lon": 80.9462},
    "kanpur": {"city": "Kanpur", "state": "Uttar Pradesh", "lat": 26.4499, "lon": 80.3319},
    "patna": {"city": "Patna", "state": "Bihar", "lat": 25.5941, "lon": 85.1376},
    "chandigarh": {"city": "Chandigarh", "state": "Chandigarh", "lat": 30.7333, "lon": 76.7794},
}


# =====================================================================
# 4. Deterministic Geo-Distance & Urban Traffic Duration Models
# =====================================================================

def calculate_haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two coordinate pairs in kilometers."""
    r = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


def estimate_urban_travel_time_minutes(distance_km: float, is_metro_available: bool = False) -> int:
    """
    Deterministically estimate road/cab transit duration with traffic buffer.
    In Indian urban metros, average cab speed is ~22 km/h + 8 min buffer for station exit/traffic lights.
    """
    if distance_km <= 0.5:
        return 5  # Walking distance
    
    # Base speed in urban traffic ~ 22 km/h
    travel_time_hrs = distance_km / 22.0
    travel_time_mins = travel_time_hrs * 60.0
    
    # Add urban dispatch / station exit buffer (8 mins)
    total_mins = int(math.ceil(travel_time_mins + 8.0))
    return max(total_mins, 10)


# =====================================================================
# 5. Durable SQLite Location & Routing Cache
# =====================================================================

class LocationCacheManager:
    """
    Durable SQLite-backed cache for geocoded venues and route estimates.
    Maintains WAL journal mode and TTL expirations.
    Architecturally separate from RailRadar client to prevent quota consumption.
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            env_db = os.environ.get("LOCATION_CACHE_DB_PATH")
            if env_db:
                self.db_path = Path(env_db)
            else:
                self.db_path = Path(__file__).resolve().parent.parent / "data" / "location_cache.sqlite"
        else:
            self.db_path = Path(db_path)

        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _ensure_tables(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS geocoding_cache (
                    cache_key TEXT PRIMARY KEY,
                    query_norm TEXT NOT NULL,
                    context_city TEXT,
                    resolved_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routing_cache (
                    route_key TEXT PRIMARY KEY,
                    distance_km REAL,
                    duration_minutes INTEGER,
                    transit_mode TEXT,
                    provider TEXT,
                    confidence TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
            """)
            conn.commit()

    def get_geocoding(self, query_norm: str, context_city: Optional[str] = None) -> Optional[dict[str, Any]]:
        cache_key = f"{query_norm.strip().lower()}|{(context_city or '').strip().lower()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT resolved_json, expires_at FROM geocoding_cache WHERE cache_key = ? AND expires_at > ?",
                (cache_key, now_iso),
            ).fetchone()
            if row:
                try:
                    return json.loads(row["resolved_json"])
                except Exception as e:
                    logger.warning(f"Error parsing cached geocoding entry {cache_key}: {e}")
        return None

    def put_geocoding(
        self,
        query_norm: str,
        resolved_data: dict[str, Any],
        context_city: Optional[str] = None,
        ttl_seconds: int = 2592000,  # 30 days default TTL for places
    ) -> None:
        cache_key = f"{query_norm.strip().lower()}|{(context_city or '').strip().lower()}"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO geocoding_cache (cache_key, query_norm, context_city, resolved_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    resolved_json = excluded.resolved_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at;
                """,
                (
                    cache_key,
                    query_norm.strip().lower(),
                    (context_city or "").strip().lower(),
                    json.dumps(resolved_data),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            conn.commit()

    def get_routing(self, route_key: str) -> Optional[dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT distance_km, duration_minutes, transit_mode, provider, confidence FROM routing_cache WHERE route_key = ? AND expires_at > ?",
                (route_key, now_iso),
            ).fetchone()
            if row:
                return dict(row)
        return None

    def put_routing(
        self,
        route_key: str,
        distance_km: float,
        duration_minutes: int,
        transit_mode: str = "cab",
        provider: str = "RailSathi Deterministic Urban Routing Model",
        confidence: str = "cached_estimate",
        ttl_seconds: int = 604800,  # 7 days TTL for route calculations
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO routing_cache (route_key, distance_km, duration_minutes, transit_mode, provider, confidence, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_key) DO UPDATE SET
                    distance_km = excluded.distance_km,
                    duration_minutes = excluded.duration_minutes,
                    transit_mode = excluded.transit_mode,
                    provider = excluded.provider,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at;
                """,
                (
                    route_key,
                    distance_km,
                    duration_minutes,
                    transit_mode,
                    provider,
                    confidence,
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            conn.commit()


# =====================================================================
# 6. Location Resolution Service
# =====================================================================

class LocationResolutionService:
    """
    Robust pipeline for place resolution, station discovery, and last-mile travel calculations.
    Ensures zero RailRadar API calls and guarantees accurate geographic coordinates.
    """

    def __init__(
        self,
        cache_manager: Optional[LocationCacheManager] = None,
        geocoding_provider: Optional[GeocodingProvider] = None,
        routing_provider: Optional[RoutingProvider] = None,
    ):
        self.cache = cache_manager or LocationCacheManager()
        self.geocoding_provider = geocoding_provider or get_geocoding_provider()
        self.routing_provider = routing_provider or get_routing_provider()
        self.geocoding_requests_count = 0
        self.geocoding_cache_hits_count = 0
        self.routing_requests_count = 0
        self.routing_cache_hits_count = 0

    def resolve_location(
        self,
        query: str,
        context_city: Optional[str] = None,
    ) -> ResolvedLocation:
        """
        Stage B: Resolve a venue, landmark, or city to geographic coordinates.
        1. Checks persistent geocoding cache.
        2. Checks Station Registry for direct station codes/names.
        3. Queries configured dynamic geocoding provider (e.g. OSM Nominatim or Mock).
        4. Validates coordinates, locality consistency, and detects multi-branch ambiguity.
        5. Falls back to verified local registry if provider returns zero results.
        6. Never silently substitutes city-centroid coordinates for unverified venues.
        """
        self.geocoding_requests_count += 1
        q_norm = query.strip().lower()
        ctx_norm = context_city.strip().lower() if context_city else None

        # 1. Check persistent SQLite cache
        cached = self.cache.get_geocoding(q_norm, ctx_norm)
        if cached:
            # If context_city specified, ensure cached record matches locality
            cached_city = (cached.get("city") or "").lower()
            if not ctx_norm or (ctx_norm in cached_city or cached_city in ctx_norm or ctx_norm in (cached.get("resolved_address") or "").lower()):
                self.geocoding_cache_hits_count += 1
                return ResolvedLocation(
                    query=query,
                    display_name=cached["display_name"],
                    resolved_address=cached.get("resolved_address"),
                    city=cached["city"],
                    state=cached.get("state", "India"),
                    country=cached.get("country", "India"),
                    latitude=cached.get("latitude"),
                    longitude=cached.get("longitude"),
                    provider=cached.get("provider", "RailSathi Place Registry (Cached)"),
                    provider_place_id=cached.get("provider_place_id"),
                    confidence=cached.get("confidence", 0.95),
                    is_cached=True,
                    requires_user_clarification=cached.get("requires_user_clarification", False),
                    clarification_options=cached.get("clarification_options", []),
                    resolution_error=cached.get("resolution_error"),
                )

        # 2. Check STATION_REGISTRY by station code or station name
        for s_code, s_info in STATION_REGISTRY.items():
            st_name_lower = s_info["station_name"].lower()
            q_words = [w for w in q_norm.split() if len(w) > 2]
            if (
                q_norm == s_code.lower()
                or q_norm == st_name_lower
                or (len(q_norm) > 4 and (st_name_lower in q_norm or q_norm in st_name_lower))
                or (q_words and all(w in st_name_lower for w in q_words))
            ):
                res = ResolvedLocation(
                    query=query,
                    display_name=s_info["station_name"],
                    resolved_address=f"{s_info['station_name']}, {s_info['city']}, {s_info['state']}",
                    city=s_info["city"],
                    state=s_info["state"],
                    country="India",
                    latitude=s_info["latitude"],
                    longitude=s_info["longitude"],
                    provider="RailSathi Station Registry (Verified)",
                    confidence=0.99,
                    is_cached=False,
                    requires_user_clarification=False,
                )
                self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
                return res

        # 3. Query Dynamic Geocoding Provider
        provider_candidates = self.geocoding_provider.search_venue(
            query=query,
            city=context_city,
        )

        if provider_candidates:
            # A. Filter candidates with valid coordinates
            valid_candidates: list[GeocodedPlaceCandidate] = []
            for cand in provider_candidates:
                if cand.latitude is not None and cand.longitude is not None:
                    if -90.0 <= cand.latitude <= 90.0 and -180.0 <= cand.longitude <= 180.0:
                        valid_candidates.append(cand)

            if not valid_candidates:
                res = ResolvedLocation(
                    query=query,
                    display_name=f"{query.title()} (Invalid Coordinates)",
                    resolved_address=None,
                    city=context_city or "Unknown",
                    state="India",
                    country="India",
                    latitude=None,
                    longitude=None,
                    provider=self.geocoding_provider.provider_name,
                    confidence=0.0,
                    is_cached=False,
                    requires_user_clarification=True,
                    resolution_error=f"Geocoding provider returned invalid coordinates for '{query}'.",
                )
                self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
                return res

            # B. Locality consistency check if context_city was provided
            if ctx_norm:
                candidates_in_city = [
                    c for c in valid_candidates
                    if (c.city and ctx_norm in c.city.lower()) or (ctx_norm in c.formatted_address.lower())
                ]
                if not candidates_in_city:
                    # Locality mismatch: venue returned by provider is in another city
                    first_city = valid_candidates[0].city or valid_candidates[0].state or "another location"
                    res = ResolvedLocation(
                        query=query,
                        display_name=f"{query.title()} (Locality Mismatch)",
                        resolved_address=None,
                        city=context_city,
                        state="India",
                        country="India",
                        latitude=None,
                        longitude=None,
                        provider=self.geocoding_provider.provider_name,
                        confidence=0.0,
                        is_cached=False,
                        requires_user_clarification=True,
                        candidates=valid_candidates,
                        resolution_error=(
                            f"Location clarification required: Venue '{query}' was found in {first_city}, which does not match requested city '{context_city}'. "
                            f"Please clarify the intended location."
                        ),
                    )
                    self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
                    return res
                usable_candidates = candidates_in_city
            else:
                usable_candidates = valid_candidates

            # C. Ambiguity check: multiple distinct candidates without a single dominant match
            distinct_locations = {c.formatted_address for c in usable_candidates}
            if len(usable_candidates) > 1 and len(distinct_locations) > 1 and not ctx_norm:
                clarification_options = [c.formatted_address for c in usable_candidates[:5]]
                res = ResolvedLocation(
                    query=query,
                    display_name=f"{query.title()} (Ambiguous Venue)",
                    resolved_address=None,
                    city="Multiple Cities",
                    state="India",
                    country="India",
                    latitude=None,
                    longitude=None,
                    provider=self.geocoding_provider.provider_name,
                    confidence=0.40,
                    is_cached=False,
                    requires_user_clarification=True,
                    clarification_options=clarification_options,
                    candidates=usable_candidates,
                    resolution_error=f"Multiple distinct locations found matching '{query}'. Please specify the city or locality.",
                )
                self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
                return res

            # D. Select best candidate
            best = usable_candidates[0]
            res = ResolvedLocation(
                query=query,
                display_name=best.place_name,
                resolved_address=best.formatted_address,
                city=best.city or context_city or "Unknown",
                state=best.state or "India",
                country=best.country or "India",
                latitude=best.latitude,
                longitude=best.longitude,
                provider=best.provider,
                provider_place_id=best.provider_place_id,
                confidence=best.confidence,
                is_cached=False,
                requires_user_clarification=False,
                candidates=usable_candidates,
            )
            self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
            return res

        # 4. Check for Ambiguous Venues without city context in local registry
        if q_norm == "tidel park" and not ctx_norm:
            clarification_options = [
                "Tidel Park, Taramani, Chennai (OMR IT Corridor)",
                "TIDEL Park Pattabiram, Chennai/Tiruvallur District",
                "TIDEL Park Coimbatore, ELCOT SEZ",
                "TIDEL / ELCOT IT Park, Madurai",
                "TIDEL Park Trichy, Panjappur",
            ]
            res = ResolvedLocation(
                query=query,
                display_name="Tidel Park (Ambiguous Location)",
                resolved_address=None,
                city="Multiple Cities",
                state="Tamil Nadu",
                country="India",
                latitude=None,
                longitude=None,
                provider="RailSathi Disambiguation Engine",
                confidence=0.40,
                is_cached=False,
                requires_user_clarification=True,
                clarification_options=clarification_options,
                resolution_error="Venue name 'Tidel Park' has multiple locations across Tamil Nadu. Please specify the locality or city.",
            )
            self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
            return res

        # 5. Match against Local Verified Venue Registry (Fallback)
        matched_venue: Optional[dict[str, Any]] = None

        # Exact keyword match
        for key, vdata in VENUE_REGISTRY.items():
            if q_norm in [k.lower() for k in vdata["keywords"]] or q_norm == key.lower():
                matched_venue = vdata
                break

        # If not exact keyword match, check if query contains locality clues
        if not matched_venue:
            if "pattabiram" in q_norm:
                matched_venue = VENUE_REGISTRY.get("tidel park, pattabiram")
            elif "coimbatore" in q_norm or (ctx_norm == "coimbatore" and "tidel" in q_norm):
                matched_venue = VENUE_REGISTRY.get("tidel park, coimbatore")
            elif "madurai" in q_norm or (ctx_norm == "madurai" and ("tidel" in q_norm or "elcot" in q_norm)):
                matched_venue = VENUE_REGISTRY.get("tidel park, madurai")
            elif "trichy" in q_norm or "tiruchirappalli" in q_norm or (ctx_norm in ["trichy", "tiruchirappalli"] and "tidel" in q_norm):
                matched_venue = VENUE_REGISTRY.get("tidel park, tiruchirappalli")
            elif ("chennai" in q_norm or ctx_norm == "chennai" or "taramani" in q_norm or "omr" in q_norm) and "tidel" in q_norm:
                matched_venue = VENUE_REGISTRY.get("tidel park, taramani, chennai")

        # Check other verified venues
        if not matched_venue:
            for key, vdata in VENUE_REGISTRY.items():
                for kw in vdata["keywords"]:
                    if kw in q_norm or (q_norm in kw and len(q_norm) > 4):
                        if "pattabiram" in q_norm and "taramani" in vdata["canonical_name"].lower():
                            continue
                        matched_venue = vdata
                        break
                if matched_venue:
                    break

        if matched_venue:
            res = ResolvedLocation(
                query=query,
                display_name=matched_venue["canonical_name"],
                resolved_address=matched_venue["resolved_address"],
                city=matched_venue["city"],
                state=matched_venue["state"],
                country="India",
                latitude=matched_venue["latitude"],
                longitude=matched_venue["longitude"],
                provider="RailSathi Venue Registry (Verified)",
                confidence=0.98,
                is_cached=False,
                requires_user_clarification=False,
            )
            self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
            return res

        # 6. Check City Centroids Registry (only if query directly targets a city)
        for c_key, c_data in CITY_CENTROIDS.items():
            if q_norm == c_key or q_norm in [f"in {c_key}", f"to {c_key}", f"{c_key} city", f"{c_key} center", f"{c_key} central"]:
                res = ResolvedLocation(
                    query=query,
                    display_name=f"{c_data['city']} City Center",
                    resolved_address=f"{c_data['city']}, {c_data['state']}, India",
                    city=c_data["city"],
                    state=c_data["state"],
                    country="India",
                    latitude=c_data["lat"],
                    longitude=c_data["lon"],
                    provider="RailSathi City Centroid Registry",
                    confidence=0.85,
                    is_cached=False,
                    requires_user_clarification=False,
                )
                self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
                return res

        # 7. Fallback for completely unknown / unverified venue:
        # DO NOT silently substitute city centroid coordinates!
        city_guess = context_city or "Unknown"
        res = ResolvedLocation(
            query=query,
            display_name=f"{query.title()} (Unverified Venue)",
            resolved_address=None,
            city=city_guess,
            state="India",
            country="India",
            latitude=None,
            longitude=None,
            provider=f"RailSathi Heuristic Unverified ({self.geocoding_provider.provider_name})",
            confidence=0.0,
            is_cached=False,
            requires_user_clarification=True,
            resolution_error=f"Venue '{query}' could not be verified with coordinates by geocoding provider. Please specify landmark or address.",
        )
        self.cache.put_geocoding(q_norm, res.model_dump(), ctx_norm)
        return res

    def detect_location_conflict(
        self,
        venue: str,
        destination_city: Optional[str],
    ) -> tuple[bool, Optional[str]]:
        """
        Detect if there is a spatial/geographical conflict between a known venue's city and the user's destination city.
        Returns (has_conflict, clarification_question).
        """
        if not destination_city or not venue:
            return False, None

        q_norm = venue.strip().lower()
        dest_city_norm = destination_city.strip()

        # If venue and destination city strings are identical or one contains the other, no conflict
        if q_norm == dest_city_norm.lower() or dest_city_norm.lower() in q_norm:
            return False, None

        resolved = self.resolve_location(venue, context_city=destination_city)
        if not resolved.latitude or not resolved.city:
            return False, None

        if resolved.city.lower() == dest_city_norm.lower():
            return False, None

        dest_loc = self.resolve_location(dest_city_norm)
        if not dest_loc.latitude or not dest_loc.longitude:
            return False, None

        dist_km = calculate_haversine_distance_km(
            resolved.latitude, resolved.longitude,
            dest_loc.latitude, dest_loc.longitude,
        )

        if dist_km > 50.0:
            question = (
                f"Location clarification required: Your specified venue '{venue}' is located in {resolved.city} "
                f"(approximately {int(dist_km)} km from '{dest_city_norm}'). "
                f"Did you mean a meeting in {resolved.city} (e.g. {resolved.display_name}), "
                f"or a destination in {dest_city_norm}?"
            )
            return True, question

        return False, None

    def find_nearby_stations(
        self,
        city_or_location: str | ResolvedLocation,
        max_distance_km: float = 50.0,
        filter_intercity: bool = True,
    ) -> list[StationCandidate]:
        """
        Stage C: Find candidate railway stations serving an origin or destination venue.
        Filters out pure suburban/MRTS halts when filter_intercity=True.
        Ranks candidates using real station coordinates and estimated travel time.
        """
        if isinstance(city_or_location, str):
            loc = self.resolve_location(city_or_location)
        else:
            loc = city_or_location

        if loc.latitude is None or loc.longitude is None:
            logger.warning(f"Cannot find nearby stations for location without coordinates: {loc.query}")
            return []

        target_city = loc.city.lower()
        candidates: list[StationCandidate] = []

        for code, info in STATION_REGISTRY.items():
            # If intercity trains required, skip suburban-only / MRTS stops
            if filter_intercity and not info.get("supports_intercity", True):
                continue

            st_city = info["city"].lower()
            dist = calculate_haversine_distance_km(
                loc.latitude, loc.longitude,
                info["latitude"], info["longitude"],
            )

            is_same_metro = (
                st_city == target_city
                or (target_city == "bengaluru" and st_city in ["bengaluru", "bangalore"])
                or (target_city == "delhi" and st_city in ["delhi", "new delhi"])
                or (target_city == "hyderabad" and st_city in ["hyderabad", "secunderabad"])
                or (target_city == "chennai" and st_city in ["chennai", "tiruvallur", "kanchipuram", "chengalpattu"])
            )

            if is_same_metro or dist <= max_distance_km:
                est_mins = estimate_urban_travel_time_minutes(dist)
                candidates.append(StationCandidate(
                    station_code=code,
                    station_name=info["station_name"],
                    city=info["city"],
                    latitude=info["latitude"],
                    longitude=info["longitude"],
                    distance_to_venue_km=dist,
                    estimated_last_mile_minutes=est_mins,
                    last_mile_mode="cab",
                    is_major_hub=info["is_major_hub"],
                    station_type=info.get("station_type", "major_intercity_terminal"),
                    supports_intercity=info.get("supports_intercity", True),
                    provider="RailSathi Station Registry",
                ))

        # Sort candidate stations: major terminals first, then closest distance
        candidates.sort(key=lambda s: (not s.is_major_hub, s.distance_to_venue_km or 999.0))
        return candidates

    def estimate_last_mile(
        self,
        station_code: str,
        destination_venue: str,
        venue_location: Optional[ResolvedLocation] = None,
    ) -> LastMileEstimate:
        """
        Stage D: Calculate or retrieve deterministic last-mile journey duration and distance.
        Uses cached route estimates if available, or delegates to the injected RoutingProvider.
        """
        self.routing_requests_count += 1
        st_info = STATION_REGISTRY.get(station_code.upper())
        if not st_info:
            return LastMileEstimate(
                origin_station_code=station_code,
                destination_venue=destination_venue,
                distance_km=None,
                duration_minutes=None,
                transit_mode="cab",
                confidence="unknown",
                provider="RailSathi Heuristic Fallback",
                source_type="unknown",
                is_heuristic=True,
                verified_at="2026-10-10",
            )

        if not venue_location:
            venue_location = self.resolve_location(destination_venue, context_city=st_info["city"])

        # If venue has no valid coordinates, return unknown duration (not zero)
        if venue_location.latitude is None or venue_location.longitude is None:
            return LastMileEstimate(
                origin_station_code=station_code,
                destination_venue=venue_location.display_name,
                distance_km=None,
                duration_minutes=None,
                transit_mode="cab",
                confidence="unknown",
                provider="Missing Destination Coordinates",
                source_type="unknown",
                is_heuristic=True,
                verified_at="2026-10-10",
            )

        # Check routing cache
        route_key = f"{station_code.upper()}:{venue_location.latitude:.4f},{venue_location.longitude:.4f}"
        cached_route = self.cache.get_routing(route_key)
        if cached_route:
            self.routing_cache_hits_count += 1
            return LastMileEstimate(
                origin_station_code=station_code,
                destination_venue=venue_location.display_name,
                distance_km=cached_route["distance_km"],
                duration_minutes=cached_route["duration_minutes"],
                transit_mode=cached_route.get("transit_mode", "cab"),
                confidence=cached_route.get("confidence", "cached_estimate"),
                provider=cached_route.get("provider", "RailSathi Routing Cache"),
                source_type="cached_route",
                is_heuristic=cached_route.get("is_heuristic", True),
                is_cached=True,
                verified_at="2026-10-10",
            )

        # Calculate using injected routing provider
        route_res = self.routing_provider.calculate_route(
            origin_lat=st_info["latitude"],
            origin_lon=st_info["longitude"],
            dest_lat=venue_location.latitude,
            dest_lon=venue_location.longitude,
            transit_mode="cab",
        )

        road_dist_km = route_res["distance_km"]
        duration_mins = route_res["duration_minutes"]
        is_heuristic = route_res.get("is_heuristic", True)
        source_type = route_res.get("source_type", "heuristic_urban_model")
        provider_name = route_res.get("provider", self.routing_provider.provider_name)

        # Store in routing cache
        self.cache.put_routing(
            route_key=route_key,
            distance_km=road_dist_km,
            duration_minutes=duration_mins,
            transit_mode="cab",
            provider=provider_name,
            confidence=route_res.get("confidence", "verified_estimate"),
        )

        return LastMileEstimate(
            origin_station_code=station_code,
            destination_venue=venue_location.display_name,
            distance_km=road_dist_km,
            duration_minutes=duration_mins,
            transit_mode="cab",
            confidence=route_res.get("confidence", "verified_estimate"),
            provider=provider_name,
            source_type=source_type,
            is_heuristic=is_heuristic,
            is_cached=False,
            verified_at="2026-10-10",
        )
