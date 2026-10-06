import re
import time
import requests

from bs4 import BeautifulSoup
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://csrc.nist.gov"
SP800_URL = "https://csrc.nist.gov/publications/sp800"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "documents"

TARGET_DOCUMENTS = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ============================================================
# CATEGORY DEFINITIONS
# ============================================================

CATEGORIES = {

    "incident_response": [
        "incident response",
        "incident",
        "digital forensics",
        "forensic",
        "cyber incident"
    ],

    "identity_access": [
        "identity",
        "access control",
        "authentication",
        "authorization",
        "credential",
        "password",
        "privileged access",
        "attribute based access",
        "identity management"
    ],

    "vulnerability_management": [
        "vulnerability",
        "vulnerabilities",
        "weakness",
        "patch",
        "software assurance",
        "security testing",
        "penetration testing"
    ],

    "cloud_application_security": [
        "cloud",
        "cloud-native",
        "cloud native",
        "application security",
        "api security",
        "api protection",
        "container",
        "microservices",
        "service mesh",
        "software security"
    ],

    "risk_management": [
        "risk",
        "risk management",
        "cybersecurity framework",
        "csf",
        "security assessment",
        "security controls",
        "privacy"
    ],

    "supply_chain_security": [
        "supply chain",
        "cybersecurity supply chain",
        "third party",
        "supplier",
        "software supply chain"
    ],

    "zero_trust_network_security": [
        "zero trust",
        "network security",
        "network",
        "firewall",
        "remote access",
        "telework",
        "network architecture"
    ],

    "threats_malware": [
        "malware",
        "threat",
        "threats",
        "attack",
        "adversarial",
        "ransomware",
        "phishing",
        "botnet"
    ],

    "cryptography_security": [
        "cryptography",
        "cryptographic",
        "encryption",
        "key management",
        "digital signature",
        "hash",
        "cryptographic algorithm"
    ],

    "ai_security": [
        "artificial intelligence",
        "machine learning",
        "generative ai",
        "ai security",
        "adversarial machine learning",
        "machine learning security"
    ]
}


# ============================================================
# CREATE CATEGORY FOLDERS
# ============================================================

def create_category_folders():

    DOCUMENTS_DIR.mkdir(exist_ok=True)

    for category in CATEGORIES:

        category_path = DOCUMENTS_DIR / category

        category_path.mkdir(
            parents=True,
            exist_ok=True
        )

    print("Category folders ready.\n")


# ============================================================
# CLASSIFY DOCUMENT
# ============================================================

def classify_document(title):

    title_lower = title.lower()

    scores = {}

    for category, keywords in CATEGORIES.items():

        score = 0

        for keyword in keywords:

            if keyword in title_lower:

                # Exact phrase gets one point
                score += 1

        scores[category] = score

    # Find category with highest score
    best_category = max(
        scores,
        key=scores.get
    )

    best_score = scores[best_category]

    # No matching cybersecurity category
    if best_score == 0:

        return "general_cybersecurity"

    return best_category


# ============================================================
# GET NIST PUBLICATIONS
# ============================================================

def get_publication_links():

    print("Fetching NIST SP 800 publications...\n")

    response = requests.get(
        SP800_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    publications = []

    for link in soup.find_all("a", href=True):

        title = link.get_text(
            " ",
            strip=True
        )

        href = link["href"]

        if "/pubs/sp/800/" not in href:

            continue

        match = re.search(
            r"/800/(\d+)(?:/([^/]+))?",
            href
        )

        if not match:

            continue

        number = match.group(1)

        url = (
            href
            if href.startswith("http")
            else BASE_URL + href
        )

        publications.append({

            "number": number,

            "title": title,

            "url": url

        })

    # Remove duplicates
    unique = {}

    for publication in publications:

        unique[publication["url"]] = publication

    return list(unique.values())


# ============================================================
# FILTER CYBERSECURITY DOCUMENTS
# ============================================================

def is_relevant(title):

    title_lower = title.lower()

    # Ignore reports that aren't useful for our knowledge base
    excluded_keywords = [

        "annual report",

        "fiscal year",

    ]

    for keyword in excluded_keywords:

        if keyword in title_lower:

            return False

    # Combine all cybersecurity keywords
    all_keywords = []

    for keywords in CATEGORIES.values():

        all_keywords.extend(keywords)

    for keyword in all_keywords:

        if keyword in title_lower:

            return True

    return False


# ============================================================
# GET PDF URL
# ============================================================

def get_pdf_url(publication_url):

    response = requests.get(
        publication_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        if ".pdf" not in href.lower():

            continue

        if href.startswith("http"):

            return href

        return BASE_URL + href

    return None


# ============================================================
# DOWNLOAD PDF
# ============================================================

def download_pdf(pdf_url, file_path):

    response = requests.get(
        pdf_url,
        headers=HEADERS,
        timeout=120
    )

    response.raise_for_status()

    with open(
        file_path,
        "wb"
    ) as file:

        file.write(
            response.content
        )


# ============================================================
# FIND EXISTING PDF
# ============================================================

def find_existing_pdf(number):

    filename = f"NIST_SP_800-{number}.pdf"

    # Search all category folders
    matches = list(
        DOCUMENTS_DIR.rglob(filename)
    )

    if matches:

        return matches[0]

    return None


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print("NIST CYBERSECURITY DOCUMENT COLLECTOR")

    print("=" * 70)

    print()

    # --------------------------------------------------------
    # Create folders
    # --------------------------------------------------------

    create_category_folders()

    # --------------------------------------------------------
    # Get publications
    # --------------------------------------------------------

    publications = get_publication_links()

    print(
        f"Found {len(publications)} "
        f"total NIST SP 800 publications.\n"
    )

    # --------------------------------------------------------
    # Filter relevant documents
    # --------------------------------------------------------

    relevant = []

    for publication in publications:

        if is_relevant(
            publication["title"]
        ):

            relevant.append(
                publication
            )

    print(
        f"Found {len(relevant)} "
        f"relevant cybersecurity publications.\n"
    )

    # --------------------------------------------------------
    # Select target documents
    # --------------------------------------------------------

    selected = relevant[
        :TARGET_DOCUMENTS
    ]

    print(
        f"Target dataset: "
        f"{len(selected)} PDFs\n"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    downloaded = 0

    skipped = 0

    failed = 0

    category_counts = {}

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    for index, publication in enumerate(
        selected,
        start=1
    ):

        number = publication["number"]

        title = publication["title"]

        print()

        print(
            f"[{index}/{len(selected)}] "
            f"SP 800-{number}"
        )

        print(
            f"Title: {title}"
        )

        # ----------------------------------------------------
        # Classify
        # ----------------------------------------------------

        category = classify_document(
            title
        )

        print(
            f"Category: {category}"
        )

        # ----------------------------------------------------
        # Create category folder
        # ----------------------------------------------------

        category_dir = (
            DOCUMENTS_DIR /
            category
        )

        category_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ----------------------------------------------------
        # Filename
        # ----------------------------------------------------

        filename = (
            f"NIST_SP_800-{number}.pdf"
        )

        file_path = (
            category_dir /
            filename
        )

        # ----------------------------------------------------
        # Check if already exists
        # ----------------------------------------------------

        existing = find_existing_pdf(
            number
        )

        if existing:

            print(
                f"⏭️ Already exists:"
            )

            print(
                f"   {existing}"
            )

            skipped += 1

            category_counts[category] = (
                category_counts.get(
                    category,
                    0
                ) + 1
            )

            continue

        # ----------------------------------------------------
        # Get PDF URL
        # ----------------------------------------------------

        try:

            pdf_url = get_pdf_url(
                publication["url"]
            )

            if not pdf_url:

                print(
                    "❌ PDF URL not found"
                )

                failed += 1

                continue

            print(
                "Downloading..."
            )

            # ------------------------------------------------
            # Download
            # ------------------------------------------------

            download_pdf(
                pdf_url,
                file_path
            )

            print(
                f"✅ Saved:"
            )

            print(
                f"   {file_path}"
            )

            downloaded += 1

            category_counts[category] = (
                category_counts.get(
                    category,
                    0
                ) + 1
            )

            # ------------------------------------------------
            # Wait
            # ------------------------------------------------

            time.sleep(1)

        except Exception as error:

            print(
                f"❌ Error: {error}"
            )

            failed += 1

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n")

    print("=" * 70)

    print("DATASET COLLECTION COMPLETE")

    print("=" * 70)

    print()

    print(
        f"New PDFs downloaded : {downloaded}"
    )

    print(
        f"Existing PDFs       : {skipped}"
    )

    print(
        f"Failed downloads    : {failed}"
    )

    print()

    print("DOCUMENTS BY CATEGORY")

    print("-" * 40)

    for category, count in sorted(
        category_counts.items()
    ):

        print(
            f"{category:35} {count}"
        )

    print()

    print(
        f"Documents folder:"
    )

    print(
        DOCUMENTS_DIR.resolve()
    )

    print()

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()