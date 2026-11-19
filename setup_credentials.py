"""Save Tapo credentials in Windows Credential Manager via keyring."""
import getpass
import keyring

email = input("Tapo e-posta: ").strip()
password = getpass.getpass("Tapo sifresi (gizli): ")
if not email or not password:
    raise SystemExit("E-posta ve sifre gerekli")
keyring.set_password("TapoHotkeys", "username", email)
keyring.set_password("TapoHotkeys", "password", password)
print("Kimlik bilgileri Windows kasa sistemine kaydedildi.")
