import glob
import json
import re

def main():
    chunk_by_id = {}
    chunks_by_doc = {}
    for fpath in glob.glob("data/chunks_*/**/*.jsonl", recursive=True):
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                cid = c["chunk_id"]
                doc = c["document_id"]
                chunk_by_id[cid] = c
                if doc not in chunks_by_doc:
                    chunks_by_doc[doc] = []
                chunks_by_doc[doc].append(c)

    print("Loaded %d chunks across %d documents." % (len(chunk_by_id), len(chunks_by_doc)))

    # Dictionary of targeted searches for Q41-Q104
    targets = {
        "Q41": ("NIST_SP_800-131", "tbl", r"Comment|legacy"),
        "Q42": ("NIST_SP_800-234", "tbl", r"Moderate Baseline|AC 2"),
        "Q43": ("NIST_SP_800-152", "tbl", r"AC 2|FederalCKMS shall support"),
        "Q44": ("NIST_SP_800-218", "tbl", r"PO1|PreparetheOrganization"),
        "Q45": ("NIST_SP_800-146", "tbl", r"Technical.*Operational.*Management"),
        "Q46": ("NIST_SP_800-190", "txt", r"image vulnerability|image scanner|registry"),
        "Q46_supp": ("NIST_SP_800-204", "txt", r"pipeline|CI/CD|software supply chain"),
        "Q47": ("NIST_SP_800-207", "txt", r"PDP|PEP|Policy Decision Point|Policy Enforcement"),
        "Q47_supp": ("NIST_SP_800-210", "txt", r"access control|cloud systems|authorization"),
        "Q48": ("NIST_SP_800-63", "txt", r"AAL3|hardware-based authenticator"),
        "Q48_supp": ("NIST_SP_800-116", "txt", r"facility access|PACS|PIV"),
        "Q49": ("NIST_SP_800-57", "txt", r"key management lifecycle|key state"),
        "Q49_supp": ("NIST_SP_800-130", "txt", r"CKMS|framework|components"),
        "Q50": ("NIST_SP_800-216", "txt", r"vulnerability disclosure|reporting|guidelines"),
        "Q50_supp": ("NIST_SP_800-218", "txt", r"RV|Respond to Vulnerabilities"),
        "Q51": ("NIST_SP_800-61", "txt", r"chain of custody|evidence|forensic"),
        "Q51_supp": ("NIST_SP_800-101", "txt", r"mobile device|acquisition|forensics"),
        "Q52": ("NIST_SP_800-53", "txt", r"CA-7|continuous monitoring"),
        "Q53": ("NIST_SP_800-161", "txt", r"contractual clause|supplier risk|assessment"),
        "Q54": ("NIST_SP_800-57", "txt", r"BYOK|Bring Your Own Key"),
        "Q55": ("NIST_SP_800-130", "txt", r"CKMS components|key management system"),
        "Q56": ("NIST_SP_800-133", "txt", r"Filippo Valsorda|key generation"),
        "Q57": ("NIST_SP_800-185", "txt", r"cSHAKE|KMAC|customization"),
        "Q58": ("NIST_SP_800-208", "txt", r"stateful hash|LMS|XMSS"),
        "Q59": ("NIST_SP_800-232", "txt", r"Ascon|lightweight|permutation"),
        "Q60": ("NIST_SP_800-73", "txt", r"CHUID|cardholder unique identifier"),
        "Q61": ("NIST_SP_800-76", "txt", r"minutiae|fingerprint|quality"),
        "Q62": ("NIST_SP_800-78", "txt", r"algorithms|key sizes|cryptographic specifications"),
        "Q63": ("NIST_SP_800-79", "txt", r"accreditation|PCI|card issuing"),
        "Q64": ("NIST_SP_800-157", "txt", r"derived credential|derived PIV"),
        "Q65": ("NIST_SP_800-217", "txt", r"federation|federated identity|trust model"),
        "Q66": ("NIST_SP_800-50", "txt", r"awareness|training|education continuum"),
        "Q67": ("NIST_SP_800-221", "txt", r"ICT risk|outcomes|measurement"),
        "Q68": ("NIST_SP_800-190", "txt", r"container architecture|threats"),
        "Q69": ("NIST_SP_800-228", "txt", r"API protection|cloud-native|gateway"),
        "Q70": ("NIST_SP_800-107", "txt", r"collision resistance|pre-image"),
        "Q71": ("NIST_SP_800-175", "txt", r"cryptographic standards|federal guidance"),
        "Q72": ("NIST_SP_800-178", "txt", r"XACML|NGAC|comparison"),
        "Q73": ("NIST_SP_800-205", "txt", r"attribute considerations|access control"),
        "Q74": ("NIST_SP_800-226", "txt", r"differential privacy|epsilon"),
        "Q75": ("NIST_SP_800-183", "txt", r"networks of things|sensor|aggregator"),
        "Q76": ("NIST_SP_800-215", "txt", r"software-defined perimeter|enterprise network"),
        "Q77": ("NIST_SP_800-231", "txt", r"Bugs Framework|fault model|weakness"),
        "Q78": ("NIST_SP_800-236", "txt", r"annual report|cryptographic research|priorities"),
        "Q79": ("NIST_SP_800-238", "txt", r"annual report|post-quantum|privacy-enhancing"),
        "Q80": ("NIST_SP_800-197", "txt", r"lightweight block cipher|comments"),
        "Q81": ("NIST_SP_800-51", "txt", r"CVE|vulnerability naming"),
        "Q82": ("NIST_SP_800-140", "txt", r"non-invasive|CMVP|test metrics"),
        "Q83": ("NIST_SP_800-223", "txt", r"HPC security|threat modeling"),
        "Q84": ("NIST_SP_800-89", "txt", r"digital signature|assurances"),
        "Q85": ("NIST_SP_800-38", "txt", r"GCM|authenticated encryption|AEAD"),
        "Q86": ("NIST_SP_800-56", "txt", r"pair-wise key establishment|discrete logarithm"),
        "Q87": ("NIST_SP_800-186", "txt", r"elliptic curve|domain parameters|Weierstrass"),
        "Q88": ("NIST_SP_800-132", "txt", r"PBKDF2|password-based key derivation|salt"),
        "Q89": ("NIST_SP_800-192", "txt", r"verification|test methods|access control policies"),
        "Q90": ("NIST_SP_800-224", "txt", r"HMAC|keyed-hash|message authentication"),
        "Q91": ("NIST_SP_800-153", "txt", r"WPA3|wireless LAN|rogue AP"),
        "Q92": ("NIST_SP_800-72", "txt", r"volatile memory|PDA forensics"),
        "Q93": ("NIST_SP_800-201", "txt", r"cloud forensic|reference architecture|multi-tenant"),
        "Q94": ("NIST_SP_800-234", "txt", r"HPC security overlay|controls"),
        "Q95": ("NIST_SP_800-114", "txt", r"telework|BYOD|VPN"),
        "Q96": ("NIST_SP_800-116", "txt", r"facility access|PIV dual-factor"),
        "Q97": ("NIST_SP_800-101", "txt", r"mobile device|forensic examination"),
        "Q98": ("NIST_SP_800-190", "txt", r"container escape|kernel"),
        "Q99": ("NIST_SP_800-228", "txt", r"BOLA|API authorization|endpoint"),
        "Q100": ("NIST_SP_800-210", "txt", r"ABAC|cloud systems|multi-tenant"),
        "Q101": ("NIST_SP_800-239", "txt", r"GPU memory|AI data center|sanitization"),
        "Q102": ("NIST_SP_800-204", "txt", r"DevSecOps|CI/CD|supply chain security"),
        "Q103": ("NIST_SP_800-216", "txt", r"vulnerability disclosure|intake|reporting"),
        "Q104": ("NIST_SP_800-221", "txt", r"ICT risk|incident triage|outcomes")
    }

    found = 0
    missing = []
    found_map = {}

    for qid, (doc, ctype_prefix, qregex) in targets.items():
        doc_chunks = chunks_by_doc.get(doc, [])
        regex = re.compile(qregex, re.IGNORECASE)
        m_list = []
        for c in doc_chunks:
            if ctype_prefix == "tbl" and c.get("content_type") != "table":
                continue
            if ctype_prefix == "txt" and c.get("content_type") != "text":
                continue
            text = f"{c.get('section_heading', '')} {c.get('section_path', '')} {c.get('text', '')}"
            if regex.search(text):
                m_list.append(c)
                if len(m_list) >= 3:
                    break
        if m_list:
            found += 1
            found_map[qid] = [m['chunk_id'] for m in m_list]
            c0 = m_list[0]
            txt = c0['text'][:90].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
            print("[%s] %s -> %s (p.%s, %s): %s..." % (qid, doc, c0['chunk_id'], c0.get('page_start'), c0.get('content_type'), txt))
        else:
            missing.append((qid, doc, qregex))
            print("[%s] %s -> MISSING for %s" % (qid, doc, qregex))

    print("\nSummary: %d / %d found, %d missing." % (found, len(targets), len(missing)))

if __name__ == '__main__':
    main()
