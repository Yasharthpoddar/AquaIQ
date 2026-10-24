"""AquaIQ — Verified District-to-State Mapping and State Metadata.

Provides authoritative state identification, 2-letter state codes, display names,
census state codes, and normalization for all 36 Indian States and Union Territories.
"""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

# Authoritative dictionary of India's 36 States and Union Territories
# Keyed by canonical 2-letter ISO/standard state code.
STATES_REGISTRY: Dict[str, Dict[str, str]] = {
    'AN': {'state_id': 'AN', 'name': 'Andaman and Nicobar Islands', 'st_code': '35', 'type': 'UT'},
    'AP': {'state_id': 'AP', 'name': 'Andhra Pradesh', 'st_code': '37', 'type': 'State'},
    'AR': {'state_id': 'AR', 'name': 'Arunachal Pradesh', 'st_code': '12', 'type': 'State'},
    'AS': {'state_id': 'AS', 'name': 'Assam', 'st_code': '18', 'type': 'State'},
    'BR': {'state_id': 'BR', 'name': 'Bihar', 'st_code': '10', 'type': 'State'},
    'CH': {'state_id': 'CH', 'name': 'Chandigarh', 'st_code': '04', 'type': 'UT'},
    'CG': {'state_id': 'CG', 'name': 'Chhattisgarh', 'st_code': '22', 'type': 'State'},
    'DD': {'state_id': 'DD', 'name': 'Dadra and Nagar Haveli and Daman and Diu', 'st_code': '26', 'type': 'UT'},
    'DL': {'state_id': 'DL', 'name': 'Delhi', 'st_code': '07', 'type': 'UT'},
    'GA': {'state_id': 'GA', 'name': 'Goa', 'st_code': '30', 'type': 'State'},
    'GJ': {'state_id': 'GJ', 'name': 'Gujarat', 'st_code': '24', 'type': 'State'},
    'HR': {'state_id': 'HR', 'name': 'Haryana', 'st_code': '06', 'type': 'State'},
    'HP': {'state_id': 'HP', 'name': 'Himachal Pradesh', 'st_code': '02', 'type': 'State'},
    'JK': {'state_id': 'JK', 'name': 'Jammu and Kashmir', 'st_code': '01', 'type': 'UT'},
    'JH': {'state_id': 'JH', 'name': 'Jharkhand', 'st_code': '20', 'type': 'State'},
    'KA': {'state_id': 'KA', 'name': 'Karnataka', 'st_code': '29', 'type': 'State'},
    'KL': {'state_id': 'KL', 'name': 'Kerala', 'st_code': '32', 'type': 'State'},
    'LA': {'state_id': 'LA', 'name': 'Ladakh', 'st_code': '38', 'type': 'UT'},
    'LD': {'state_id': 'LD', 'name': 'Lakshadweep', 'st_code': '31', 'type': 'UT'},
    'MP': {'state_id': 'MP', 'name': 'Madhya Pradesh', 'st_code': '23', 'type': 'State'},
    'MH': {'state_id': 'MH', 'name': 'Maharashtra', 'st_code': '27', 'type': 'State'},
    'MN': {'state_id': 'MN', 'name': 'Manipur', 'st_code': '14', 'type': 'State'},
    'ML': {'state_id': 'ML', 'name': 'Meghalaya', 'st_code': '17', 'type': 'State'},
    'MZ': {'state_id': 'MZ', 'name': 'Mizoram', 'st_code': '15', 'type': 'State'},
    'NL': {'state_id': 'NL', 'name': 'Nagaland', 'st_code': '13', 'type': 'State'},
    'OD': {'state_id': 'OD', 'name': 'Odisha', 'st_code': '21', 'type': 'State'},
    'PB': {'state_id': 'PB', 'name': 'Punjab', 'st_code': '03', 'type': 'State'},
    'PY': {'state_id': 'PY', 'name': 'Puducherry', 'st_code': '34', 'type': 'UT'},
    'RJ': {'state_id': 'RJ', 'name': 'Rajasthan', 'st_code': '08', 'type': 'State'},
    'SK': {'state_id': 'SK', 'name': 'Sikkim', 'st_code': '11', 'type': 'State'},
    'TN': {'state_id': 'TN', 'name': 'Tamil Nadu', 'st_code': '33', 'type': 'State'},
    'TS': {'state_id': 'TS', 'name': 'Telangana', 'st_code': '36', 'type': 'State'},
    'TR': {'state_id': 'TR', 'name': 'Tripura', 'st_code': '16', 'type': 'State'},
    'UP': {'state_id': 'UP', 'name': 'Uttar Pradesh', 'st_code': '09', 'type': 'State'},
    'UK': {'state_id': 'UK', 'name': 'Uttarakhand', 'st_code': '05', 'type': 'State'},
    'WB': {'state_id': 'WB', 'name': 'West Bengal', 'st_code': '19', 'type': 'State'},
}

# Historical and colloquial name aliases to canonical state code
STATE_ALIASES: Dict[str, str] = {
    'orissa': 'OD',
    'odisha': 'OD',
    'uttaranchal': 'UK',
    'uttarakhand': 'UK',
    'pondicherry': 'PY',
    'puducherry': 'PY',
    'delhi': 'DL',
    'nct of delhi': 'DL',
    'national capital territory of delhi': 'DL',
    'andaman and nicobar': 'AN',
    'andaman and nicobar islands': 'AN',
    'andaman & nicobar islands': 'AN',
    'andaman & nicobar': 'AN',
    'dadra and nagar haveli': 'DD',
    'daman and diu': 'DD',
    'dadra and nagar haveli and daman and diu': 'DD',
    'the dadra and nagar haveli and daman and diu': 'DD',
    'jammu & kashmir': 'JK',
    'jammu and kashmir': 'JK',
}


def normalize_state_name(value: str) -> str:
    """Normalize a state name by lowercasing, stripping punctuation, and removing leading articles."""
    text = re.sub(r'[^a-z0-9]+', ' ', str(value).casefold().replace('&', ' and ')).strip()
    text = re.sub(r'\s+', ' ', text)
    if text.startswith('the '):
        text = text[4:].strip()
    return text


# Precompute normalized state name to canonical state ID lookup
_NAME_TO_CODE: Dict[str, str] = {}
for code, meta in STATES_REGISTRY.items():
    _NAME_TO_CODE[normalize_state_name(meta['name'])] = code

for alias, code in STATE_ALIASES.items():
    _NAME_TO_CODE[normalize_state_name(alias)] = code


def resolve_state_id(identifier: str) -> str:
    """Resolve an input identifier (2-letter code, state name, or district ID) to a canonical 2-letter state ID.

    Raises LookupError if the state cannot be determined unambiguously.
    """
    if not identifier or not isinstance(identifier, str):
        raise LookupError("State identifier must be a non-empty string.")

    cleaned = identifier.strip()

    # 1. Direct uppercase 2-letter code match
    upper = cleaned.upper()
    if upper in STATES_REGISTRY:
        return upper

    # 2. Canonical district ID format (e.g. 'UP-Deoria', 'TN-Cuddalore')
    if '-' in cleaned:
        prefix = cleaned.split('-', 1)[0].upper()
        if prefix in STATES_REGISTRY:
            return prefix

    # 3. State name match (with normalization and alias resolution)
    norm = normalize_state_name(cleaned)
    if norm in _NAME_TO_CODE:
        return _NAME_TO_CODE[norm]

    raise LookupError(f"Unknown or ambiguous state identifier: '{identifier}'.")


def get_state_metadata(state_id: str) -> Dict[str, str]:
    """Return verified metadata dictionary for a state.

    Raises LookupError if state_id is invalid.
    """
    code = resolve_state_id(state_id)
    return dict(STATES_REGISTRY[code])


def list_states() -> List[Dict[str, str]]:
    """Return sorted list of all 36 verified States and Union Territories."""
    return [dict(meta) for code, meta in sorted(STATES_REGISTRY.items(), key=lambda x: x[1]['name'])]
