"""Safe-field registry for the personal_context skill.

This is the single source of truth for which personal fields may be
retrieved, how they are categorised, and where each value is stored.

Security contract:
    - SAFE_FIELDS is an explicit allowlist — nothing outside it is ever read.
    - SECRET_FIELDS are hard-blocked: even if a value exists in the database,
      retrieval is refused and the database is never queried for them.
    - STORAGE_KEYS maps a safe field to the settings-table key that holds it
      (default: the field name itself). Only allowlisted keys ever reach SQL.

The database remains the source of truth: this module only defines the
retrieval surface. It never invents or populates personal information.
"""

# Logical categories for the personal profile (display/documentation only —
# retrieval is flat: one field at a time).
CATEGORY_ORDER = ("identity", "contact", "education", "skills", "projects", "links", "documents")

FIELD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "identity": ("full_name", "preferred_name"),
    "contact": ("email", "phone"),
    "education": ("college_name", "degree", "branch", "graduation_year"),
    "skills": ("programming_languages", "frameworks", "tools"),
    "projects": ("projects",),
    "links": ("github", "linkedin", "portfolio"),
    "documents": ("resume",),
}

# The complete allowlist of fields the personal_context tool may return.
# Computed from the categories so the two can never drift apart.
SAFE_FIELDS: frozenset[str] = frozenset(
    field for fields in FIELD_CATEGORIES.values() for field in fields
)

# Where each safe field's value lives in the settings key/value table.
# ``github`` reuses the existing github_username key written by the
# user_config skill ("set my github username to ...").
STORAGE_KEYS: dict[str, str] = {
    "github": "github_username",
}

# Human-readable labels for skill replies ("Your GitHub username is ...").
DISPLAY_NAMES: dict[str, str] = {
    "full_name": "full name",
    "preferred_name": "preferred name",
    "college_name": "college name",
    "graduation_year": "graduation year",
    "programming_languages": "programming languages",
    "github": "GitHub username",
    "linkedin": "LinkedIn",
    "portfolio": "portfolio",
    "resume": "resume",
}

# Fields the brain-path skill recognises in a target, mapped to the canonical
# safe field name. ("college" -> "college_name", "github" -> "github", ...)
FIELD_ALIASES: dict[str, str] = {
    "college": "college_name",
    "college_name": "college_name",
    "degree": "degree",
    "branch": "branch",
    "graduation": "graduation_year",
    "graduation_year": "graduation_year",
    "email": "email",
    "phone": "phone",
    "phone_number": "phone",
    "github": "github",
    "linkedin": "linkedin",
    "portfolio": "portfolio",
    "resume": "resume",
    "full_name": "full_name",
    "name": "full_name",
    "preferred_name": "preferred_name",
    "projects": "projects",
}

# Fields that must NEVER be retrievable through this tool, even if a value
# exists in the database: authentication secrets, API keys, tokens,
# government identifiers, financial information, addresses and birth dates.
SECRET_FIELDS: frozenset[str] = frozenset(
    {
        # Authentication & secrets
        "password",
        "passwords",
        "password_hash",
        "secret",
        "secrets",
        "client_secret",
        "api_key",
        "api_keys",
        "apikey",
        "token",
        "tokens",
        "access_token",
        "auth_token",
        "refresh_token",
        # Government identifiers
        "ssn",
        "social_security",
        "aadhaar",
        "pan",
        "passport",
        "passport_number",
        # Personal sensitive attributes
        "date_of_birth",
        "dob",
        "birth_date",
        "address",
        "home_address",
        # Financial
        "bank_account",
        "account_number",
        "credit_card",
        "card_number",
        "cvv",
        "pin",
    }
)

# Never allow a secret field into the safe allowlist.
assert SECRET_FIELDS.isdisjoint(SAFE_FIELDS), "secret fields leaked into SAFE_FIELDS"


def normalize_field(field: str | None) -> str:
    """Lower-case, stripped canonical form of a requested field name."""
    return (field or "").strip().lower()


def storage_key(field: str) -> str:
    """The settings-table key that stores a safe field's value."""
    return STORAGE_KEYS.get(field, field)


def display_name(field: str) -> str:
    """Human-readable label for a safe field."""
    return DISPLAY_NAMES.get(field, field.replace("_", " "))
