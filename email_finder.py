import re
import sys
import smtplib
import socket
import dns.resolver
import urllib.request
import json
import os

SENDER_EMAIL = "verify@mailcheck.com"

def get_mx_records(domain):
    """Retrieves MX records for a domain sorted by priority."""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        records = sorted([(ans.preference, str(ans.exchange).rstrip('.')) for ans in answers])
        return [rec[1] for rec in records]
    except Exception as e:
        print(f"[DNS Check] Error: No MX records found for '{domain}': {e}")
        return []

def clean_domain(domain):
    """Strips protocols and directories from a URL to return a clean domain."""
    domain = domain.strip().lower()
    domain = re.sub(r'^https?://(?:www\.)?', '', domain)
    domain = domain.split('/')[0]
    return domain

def generate_permutations(name, domain):
    """Generates standard corporate email permutations for a person's name."""
    name_clean = name.strip().lower()
    name_clean = re.sub(r'[^a-z\s]', '', name_clean)  # keep letters and spaces
    parts = name_clean.split()

    if not parts:
        return []

    if len(parts) == 1:
        first = parts[0]
        last = ""
    else:
        first = parts[0]
        last = parts[-1]

    domain = clean_domain(domain)

    perms = []
    def add_perm(email):
        if email not in perms:
            perms.append(email)

    if last:
        add_perm(f"{first}.{last}@{domain}")
        add_perm(f"{first}{last}@{domain}")
        add_perm(f"{first[0]}.{last}@{domain}")
        add_perm(f"{first[0]}{last}@{domain}")
        add_perm(f"{first}.{last[0]}@{domain}")
        add_perm(f"{first}{last[0]}@{domain}")
        add_perm(f"{first}_{last}@{domain}")
        add_perm(f"{last}@{domain}")  # added last name only (e.g. rafi@domain)
        
    add_perm(f"{first}@{domain}")
    return perms

def verify_smtp(email, mx_host):
    """Attempts SMTP handshake verification for a single email address."""
    try:
        server = smtplib.SMTP(timeout=5)
        server.connect(mx_host, 25)
        server.helo()
        server.mail(SENDER_EMAIL)
        code, message = server.rcpt(email)
        server.quit()
        
        if code in [250, 251, 252]:
            return "valid"
        elif code == 550:
            return "invalid"
        else:
            return "unverifiable"
    except Exception as e:
        return f"error: {e}"

def check_hunter_io(email, api_key):
    """Queries Hunter.io API to verify the email address using their database."""
    if not api_key:
        return None
    url = f"https://api.hunter.io/v2/email-verifier?email={email}&api_key={api_key}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as response:
            res_data = json.loads(response.read().decode())
            data_sec = res_data.get("data", {})
            result = data_sec.get("result") # 'deliverable', 'undeliverable', 'risky', 'unknown'
            if result == "deliverable":
                return "valid"
            elif result == "undeliverable":
                return "invalid"
            return "unverifiable"
    except Exception:
        return None

def run_finder(name, domain):
    domain = clean_domain(domain)
    print("\n" + "="*50)
    print(f" Target: {name} at {domain}")
    print("="*50)

    # Load API key
    hunter_key = os.getenv("HUNTER_API_KEY")
    if not hunter_key and os.path.exists(".env"):
        try:
            with open(".env", "r") as f:
                for line in f:
                    if line.strip().startswith("HUNTER_API_KEY="):
                        val = line.strip().split("=", 1)[1].strip()
                        hunter_key = val.strip("'\"")
        except Exception:
            pass

    # 1. Generate combinations
    perms = generate_permutations(name, domain)
    if not perms:
        print("[Error] Could not generate permutations. Check your input name.")
        return

    print(f"\n[1] Generated {len(perms)} email candidates to check:")
    for p in perms:
        print(f"  - {p}")

    # 2. Check MX Records
    print(f"\n[2] Looking up DNS MX records for '{domain}'...")
    mxs = get_mx_records(domain)
    if not mxs:
        print(f"[Error] Domain '{domain}' has no valid mail servers. All emails are likely invalid.")
        return
    
    mx_host = mxs[0]
    print(f"  Found mail server: {mx_host}")

    # 3. SMTP Verification Checks
    print("\n[3] Initiating passive SMTP handshake checks...")
    
    # Test catch-all status first using a random gibberish address
    test_catch_all_email = f"verify_catch_all_test_123456@{domain}"
    print(f"  Checking if domain is catch-all (testing random mailbox)...")
    catch_all_status = verify_smtp(test_catch_all_email, mx_host)
    
    if "error" in catch_all_status:
        print("\n" + "!"*50)
        print(f" [WARNING] SMTP Handshake Connection Error: {catch_all_status}")
        if hunter_key:
            print(" Falling back to Hunter.io database check...")
        else:
            print(" We cannot verify active status without direct mail server access.")
            print(" (Set 'HUNTER_API_KEY' in a '.env' file to run database verification).")
        print("!"*50)
        
        if not hunter_key:
            print("\nPlease try manually contacting using one of the generated combinations above.")
            return
        
        # Hunter.io verification loop
        valid_email = None
        for email in perms:
            print(f"  Checking database for {email} ... ", end="", flush=True)
            status = check_hunter_io(email, hunter_key)
            if status:
                print(status)
                if status == "valid":
                    valid_email = email
                    break
            else:
                print("skipped (API limit or error)")
        
        print("\n" + "="*50)
        if valid_email:
            print(f" SUCCESS: Found verified email in Hunter.io database!")
            print(f" ---> {valid_email} <---")
        else:
            print(" RESULT: No verified email found in Hunter.io database for these combinations.")
        print("="*50 + "\n")
        return

    if catch_all_status == "valid":
        print("\n" + "-"*50)
        print(f" [NOTICE] Domain '{domain}' is a CATCH-ALL domain.")
        print(" The mail server accepts all email addresses and forwards them.")
        if hunter_key:
            print(" Using Hunter.io API database fallback to find verified emails...")
        else:
            print(" We cannot verify the specific correct mailbox via SMTP.")
            print(" (Set 'HUNTER_API_KEY' in a '.env' file to run database verification).")
        print("-"*50)
        
        if not hunter_key:
            print("\nYou can use any of the standard permutations listed above.")
            return
        
        # Hunter.io verification loop
        valid_email = None
        for email in perms:
            print(f"  Checking database for {email} ... ", end="", flush=True)
            status = check_hunter_io(email, hunter_key)
            if status:
                print(status)
                if status == "valid":
                    valid_email = email
                    break
            else:
                print("skipped (API limit or error)")
        
        print("\n" + "="*50)
        if valid_email:
            print(f" SUCCESS: Found verified email in Hunter.io database!")
            print(f" ---> {valid_email} <---")
        else:
            print(" RESULT: No verified email found in Hunter.io database for these combinations.")
        print("="*50 + "\n")
        return

    print("  Domain is not catch-all. Starting individual verification...")
    valid_email = None
    
    for email in perms:
        print(f"  Testing {email} ... ", end="", flush=True)
        status = verify_smtp(email, mx_host)
        print(status)
        
        if status == "valid":
            valid_email = email
            break

    print("\n" + "="*50)
    if valid_email:
        print(f" SUCCESS: Found working email address!")
        print(f" ---> {valid_email} <---")
    else:
        print(" RESULT: No valid email address found (all combinations returned 550).")
    print("="*50 + "\n")

def main():
    # Check if arguments are supplied via command-line
    if len(sys.argv) >= 3:
        name = sys.argv[1]
        domain = sys.argv[2]
        run_finder(name, domain)
    else:
        # Interactive mode
        print("="*50)
        print("      Professional Email Finder & Verifier CLI     ")
        print("="*50)
        try:
            name = input("Enter person's full name (e.g. Rahul Bose): ").strip()
            if not name:
                print("Name cannot be empty.")
                return
            domain = input("Enter company domain name (e.g. gmail.com): ").strip()
            if not domain:
                print("Domain cannot be empty.")
                return
            
            run_finder(name, domain)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting finder.")

if __name__ == "__main__":
    main()
