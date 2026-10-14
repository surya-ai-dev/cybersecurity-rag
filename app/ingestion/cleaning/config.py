"""Configuration for conservative document text cleaning."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set


@dataclass
class CleaningConfig:
    """Settings controlling conservative text cleaning operations."""

    output_dir: Path = Path("data/cleaned_pilot")
    pilot_mode: bool = True

    # Transformations
    remove_running_headers: bool = True
    remove_running_footers: bool = True
    repair_line_end_hyphens: bool = True
    handle_replacement_chars: bool = True
    normalize_whitespace: bool = True
    tag_boilerplate: bool = True

    # Detection thresholds
    min_header_frequency: int = 4
    min_header_ratio: float = 0.15
    min_footer_frequency: int = 4

    # Whitelist of terms that must NEVER have hyphens removed
    protected_hyphen_terms: Set[str] = field(default_factory=lambda: {
        "aes-256", "aes-192", "aes-128", "aes-gcm", "aes-ccm", "aes-cbc",
        "sha-1", "sha-224", "sha-256", "sha-384", "sha-512", "sha-3",
        "hmac-sha-256", "rsa-2048", "rsa-4096", "ecdsa-p256", "ecdsa-p384",
        "zero-trust", "cross-site", "role-based", "attribute-based",
        "public-key", "private-key", "pair-wise", "high-performance",
        "supply-chain", "third-party", "real-time", "cloud-native",
        "machine-readable", "well-defined", "end-to-end", "fips-140-3",
        "sp-800-53", "sp-800-39", "sp-800-116", "sp-800-152", "sp-800-186"
    })
