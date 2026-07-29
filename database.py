import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("CAR_AI_DATABASE_PATH", BASE_DIR / "data" / "car_company.db"))
TIME_SLOTS = ("10:00 AM", "12:00 PM", "02:00 PM", "04:00 PM")


SCHEMA = """
CREATE TABLE IF NOT EXISTS dealerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('ARENA', 'NEXA')),
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    pincode TEXT NOT NULL,
    phone TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS car_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('ARENA', 'NEXA')),
    body_type TEXT NOT NULL,
    fuel_types TEXT NOT NULL,
    transmission_types TEXT NOT NULL,
    seating_capacity INTEGER NOT NULL,
    starting_price INTEGER NOT NULL,
    maximum_price INTEGER,
    price_note TEXT,
    description TEXT NOT NULL,
    official_url TEXT,
    price_as_of TEXT NOT NULL,
    launch_date TEXT,
    is_recent INTEGER NOT NULL DEFAULT 0 CHECK (is_recent IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dealer_sales_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealership_id INTEGER NOT NULL REFERENCES dealerships(id),
    car_model_id INTEGER NOT NULL REFERENCES car_models(id),
    available_quantity INTEGER NOT NULL DEFAULT 0 CHECK (available_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0),
    expected_delivery_days INTEGER NOT NULL DEFAULT 7 CHECK (expected_delivery_days >= 0),
    inventory_source TEXT NOT NULL DEFAULT 'DEMO_SEED',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dealership_id, car_model_id)
);

CREATE TABLE IF NOT EXISTS test_drive_vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealership_id INTEGER NOT NULL REFERENCES dealerships(id),
    car_model_id INTEGER NOT NULL REFERENCES car_models(id),
    fleet_code TEXT NOT NULL UNIQUE,
    registration_masked TEXT NOT NULL,
    fuel_type TEXT NOT NULL,
    transmission TEXT NOT NULL,
    color TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_drive_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealership_id INTEGER NOT NULL REFERENCES dealerships(id),
    car_model_id INTEGER NOT NULL REFERENCES car_models(id),
    availability_date TEXT NOT NULL,
    time_slot TEXT NOT NULL,
    total_quantity INTEGER NOT NULL CHECK (total_quantity >= 0),
    booked_quantity INTEGER NOT NULL DEFAULT 0 CHECK (booked_quantity >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dealership_id, car_model_id, availability_date, time_slot),
    CHECK (booked_quantity <= total_quantity)
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    mobile TEXT NOT NULL UNIQUE,
    email TEXT,
    address_line TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    pincode TEXT NOT NULL,
    consent_given INTEGER NOT NULL CHECK (consent_given IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL CHECK (document_type IN ('DRIVING_LICENSE', 'AADHAAR', 'PAN')),
    document_last4 TEXT NOT NULL,
    document_number_hash TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, document_type)
);

CREATE TABLE IF NOT EXISTS test_drive_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    dealership_id INTEGER NOT NULL REFERENCES dealerships(id),
    car_model_id INTEGER NOT NULL REFERENCES car_models(id),
    availability_id INTEGER NOT NULL REFERENCES test_drive_availability(id),
    booking_date TEXT NOT NULL,
    time_slot TEXT NOT NULL,
    location_type TEXT NOT NULL CHECK (location_type IN ('HOME', 'DEALERSHIP')),
    test_drive_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')),
    customer_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dealerships_city ON dealerships(city, active);
CREATE INDEX IF NOT EXISTS idx_sales_inventory_dealer ON dealer_sales_inventory(dealership_id);
CREATE INDEX IF NOT EXISTS idx_availability_lookup
    ON test_drive_availability(dealership_id, car_model_id, availability_date);
CREATE INDEX IF NOT EXISTS idx_test_drive_bookings_customer ON test_drive_bookings(customer_id);
CREATE INDEX IF NOT EXISTS idx_test_drive_bookings_slot ON test_drive_bookings(availability_id, status);
"""


DEALERS = [
    {
        "code": "ARENA-COMPETENT-CP",
        "name": "Competent Automobiles Co. Ltd.",
        "channel": "ARENA",
        "address": "F-14, Competent House, Middle Circle, Connaught Place",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110001",
        "phone": None,
    },
    {
        "code": "ARENA-TRS-INDRAPRASTHA",
        "name": "T.R. Sawhney Motors Pvt. Ltd.",
        "channel": "ARENA",
        "address": "Main Ring Road, Indraprastha",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110002",
        "phone": None,
    },
    {
        "code": "ARENA-MAGIC-KAROLBAGH",
        "name": "Magic Auto Pvt. Ltd.",
        "channel": "ARENA",
        "address": "7/56, Desh Bandhu Gupta Road, Karol Bagh",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110005",
        "phone": None,
    },
    {
        "code": "NEXA-TRS-DARYAGANJ",
        "name": "T.R. Sawhney Automobiles Pvt. Ltd.",
        "channel": "NEXA",
        "address": "11/3, Laxman House, Asaf Ali Road, Near Delite Cinema, Daryaganj",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110002",
        "phone": "9999525747",
    },
    {
        "code": "NEXA-SINGLA-LAJPAT",
        "name": "Singla Link Agency Pvt. Ltd.",
        "channel": "NEXA",
        "address": "30-B, Ring Road, Lajpat Nagar-IV",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110024",
        "phone": "8826892688",
    },
    {
        "code": "NEXA-RANA-EOK",
        "name": "Rana Motors Pvt. Ltd.",
        "channel": "NEXA",
        "address": "E-9, East of Kailash",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110065",
        "phone": "9999788886",
    },
    {
        "code": "NEXA-DWARKA-DEMO",
        "name": "NEXA Dwarka Customer Experience Centre",
        "channel": "NEXA",
        "address": "Sector 12, Dwarka, New Delhi",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "phone": "01145001212",
    },
    {
        "code": "ARENA-DWARKA-DEMO",
        "name": "Maruti Suzuki ARENA Dwarka Centre",
        "channel": "ARENA",
        "address": "Sector 10, Dwarka, New Delhi",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "phone": "01145001010",
    },
]


MODELS = [
    ("SPRESSO", "S-Presso", "ARENA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 349900, None, None, "Compact city car with a high seating position."),
    ("ALTO-K10", "Alto K10", "ARENA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 369900, None, None, "Efficient entry hatchback for everyday city driving."),
    ("CELERIO", "Celerio", "ARENA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 469900, None, None, "Practical hatchback focused on efficiency and easy driving."),
    ("WAGONR", "WagonR", "ARENA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 498900, None, None, "Tall-boy hatchback with flexible cabin space."),
    ("EECO", "Eeco", "ARENA", "Van", ["Petrol", "S-CNG"], ["Manual"], 5, 523400, None, None, "Versatile passenger van for families and utility needs."),
    ("SWIFT", "Swift", "ARENA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 578900, None, None, "Sporty hatchback designed for city and highway use."),
    ("DZIRE", "Dzire", "ARENA", "Sedan", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 625600, None, None, "Compact sedan with a comfortable cabin and practical boot."),
    ("BREZZA", "Brezza", "ARENA", "SUV", ["Petrol", "S-CNG"], ["Manual", "Automatic"], 5, 739900, None, None, "Compact SUV with a commanding driving position."),
    ("ERTIGA", "Ertiga", "ARENA", "MPV", ["Petrol", "S-CNG"], ["Manual", "Automatic"], 7, 885000, None, None, "Three-row family MPV with flexible seating."),
    ("VICTORIS", "Victoris", "ARENA", "SUV", ["Petrol", "Strong Hybrid", "S-CNG"], ["Manual", "Automatic"], 5, 1049900, None, None, "Feature-rich SUV in the current Arena range."),
    ("BALENO", "Baleno", "NEXA", "Hatchback", ["Petrol", "S-CNG"], ["Manual", "AGS"], 5, 598900, 917000, None, "Premium hatchback with a spacious cabin."),
    ("FRONX", "Fronx", "NEXA", "SUV", ["Petrol", "Turbo Petrol", "S-CNG"], ["Manual", "AGS", "Automatic"], 5, 684900, 1198000, None, "Compact crossover with coupe-inspired styling."),
    ("GRAND-VITARA", "Grand Vitara", "NEXA", "SUV", ["Petrol", "Strong Hybrid", "S-CNG"], ["Manual", "Automatic"], 5, 1076500, 1972000, None, "Mid-size SUV with hybrid and all-wheel-drive options."),
    ("XL6", "XL6", "NEXA", "MPV", ["Petrol", "S-CNG"], ["Manual", "Automatic"], 6, 1157300, 1453000, None, "Premium six-seat MPV with captain seats."),
    ("JIMNY", "Jimny", "NEXA", "SUV", ["Petrol"], ["Manual", "Automatic"], 4, 1239000, 1452000, None, "Compact 4x4 SUV designed for off-road capability."),
    ("INVICTO", "Invicto", "NEXA", "MPV", ["Strong Hybrid"], ["Automatic"], 7, 2497400, 2870000, None, "Premium strong-hybrid multi-purpose vehicle."),
    ("EVITARA", "e VITARA", "NEXA", "Electric SUV", ["Electric"], ["Automatic"], 5, 1099000, None, "Introductory BaaS price; battery EMI applies separately.", "Maruti Suzuki's electric SUV with battery-as-a-service pricing."),
]


MODEL_URLS = {
    "ARENA": "https://www.marutisuzuki.com/arena",
    "NEXA": "https://www.nexaexperience.com/e-brochure",
}

RECENT_MODEL_LAUNCHES = {
    "EVITARA": "2026-02-17",
    "VICTORIS": "2025-09-03",
    "DZIRE": "2024-11-11",
    "SWIFT": "2024-05-09",
}


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=15.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with db_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        _apply_schema_migrations(connection)
        _seed_catalog(connection)
        _ensure_test_drive_availability(connection)
        connection.commit()

def _apply_schema_migrations(connection: sqlite3.Connection) -> None:
    car_model_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(car_models)").fetchall()
    }
    if "launch_date" not in car_model_columns:
        connection.execute("ALTER TABLE car_models ADD COLUMN launch_date TEXT")
    if "is_recent" not in car_model_columns:
        connection.execute(
            "ALTER TABLE car_models ADD COLUMN is_recent INTEGER NOT NULL DEFAULT 0"
        )


def _seed_catalog(connection: sqlite3.Connection) -> None:
    for dealer in DEALERS:
        connection.execute(
            """
            INSERT INTO dealerships (code, name, channel, address, city, state, pincode, phone)
            VALUES (:code, :name, :channel, :address, :city, :state, :pincode, :phone)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                channel = excluded.channel,
                address = excluded.address,
                city = excluded.city,
                state = excluded.state,
                pincode = excluded.pincode,
                phone = excluded.phone,
                active = 1
            """,
            dealer,
        )

    for model in MODELS:
        (
            code, name, channel, body_type, fuels, transmissions, seats,
            starting_price, maximum_price, price_note, description,
        ) = model
        connection.execute(
            """
            INSERT INTO car_models (
                code, name, channel, body_type, fuel_types, transmission_types,
                seating_capacity, starting_price, maximum_price, price_note,
                description, official_url, price_as_of, launch_date, is_recent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                channel = excluded.channel,
                body_type = excluded.body_type,
                fuel_types = excluded.fuel_types,
                transmission_types = excluded.transmission_types,
                seating_capacity = excluded.seating_capacity,
                starting_price = excluded.starting_price,
                maximum_price = excluded.maximum_price,
                price_note = excluded.price_note,
                description = excluded.description,
                official_url = excluded.official_url,
                price_as_of = excluded.price_as_of,
                launch_date = excluded.launch_date,
                is_recent = excluded.is_recent,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                code, name, channel, body_type, json.dumps(fuels),
                json.dumps(transmissions), seats, starting_price, maximum_price,
                price_note, description, MODEL_URLS[channel], "2026-07-29",
                RECENT_MODEL_LAUNCHES.get(code),
                int(code in RECENT_MODEL_LAUNCHES),
            ),
        )

    dealers = connection.execute("SELECT id, code, channel FROM dealerships WHERE active = 1").fetchall()
    models = connection.execute(
        "SELECT id, code, channel, fuel_types, transmission_types FROM car_models WHERE active = 1"
    ).fetchall()
    popular_codes = {"SWIFT", "BREZZA", "ERTIGA", "BALENO", "FRONX", "GRAND-VITARA"}
    colors = ("Pearl White", "Metallic Grey", "Nexa Blue", "Splendid Silver")

    for dealer_index, dealer in enumerate(dealers):
        for model_index, model in enumerate(models):
            if dealer["channel"] != model["channel"]:
                continue

            sale_quantity = 2 + ((dealer["id"] + model["id"]) % 7)
            delivery_days = 2 + ((dealer["id"] * model["id"]) % 12)
            connection.execute(
                """
                INSERT INTO dealer_sales_inventory (
                    dealership_id, car_model_id, available_quantity,
                    reserved_quantity, expected_delivery_days, inventory_source
                )
                VALUES (?, ?, ?, 0, ?, 'DEMO_SEED')
                ON CONFLICT(dealership_id, car_model_id) DO NOTHING
                """,
                (dealer["id"], model["id"], sale_quantity, delivery_days),
            )

            fleet_quantity = 2 if model["code"] in popular_codes else 1
            fuels = json.loads(model["fuel_types"])
            transmissions = json.loads(model["transmission_types"])
            for fleet_index in range(fleet_quantity):
                fleet_code = f"{dealer['code']}-{model['code']}-{fleet_index + 1}"
                connection.execute(
                    """
                    INSERT INTO test_drive_vehicles (
                        dealership_id, car_model_id, fleet_code, registration_masked,
                        fuel_type, transmission, color
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fleet_code) DO UPDATE SET active = 1
                    """,
                    (
                        dealer["id"],
                        model["id"],
                        fleet_code,
                        f"DL ** ** {model['id']:04d}",
                        fuels[fleet_index % len(fuels)],
                        transmissions[fleet_index % len(transmissions)],
                        colors[(dealer_index + model_index + fleet_index) % len(colors)],
                    ),
                )


def _ensure_test_drive_availability(connection: sqlite3.Connection, days: int = 30) -> None:
    fleet_counts = connection.execute(
        """
        SELECT dealership_id, car_model_id, COUNT(*) AS vehicle_count
        FROM test_drive_vehicles
        WHERE active = 1
        GROUP BY dealership_id, car_model_id
        """
    ).fetchall()
    start_date = date.today()
    for day_offset in range(days + 1):
        availability_date = (start_date + timedelta(days=day_offset)).isoformat()
        for fleet in fleet_counts:
            for time_slot in TIME_SLOTS:
                connection.execute(
                    """
                    INSERT INTO test_drive_availability (
                        dealership_id, car_model_id, availability_date,
                        time_slot, total_quantity, booked_quantity
                    )
                    VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(dealership_id, car_model_id, availability_date, time_slot)
                    DO UPDATE SET
                        total_quantity = CASE
                            WHEN test_drive_availability.booked_quantity <= excluded.total_quantity
                            THEN excluded.total_quantity
                            ELSE test_drive_availability.total_quantity
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        fleet["dealership_id"],
                        fleet["car_model_id"],
                        availability_date,
                        time_slot,
                        fleet["vehicle_count"],
                    ),
                )


def list_dealerships(city: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT id, code, name, channel, address, city, state, pincode, phone
        FROM dealerships
        WHERE active = 1
    """
    params: List[Any] = []
    if city:
        query += " AND lower(city) = lower(?)"
        params.append(city.strip())
    query += " ORDER BY channel, name"
    with db_connection() as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def list_models(dealership_id: Optional[int] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT
            m.id, m.code, m.name, m.channel, m.body_type, m.fuel_types,
            m.transmission_types, m.seating_capacity, m.starting_price,
            m.maximum_price, m.price_note, m.description, m.official_url,
            m.price_as_of, m.launch_date, m.is_recent,
            i.available_quantity AS sale_quantity,
            i.reserved_quantity,
            i.expected_delivery_days,
            COALESCE(f.test_drive_quantity, 0) AS test_drive_quantity
        FROM car_models m
        LEFT JOIN dealer_sales_inventory i ON i.car_model_id = m.id
        LEFT JOIN (
            SELECT dealership_id, car_model_id, COUNT(*) AS test_drive_quantity
            FROM test_drive_vehicles
            WHERE active = 1
            GROUP BY dealership_id, car_model_id
        ) f ON f.car_model_id = m.id AND f.dealership_id = i.dealership_id
        WHERE m.active = 1
    """
    params: List[Any] = []
    if dealership_id is not None:
        query += " AND i.dealership_id = ?"
        params.append(dealership_id)
    else:
        query = """
            SELECT
                m.id, m.code, m.name, m.channel, m.body_type, m.fuel_types,
                m.transmission_types, m.seating_capacity, m.starting_price,
                m.maximum_price, m.price_note, m.description, m.official_url,
                m.price_as_of, m.launch_date, m.is_recent,
                COALESCE(i.sale_quantity, 0) AS sale_quantity,
                COALESCE(i.reserved_quantity, 0) AS reserved_quantity,
                i.expected_delivery_days,
                COALESCE(tv.test_drive_quantity, 0) AS test_drive_quantity
            FROM car_models m
            LEFT JOIN (
                SELECT
                    car_model_id,
                    SUM(available_quantity) AS sale_quantity,
                    SUM(reserved_quantity) AS reserved_quantity,
                    MIN(expected_delivery_days) AS expected_delivery_days
                FROM dealer_sales_inventory
                GROUP BY car_model_id
            ) i ON i.car_model_id = m.id
            LEFT JOIN (
                SELECT car_model_id, COUNT(*) AS test_drive_quantity
                FROM test_drive_vehicles
                WHERE active = 1
                GROUP BY car_model_id
            ) tv ON tv.car_model_id = m.id
            WHERE m.active = 1
        """
    query += " ORDER BY m.channel, m.starting_price, m.name"

    with db_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["fuel_types"] = json.loads(item["fuel_types"])
        item["transmission_types"] = json.loads(item["transmission_types"])
        results.append(item)
    return results


def get_availability(dealership_id: int, car_model_id: int, booking_date: str) -> List[Dict[str, Any]]:
    requested_date = date.fromisoformat(booking_date)
    if requested_date < date.today() or requested_date > date.today() + timedelta(days=30):
        raise ValueError("Test-drive date must be between today and 30 days from today.")

    with db_connection() as connection:
        _ensure_test_drive_availability(connection)
        connection.commit()
        rows = connection.execute(
            """
            SELECT id, time_slot, total_quantity, booked_quantity,
                   total_quantity - booked_quantity AS available_quantity
            FROM test_drive_availability
            WHERE dealership_id = ? AND car_model_id = ? AND availability_date = ?
            ORDER BY id
            """,
            (dealership_id, car_model_id, booking_date),
        ).fetchall()
    return [dict(row) for row in rows]

def get_sales_concierge_context(city: str = "New Delhi") -> Dict[str, Any]:
    """Build fresh model/dealer/fleet context for the sales LLM from SQLite."""
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=7)).isoformat()
    with db_connection() as connection:
        _ensure_test_drive_availability(connection)
        connection.commit()
        rows = connection.execute(
            """
            SELECT
                m.id, m.code, m.name, m.channel, m.body_type, m.starting_price,
                m.maximum_price, m.price_note, m.launch_date,
                CASE
                    WHEN m.launch_date IS NOT NULL
                         AND date(m.launch_date) >= date(?, '-30 months')
                    THEN 1 ELSE 0
                END AS is_recent,
                m.fuel_types, m.transmission_types,
                (
                    SELECT COALESCE(SUM(i.available_quantity), 0)
                    FROM dealer_sales_inventory i
                    JOIN dealerships d ON d.id = i.dealership_id
                    WHERE i.car_model_id = m.id
                      AND d.active = 1
                      AND lower(d.city) = lower(?)
                ) AS sale_quantity,
                (
                    SELECT COUNT(*)
                    FROM test_drive_vehicles tv
                    JOIN dealerships d ON d.id = tv.dealership_id
                    WHERE tv.car_model_id = m.id
                      AND tv.active = 1
                      AND d.active = 1
                      AND lower(d.city) = lower(?)
                ) AS test_drive_vehicle_count,
                (
                    SELECT COUNT(*)
                    FROM test_drive_availability a
                    JOIN dealerships d ON d.id = a.dealership_id
                    WHERE a.car_model_id = m.id
                      AND a.availability_date BETWEEN ? AND ?
                      AND a.booked_quantity < a.total_quantity
                      AND d.active = 1
                      AND lower(d.city) = lower(?)
                ) AS available_slots_next_7_days
            FROM car_models m
            WHERE m.active = 1
              AND EXISTS (
                  SELECT 1
                  FROM dealer_sales_inventory i
                  JOIN dealerships d ON d.id = i.dealership_id
                  WHERE i.car_model_id = m.id
                    AND d.active = 1
                    AND lower(d.city) = lower(?)
              )
            ORDER BY is_recent DESC, m.launch_date DESC, m.starting_price
            """,
            (today, city, city, today, horizon, city, city),
        ).fetchall()
        dealer_rows = connection.execute(
            """
            SELECT
                d.id, d.name, d.channel, d.address, d.city, d.pincode,
                GROUP_CONCAT(m.name, ', ') AS test_drive_models
            FROM dealerships d
            JOIN test_drive_vehicles tv ON tv.dealership_id = d.id AND tv.active = 1
            JOIN car_models m ON m.id = tv.car_model_id
            WHERE d.active = 1 AND lower(d.city) = lower(?)
            GROUP BY d.id
            ORDER BY d.channel, d.name
            """,
            (city,),
        ).fetchall()

    models: List[Dict[str, Any]] = []
    for row in rows:
        model = dict(row)
        model["fuel_types"] = json.loads(model["fuel_types"])
        model["transmission_types"] = json.loads(model["transmission_types"])
        model["ready_for_test_drive"] = (
            model["test_drive_vehicle_count"] > 0
            and model["available_slots_next_7_days"] > 0
        )
        models.append(model)

    recent_ready = [
        model for model in models
        if model["is_recent"] and model["ready_for_test_drive"]
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "city": city,
        "catalog_price_as_of": "2026-07-29",
        "inventory_type": "local_demo_inventory",
        "recent_models_ready_for_test_drive": recent_ready,
        "all_models_ready_for_test_drive": [
            model for model in models if model["ready_for_test_drive"]
        ],
        "dealerships": [dict(row) for row in dealer_rows],
        "booking_requirements": {
            "customer_fields": ["full name", "mobile", "complete address"],
            "schedule_fields": ["model", "dealership", "date", "time", "home or dealership"],
            "documents_to_carry": [
                "original valid driving licence",
                "original Aadhaar or PAN",
            ],
            "document_collection": "Do not collect document numbers in the app. Remind the customer to keep the originals available for both dealership and home test drives.",
            "completion_action": "Use the in-app Book Test Drive form; do not send the customer to another website.",
        },
    }


def _normalize_document(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def _document_fingerprint(value: str) -> str:
    normalized = _normalize_document(value)
    pepper = os.getenv("DOCUMENT_HASH_PEPPER", "local-demo-pepper")
    return hashlib.sha256(f"{pepper}:{normalized}".encode("utf-8")).hexdigest()


def create_test_drive_booking(payload: Dict[str, Any]) -> Dict[str, Any]:
    mobile = re.sub(r"\D", "", payload["mobile"])
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    booking_date = str(payload["booking_date"])

    # Voice clients can retry the final turn if audio playback or the network
    # response fails after the transaction commits. Return the already-created
    # booking instead of treating its slot as a new capacity conflict.
    with db_connection() as connection:
        existing_booking = connection.execute(
            """
            SELECT b.reference_id
            FROM test_drive_bookings b
            JOIN customers c ON c.id = b.customer_id
            WHERE c.mobile = ?
              AND b.dealership_id = ?
              AND b.car_model_id = ?
              AND b.booking_date = ?
              AND b.time_slot = ?
              AND b.status = 'CONFIRMED'
            ORDER BY b.created_at DESC
            LIMIT 1
            """,
            (
                mobile,
                payload["dealership_id"],
                payload["car_model_id"],
                booking_date,
                payload["time_slot"],
            ),
        ).fetchone()
    if existing_booking is not None:
        return get_test_drive_booking(existing_booking["reference_id"])

    reference_id = f"TD-{secrets.token_hex(4).upper()}"
    customer_address = ", ".join(
        filter(
            None,
            [
                payload["address_line"].strip(),
                payload["city"].strip(),
                payload["state"].strip(),
                payload["pincode"].strip(),
            ],
        )
    )

    with db_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")

            dealership = connection.execute(
                "SELECT * FROM dealerships WHERE id = ? AND active = 1",
                (payload["dealership_id"],),
            ).fetchone()
            if dealership is None:
                raise LookupError("Selected dealership is not available.")

            model = connection.execute(
                """
                SELECT m.*
                FROM car_models m
                JOIN dealer_sales_inventory i ON i.car_model_id = m.id
                WHERE m.id = ? AND i.dealership_id = ? AND m.active = 1
                """,
                (payload["car_model_id"], payload["dealership_id"]),
            ).fetchone()
            if model is None:
                raise LookupError("Selected car is not available at this dealership.")

            availability = connection.execute(
                """
                SELECT *
                FROM test_drive_availability
                WHERE dealership_id = ? AND car_model_id = ?
                  AND availability_date = ? AND time_slot = ?
                """,
                (
                    payload["dealership_id"],
                    payload["car_model_id"],
                    booking_date,
                    payload["time_slot"],
                ),
            ).fetchone()
            if availability is None:
                raise LookupError("Selected test-drive slot does not exist.")
            if availability["booked_quantity"] >= availability["total_quantity"]:
                raise RuntimeError("Selected test-drive slot is fully booked.")

            existing_customer = connection.execute(
                "SELECT id FROM customers WHERE mobile = ?", (mobile,)
            ).fetchone()
            if existing_customer:
                customer_id = existing_customer["id"]
                connection.execute(
                    """
                    UPDATE customers SET
                        full_name = ?, email = ?, address_line = ?, city = ?,
                        state = ?, pincode = ?, consent_given = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        payload["full_name"].strip(),
                        (payload.get("email") or "").strip() or None,
                        payload["address_line"].strip(),
                        payload["city"].strip(),
                        payload["state"].strip(),
                        payload["pincode"].strip(),
                        customer_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO customers (
                        full_name, mobile, email, address_line, city, state,
                        pincode, consent_given
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        payload["full_name"].strip(),
                        mobile,
                        (payload.get("email") or "").strip() or None,
                        payload["address_line"].strip(),
                        payload["city"].strip(),
                        payload["state"].strip(),
                        payload["pincode"].strip(),
                    ),
                )
                customer_id = cursor.lastrowid

            update = connection.execute(
                """
                UPDATE test_drive_availability
                SET booked_quantity = booked_quantity + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND booked_quantity < total_quantity
                """,
                (availability["id"],),
            )
            if update.rowcount != 1:
                raise RuntimeError("Selected test-drive slot was just booked by another customer.")

            test_drive_address = (
                customer_address if payload["location_type"] == "HOME"
                else f"{dealership['name']}, {dealership['address']}, {dealership['city']}"
            )
            connection.execute(
                """
                INSERT INTO test_drive_bookings (
                    reference_id, customer_id, dealership_id, car_model_id,
                    availability_id, booking_date, time_slot, location_type,
                    test_drive_address, customer_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_id,
                    customer_id,
                    payload["dealership_id"],
                    payload["car_model_id"],
                    availability["id"],
                    booking_date,
                    payload["time_slot"],
                    payload["location_type"],
                    test_drive_address,
                    (payload.get("customer_notes") or "").strip() or None,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return get_test_drive_booking(reference_id)


def get_test_drive_booking(reference_id: str) -> Dict[str, Any]:
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                b.reference_id, b.booking_date, b.time_slot, b.location_type,
                b.test_drive_address, b.status, b.customer_notes, b.created_at,
                c.full_name AS customer_name, c.mobile AS customer_mobile,
                c.email AS customer_email,
                d.name AS dealership_name, d.channel AS dealership_channel,
                d.address AS dealership_address, d.city AS dealership_city,
                m.name AS car_model, m.body_type, m.starting_price,
                dl.document_last4 AS driving_license_last4,
                identity.document_type AS identity_document_type,
                identity.document_last4 AS identity_document_last4
            FROM test_drive_bookings b
            JOIN customers c ON c.id = b.customer_id
            JOIN dealerships d ON d.id = b.dealership_id
            JOIN car_models m ON m.id = b.car_model_id
            LEFT JOIN customer_documents dl
                ON dl.customer_id = c.id AND dl.document_type = 'DRIVING_LICENSE'
            LEFT JOIN customer_documents identity
                ON identity.customer_id = c.id AND identity.document_type IN ('AADHAAR', 'PAN')
            WHERE upper(b.reference_id) = upper(?)
            """,
            (reference_id.strip(),),
        ).fetchone()
    if row is None:
        raise LookupError("Test-drive booking not found.")
    result = dict(row)
    result["document_requirement"] = (
        "Keep the original driving licence and original Aadhaar or PAN available "
        "for the test drive, including home test drives."
    )
    return result


def cancel_test_drive_booking(reference_id: str) -> Dict[str, Any]:
    with db_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            booking = connection.execute(
                "SELECT id, availability_id, status FROM test_drive_bookings WHERE upper(reference_id) = upper(?)",
                (reference_id.strip(),),
            ).fetchone()
            if booking is None:
                raise LookupError("Test-drive booking not found.")
            if booking["status"] == "CANCELLED":
                connection.rollback()
                return get_test_drive_booking(reference_id)
            if booking["status"] != "CONFIRMED":
                raise RuntimeError(f"Only confirmed bookings can be cancelled; current status is {booking['status']}.")

            connection.execute(
                "UPDATE test_drive_bookings SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (booking["id"],),
            )
            connection.execute(
                """
                UPDATE test_drive_availability
                SET booked_quantity = MAX(0, booked_quantity - 1),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (booking["availability_id"],),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return get_test_drive_booking(reference_id)


def database_stats() -> Dict[str, int]:
    tables = (
        "customers",
        "dealerships",
        "car_models",
        "dealer_sales_inventory",
        "test_drive_vehicles",
        "test_drive_availability",
        "test_drive_bookings",
    )
    with db_connection() as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
